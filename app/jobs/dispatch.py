"""In-process pipeline dispatch for frozen builds.

In a PyInstaller exe ``python -m pipelines.x`` is unavailable, so the job
runner re-launches the exe as ``ALEXIS.exe --run-pipeline <job_id>`` and
app.__main__ calls :func:`run_pipeline`, which runs the catalog target via
runpy exactly as ``-m module <argv>`` / ``script <argv>`` would.
"""

from __future__ import annotations

import runpy
import sys

from core.paths import app_root
from app.jobs import catalog


def _exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1  # a string/other -> treat as failure


def _script_to_module(script: str) -> str:
    """'pipelines/diff_chictr_snapshots.py' -> 'pipelines.diff_chictr_snapshots'."""
    rel = script.replace("\\", "/").strip("/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    return rel.replace("/", ".")


def _run_module(mod: str, tail: list[str]) -> None:
    sys.argv = [mod, *tail]
    runpy.run_module(mod, run_name="__main__", alter_sys=True)


def _run_script_file(path, tail: list[str]) -> None:
    """Exec a .py bundled as a *data file* (e.g. tools/verify_portability.py),
    which has no importable module name.

    Deliberately avoids ``runpy.run_path``: for a path inside the PyInstaller
    bundle, run_path resolves it through the frozen path hook and then looks for
    a ``__main__`` submodule there, failing with
    ``ImportError: can't find '__main__' module in '<path>'``.
    """
    src = path.read_text(encoding="utf-8")
    code = compile(src, str(path), "exec")
    sys.argv = [str(path), *tail]
    exec(code, {"__name__": "__main__", "__file__": str(path)})


def run_pipeline(job_id: str, extra_args: list[str] | None = None) -> int:
    """Run a catalog pipeline in this process. Returns its exit code.

    ``extra_args`` are the parameter flags the parent appended after
    ``--run-pipeline <id>`` (e.g. ``--aact-dir ...``); they are forwarded to the
    pipeline's argv so a frozen build honours GUI form values.
    """
    # In a windowed frozen build sys.stdout/err are None; reattach the handles
    # the parent runner gave us (fd 1/2 -> the per-run log file).
    try:
        from app.main import ensure_streams
        ensure_streams()
    except Exception:  # noqa: BLE001
        pass

    entry = catalog.get_entry(job_id)
    if entry is None:
        print(f"[err] unknown pipeline: {job_id}")
        return 2

    tail = list(entry.get("argv", [])) + list(extra_args or [])
    try:
        if entry.get("module"):
            _run_module(entry["module"], tail)
            return 0
        if entry.get("script"):
            # Two ways a `script:` target ships in the frozen bundle:
            #  * pipelines/*.py are collected as importable modules into the PYZ
            #    archive -- there is NO loose .py on disk -- so run them by module
            #    name (runpy.run_module), exactly like `module:` entries.
            #  * tools/verify_portability.py is bundled as a real data FILE, with
            #    no importable module name -- exec that file directly.
            # The reliable discriminator is whether the loose file exists on disk.
            # (We avoid runpy.run_path on bundle-internal paths: PyInstaller's
            # frozen path hook makes it hunt for a non-existent `__main__`
            # submodule -> "ImportError: can't find '__main__' module".)
            path = app_root() / entry["script"]
            if path.exists():
                _run_script_file(path, tail)
            else:
                _run_module(_script_to_module(entry["script"]), tail)
            return 0
    except SystemExit as exc:
        return _exit_code(exc)
    except Exception as exc:  # noqa: BLE001 -- surface to the job log
        print(f"[err] pipeline {job_id} crashed: {type(exc).__name__}: {exc}")
        return 1

    print(f"[err] pipeline {job_id} has no module/script target")
    return 2
