from __future__ import annotations

from functools import lru_cache
from typing import Any
import requests

"""
MeSH tree prefix -> drug submodality mapping.

NLM MeSH JSON often returns treeNumber values as URLs, e.g.:
  "treeNumber": ["http://id.nlm.nih.gov/mesh/D03.383.621....", ...]

We must normalize those to bare tree codes like:
  "D03.383.621...."

Then prefix matching against MeSH hierarchy works.
"""

# Most-specific-first ordering matters (first match wins).
MESH_PREFIX_TO_SUBMODALITY: list[tuple[str, str]] = [
    # Biologic subtypes
    ("D12.776.124.486.485.114.224", "monoclonal_antibody"),
    ("D12.776.124.486.485.114", "antibody_protein"),
    ("D12.776.828.300", "fusion_protein"),

    # Vaccines
    ("D12.776.828.868", "vaccine"),
    ("D20.215.894", "vaccine"),
    ("D12.776.828", "recombinant_protein"),

    # Oligonucleotide based drugs (nucleic acids)
    ("D13", "oligonucleotide"),

    # Small molecules
    ("D02", "small_molecule"),
    ("D03", "small_molecule"),
    ("D04", "small_molecule"),
    ("D26", "small_molecule"),
    ("D27", "small_molecule"),

    # Fallback biologic
    ("D12", "biologic"),
    ("D23", "biologic"),
]


# ----------------------------
# Public API
# ----------------------------

def mesh_tree_to_submodality(mesh_id: str | None, term: str | None, base_modality: str) -> str | None:
    """
    Given a MeSH descriptor/supplementary ID and optional term text,
    return a detailed submodality label if possible based on MeSH tree prefixes.

    Returns:
      - submodality string (e.g. "small_molecule", "monoclonal_antibody") if inferred
      - None if cannot infer
    """
    if not mesh_id:
        return None

    tree_nums = _get_tree_numbers(mesh_id)

    # Match against prefix list in order
    # match against prefix list in order (most-specific-first)
    for prefix, submod in MESH_PREFIX_TO_SUBMODALITY:
        if any(num.startswith(prefix) for num in tree_nums):
            return submod


    # Lightweight term fallback (kept conservative)
    if term:
        t = term.lower()
        if ("monoclonal" in t) or ("antibody" in t):
            return "monoclonal_antibody"
        if ("fusion protein" in t) or ("chimeric" in t):
            return "fusion_protein"
        if "vaccine" in t:
            return "vaccine"

    return None


# ----------------------------
# Helpers: retrieve and cache MeSH tree numbers
# ----------------------------

@lru_cache(maxsize=10000)
def _get_tree_numbers(mesh_id: str) -> list[str]:
    """
    Retrieve tree numbers for a descriptor or its mapped descriptors.
    - If the ID is a descriptor (D...), return its tree numbers.
    - If it is a supplementary concept (C...), map it to descriptors first,
      then return the union of their tree numbers.
    """
    mesh_id = mesh_id.strip()
    if not mesh_id:
        return []

    if mesh_id.startswith("D"):
        return _fetch_tree_nums_descriptor(mesh_id)

    if mesh_id.startswith("C"):
        mapped = _fetch_mapped_descriptors(mesh_id)
        nums: list[str] = []
        for d_id in mapped:
            nums.extend(_fetch_tree_nums_descriptor(d_id))
        # de-dup while preserving order
        return _dedup_preserve_order(nums)

    return []


def _fetch_tree_nums_descriptor(descr_id: str) -> list[str]:
    """
    Fetch tree numbers for a MeSH descriptor using NLM’s MeSH REST API.
    Normalizes URLs into bare tree codes.
    """
    descr_id = descr_id.strip()
    if not descr_id:
        return []

    try:
        url = f"https://id.nlm.nih.gov/mesh/{descr_id}.json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        raw = data.get("treeNumber", [])

        if isinstance(raw, list):
            out = [_normalize_tree_num(v) for v in raw]
            return [v for v in out if v]

        if isinstance(raw, str):
            v = _normalize_tree_num(raw)
            return [v] if v else []

        # Unexpected type
        return []

    except Exception:
        return []


def _fetch_mapped_descriptors(supp_id: str) -> list[str]:
    """
    For supplementary concept records (C...), fetch mapped descriptors (D...).

    NLM JSON fields like "pharmacologicAction" may be URL strings.
    We normalize and keep only D* IDs.
    """
    supp_id = supp_id.strip()
    if not supp_id:
        return []

    try:
        url = f"https://id.nlm.nih.gov/mesh/{supp_id}.json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        mapped: list[str] = []

        for field in ("pharmacologicAction", "headingMappedTo"):
            entries = data.get(field) or []
            if not isinstance(entries, list):
                continue

            for ent in entries:
                did = ""

                # ent can be a URL string or sometimes a dict (rare)
                if isinstance(ent, str):
                    did = _normalize_mesh_id(ent)

                elif isinstance(ent, dict):
                    # If the API ever returns dicts, try common keys.
                    # Also normalize in case value is a URL.
                    cand = ent.get("meshId") or ent.get("id") or ent.get("@id") or ""
                    did = _normalize_mesh_id(cand) if isinstance(cand, str) else ""

                if did.startswith("D"):
                    mapped.append(did)

        return _dedup_preserve_order(mapped)

    except Exception:
        return []


# ----------------------------
# Normalization utilities
# ----------------------------

def _normalize_tree_num(x: Any) -> str:
    """
    Convert treeNumber entry into a bare tree code string.

    Examples:
      "http://id.nlm.nih.gov/mesh/D03.383.621" -> "D03.383.621"
      "D03.383.621" -> "D03.383.621"
    """
    if not isinstance(x, str):
        return ""

    s = x.strip()
    if not s:
        return ""

    # Most common form: http(s)://id.nlm.nih.gov/mesh/Dxx.xxx...
    marker = "/mesh/"
    if marker in s:
        s = s.split(marker, 1)[1].strip()

    return s


def _normalize_mesh_id(x: Any) -> str:
    """
    Normalize a MeSH ID possibly expressed as a URL:
      "http://id.nlm.nih.gov/mesh/D010797" -> "D010797"
      "D010797" -> "D010797"
    """
    if not isinstance(x, str):
        return ""

    s = x.strip()
    if not s:
        return ""

    marker = "/mesh/"
    if marker in s:
        s = s.split(marker, 1)[1].strip()

    return s


def _dedup_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x and (x not in seen):
            seen.add(x)
            out.append(x)
    return out

