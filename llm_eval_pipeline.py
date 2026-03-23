#!/usr/bin/env python3
import json, sys, time, gc
from pathlib import Path
import pandas as pd

BASE = Path(r"//wsl.localhost/Ubuntu/home/jeanmfc/projects/ALEXIS")
SNAPSHOT = BASE / "storage" / "snapshots" / "clinical_trials_v2" / "active_universe"
RAW = SNAPSHOT / "raw 01-01-26"
MASTER_DB = SNAPSHOT / "master_DB_2025_Q4_patched.json"
CHUNK_DIR = SNAPSHOT / "llm_eval_chunks"
TRIALS_PER_CHUNK = 100
LOAD_CHUNKSIZE = 50000

def load_master_db():
    print("Loading master DB...")
    with open(MASTER_DB, encoding="utf-8") as f:
        data = json.load(f)
    trials = data["trials"]
    nct_set = {t["nct_id"] for t in trials}
    trial_dict = {t["nct_id"]: t for t in trials}
    print("  Loaded " + str(len(nct_set)) + " NCT IDs")
    return nct_set, trial_dict


def load_filtered(filename, usecols, nct_set):
    path = RAW / filename
    print("  Loading " + filename + "...", end=" ", flush=True)
    t0 = time.time()
    kept = []
    for chunk in pd.read_csv(path, sep="|", usecols=usecols, dtype=str,
                             na_values=["", "NA"], keep_default_na=True,
                             encoding="utf-8", on_bad_lines="skip",
                             low_memory=False, chunksize=LOAD_CHUNKSIZE):
        chunk = chunk.fillna("")
        filtered = chunk[chunk["nct_id"].isin(nct_set)]
        if len(filtered) > 0:
            kept.append(filtered)
    df = pd.concat(kept, ignore_index=True) if kept else pd.DataFrame(columns=usecols)
    print(str(len(df)) + " rows in " + str(round(time.time()-t0, 1)) + "s")
    return df


def load_all_tables(nct_set):
    print("")
    print("Loading raw AACT tables (chunked, filtered)...")
    tables = {}
    tables["studies"] = load_filtered("studies.txt",
        ["nct_id", "brief_title", "official_title", "phase", "source_class", "overall_status"], nct_set)
    tables["studies"] = tables["studies"].drop_duplicates("nct_id").set_index("nct_id")
    tables["summaries"] = load_filtered("brief_summaries.txt", ["nct_id", "description"], nct_set)
    tables["summaries"] = tables["summaries"].drop_duplicates("nct_id").set_index("nct_id")
    tables["summaries"].columns = ["brief_summary"]
    tables["descriptions"] = load_filtered("detailed_descriptions.txt", ["nct_id", "description"], nct_set)
    tables["descriptions"] = tables["descriptions"].drop_duplicates("nct_id").set_index("nct_id")
    tables["descriptions"].columns = ["detailed_description"]
    tables["interventions"] = load_filtered("interventions.txt",
        ["nct_id", "intervention_type", "name", "description"], nct_set)
    tables["int_mesh"] = load_filtered("browse_interventions.txt", ["nct_id", "mesh_term"], nct_set)
    tables["conditions"] = load_filtered("conditions.txt", ["nct_id", "name"], nct_set)
    tables["cond_mesh"] = load_filtered("browse_conditions.txt", ["nct_id", "mesh_term"], nct_set)
    tables["outcomes"] = load_filtered("design_outcomes.txt",
        ["nct_id", "outcome_type", "measure", "description"], nct_set)
    gc.collect()
    tables["eligibilities"] = load_filtered("eligibilities.txt", ["nct_id", "criteria"], nct_set)
    tables["eligibilities"] = tables["eligibilities"].drop_duplicates("nct_id").set_index("nct_id")
    return tables


def cap(text, maxlen):
    text = str(text or "").strip()
    return text[:maxlen] if len(text) > maxlen else text


