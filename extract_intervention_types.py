import json
import csv

INPUT_JSON = "raw_ctgov_full_dump.json"
OUTPUT_CSV = "intervention_types.csv"

with open(INPUT_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["nct_id", "intervention_type"])

    for record in data:
        nct_id = record.get("idInfo", {}).get("nctId", "")
        interventions = (
            record.get("protocolSection", {})
            .get("armsInterventionsModule", {})
            .get("interventions", [])
        )

        if not interventions:
            # no structured intervention, write blank
            writer.writerow([nct_id, ""])
        else:
            for iv in interventions:
                iv_type = iv.get("type", "")
                writer.writerow([nct_id, iv_type])
