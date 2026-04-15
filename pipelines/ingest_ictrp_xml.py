# pipelines/ingest_ictrp_xml.py
"""
WHO ICTRP XML ingestion for ChiCTR (and other registry) records.
Input: XML export from https://trialsearch.who.int/AdvSearch.aspx
Output: pandas DataFrame with ALEXIS-compatible fields + saves to parquet

Uses iterparse to handle large/truncated files gracefully.
"""

import xml.etree.ElementTree as ET
import pandas as pd
from pathlib import Path
import sys


# ------------------------------------------------------------------
# Field mapping: ICTRP XML tag -> ALEXIS column name
# Tag names verified against actual ICTRP XML output 2026-03-30
# ------------------------------------------------------------------
FIELD_MAP = {
    "TrialID":               "trial_id",
    "Secondary_ID":          "secondary_ids",
    "Public_title":          "brief_title",
    "Scientific_title":      "official_title",
    "Primary_sponsor":       "lead_sponsor_name",
    "Date_registration":     "registration_date",
    "Date_enrollement":      "start_date",          # typo is in the source
    "Target_size":           "enrollment",
    "Recruitment_Status":    "overall_status",       # capital S
    "web_address":           "source_url",
    "Study_type":            "study_type",           # capital S
    "Study_design":          "study_design",
    "Phase":                 "phase",
    "Countries":             "countries",
    "Condition":             "conditions_raw",
    "Intervention":          "interventions_raw",    # singular field, not Intervention_1/2/3
    "Primary_outcome":       "primary_outcome",
    "Secondary_outcome":     "secondary_outcome",
    "Ethics_review_status":  "ethics_status",
    "Contact_Firstname":     "contact_firstname",    # capital F
    "Contact_Lastname":      "contact_lastname",     # capital L
    "Contact_Affiliation":   "contact_affiliation",  # capital A
    "Source_Register":       "source_register",
    "Inclusion_Criteria":    "inclusion_criteria",
    "Exclusion_Criteria":    "exclusion_criteria",
    "Source_Support":        "funding_source",
}


def _detect_registry(trial_id: str) -> str:
    trial_id = trial_id.upper()
    prefixes = {
        "CHICTR":  "ChiCTR",
        "ACTRN":   "ANZCTR",
        "EUCTR":   "EudraCT",
        "ISRCTN":  "ISRCTN",
        "IRCT":    "IRCT",
        "DRKS":    "DRKS",
        "JPRN":    "JPRN",
        "CTRI":    "CTRI",
        "NCT":     "ClinicalTrials.gov",
        "NL":      "OMON",
        "PACTR":   "PACTR",
        "RPCEC":   "RPCEC",
        "TCTR":    "TCTR",
    }
    for prefix, name in prefixes.items():
        if trial_id.startswith(prefix):
            return name
    return "Unknown"


def _normalize_status(status: str | None) -> str | None:
    if not status:
        return None
    s = status.strip().lower()
    mapping = {
        "recruiting":              "RECRUITING",
        "not recruiting":          "NOT_YET_RECRUITING",
        "not yet recruiting":      "NOT_YET_RECRUITING",
        "completed":               "COMPLETED",
        "terminated":              "TERMINATED",
        "suspended":               "SUSPENDED",
        "withdrawn":               "WITHDRAWN",
        "active, not recruiting":  "ACTIVE_NOT_RECRUITING",
        "enrolling by invitation": "ENROLLING_BY_INVITATION",
    }
    return mapping.get(s, status.strip().upper().replace(" ", "_"))


def parse_ictrp_xml(xml_path: str | Path) -> pd.DataFrame:
    xml_path = Path(xml_path)
    print(f"Parsing: {xml_path} ({xml_path.stat().st_size / 1e6:.1f} MB)")
    print("Using iterparse — will handle truncated file gracefully...")

    rows = []
    try:
        context = ET.iterparse(xml_path, events=("end",))
        for event, elem in context:
            if elem.tag != "Trial":
                continue

            row = {}
            for xml_tag, col_name in FIELD_MAP.items():
                el = elem.find(xml_tag)
                row[col_name] = el.text.strip() if el is not None and el.text else None

            # Derived fields
            row["registry"] = _detect_registry(row.get("trial_id", "") or "")

            rows.append(row)
            elem.clear()  # free memory as we go

            if len(rows) % 10000 == 0:
                print(f"  {len(rows):,} records parsed...")

    except ET.ParseError as e:
        print(f"\nXML truncated at: {e} — processed {len(rows):,} complete records")

    print(f"Total records parsed: {len(rows):,}")

    df = pd.DataFrame(rows)

    # Normalize status
    df["overall_status"] = df["overall_status"].apply(_normalize_status)

    # Coerce enrollment to numeric
    df["enrollment"] = pd.to_numeric(df["enrollment"], errors="coerce")

    # Parse dates
    for date_col in ["registration_date", "start_date"]:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    return df


def build_classification_input(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["classification_text"] = (
        df["brief_title"].fillna("") + " "
        + df["official_title"].fillna("") + " "
        + df["conditions_raw"].fillna("") + " "
        + df["interventions_raw"].fillna("") + " "
        + df["study_design"].fillna("")
    ).str.strip()
    return df


if __name__ == "__main__":
    xml_path = sys.argv[1] if len(sys.argv) > 1 else "storage/ICTRP-Results - China.xml"

    df = parse_ictrp_xml(xml_path)
    df = build_classification_input(df)

    print(f"\nRegistries found:")
    print(df["registry"].value_counts().to_string())

    print(f"\nStatus breakdown:")
    print(df["overall_status"].value_counts().head(10).to_string())

    print(f"\nPhase breakdown:")
    print(df["phase"].value_counts().head(15).to_string())

    print(f"\nField completeness (% non-null):")
    print((df.notnull().mean() * 100).round(1).sort_values(ascending=False).to_string())

    print(f"\nSample records (ChiCTR only):")
    cols = ["trial_id", "brief_title", "interventions_raw", "conditions_raw",
            "phase", "overall_status", "lead_sponsor_name"]
    chictr = df[df["registry"] == "ChiCTR"]
    print(chictr[cols].sample(min(5, len(chictr))).to_string())

    out_path = Path("storage/ictrp_china_parsed.parquet")
    df.to_parquet(out_path, index=False)
    print(f"\nSaved {len(df):,} records → {out_path}")
