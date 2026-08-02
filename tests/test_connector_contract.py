"""The evidence-source contract.

Exercised against in-test fakes. No real connector exists until Phase 3, and the
point of these tests is that the contract holds for anything implementing it.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from decision_lens.connectors import BaseEvidenceSource, EvidenceSource, EvidenceSourceError
from decision_lens.models import (
    EvidenceRecord,
    EvidenceRequest,
    EvidenceType,
    SourceSystem,
    UserContext,
)


def _record(record_id: str, system: SourceSystem = SourceSystem.LOCAL_FILE) -> EvidenceRecord:
    return EvidenceRecord(
        id=record_id,
        source_system=system,
        source_id=f"{record_id}.md",
        content=f"Synthetic content for {record_id}.",
        evidence_type=EvidenceType.OPERATIONAL_RECORD,
    )


class FakeSource(BaseEvidenceSource):
    """Minimal source used to test the shared plumbing in BaseEvidenceSource."""

    def __init__(self, records: Sequence[EvidenceRecord]) -> None:
        self._records = tuple(records)
        self.calls = 0

    @property
    def source_system(self) -> SourceSystem:
        return SourceSystem.LOCAL_FILE

    def _retrieve(self, request: EvidenceRequest) -> Sequence[EvidenceRecord]:
        self.calls += 1
        return self._records


class TestProtocolConformance:
    def test_base_subclass_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeSource([]), EvidenceSource)

    def test_inheritance_is_not_required(self) -> None:
        # A source may satisfy the contract structurally — an adapter around an
        # existing enterprise client need not inherit from DecisionLens.
        class Standalone:
            @property
            def source_system(self) -> SourceSystem:
                return SourceSystem.JIRA

            def retrieve(self, request: EvidenceRequest) -> Sequence[EvidenceRecord]:
                return ()

        assert isinstance(Standalone(), EvidenceSource)

    def test_missing_retrieve_fails_the_protocol(self) -> None:
        class NotASource:
            @property
            def source_system(self) -> SourceSystem:
                return SourceSystem.JIRA

        assert not isinstance(NotASource(), EvidenceSource)

    def test_runtime_check_does_not_verify_signatures(self) -> None:
        # Pinning a real limitation rather than implying safety the check does not
        # provide: runtime_checkable tests attribute *presence* only. A retrieve()
        # with the wrong arguments and return type still passes isinstance.
        # Signature conformance is mypy's job, enforced statically.
        class WrongShape:
            source_system = "not-an-enum"

            def retrieve(self, wrong_arg: int, extra: str) -> str:
                return "a conclusion, not evidence"

        assert isinstance(WrongShape(), EvidenceSource)

    def test_base_class_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            BaseEvidenceSource()  # type: ignore[abstract]


class TestRetrievalBehaviour:
    def test_returns_records(self, evidence_request: EvidenceRequest) -> None:
        source = FakeSource([_record("EV-1"), _record("EV-2")])
        assert [r.id for r in source.retrieve(evidence_request)] == ["EV-1", "EV-2"]

    def test_no_matches_returns_empty_and_does_not_raise(
        self, evidence_request: EvidenceRequest
    ) -> None:
        # Finding nothing is a legitimate answer. A caller must be able to tell
        # "none" apart from "failed" — a silent gap only becomes visible that way.
        assert FakeSource([]).retrieve(evidence_request) == ()

    def test_max_records_is_enforced(self, user: UserContext) -> None:
        source = FakeSource([_record(f"EV-{i}") for i in range(10)])
        request = EvidenceRequest(query="q", requested_by=user, max_records=3)
        assert len(source.retrieve(request)) == 3

    def test_max_records_must_be_positive(self, user: UserContext) -> None:
        with pytest.raises(ValueError):
            EvidenceRequest(query="q", requested_by=user, max_records=0)

    def test_source_filter_skips_unrequested_systems(self, user: UserContext) -> None:
        source = FakeSource([_record("EV-1")])
        request = EvidenceRequest(query="q", requested_by=user, source_systems=(SourceSystem.JIRA,))
        assert source.retrieve(request) == ()
        assert source.calls == 0  # not merely filtered afterwards — never queried

    def test_matching_source_filter_permits_retrieval(self, user: UserContext) -> None:
        source = FakeSource([_record("EV-1")])
        request = EvidenceRequest(
            query="q", requested_by=user, source_systems=(SourceSystem.LOCAL_FILE,)
        )
        assert len(source.retrieve(request)) == 1


class TestContractInvariants:
    def test_duplicate_ids_are_rejected(self, evidence_request: EvidenceRequest) -> None:
        # Two records sharing an id would make every citation to it ambiguous.
        source = FakeSource([_record("EV-1"), _record("EV-1")])
        with pytest.raises(EvidenceSourceError, match="duplicate evidence id"):
            source.retrieve(evidence_request)

    def test_mislabelled_source_system_is_rejected(self, evidence_request: EvidenceRequest) -> None:
        source = FakeSource([_record("EV-1", system=SourceSystem.JIRA)])
        with pytest.raises(EvidenceSourceError, match="expected"):
            source.retrieve(evidence_request)


class TestBoundary:
    def test_a_source_can_only_return_evidence(self, evidence_request: EvidenceRequest) -> None:
        # Connectors retrieve; they do not interpret. The return type is the
        # enforcement: there is no channel for a conclusion, ranking, or judgment.
        results = FakeSource([_record("EV-1")]).retrieve(evidence_request)
        assert all(isinstance(r, EvidenceRecord) for r in results)
        assert not hasattr(results[0], "recommendation")
        assert not hasattr(results[0], "support_level")
