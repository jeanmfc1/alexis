from __future__ import annotations

from functools import lru_cache
from typing import Any
import requests

from classifiers.modality_result import ModalityResult

"""
MeSH tree prefix -> drug submodality mapping.

This module performs MeSH-only inference using MeSH treeNumber prefixes.
It does NOT do text inference.
"""

MESH_REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "alexis-modality/1.0",
}

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


def mesh_tree_to_submodality(mesh_id: str | None) -> ModalityResult:
    """
    Return a ModalityResult inferred strictly from MeSH tree numbers.
    """
    if not mesh_id:
        return ModalityResult(modality=None, source="unknown")

    tree_nums = _get_tree_numbers(mesh_id)

    # prefix-first matching across ALL tree numbers
    for prefix, submod in MESH_PREFIX_TO_SUBMODALITY:
        if any(num.startswith(prefix) for num in tree_nums):
            return ModalityResult(
                modality=submod,
                source="mesh_tree",
                mesh_id=mesh_id,
                matched_prefix=prefix,
                tree_numbers=tree_nums or None,
            )

    return ModalityResult(
        modality=None,
        source="unknown",
        mesh_id=mesh_id,
        tree_numbers=tree_nums or None,
    )


@lru_cache(maxsize=10000)
def _get_tree_numbers(mesh_id: str) -> list[str]:
    """
    Retrieve tree numbers for a descriptor or its mapped descriptors.
    - D...: descriptor -> tree numbers directly
    - C...: supplementary concept -> map to descriptors -> tree numbers
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
        return _dedup_preserve_order(nums)

    return []


def _fetch_tree_nums_descriptor(descr_id: str) -> list[str]:
    """
    Fetch tree numbers for a MeSH descriptor using NLM’s MeSH REST API.
    """
    descr_id = descr_id.strip()
    if not descr_id:
        return []

    try:
        url = f"https://id.nlm.nih.gov/mesh/{descr_id}.json"
        resp = requests.get(url, headers=MESH_REQUEST_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        raw = data.get("treeNumber", [])
        if isinstance(raw, list):
            out = [_normalize_tree_num(v) for v in raw]
            return [v for v in out if v]
        if isinstance(raw, str):
            v = _normalize_tree_num(raw)
            return [v] if v else []

        return []

    except Exception:
        return []


def _fetch_mapped_descriptors(supp_id: str) -> list[str]:
    """
    For supplementary concept records (C...), fetch mapped descriptors (D...).
    """
    supp_id = supp_id.strip()
    if not supp_id:
        return []

    try:
        url = f"https://id.nlm.nih.gov/mesh/{supp_id}.json"
        resp = requests.get(url, headers=MESH_REQUEST_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        mapped: list[str] = []
        for field in ("pharmacologicAction", "headingMappedTo"):
            entries = data.get(field) or []
            if not isinstance(entries, list):
                continue

            for ent in entries:
                did = ""
                if isinstance(ent, str):
                    did = _normalize_mesh_id(ent)
                elif isinstance(ent, dict):
                    cand = ent.get("meshId") or ent.get("id") or ent.get("@id") or ""
                    did = _normalize_mesh_id(cand) if isinstance(cand, str) else ""

                if did.startswith("D"):
                    mapped.append(did)

        return _dedup_preserve_order(mapped)

    except Exception:
        return []


def _normalize_tree_num(x: Any) -> str:
    if not isinstance(x, str):
        return ""
    s = x.strip()
    if not s:
        return ""
    marker = "/mesh/"
    if marker in s:
        s = s.split(marker, 1)[1].strip()
    return s


def _normalize_mesh_id(x: Any) -> str:
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
