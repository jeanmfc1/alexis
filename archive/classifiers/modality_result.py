from dataclasses import dataclass
from typing import Optional, List

@dataclass(frozen=True)
class ModalityResult:
    """
    Structured result of modality classification.

    This object captures *what* modality was assigned and *why*,
    without performing any logging or side effects.
    """
    modality: Optional[str]

    # Where the decision came from
    source: str  # "mesh_tree" | "text" | "intervention_type" | "unknown"

    # Evidence context (optional, for audit/debug)
    mesh_id: Optional[str] = None
    matched_prefix: Optional[str] = None
    tree_numbers: Optional[List[str]] = None
    text_used: Optional[str] = None
