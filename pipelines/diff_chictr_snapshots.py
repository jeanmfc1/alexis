"""
pipelines/diff_chictr_snapshots.py -- Diff two ChiCTR snapshots.

Compares a prior snapshot to a current snapshot and produces:
  - an enriched snapshot (current trials tagged with update_type + update_categories)
  - a changelog summary JSON

Usage (direct):
    PYTHONPATH=. python pipelines/diff_chictr_snapshots.py --prior PRIOR --current CURR

Usually invoked via pipelines/run_diff_chictr.py (interactive launcher).
"""

from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

W = 72

FIELD_TO_CATEGORY = {
    "title":                   "title_change",
    "phase":                   "phase_change",
    "study_type":              "study_type_change",
    "sponsor_class":           "sponsor_change",
    "sponsor_name":            "sponsor_change",
    "conditions":              "condition_change",
    "interventions_text":      "intervention_change",
    "is_drug_trial":           "drug_status_change",
    "modality":                "modality_change",
    "therapeutic_area":        "ta_change",
    "study_intent":            "intent_change",
    "study_category":          "intent_change",
    "start_date":              "date_change",
    "completion_date":         "date_change",
    "primary_completion_date": "date_change",
    "first_posted_date":       "date_change",
}


def _norm(v):
    if isinstance(v, list):
        return tuple(sorted(str(x) for x in v if x is not None))
    if isinstance(v, str):
        return v.strip()
    return v


def diff_trial(prior, current):
    changes = []
    for field, category in FIELD_TO_CATEGORY.items():
        p = _norm(prior.get(field))
        c = _norm(current.get(field))
        if p != c:
            changes.append({
                "category": category,
                "field":    field,
                "prior":    prior.get(field),
                "current":  current.get(field),
            })
    return changes


def compute_diff(prior_snap, current_snap):
    prior_map   = {t["nct_id"]: t for t in prior_snap["trials"]}
    current_map = {t["nct_id"]: t for t in current_snap["trials"]}

    prior_ids   = set(prior_map)
    current_ids = set(current_map)
    new_ids     = current_ids - prior_ids
    removed_ids = prior_ids - current_ids

    enriched = []
    update_count = Counter()
    category_count = Counter()
    category_combos = Counter()
    per_trial_change_count = Counter()

    for nct in current_ids:
        row = dict(current_map[nct])
        if nct in new_ids:
            row["update_type"] = "new"
            row["update_categories"] = []
            update_count["new"] += 1
        else:
            changes = diff_trial(prior_map[nct], current_map[nct])
            if changes:
                row["update_type"] = "existing"
                row["update_categories"] = changes
                update_count["existing"] += 1
                cats = {c["category"] for c in changes}
                for cat in cats:
                    category_count[cat] += 1
                category_combos[tuple(sorted(cats))] += 1
                per_trial_change_count[len(changes)] += 1
            else:
                row["update_type"] = "unchanged"
                row["update_categories"] = []
                update_count["unchanged"] += 1
        enriched.append(row)

    changelog = {
        "prior_snapshot":    prior_snap.get("metadata", {}),
        "current_snapshot":  current_snap.get("metadata", {}),
        "generated_at":      datetime.now().isoformat(),
        "counts": {
            "prior_trials":       len(prior_ids),
            "current_trials":     len(current_ids),
            "new":                len(new_ids),
            "removed":            len(removed_ids),
            "existing_changed":   update_count["existing"],
            "existing_unchanged": update_count["unchanged"],
        },
        "removed_nct_ids":   sorted(removed_ids)[:500],
        "category_counts":   dict(category_count),
        "category_combos":   {" + ".join(combo): n for combo, n in category_combos.most_common()},
        "per_trial_change_count": dict(per_trial_change_count),
    }
    return enriched, changelog


def _hr(ch="=", w=W): print(ch * w)

def _section(title, ch="="):
    print(); _hr(ch); print("  " + title); _hr(ch)


