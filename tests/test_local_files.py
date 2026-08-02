"""LocalFileEvidenceSource: the one connector the prototype implements.

Everything here writes real files to tmp_path. A connector that passes against
mocks and fails against a directory is worthless.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from decision_lens.connectors import EvidenceSourceError, LocalFileEvidenceSource
from decision_lens.models import (
    EvidenceRequest,
    EvidenceType,
    SourceSystem,
    UserContext,
)

STAMP = datetime(2026, 8, 2, 9, 0, 0)


def make_source(root: Path, **kwargs: Any) -> LocalFileEvidenceSource:
    """Build a source with a fixed timestamp so records are reproducible."""
    return LocalFileEvidenceSource(root, retrieved_at=STAMP, **kwargs)


@pytest.fixture
def req(user: UserContext) -> EvidenceRequest:
    # Empty query: retrieve everything. Narrowing is tested separately.
    return EvidenceRequest(query="", requested_by=user)


class TestMarkdownAndText:
    def test_markdown_becomes_one_record_with_section_excerpts(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "technical_constraints.md").write_text(
            "# Constraints\n\n## Driver app\nCannot change before Q3.\n\n"
            "## Address service\nRate limited to 50 rps.\n",
            encoding="utf-8",
        )
        records = make_source(tmp_path).retrieve(req)
        assert len(records) == 1
        record = records[0]
        assert record.title == "technical constraints"
        assert record.source_system is SourceSystem.LOCAL_FILE
        assert record.source_id == "technical_constraints.md"
        locators = [e.locator for e in record.excerpts]
        assert "§Constraints > Driver app" in locators
        assert "§Constraints > Address service" in locators
        # Excerpts are verbatim, so citations resolve against the record.
        assert all(record.contains(e.text) for e in record.excerpts)

    def test_heading_locators_carry_the_full_path(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "doc.md").write_text(
            "# Top\nIntro text.\n\n## Middle\nMiddle text.\n\n### Deep\nDeep text.\n",
            encoding="utf-8",
        )
        record = make_source(tmp_path).retrieve(req)[0]
        assert [e.locator for e in record.excerpts] == [
            "§Top",
            "§Top > Middle",
            "§Top > Middle > Deep",
        ]

    def test_repeated_heading_paths_get_distinguishable_locators(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        # An ambiguous locator sends a reader to the wrong passage, which is
        # worse than no locator at all.
        (tmp_path / "doc.md").write_text(
            "## Risks\nFirst set of risks.\n\n## Risks\nSecond set of risks.\n",
            encoding="utf-8",
        )
        record = make_source(tmp_path).retrieve(req)[0]
        locators = [e.locator for e in record.excerpts]
        assert locators == ["§Risks", "§Risks (2)"]
        assert len(set(locators)) == len(locators)

    def test_sibling_headings_do_not_nest(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / "doc.md").write_text(
            "## A\nText A.\n\n## B\nText B.\n",
            encoding="utf-8",
        )
        record = make_source(tmp_path).retrieve(req)[0]
        assert [e.locator for e in record.excerpts] == ["§A", "§B"]

    def test_plain_text_becomes_one_record_without_excerpts(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "notes.txt").write_text("Exceptions rose in June.", encoding="utf-8")
        records = make_source(tmp_path).retrieve(req)
        assert len(records) == 1
        assert records[0].excerpts == ()
        assert records[0].content == "Exceptions rose in June."

    def test_nested_directories_are_searched(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "deep.md").write_text("# T\nBody text.", encoding="utf-8")
        records = make_source(tmp_path).retrieve(req)
        assert records[0].source_id == "sub/deep.md"


class TestCsv:
    def test_each_row_becomes_a_citable_record(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / "support_ticket_summaries.csv").write_text(
            "ticket_id,category,summary\n"
            "T-1,address_error,Missing apartment number\n"
            "T-2,access_issue,Gate code not provided\n"
            "T-3,address_error,Street name misspelled\n",
            encoding="utf-8",
        )
        records = make_source(tmp_path).retrieve(req)
        assert len(records) == 3
        assert [r.title for r in records] == [
            "support ticket summaries row 1",
            "support ticket summaries row 2",
            "support ticket summaries row 3",
        ]
        assert "Gate code not provided" in records[1].content
        assert records[1].contains("Gate code not provided")

    def test_row_content_is_quotable_field_by_field(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "t.csv").write_text("id,summary\nT-1,Address missing\n", encoding="utf-8")
        record = make_source(tmp_path).retrieve(req)[0]
        assert record.content == "id: T-1\nsummary: Address missing"

    def test_blank_rows_are_dropped(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / "t.csv").write_text(
            "id,summary\nT-1,Real\n,\nT-2,Also real\n", encoding="utf-8"
        )
        records = make_source(tmp_path).retrieve(req)
        assert len(records) == 2

    def test_headerless_csv_is_skipped_with_a_reason(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "broken.csv").write_text("\n\n", encoding="utf-8")
        source = make_source(tmp_path)
        assert source.retrieve(req) == ()
        assert source.diagnostics.had_failures


class TestJson:
    def test_array_becomes_one_record_per_element(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "prior_experiments.json").write_text(
            json.dumps(
                [{"name": "notifications", "lift": 0.02}, {"name": "address", "lift": 0.11}]
            ),
            encoding="utf-8",
        )
        records = make_source(tmp_path).retrieve(req)
        assert len(records) == 2
        assert [r.source_reference.split("#")[-1] for r in records] == ["[0]", "[1]"]
        assert "notifications" in records[0].content

    def test_object_becomes_a_single_record(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / "objectives.json").write_text(
            json.dumps({"goal": "first-attempt success"}), encoding="utf-8"
        )
        records = make_source(tmp_path).retrieve(req)
        assert len(records) == 1
        assert "first-attempt success" in records[0].content

    def test_invalid_json_is_skipped_not_fatal(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / "good.md").write_text("# Fine\nUsable content.", encoding="utf-8")
        (tmp_path / "bad.json").write_text("{not valid json,,,", encoding="utf-8")
        source = make_source(tmp_path)
        records = source.retrieve(req)
        # One bad file must not cost the whole retrieval.
        assert len(records) == 1
        assert records[0].source_id == "good.md"
        reasons = [s.reason for s in source.diagnostics.skipped]
        assert any("invalid JSON" in r for r in reasons)


class TestFailureHandling:
    def test_missing_directory_raises(self, tmp_path: Path, req: EvidenceRequest) -> None:
        with pytest.raises(EvidenceSourceError, match="does not exist"):
            make_source(tmp_path / "nope").retrieve(req)

    def test_file_instead_of_directory_raises(self, tmp_path: Path, req: EvidenceRequest) -> None:
        target = tmp_path / "a.md"
        target.write_text("x", encoding="utf-8")
        with pytest.raises(EvidenceSourceError, match="not a directory"):
            make_source(target).retrieve(req)

    def test_empty_directory_returns_nothing_without_raising(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        assert make_source(tmp_path).retrieve(req) == ()

    def test_unsupported_types_are_skipped_and_recorded(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "report.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "sheet.xlsx").write_bytes(b"PK fake")
        (tmp_path / "ok.md").write_text("# T\nContent.", encoding="utf-8")
        source = make_source(tmp_path)
        records = source.retrieve(req)
        assert len(records) == 1
        skipped = {s.path for s in source.diagnostics.skipped}
        assert skipped == {"report.pdf", "sheet.xlsx"}

    def test_empty_file_is_skipped_with_a_reason(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "blank.md").write_text("   \n\n", encoding="utf-8")
        source = make_source(tmp_path)
        assert source.retrieve(req) == ()
        assert source.diagnostics.skipped[0].reason == "file is empty"

    def test_bad_encoding_degrades_rather_than_losing_the_file(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        # A stray byte should cost one character, not the whole document.
        (tmp_path / "legacy.txt").write_bytes(b"Caf\xe9 delivery notes: 40% address errors.")
        records = make_source(tmp_path).retrieve(req)
        assert len(records) == 1
        assert "40% address errors" in records[0].content

    def test_hidden_files_are_ignored(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / ".DS_Store").write_text("junk", encoding="utf-8")
        (tmp_path / "real.md").write_text("# T\nContent.", encoding="utf-8")
        assert len(make_source(tmp_path).retrieve(req)) == 1


class TestIdentifiers:
    def test_ids_are_stable_across_runs(self, tmp_path: Path, req: EvidenceRequest) -> None:
        # The property a citation depends on: yesterday's brief still resolves.
        (tmp_path / "a.md").write_text("# T\nStable content.", encoding="utf-8")
        first = make_source(tmp_path).retrieve(req)
        second = make_source(tmp_path).retrieve(req)
        assert [r.id for r in first] == [r.id for r in second]

    def test_adding_a_file_does_not_renumber_the_others(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "b.md").write_text("# B\nSecond.", encoding="utf-8")
        before = {r.source_id: r.id for r in make_source(tmp_path).retrieve(req)}
        (tmp_path / "a.md").write_text("# A\nFirst, sorts earlier.", encoding="utf-8")
        after = {r.source_id: r.id for r in make_source(tmp_path).retrieve(req)}
        assert after["b.md"] == before["b.md"]

    def test_editing_content_changes_the_id(self, tmp_path: Path, req: EvidenceRequest) -> None:
        # Correct behaviour: the cited text no longer exists, so the citation
        # should stop resolving rather than silently point at different words.
        path = tmp_path / "a.md"
        path.write_text("# T\nOriginal.", encoding="utf-8")
        before = make_source(tmp_path).retrieve(req)[0].id
        path.write_text("# T\nRewritten.", encoding="utf-8")
        assert make_source(tmp_path).retrieve(req)[0].id != before

    def test_csv_rows_get_distinct_ids(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / "t.csv").write_text("id,note\n1,same\n2,same\n", encoding="utf-8")
        ids = [r.id for r in make_source(tmp_path).retrieve(req)]
        assert len(set(ids)) == 2

    def test_identical_files_at_different_paths_both_survive(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        # Two sources saying the same thing is corroboration, not duplication.
        (tmp_path / "one.md").write_text("# T\nSame words.", encoding="utf-8")
        (tmp_path / "two.md").write_text("# T\nSame words.", encoding="utf-8")
        records = make_source(tmp_path).retrieve(req)
        assert len(records) == 2
        assert records[0].id != records[1].id


class TestManifestMetadata:
    def _write_case(self, tmp_path: Path) -> None:
        (tmp_path / "customer_feedback.csv").write_text(
            "id,comment\nC-1,Driver could not find the door\n", encoding="utf-8"
        )
        (tmp_path / "case_manifest.json").write_text(
            json.dumps(
                {
                    "files": {
                        "customer_feedback.csv": {
                            "evidence_type": "qualitative_research",
                            "created_at": "2026-03-01",
                            "updated_at": "2026-05-15",
                            "owner": "research-team",
                            "product_area": "delivery",
                            "permission_scope": "pm-delivery",
                            "labels": ["synthetic", "voice-of-customer"],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def test_manifest_metadata_is_preserved_on_records(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        self._write_case(tmp_path)
        record = make_source(tmp_path).retrieve(req)[0]
        assert record.evidence_type is EvidenceType.QUALITATIVE_RESEARCH
        assert record.created_at == date(2026, 3, 1)
        assert record.updated_at == date(2026, 5, 15)
        assert record.owner == "research-team"
        assert record.product_area == "delivery"
        assert record.permission_scope == "pm-delivery"
        assert set(record.labels) == {"synthetic", "voice-of-customer"}
        assert record.retrieved_at == STAMP

    def test_manifest_is_not_returned_as_evidence(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        self._write_case(tmp_path)
        records = make_source(tmp_path).retrieve(req)
        assert all(r.source_id != "case_manifest.json" for r in records)

    def test_unlisted_files_fall_back_to_the_default_type(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "loose.md").write_text("# T\nNo manifest entry.", encoding="utf-8")
        record = make_source(tmp_path, default_evidence_type=EvidenceType.PRIOR_DECISION).retrieve(
            req
        )[0]
        assert record.evidence_type is EvidenceType.PRIOR_DECISION

    def test_invalid_manifest_json_raises(self, tmp_path: Path, req: EvidenceRequest) -> None:
        # Unlike a broken evidence file, a broken manifest silently mislabels
        # everything, so it fails loudly.
        (tmp_path / "a.md").write_text("# T\nContent.", encoding="utf-8")
        (tmp_path / "case_manifest.json").write_text("{oops", encoding="utf-8")
        with pytest.raises(EvidenceSourceError, match="not valid JSON"):
            make_source(tmp_path).retrieve(req)

    def test_unknown_evidence_type_is_skipped_with_a_reason(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "a.md").write_text("# T\nContent.", encoding="utf-8")
        (tmp_path / "case_manifest.json").write_text(
            json.dumps({"files": {"a.md": {"evidence_type": "vibes"}}}), encoding="utf-8"
        )
        source = make_source(tmp_path)
        assert source.retrieve(req) == ()
        assert "unknown evidence_type" in source.diagnostics.skipped[0].reason

    def test_invalid_date_is_skipped_with_a_reason(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "a.md").write_text("# T\nContent.", encoding="utf-8")
        (tmp_path / "case_manifest.json").write_text(
            json.dumps({"files": {"a.md": {"created_at": "last Tuesday"}}}), encoding="utf-8"
        )
        source = make_source(tmp_path)
        assert source.retrieve(req) == ()
        assert "invalid date" in source.diagnostics.skipped[0].reason


class TestCoarseSearch:
    def _write(self, tmp_path: Path) -> None:
        (tmp_path / "address.md").write_text(
            "# Address\nAddress errors dominate.", encoding="utf-8"
        )
        (tmp_path / "weather.md").write_text("# Weather\nStorms delayed routes.", encoding="utf-8")

    def test_query_narrows_and_the_drop_is_reported(
        self, tmp_path: Path, user: UserContext
    ) -> None:
        # Filtering must never be invisible: a PM has to know evidence was
        # removed before the analysis ever saw it.
        self._write(tmp_path)
        source = make_source(tmp_path)
        records = source.retrieve(EvidenceRequest(query="address errors", requested_by=user))
        assert len(records) == 1
        assert source.diagnostics.records_built == 2
        assert source.diagnostics.records_filtered_out == 1

    def test_empty_query_returns_everything(self, tmp_path: Path, req: EvidenceRequest) -> None:
        self._write(tmp_path)
        source = make_source(tmp_path)
        assert len(source.retrieve(req)) == 2
        assert source.diagnostics.records_filtered_out == 0

    def test_label_filter_applies(self, tmp_path: Path, user: UserContext) -> None:
        (tmp_path / "a.md").write_text("# A\nContent.", encoding="utf-8")
        (tmp_path / "case_manifest.json").write_text(
            json.dumps({"files": {"a.md": {"labels": ["governance"]}}}), encoding="utf-8"
        )
        source = make_source(tmp_path)
        hit = EvidenceRequest(query="", requested_by=user, labels=("governance",))
        miss = EvidenceRequest(query="", requested_by=user, labels=("finance",))
        assert len(source.retrieve(hit)) == 1
        assert source.retrieve(miss) == ()

    def test_max_records_is_enforced_by_the_base_class(
        self, tmp_path: Path, user: UserContext
    ) -> None:
        (tmp_path / "t.csv").write_text(
            "id,note\n" + "".join(f"{i},note {i}\n" for i in range(20)), encoding="utf-8"
        )
        source = make_source(tmp_path)
        capped = EvidenceRequest(query="", requested_by=user, max_records=5)
        assert len(source.retrieve(capped)) == 5


class TestEdgeCases:
    def test_unreadable_file_is_skipped_not_fatal(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "ok.md").write_text("# T\nReadable.", encoding="utf-8")
        locked = tmp_path / "locked.md"
        locked.write_text("# T\nSecret.", encoding="utf-8")
        locked.chmod(0o000)
        try:
            source = make_source(tmp_path)
            records = source.retrieve(req)
        finally:
            locked.chmod(0o644)
        if not records:
            pytest.skip("running as a user that can read mode-000 files")
        assert [r.source_id for r in records] == ["ok.md"]
        assert any("unreadable" in s.reason for s in source.diagnostics.skipped)

    def test_manifest_with_a_non_object_files_entry_raises(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "a.md").write_text("# T\nContent.", encoding="utf-8")
        (tmp_path / "case_manifest.json").write_text(
            json.dumps({"files": ["not", "a", "mapping"]}), encoding="utf-8"
        )
        with pytest.raises(EvidenceSourceError, match="map file paths"):
            make_source(tmp_path).retrieve(req)

    def test_product_area_filter_applies(self, tmp_path: Path, user: UserContext) -> None:
        (tmp_path / "a.md").write_text("# A\nDelivery content.", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\nPayments content.", encoding="utf-8")
        (tmp_path / "case_manifest.json").write_text(
            json.dumps(
                {
                    "files": {
                        "a.md": {"product_area": "delivery"},
                        "b.md": {"product_area": "payments"},
                    }
                }
            ),
            encoding="utf-8",
        )
        source = make_source(tmp_path)
        scoped = EvidenceRequest(query="", requested_by=user, product_area="Delivery")
        records = source.retrieve(scoped)
        assert [r.source_id for r in records] == ["a.md"]  # match is case-insensitive

    def test_duplicate_record_ids_are_skipped_rather_than_fatal(
        self, tmp_path: Path, req: EvidenceRequest, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Not reachable from the filesystem, since an id is a function of path,
        # locator and content. Pinned anyway: the base class treats a duplicate id
        # as fatal, and this connector must degrade instead.
        (tmp_path / "a.md").write_text("# T\nContent.", encoding="utf-8")
        source = make_source(tmp_path)
        original = source._build_records

        def twice(*args: Any, **kwargs: Any) -> Any:
            built = list(original(*args, **kwargs))
            return iter(built + built)

        monkeypatch.setattr(source, "_build_records", twice)
        records = source.retrieve(req)
        assert len(records) == 1
        assert any("duplicate" in s.reason for s in source.diagnostics.skipped)


class TestDiagnostics:
    def test_counts_describe_what_happened(self, tmp_path: Path, req: EvidenceRequest) -> None:
        (tmp_path / "a.md").write_text("# A\nOne.", encoding="utf-8")
        (tmp_path / "t.csv").write_text("id,x\n1,a\n2,b\n", encoding="utf-8")
        (tmp_path / "skip.pdf").write_bytes(b"%PDF")
        source = make_source(tmp_path)
        source.retrieve(req)
        d = source.diagnostics
        assert d.files_seen == 3
        assert d.files_read == 2
        assert d.records_built == 3  # 1 markdown + 2 csv rows
        assert len(d.skipped) == 1

    def test_diagnostics_reset_between_retrievals(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        (tmp_path / "bad.json").write_text("{oops", encoding="utf-8")
        source = make_source(tmp_path)
        source.retrieve(req)
        assert source.diagnostics.had_failures
        (tmp_path / "bad.json").unlink()
        (tmp_path / "good.md").write_text("# T\nFine.", encoding="utf-8")
        source.retrieve(req)
        assert not source.diagnostics.had_failures


class TestBoundary:
    def test_the_connector_returns_evidence_only(
        self, tmp_path: Path, req: EvidenceRequest
    ) -> None:
        # Retrieval assigns no support level and reaches no conclusion.
        (tmp_path / "a.md").write_text("# T\nContent.", encoding="utf-8")
        record = make_source(tmp_path).retrieve(req)[0]
        assert not hasattr(record, "support_level")
        assert not hasattr(record, "recommendation")
        assert not hasattr(record, "relevance")
