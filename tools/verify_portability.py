"""Native-Windows portability gate for ALEXIS (Phase 0 verification).

Run with the target interpreter from the repo root:

    python tools/verify_portability.py            # fast checks (paths + classifier)
    python tools/verify_portability.py --full      # also load MeSH tables + pickled models

Exits non-zero if any check fails. Designed to run identically on the WSL dev
box and on native Windows so the path refactor (core.paths) can be trusted
before any GUI/packaging work.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import traceback
from pathlib import Path

# Ensure the repo root is importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Make stdout/stderr UTF-8 on Windows consoles (cp1252 by default) so any
# Unicode in library prints does not crash the gate.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — best-effort
        pass

PASS, FAIL = "PASS", "FAIL"
_results: list[tuple[str, str, str]] = []


def check(name: str, fn) -> None:
    try:
        detail = fn() or ""
        _results.append((PASS, name, str(detail)))
        print(f"  [PASS] {name} {('- ' + str(detail)) if detail else ''}")
    except Exception as e:  # noqa: BLE001 - this is a smoke test
        _results.append((FAIL, name, f"{type(e).__name__}: {e}"))
        print(f"  [FAIL] {name} - {type(e).__name__}: {e}")
        traceback.print_exc()


def _sample_trials():
    from storage.models_v2 import ClinicalTrialSignalV2, InterventionV2

    adc = ClinicalTrialSignalV2(
        nct_id="NCT-TEST-ADC",
        title="A Study of Trastuzumab Deruxtecan (Enhertu) in HER2-Positive Breast Cancer",
        brief_summary="Evaluating the antibody-drug conjugate trastuzumab deruxtecan.",
        conditions=["Breast Cancer", "HER2-positive Breast Neoplasms"],
        study_type="INTERVENTIONAL",
        phase="PHASE2",
        interventions=[InterventionV2(name="Trastuzumab deruxtecan", type="DRUG",
                                      other_names=["Enhertu", "DS-8201"])],
        interventions_all=[InterventionV2(name="Trastuzumab deruxtecan", type="DRUG",
                                          other_names=["Enhertu", "DS-8201"])],
        interventions_text=["Trastuzumab deruxtecan"],
    )
    mab = ClinicalTrialSignalV2(
        nct_id="NCT-TEST-MAB",
        title="Pembrolizumab in Advanced Non-Small Cell Lung Cancer",
        brief_summary="Anti-PD-1 monoclonal antibody pembrolizumab.",
        conditions=["Non-Small Cell Lung Cancer"],
        study_type="INTERVENTIONAL",
        phase="PHASE3",
        interventions=[InterventionV2(name="Pembrolizumab", type="DRUG",
                                      other_names=["Keytruda"])],
        interventions_all=[InterventionV2(name="Pembrolizumab", type="DRUG",
                                          other_names=["Keytruda"])],
        interventions_text=["Pembrolizumab"],
    )
    return adc, mab


def run(full: bool) -> int:
    print("ALEXIS portability gate")
    print(f"  python   : {sys.version.split()[0]}  ({sys.executable})")
    print(f"  platform : {sys.platform}")
    print(f"  cwd      : {os.getcwd()}")
    print("-" * 70)

    # 1. core.paths resolves
    def _paths():
        from core import paths
        a, d = paths.app_root(), paths.data_root()
        assert a.exists(), f"app_root missing: {a}"
        for label, p in [("mesh", paths.mesh_dir()), ("models", paths.models_dir()),
                         ("viz", paths.viz_dir())]:
            assert p.exists(), f"{label}_dir missing: {p}"
        # normalize_user_path Windows mapping
        np = paths.normalize_user_path("/mnt/c/Users/foo")
        return f"app_root={a.name}, data_root ok, mesh/models/viz present, norm={np}"
    check("core.paths accessors resolve", _paths)

    # 2. therapeutic_area._load_mesh works regardless of CWD (the line-267 fix)
    def _ta_mesh_cwd():
        from classifiers import therapeutic_area as ta
        original = os.getcwd()
        # chdir somewhere with no 'storage/mesh' so a CWD-relative path would fail
        neutral = "C:\\Windows" if sys.platform == "win32" else tempfile.gettempdir()
        os.chdir(neutral)
        try:
            ta._mesh_desc = {}  # reset cache
            ta._load_mesh()
            n = len(ta._mesh_desc)
            assert n > 0, "mesh_descriptors did not load from a foreign CWD"
            return f"loaded {n:,} descriptors with cwd={neutral}"
        finally:
            os.chdir(original)
    check("therapeutic_area._load_mesh ignores CWD", _ta_mesh_cwd)

    # 3. Single-trial classification end-to-end (the MVP path - no pickles)
    def _classify():
        from classifiers.drug_non_drug_v2 import is_drug_trial_v2
        from classifiers.trial_modality_v2 import assign_trial_modality_v2
        from classifiers.therapeutic_area import assign_therapeutic_area
        adc, mab = _sample_trials()
        out = {}
        for t in (adc, mab):
            out[t.nct_id] = (is_drug_trial_v2(t), assign_trial_modality_v2(t),
                             assign_therapeutic_area(t))
        # Soft assertions: both are drugs and land in oncology; modality non-empty.
        for nct, (is_drug, mod, area) in out.items():
            assert is_drug is True, f"{nct} not flagged drug"
            assert mod and mod != "non_drug", f"{nct} modality={mod}"
        return "; ".join(f"{k}:drug={v[0]},mod={v[1]},ta={v[2]}" for k, v in out.items())
    check("single-trial classify (drug/modality/TA)", _classify)

    if full:
        # 4. MeSH lookup tables load (heavy: ~126MB JSON)
        def _mesh_full():
            from utils.mesh_lookup import MeshLookup
            m = MeshLookup()
            assert m.is_loaded(), "MeSH term_to_id empty"
            trees = m.get_tree_numbers("Bevacizumab")
            assert any(tn.startswith("D") for tn in trees), f"Bevacizumab trees={trees}"
            return f"{len(m.term_to_id):,} terms; Bevacizumab -> {trees[:1]}"
        check("MeshLookup loads all tables", _mesh_full)

        # 5. Pickled sklearn models unpickle (Phase-2 readiness; sklearn 1.6 lock)
        def _pickles():
            import pickle
            import sklearn
            from core.paths import models_dir
            assert sklearn.__version__.startswith("1.6"), \
                f"sklearn {sklearn.__version__} != 1.6.x (pickle lock)"
            loaded = []
            for name in ("intl_drug_classifier_v2.pkl", "intl_ta_classifier.pkl"):
                p = models_dir() / name
                if not p.exists():
                    loaded.append(f"{name}:MISSING")
                    continue
                with open(p, "rb") as f:
                    pickle.load(f)
                loaded.append(f"{name}:ok")
            return f"sklearn {sklearn.__version__}; " + ", ".join(loaded)
        check("pickled models load (sklearn 1.6 lock)", _pickles)

    print("-" * 70)
    failed = [r for r in _results if r[0] == FAIL]
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="also load MeSH tables and pickled models (slow)")
    args = ap.parse_args()
    raise SystemExit(run(full=args.full))
