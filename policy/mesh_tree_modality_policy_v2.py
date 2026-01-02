from functools import lru_cache
import requests

"""
This module implements MeSH tree prefix -> drug submodality mapping.
Each prefix is drawn from the actual MeSH hierarchy:

"""

# Precise prefix mapping based on the MeSH hierarchy:
MESH_PREFIX_TO_SUBMODALITY = [
    # ---- Highly specific biologic subtypes ----
    ("D12.776.828.300", "fusion_protein"),           # Recombinant Fusion Proteins subtype (therapeutic fusion constructs) :contentReference[oaicite:1]{index=1}
    ("D12.776.124.486.485.114.224", "monoclonal_antibody"),  # Combined/bispecific & related antibody therapeutics :contentReference[oaicite:2]{index=2}
    ("D12.776.124.486.485.114", "antibody_protein"),         # General antibody proteins subcategory :contentReference[oaicite:3]{index=3}

    # ---- Broad recombinant biologics ----
    ("D12.776.828.868", "vaccine"),                # Synthetic vaccine branch under recombinant proteins :contentReference[oaicite:4]{index=4}
    ("D20.215.894", "vaccine"),                    # Biological Products -> Vaccines (complex mixtures) :contentReference[oaicite:5]{index=5}
    ("D12.776.828", "recombinant_protein"),        # General recombinant proteins (e.g., engineered cytokines) :contentReference[oaicite:6]{index=6}

    # ---- Oligonucleotide / nucleic acid based ----
    ("D13", "oligonucleotide"),                    # Nucleic Acids category (oligo/siRNA/etc.) — use with base_modality context

    # ---- Small molecule substructure classes ----
    ("D02", "small_molecule"),                     # Organic Chemicals (core small molecule classification)
    ("D03", "small_molecule"),                     # Heterocyclic compounds (common small molecule scaffolds)
    ("D04", "small_molecule"),                     # Polycyclic compounds (e.g., steroid frameworks)
    ("D26", "small_molecule"),                     # Pharmaceutical Preparations common in small molecule drugs
    ("D27", "small_molecule"),                     # Chemical Actions & Uses pharmacologic branch

    # ---- Fallback broad biologic if nothing more specific ----
    ("D12", "biologic"),                           # Proteins / peptides not caught above
    ("D23", "biologic"),                           # Biological factors (immune proteins, etc.)
]

def mesh_tree_to_submodality(mesh_id: str | None, term: str | None, base_modality: str) -> str | None:
    """
    Given a MeSH ID/term and base modality,
    return a detailed submodality label if possible based on MeSH tree prefixes.
    """
    if not mesh_id:
        return None

    # get all relevant tree numbers for the descriptor
    tree_nums = _get_tree_numbers(mesh_id)

    # match against prefix list in order
    for num in tree_nums:
        for prefix, submod in MESH_PREFIX_TO_SUBMODALITY:
            if num.startswith(prefix):
                return submod

    # fallback: look at the term text if provided
    if term:
        t = term.lower()
        if "monoclonal" in t or "antibody" in t:
            return "monoclonal_antibody"
        if "fusion protein" in t or "chimeric" in t:
            return "fusion_protein"
        if "vaccine" in t:
            return "vaccine"

    return None


# --- Helpers: retrieve and cache MeSH tree numbers ---

@lru_cache(maxsize=10000)
def _get_tree_numbers(mesh_id: str) -> list[str]:
    """
    Retrieve tree numbers for a descriptor or its mapped descriptors.
    If the ID is a descriptor (D...), return its tree numbers.
    If it is a supplementary concept (C...), map it to descriptors first.
    """
    if mesh_id.startswith("D"):
        return _fetch_tree_nums_descriptor(mesh_id)
    if mesh_id.startswith("C"):
        mapped = _fetch_mapped_descriptors(mesh_id)
        nums: list[str] = []
        for d_id in mapped:
            nums.extend(_fetch_tree_nums_descriptor(d_id))
        return nums
    return []


def _fetch_tree_nums_descriptor(descr_id: str) -> list[str]:
    """
    Fetch tree numbers for a MeSH descriptor using NLM’s MeSH REST API.
    """
    try:
        url = f"https://id.nlm.nih.gov/mesh/{descr_id}.json"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("treeNumber") or []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            return [raw]
    except Exception:
        pass
    return []


def _fetch_mapped_descriptors(supp_id: str) -> list[str]:
    """
    For a supplementary concept (C...), attempt to resolve it
    to underlying descriptors via relevant fields like 'pharmacologicAction' or 'headingMappedTo'.
    """
    try:
        url = f"https://id.nlm.nih.gov/mesh/{supp_id}.json"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        mapped: list[str] = []
        for field in ("pharmacologicAction", "headingMappedTo"):
            for ent in data.get(field) or []:
                did = ent.get("meshId") or ent.get("id")
                if isinstance(did, str) and did.startswith("D"):
                    mapped.append(did)
        return mapped
    except Exception:
        return []
