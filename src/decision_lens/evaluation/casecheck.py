"""Checking that a case and its answer key describe the same corpus.

An answer key drifts from its evidence silently. Someone edits a line in a CSV,
the ground truth still quotes the old wording, and the contradiction it claims to
describe no longer exists — but the file still parses, the harness still runs,
and the recall figure it produces is measured against a conflict that is not
there. Nothing in the output looks wrong.

So every quotation in the key is checked against the corpus before any case is
allowed to score — against the *evidence records*, which is what the system
actually reads, rather than the file bytes. A CSV row reaches the agent as
rendered fields, never as the comma-separated line, so a key quoting the raw file
would be quoting text nothing ever sees. This is the same rule the product lives
under, turned on the thing doing the judging: a claim about the evidence has to
be findable in the evidence.

The checks are deliberately mechanical. Whether a planted contradiction is
*interesting* is a judgment nobody can automate; whether both sides of it are
actually present in the files is not, and that is the failure that survives
review because it looks like nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from decision_lens.connectors.local_files import LocalFileEvidenceSource
from decision_lens.evaluation.ground_truth import GroundTruth
from decision_lens.models import EvidenceRequest, UserContext
from decision_lens.quoting import normalise

__all__ = ["CaseReport", "check_case", "check_all_cases"]

#: Words that make a line a disclaimer rather than an assertion. Checked per
#: line, not per file: every case file already carries a synthetic notice, so a
#: file-level rule is satisfied by that notice and can never fire again — which
#: is what it did, silently, until a deliberately planted violation walked past
#: it. A check that cannot fail is not a check.
_DISCLAIMER_WORDS = ("synthetic", "fictional", "no real", "invented")


@dataclass
class CaseReport:
    """What is wrong with one case, or nothing."""

    case_id: str
    directory: Path
    problems: list[str] = field(default_factory=list)
    span_count: int = 0
    record_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems

    def describe(self) -> str:
        head = f"{self.case_id}: {self.record_count} records, {self.span_count} spans"
        if self.ok:
            return f"  OK    {head}"
        lines = [f"  FAIL  {head}"]
        lines += [f"          - {p}" for p in self.problems]
        return "\n".join(lines)


def _find_span(needle: str, haystack: str) -> bool:
    """Whether the quotation is present, allowing only typography to differ.

    The same latitude the product gets when it cites evidence. A ground truth
    written by hand against a CSV picks up a stray space or a curly quote in
    exactly the way a model does, and failing the case for it would mean hunting
    invisible characters rather than checking the corpus.
    """
    if needle in haystack:
        return True
    folded_needle, _ = normalise(needle)
    folded_hay, _ = normalise(haystack)
    return folded_needle.strip() in folded_hay


def check_case(directory: Path, ground_truth_path: Path) -> CaseReport:
    """Verify one case against its answer key. Never raises; collects problems."""
    report = CaseReport(case_id=directory.name, directory=directory)

    if not directory.is_dir():
        report.problems.append(f"case directory missing: {directory}")
        return report
    if not ground_truth_path.is_file():
        report.problems.append(f"ground truth missing: {ground_truth_path}")
        return report

    try:
        truth = GroundTruth.model_validate_json(ground_truth_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is a case problem
        report.problems.append(f"ground truth does not parse: {exc}")
        return report

    report.case_id = truth.case_id
    if truth.case_id != directory.name:
        report.problems.append(
            f"case_id {truth.case_id!r} does not match directory {directory.name!r}"
        )

    try:
        source = LocalFileEvidenceSource(directory)
        records = tuple(source.retrieve(EvidenceRequest(requested_by=UserContext(user_id="eval"))))
    except Exception as exc:  # noqa: BLE001 - a corpus that will not load cannot be scored
        report.problems.append(f"corpus does not load: {exc}")
        return report

    report.record_count = len(records)
    if not records:
        report.problems.append("corpus loaded but produced no evidence records")

    # Spans are matched against the *records*, not the file bytes. A CSV row
    # reaches the system as "period: 2026-Q2\nmetric: ...", never as the comma
    # separated line on disk, so an answer key quoting the raw file would be
    # quoting text the system is never shown. Checking the rendered form is what
    # makes the key describe the same corpus the agent reads.
    contents: dict[str, str] = {}
    for record in records:
        contents.setdefault(record.source_id, "")
        contents[record.source_id] += record.content + "\n\n"
    for name in sorted(truth.sources()):
        if name not in contents:
            report.problems.append(f"answer key cites {name}, which produced no evidence records")

    spans = truth.spans()
    report.span_count = len(spans)
    if not spans:
        report.problems.append("answer key quotes the corpus nowhere; nothing anchors it")

    for owner, ref in spans:
        body = contents.get(ref.source)
        if body is None:
            continue  # already reported as a missing file
        if not _find_span(ref.span, body):
            report.problems.append(
                f"{owner}: quoted text not found in {ref.source}: {ref.span[:70]!r}"
            )

    _check_notices(directory, truth, report)
    _check_coverage(directory, truth, report)
    return report


def _check_notices(directory: Path, truth: GroundTruth, report: CaseReport) -> None:
    """Synthetic labelling, and no unqualified mention of the real company."""
    if "synthetic" not in truth.notice.lower():
        report.problems.append("ground-truth notice does not say the case is synthetic")

    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            lowered = line.lower()
            if "walmart" not in lowered:
                continue
            if not any(word in lowered for word in _DISCLAIMER_WORDS):
                report.problems.append(
                    f"{path.name}:{number} names Walmart outside a disclaimer: "
                    f"{line.strip()[:70]!r}. No case may imply real internal data."
                )


def _check_coverage(directory: Path, truth: GroundTruth, report: CaseReport) -> None:
    """Every evidence file should be anchored by at least one entry.

    A file nothing in the answer key refers to is either decoration — in which
    case it should be declared as irrelevant_evidence, so the system is scored
    for ignoring it — or an oversight. Both are worth surfacing; silence about a
    file is the one reading that helps nobody.
    """
    on_disk = {
        p.name
        for p in directory.iterdir()
        if p.is_file() and p.name != "case_manifest.json" and not p.name.startswith(".")
    }
    unanchored = sorted(on_disk - truth.sources())
    if unanchored:
        report.problems.append(
            "evidence files no answer-key entry refers to (declare them as "
            f"irrelevant_evidence if deliberate): {', '.join(unanchored)}"
        )


def check_all_cases(data_root: Path, truth_root: Path) -> tuple[CaseReport, ...]:
    """Check every case directory under ``data_root``."""
    reports = []
    for directory in sorted(p for p in data_root.iterdir() if p.is_dir()):
        reports.append(check_case(directory, truth_root / f"{directory.name}.json"))
    return tuple(reports)
