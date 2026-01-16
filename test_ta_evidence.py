import json
from storage.models_v2 import ClinicalTrialSignalV2, MeshTermV2, InterventionV2
from classifiers.therapeutic_area import detect_therapeutic_area_evidence

SNAPSHOT_PATH = "storage/snapshots/clinical_trials_v2/last_update/2026-01-15T14-35-50.json"

# Load snapshot
with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
    snap = json.load(f)

# Find ONE trial with immune ancestry
raw = None
for t in snap["trials"]:
    anc = t.get("condition_mesh_ancestors") or []
    if any(
        isinstance(m, dict) and m.get("term") == "Immune System Diseases"
        for m in anc
    ):
        raw = t
        break

if raw is None:
    raise RuntimeError("No immune trial found in snapshot")

# Helper to rebuild MeshTermV2 list
def mesh_list(key):
    return [
        MeshTermV2(id=m.get("id"), term=m.get("term"))
        for m in (raw.get(key) or [])
    ]

# Reconstruct a single trial object (same as reclassifier)
trial = ClinicalTrialSignalV2(
    nct_id=raw.get("nct_id"),
    title=raw.get("title"),
    study_type=raw.get("study_type"),
    phase=raw.get("phase"),
    sponsor_class=raw.get("sponsor_class"),
    conditions=raw.get("conditions") or [],
    first_posted_date=raw.get("first_posted_date"),
    last_update_posted_date=raw.get("last_update_posted_date"),
    interventions=[
        InterventionV2(name=iv.get("name"), type=iv.get("type"))
        for iv in (raw.get("interventions") or [])
    ],
    interventions_all=[
        InterventionV2(name=iv.get("name"), type=iv.get("type"))
        for iv in (raw.get("interventions") or [])
    ],
    interventions_text=raw.get("interventions_text") or [],
    arm_group_map=raw.get("arm_group_map") or {},
    intervention_meshes=mesh_list("intervention_meshes"),
    intervention_mesh_ancestors=mesh_list("intervention_mesh_ancestors"),
    condition_meshes=mesh_list("condition_meshes"),
    condition_mesh_ancestors=mesh_list("condition_mesh_ancestors"),
    therapeutic_area=raw.get("therapeutic_area"),
    is_drug_trial=raw.get("is_drug_trial"),
    modality=raw.get("modality"),
    info_flags=raw.get("info_flags") or [],
)

# Run evidence detection
evidence = detect_therapeutic_area_evidence(trial)

print("NCT:", trial.nct_id)
print("Conditions:", trial.conditions)
print("Evidence:", evidence)