def build_trial_text(nct_id, t):
    s = t["studies"]
    row = s.loc[nct_id] if nct_id in s.index else pd.Series(dtype=str)
    title = str(row.get("official_title", "") or row.get("brief_title", ""))
    phase = str(row.get("phase", ""))
    sponsor = str(row.get("source_class", ""))
    summ = t["summaries"]
    brief = cap(summ.loc[nct_id, "brief_summary"] if nct_id in summ.index else "", 800)
    desc = t["descriptions"]
    detailed = cap(desc.loc[nct_id, "detailed_description"] if nct_id in desc.index else "", 1000)
    ints_df = t["interventions"]
    ints = ints_df[ints_df["nct_id"] == nct_id].head(3)
    int_lines = []
    for _, r in ints.iterrows():
        name = r.get("name", "")
        itype = r.get("intervention_type", "")
        d = cap(r.get("description", ""), 400)
        line = name + " (" + itype + ")"
        if d:
            line = line + " - " + d
        int_lines.append(line)
    imesh = t["int_mesh"]
    int_meshes = imesh[imesh["nct_id"] == nct_id]["mesh_term"].tolist()
    conds = t["conditions"]
    cond_names = conds[conds["nct_id"] == nct_id]["name"].tolist()
    cmesh = t["cond_mesh"]
    cond_meshes = cmesh[cmesh["nct_id"] == nct_id]["mesh_term"].tolist()
    out_df = t["outcomes"]
    trial_out = out_df[out_df["nct_id"] == nct_id]
    primary = trial_out[trial_out["outcome_type"].str.lower() == "primary"].head(3)
    pri_lines = []
    for _, r in primary.iterrows():
        m = str(r.get("measure", ""))
        d = cap(r.get("description", ""), 200)
        if d:
            pri_lines.append(m + ": " + d)
        else:
            pri_lines.append(m)
    secondary = trial_out[trial_out["outcome_type"].str.lower() == "secondary"].head(5)
    sec_lines = []
    for _, r in secondary.iterrows():
        m = str(r.get("measure", ""))
        d = cap(r.get("description", ""), 150)
        if d:
            sec_lines.append(m + ": " + d)
        else:
            sec_lines.append(m)
    elig = t["eligibilities"]
    criteria = cap(elig.loc[nct_id, "criteria"] if nct_id in elig.index else "", 1000)
    lines = []
    lines.append("NCT ID: " + nct_id)
    lines.append("Title: " + title)
    lines.append("Phase: " + phase)
    lines.append("Sponsor class: " + sponsor)
    lines.append("Brief summary: " + brief)
    if detailed:
        lines.append("Detailed description: " + detailed)
    if int_lines:
        lines.append("Interventions: " + "; ".join(int_lines))
    if int_meshes:
        lines.append("Intervention MeSH: " + ", ".join(int_meshes))
    if cond_names:
        lines.append("Conditions: " + ", ".join(cond_names))
    if cond_meshes:
        lines.append("Condition MeSH: " + ", ".join(cond_meshes))
    if pri_lines:
        lines.append("Primary outcomes: " + "; ".join(pri_lines))
    if sec_lines:
        lines.append("Secondary outcomes: " + "; ".join(sec_lines))
    if criteria:
        lines.append("Eligibility criteria: " + criteria)
    return chr(10).join(lines)


def main():
    t0 = time.time()
    nct_set, trial_dict = load_master_db()
    tables = load_all_tables(nct_set)
    print("")
    print("Filtered table sizes:")
    for name, df in tables.items():
        print("  " + name + ": " + str(len(df)) + " rows")
    print("")
    print("Building trial text for " + str(len(nct_set)) + " trials...")
    trial_texts = {}
    for i, nct_id in enumerate(sorted(nct_set)):
        trial_texts[nct_id] = build_trial_text(nct_id, tables)
        if (i + 1) % 5000 == 0:
            print("  Built " + str(i+1) + "/" + str(len(nct_set)))
    print("  Done: " + str(len(trial_texts)) + " trial texts")
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    nct_list = sorted(trial_texts.keys())
    chunks = []
    for i in range(0, len(nct_list), TRIALS_PER_CHUNK):
        chunk_ids = nct_list[i:i + TRIALS_PER_CHUNK]
        chunk_data = {nid: trial_texts[nid] for nid in chunk_ids}
        cf = CHUNK_DIR / ("chunk_" + str(i).zfill(5) + ".json")
        with open(cf, "w", encoding="utf-8") as f:
            json.dump(chunk_data, f, ensure_ascii=False)
        chunks.append({"file": str(cf), "nct_ids": chunk_ids, "start": i})
    manifest = CHUNK_DIR / "manifest.json"
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump({"total_trials": len(nct_list), "chunk_size": TRIALS_PER_CHUNK,
                    "num_chunks": len(chunks),
                    "chunk_files": [c["file"] for c in chunks]}, f, indent=2)
    print("")
    print("Saved " + str(len(chunks)) + " chunks to " + str(CHUNK_DIR))
    print("Data prep done in " + str(int(time.time()-t0)) + "s")
    sep = "=" * 60
    for j, nid in enumerate(nct_list[:3]):
        print("")
        print(sep)
        print("SAMPLE TRIAL " + str(j+1) + " (" + nid + "):")
        print(sep)
        txt = trial_texts[nid]
        print(txt[:2000])
        if len(txt) > 2000:
            print("... (truncated, " + str(len(txt)) + " chars total)")


if __name__ == "__main__":
    main()

