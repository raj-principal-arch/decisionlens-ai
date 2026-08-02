"""The evidence-source contract.

A connector authenticates, applies the requesting user's permissions, searches,
retrieves, preserves metadata, normalizes, and returns evidence. It does not
decide what the company should build.

That boundary is enforced by the signature, not by convention: `retrieve` takes an
`EvidenceRequest` (scope) and returns `EvidenceRecord`s (source material). There is
no channel through which a connector can return a conclusion, a ranking, or a
judgment about quality — those are the analysis skills' work.

The prototype implements one source, `LocalFileEvidenceSource` (Phase 3).
Enterprise sources — Jira, Confluence, product metrics, customer feedback, support
tickets — are specified in docs/03 and deliberately not stubbed here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from decision_lens.models import EvidenceRecord, EvidenceRequest, SourceSystem


class EvidenceSourceError(RuntimeError):
    """A source could not serve a request.

    Raised for unreachable sources, malformed inputs, and authorization failures.
    The orchestrator handles partial failure by recording it in the run trace: one
    dead connector degrades a brief, it does not abort it.
    """


@runtime_checkable
class EvidenceSource(Protocol):
    """Structural contract every evidence source satisfies.

    A Protocol rather than a base class so a source need not inherit from
    DecisionLens to be usable — including test fakes and future adapters wrapping
    an existing enterprise client.

    Note what `runtime_checkable` buys and what it does not. `isinstance` checks
    only that the named attributes *exist*; a class whose `retrieve` takes the
    wrong arguments or returns the wrong type still passes. Signature conformance
    is enforced statically by mypy, not at runtime. Treat an isinstance check as a
    smoke test, never as a guarantee that a source honours the contract.
    """

    @property
    def source_system(self) -> SourceSystem:
        """Which system this source retrieves from."""
        ...

    def retrieve(self, request: EvidenceRequest) -> Sequence[EvidenceRecord]:
        """Return evidence matching the request scope.

        Returns an empty sequence when nothing matches. Finding nothing is a
        legitimate answer and must not raise — a silent gap becomes a visible one
        only if the caller can tell the difference between "none" and "failed".
        """
        ...


class BaseEvidenceSource(ABC):
    """Optional base for sources that want the shared plumbing.

    Implementations override `source_system` and `_retrieve`. This class owns the
    invariants every source must hold, so no connector can forget them:

    * record IDs are unique within a response
    * every record is stamped with this source's `source_system`
    * `max_records` is respected
    """

    @property
    @abstractmethod
    def source_system(self) -> SourceSystem: ...

    @abstractmethod
    def _retrieve(self, request: EvidenceRequest) -> Sequence[EvidenceRecord]:
        """Source-specific retrieval. Called by `retrieve` after validation."""

    def retrieve(self, request: EvidenceRequest) -> Sequence[EvidenceRecord]:
        if request.source_systems and self.source_system not in request.source_systems:
            return ()

        records = tuple(self._retrieve(request))

        seen: set[str] = set()
        for record in records:
            if record.id in seen:
                raise EvidenceSourceError(
                    f"{type(self).__name__} returned duplicate evidence id {record.id!r}; "
                    "citations would be ambiguous"
                )
            seen.add(record.id)
            if record.source_system is not self.source_system:
                raise EvidenceSourceError(
                    f"{type(self).__name__} returned a record stamped "
                    f"{record.source_system!r}, expected {self.source_system!r}"
                )

        return records[: request.max_records]
