"""Connectors retrieve authorized evidence. They do not interpret it.

A connector returns `EvidenceRecord`s with stable, citable IDs and locators that
point back into the original source. It assigns no support level, draws no
conclusion, and resolves no conflict — that is the analysis skills' work. Keeping
the boundary strict is what lets a reader tell "the record says X" apart from
"DecisionLens concluded X".

The prototype implements one connector, `LocalFileEvidenceSource` (Phase 3).
Enterprise connectors are specified in docs/03 rather than stubbed, because a
written contract is more honest than a class that raises NotImplementedError.
"""

from decision_lens.connectors.base import (
    BaseEvidenceSource,
    EvidenceSource,
    EvidenceSourceError,
)

__all__ = ["BaseEvidenceSource", "EvidenceSource", "EvidenceSourceError"]
