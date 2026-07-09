"""Subprocess job runner: single pipelines, parameterized jobs, and chains.

Launches catalog pipelines as child processes, captures combined stdout+stderr
to a per-run log file, tracks status in a JobRegistry, and supports cancel. A
chain runs its steps sequentially in one run (one log), stopping on the first
failure. Windows-first with a POSIX fallback for the WSL dev box.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from core.paths import app_root, data_root, logs_dir, ensure_dir
from app.jobs import catalog
from app.jobs.registry import JobRegistry

_IS_WIN = sys.platform == "win32"
_CANCEL_GRACE_S = 3.0


class JobRunner:
    def __init__(self) -> None:
        self.registry = JobRegistry()
        # run_id -> {"proc": Popen|None, "fh": handle, "cancel": bool}
        self._procs: dict[str, dict] = {}
        self._lock = threading.Lock()

    # -- environment / flags --------------------------------------------------
    def _child_env(self) -> dict:
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        # UTF-8 mode: forces utf-8 stdio in the child AND in multiprocessing
        # workers it spawns (they inherit this env), so pipeline output with
        # unicode (arrows, box chars) never hits a cp1252 encode error.
        env["PYTHONUTF8"] = "1"
        root = str(app_root())
        prior = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = root + (os.pathsep + prior if prior else "")
        return env

    def _run_cwd(self) -> Path:
        """Working directory for pipeline children.

        Pipelines that use *relative* data paths (e.g. ``Path("storage/...")``)
        resolve them against this CWD, so it MUST be the user's data folder
        (data_root) -- that is where the rest of the app reads/writes via
        core.paths. In a frozen build data_root != app_root (the read-only
        bundle); using app_root() here is what made pulls/enrich/reclassify
        mis-locate their files inside ``_internal``. Bundled assets (viz, models,
        policy, MeSH) load via absolute core.paths and are unaffected by CWD.
        Falls back to app_root() if data_root does not exist yet (a fresh
        install before the folder is initialised), since Popen needs a real cwd.
        """
        d = data_root()
        return d if d.is_dir() else app_root()

    def _popen(self, argv: list[str], fh) -> subprocess.Popen:
        creationflags = 0
        start_new_session = False
        if _IS_WIN:
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            start_new_session = True
        return subprocess.Popen(
            argv, cwd=str(self._run_cwd()), env=self._child_env(),
            stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=creationflags, start_new_session=start_new_session,
        )

    # -- start ----------------------------------------------------------------
    def start(self, job_id: str, params: dict | None = None) -> dict:
        entry = catalog.get_entry(job_id)
        if entry is None:
            raise ValueError(f"unknown job_id: {job_id}")
        if not entry.get("ready", False):
            raise ValueError(f"job not ready to run: {job_id}")

        is_chain = catalog.is_chain(job_id)
        argv_display = (["<chain>"] + list(entry.get("steps", []))
                        if is_chain else catalog.build_argv(job_id, params))
        run = self.registry.create(
            job_id=job_id, label=entry["label"],
            argv=argv_display, produces=entry.get("produces"),
        )
        run_id = run["run_id"]

        ensure_dir(logs_dir())
        log_path = logs_dir() / f"{run_id}.log"
        self.registry.update(run_id, log_file=str(log_path))

        fh = open(log_path, "wb")
        with self._lock:
            self._procs[run_id] = {"proc": None, "fh": fh, "cancel": False}
        self.registry.mark_started(run_id, pid=0)

        if is_chain:
            target = self._run_chain
            args = (run_id, entry, fh)
        else:
            target = self._run_single
            args = (run_id, job_id, params, fh)

        threading.Thread(target=target, args=args,
                         name=f"alexis-job-{run_id[:8]}", daemon=True).start()
        return self.registry.get(run_id)

    def _log(self, fh, text: str) -> None:
        try:
            fh.write(text.encode("utf-8"))
            fh.flush()
        except Exception:  # noqa: BLE001
            pass

    # -- single job -----------------------------------------------------------
    def _run_single(self, run_id: str, job_id: str, params: dict | None, fh) -> None:
        try:
            argv = catalog.build_argv(job_id, params)
            self._log(fh, f"[runner] $ {' '.join(argv)}\n")
            proc = self._popen(argv, fh)
            with self._lock:
                self._procs[run_id]["proc"] = proc
            self.registry.update(run_id, pid=proc.pid)
            rc = proc.wait()
        except Exception as exc:  # noqa: BLE001
            self._log(fh, f"[runner] failed to start: {exc}\n")
            rc = -1
        finally:
            self._close(fh)
        self.registry.mark_finished(run_id, returncode=rc)

    # -- chain ----------------------------------------------------------------
    def _run_chain(self, run_id: str, entry: dict, fh) -> None:
        steps = entry.get("steps", [])
        overall_rc = 0
        try:
            for i, step_id in enumerate(steps, 1):
                if self._is_cancelled(run_id):
                    self._log(fh, "[runner] chain cancelled before next step\n")
                    self.registry.mark_cancelled(run_id)
                    return
                step = catalog.get_entry(step_id)
                label = step["label"] if step else step_id
                self._log(fh, f"\n[chain] step {i}/{len(steps)}: {label}\n")
                argv = catalog.build_argv(step_id)
                self._log(fh, f"[runner] $ {' '.join(argv)}\n")
                proc = self._popen(argv, fh)
                with self._lock:
                    self._procs[run_id]["proc"] = proc
                self.registry.update(run_id, pid=proc.pid)
                rc = proc.wait()
                if self._is_cancelled(run_id):
                    self.registry.mark_cancelled(run_id)
                    return
                if rc != 0:
                    self._log(fh, f"[runner] step failed (rc={rc}); stopping chain.\n")
                    overall_rc = rc
                    break
            else:
                self._log(fh, "\n[chain] all steps completed.\n")
        except Exception as exc:  # noqa: BLE001
            self._log(fh, f"[runner] chain error: {exc}\n")
            overall_rc = 1
        finally:
            self._close(fh)
        if not JobRegistry.is_terminal(self.registry.get(run_id)):
            self.registry.mark_finished(run_id, returncode=overall_rc)

    # -- helpers --------------------------------------------------------------
    def _close(self, fh) -> None:
        try:
            fh.flush()
            fh.close()
        except Exception:  # noqa: BLE001
            pass

    def _is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            h = self._procs.get(run_id)
            return bool(h and h.get("cancel"))

    # -- cancel ---------------------------------------------------------------
    def cancel(self, run_id: str) -> dict:
        run = self.registry.get(run_id)
        if run is None:
            raise KeyError(run_id)
        if JobRegistry.is_terminal(run):
            raise ValueError("run already finished")

        with self._lock:
            h = self._procs.get(run_id)
            if h is not None:
                h["cancel"] = True
            proc = h["proc"] if h else None

        self.registry.mark_cancelled(run_id)

        if proc is not None and proc.poll() is None:
            try:
                if _IS_WIN:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            if not self._wait(proc, _CANCEL_GRACE_S):
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass
                if not self._wait(proc, _CANCEL_GRACE_S):
                    try:
                        proc.kill()
                    except Exception:  # noqa: BLE001
                        pass
        return self.registry.get(run_id)

    @staticmethod
    def _wait(proc: subprocess.Popen, timeout: float) -> bool:
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    # -- introspection --------------------------------------------------------
    def get(self, run_id: str) -> dict | None:
        return self.registry.get(run_id)

    def list_runs(self) -> list[dict]:
        return self.registry.list_runs()


RUNNER = JobRunner()