def print_report(prior_path, current_path, prior_snap, current_snap, enriched, changelog):
    c = changelog["counts"]
    pm = prior_snap.get("metadata", {})
    cm = current_snap.get("metadata", {})

    _section("SNAPSHOT OVERVIEW")
    print(f"  Prior:   {prior_path.name}")
    print(f"    as_of:        {pm.get('as_of')}")
    print(f"    generated_at: {pm.get('generated_at')}")
    print(f"    trials:       {c['prior_trials']:,}")
    if pm.get("drug_trials") is not None:
        print(f"    drug_trials:  {pm.get('drug_trials'):,}")
    print(f"  Current: {current_path.name}")
    print(f"    as_of:        {cm.get('as_of')}")
    print(f"    generated_at: {cm.get('generated_at')}")
    print(f"    trials:       {c['current_trials']:,}")
    if cm.get("drug_trials") is not None:
        print(f"    drug_trials:  {cm.get('drug_trials'):,}")

    _section("TOP-LEVEL DELTA")
    print(f"  {'NEW trials':35s}  {c['new']:>8,}")
    print(f"  {'REMOVED trials':35s}  {c['removed']:>8,}")
    print(f"  {'EXISTING - changed':35s}  {c['existing_changed']:>8,}")
    print(f"  {'EXISTING - unchanged':35s}  {c['existing_unchanged']:>8,}")
    print(f"  {'-'*45}")
    total_check = c['new'] + c['existing_changed'] + c['existing_unchanged']
    print(f"  {'Sum (new + changed + unchanged)':35s}  {total_check:>8,}")
    print(f"  {'Current total (sanity check)':35s}  {c['current_trials']:>8,}")
    if c['current_trials'] > 0:
        rate = (c['new'] + c['existing_changed']) / c['current_trials']
        print(f"  Overall change rate: {rate:.2%} of current snapshot")

    new_trials = [t for t in enriched if t["update_type"] == "new"]
    if new_trials:
        _section(f"NEW TRIALS  (n = {len(new_trials):,})")
        drug_n = sum(1 for t in new_trials if t.get("is_drug_trial"))
        non_n  = len(new_trials) - drug_n
        print(f"  Drug trials:      {drug_n:>5,}  ({drug_n/len(new_trials):.1%})")
        print(f"  Non-drug trials:  {non_n:>5,}  ({non_n/len(new_trials):.1%})")

        if drug_n > 0:
            print()
            print("  Top modalities (drug only):")
            mods = Counter(t.get("modality") for t in new_trials if t.get("is_drug_trial"))
            total_mod = sum(mods.values())
            top_mod = mods.most_common(1)[0][1] if mods else 1
            for k, v in mods.most_common(12):
                pct = v / total_mod if total_mod else 0
                bar = "#" * min(35, int(40 * v / top_mod))
                print(f"    {str(k):25s} {v:>5,}  ({pct:5.1%})  {bar}")

            print()
            print("  Top therapeutic areas (drug only):")
            tas = Counter(t.get("therapeutic_area") for t in new_trials if t.get("is_drug_trial"))
            total_ta = sum(tas.values())
            top_ta = tas.most_common(1)[0][1] if tas else 1
            for k, v in tas.most_common(15):
                pct = v / total_ta if total_ta else 0
                bar = "#" * min(35, int(40 * v / top_ta))
                print(f"    {str(k):38s} {v:>5,}  ({pct:5.1%})  {bar}")

            print()
            print("  Drug trial phase distribution:")
            phases = Counter((t.get("phase") or "(unspecified)") for t in new_trials if t.get("is_drug_trial"))
            for k, v in phases.most_common(12):
                print(f"    {str(k):25s} {v:>5,}")

        print()
        print("  Study type distribution (all new):")
        stypes = Counter((t.get("study_type") or "(unspecified)") for t in new_trials)
        for k, v in stypes.most_common(8):
            print(f"    {str(k)[:40]:42s} {v:>5,}")

        print()
        print("  Top sponsors among new trials:")
        spons = Counter((t.get("sponsor_name") or "(unknown)").strip() for t in new_trials)
        for k, v in spons.most_common(12):
            print(f"    {str(k)[:58]:60s} {v:>4,}")

        print()
        print("  Sample (first 5 new trials):")
        for t in new_trials[:5]:
            mod = t.get("modality") or "-"
            ta  = t.get("therapeutic_area") or "-"
            print(f"    {t['nct_id']}  [drug={t.get('is_drug_trial')} / {mod} / {ta}]")
            title = (t.get("title") or "").strip().replace(chr(10), " ")
            print(f"      {title[:120]}")

    updated = [t for t in enriched if t["update_type"] == "existing" and t["update_categories"]]
    if updated:
        _section(f"UPDATED TRIALS  (n = {len(updated):,})")
        print("  Updates by category (a trial may hit multiple):")
        cc = changelog["category_counts"]
        maxv = max(cc.values()) if cc else 1
        for cat, n in sorted(cc.items(), key=lambda x: -x[1]):
            bar = "#" * min(40, int(40 * n / maxv))
            print(f"    {cat:25s} {n:>5,}  {bar}")

        print()
        print("  Histogram -- category hits per updated trial:")
        hist = changelog["per_trial_change_count"]
        if hist:
            max_cats = max(hist.keys())
            maxv = max(hist.values())
            for n in range(1, max_cats + 1):
                count = hist.get(n, 0)
                if count == 0:
                    continue
                bar = "#" * min(40, int(40 * count / maxv))
                label = "category" if n == 1 else "categories"
                print(f"    {n:>3} {label:10s} {count:>5,}  {bar}")

        print()
        print("  Top category combinations (top 15):")
        for combo, n in list(changelog["category_combos"].items())[:15]:
            print(f"    {n:>5,}  {combo}")

        print()
        print("  Sample updated trials (first 5):")
        for t in updated[:5]:
            cats = t["update_categories"]
            print(f"    {t['nct_id']}  ({len(cats)} field changes)")
            for ch in cats[:5]:
                p = str(ch.get("prior"))
                cc_ = str(ch.get("current"))
                if len(p) > 60:   p = p[:57] + "..."
                if len(cc_) > 60: cc_ = cc_[:57] + "..."
                print(f"      - {ch['field']} [{ch['category']}]: {p!r} -> {cc_!r}")

    if c["removed"] > 0:
        _section(f"REMOVED TRIALS  (n = {c['removed']:,})")
        print("  Trials in prior but not current (first 15):")
        for nid in changelog["removed_nct_ids"][:15]:
            print(f"    {nid}")
        if c["removed"] > 15:
            print(f"    ... and {c['removed']-15:,} more")

    _section("DONE")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior",   required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--out-dir", default="storage/chictr_changelogs")
    parser.add_argument("--output-enriched", default=None)
    parser.add_argument("--output-changelog", default=None)
    args = parser.parse_args(argv)

    prior_path   = Path(args.prior)
    current_path = Path(args.current)
    out_dir      = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _section("LOADING SNAPSHOTS")
    print(f"  Prior:   {prior_path}")
    print(f"  Current: {current_path}")
    t0 = datetime.now()
    prior_snap   = json.load(open(prior_path, encoding="utf-8"))
    current_snap = json.load(open(current_path, encoding="utf-8"))
    dt = (datetime.now() - t0).total_seconds()
    print(f"  Loaded in {dt:.1f}s")
    print(f"    prior trials:    {len(prior_snap['trials']):,}")
    print(f"    current trials:  {len(current_snap['trials']):,}")

    _section("COMPUTING DIFF")
    t0 = datetime.now()
    enriched, changelog = compute_diff(prior_snap, current_snap)
    dt = (datetime.now() - t0).total_seconds()
    print(f"  Diff done in {dt:.1f}s")

    print_report(prior_path, current_path, prior_snap, current_snap, enriched, changelog)

    prior_stem = prior_path.stem.split("_chictr_v1")[0]
    curr_stem  = current_path.stem.split("_chictr_v1")[0]
    enr_path  = Path(args.output_enriched) if args.output_enriched else (
        out_dir / f"chictr_enriched_{curr_stem}_vs_{prior_stem}.json")
    clog_path = Path(args.output_changelog) if args.output_changelog else (
        out_dir / f"chictr_changelog_{curr_stem}_vs_{prior_stem}.json")

    enriched_out = {
        "metadata": {
            "source":          "ChiCTR",
            "diff_prior":      str(prior_path),
            "diff_current":    str(current_path),
            "generated_at":    datetime.now().isoformat(),
            **current_snap.get("metadata", {}),
        },
        "trials":            enriched,
        "changelog_counts":  changelog["counts"],
    }

    _section("WRITING OUTPUTS")
    enr_path.parent.mkdir(parents=True, exist_ok=True)
    clog_path.parent.mkdir(parents=True, exist_ok=True)
    enr_path.write_text(json.dumps(enriched_out, ensure_ascii=False, default=str), encoding="utf-8")
    clog_path.write_text(json.dumps(changelog, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"  Enriched snapshot: {enr_path}  ({enr_path.stat().st_size/1e6:.1f} MB)")
    print(f"  Changelog:         {clog_path}  ({clog_path.stat().st_size/1e3:.1f} KB)")

    c = changelog["counts"]
    print()
    print("=" * W)
    print(f"  FINAL:  new={c['new']:,}  changed={c['existing_changed']:,}  "
          f"unchanged={c['existing_unchanged']:,}  removed={c['removed']:,}")
    print("=" * W)


if __name__ == "__main__":
    main()
