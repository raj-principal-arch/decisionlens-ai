"""Running both arms over every case, and turning that into results.

The comparison this repository exists to make is one call against a controlled
workflow, on identical evidence, judged the same way. This module is the part
that actually makes it, and its main job is to stay boring: load a case, run
each arm, score each brief, write everything down including the failures.

Two design choices are worth stating because they are what make the output
trustworthy rather than merely present.

**A failed arm is a result, not an omission.** If DecisionLens fails a stage or
the baseline returns unparseable output, that case still appears in the results
with the failure recorded. Dropping it would quietly improve whichever arm broke
more often, which is the opposite of measurement.

**The evidence is retrieved once per case and handed to both arms.** Not
retrieved twice — the record ids must be identical or the two briefs cannot be
scored against the same answer key, and a difference in retrieval would be
attributed to the workflow.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from decision_lens.baseline import BaselineError, StrongBaseline
from decision_lens.case import load_case
from decision_lens.evaluation.ground_truth import GroundTruth
from decision_lens.evaluation.metrics import CaseScore, score_brief
from decision_lens.llm import ModelProvider
from decision_lens.models import (
    DecisionBrief,
    EvidenceRecord,
    EvidenceRequest,
    UserContext,
)
from decision_lens.orchestrator import DecisionLens, DecisionLensError
from decision_lens.report import to_markdown

__all__ = ["ArmResult", "CaseResult", "EvaluationRun", "evaluate_case", "evaluate_all"]

#: A live stage over a large corpus is slow; the cached path is instant. Sized
#: for the live case so a real run is not converted into a timeout.
EVAL_TIMEOUT_SECONDS = 1_900.0

DECISIONLENS = "decisionlens"
BASELINE = "baseline"


@dataclass
class ArmResult:
    """One arm's attempt at one case."""

    arm: str
    brief: DecisionBrief | None = None
    markdown: str = ""
    score: CaseScore | None = None
    error: str = ""
    seconds: float = 0.0

    @property
    def produced_a_brief(self) -> bool:
        return self.brief is not None


@dataclass
class CaseResult:
    case_id: str
    records: int
    arms: dict[str, ArmResult] = field(default_factory=dict)
    error: str = ""

    def arm(self, name: str) -> ArmResult | None:
        return self.arms.get(name)


@dataclass
class EvaluationRun:
    """Every case, both arms, plus what the run itself could not do."""

    cases: list[CaseResult] = field(default_factory=list)
    started_at: datetime | None = None
    provider_id: str = ""
    model_id: str = ""

    def scored(self, arm: str) -> list[CaseScore]:
        out = []
        for case in self.cases:
            result = case.arm(arm)
            if result is not None and result.score is not None:
                out.append(result.score)
        return out


def _retrieve(sources: Sequence[object], case_id: str) -> tuple[EvidenceRecord, ...]:
    request = EvidenceRequest(requested_by=UserContext(user_id="evaluation"))
    records: list[EvidenceRecord] = []
    for source in sources:
        retrieve = getattr(source, "retrieve", None)
        if retrieve is None:  # pragma: no cover - every source implements the protocol
            continue
        records.extend(retrieve(request))
    return tuple(records)


def evaluate_case(
    directory: Path,
    truth_path: Path,
    provider: ModelProvider,
    *,
    clock: datetime | None = None,
    arms: Sequence[str] = (DECISIONLENS, BASELINE),
) -> CaseResult:
    """Run the requested arms over one case and score whatever comes back."""
    try:
        truth = GroundTruth.model_validate_json(truth_path.read_text(encoding="utf-8"))
        loaded = load_case(directory)
    except Exception as exc:  # noqa: BLE001 - an unloadable case is a reportable result
        return CaseResult(case_id=directory.name, records=0, error=f"{type(exc).__name__}: {exc}")

    records = _retrieve(loaded.sources, loaded.case_id)
    result = CaseResult(case_id=loaded.case_id, records=len(records))

    for arm in arms:
        started = time.perf_counter()
        attempt = ArmResult(arm=arm)
        try:
            if arm == DECISIONLENS:
                attempt.brief = DecisionLens(
                    provider,
                    loaded.sources,
                    as_of=loaded.as_of,
                    clock=clock,
                    timeout_seconds=EVAL_TIMEOUT_SECONDS,
                ).run(loaded.request)
            else:
                attempt.brief = StrongBaseline(
                    provider, clock=clock, timeout_seconds=EVAL_TIMEOUT_SECONDS
                ).run(loaded.request, records)
        except (DecisionLensError, BaselineError) as exc:
            attempt.error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 - never let one arm end the run
            attempt.error = f"unexpected {type(exc).__name__}: {exc}"
        attempt.seconds = time.perf_counter() - started

        if attempt.brief is not None:
            attempt.markdown = to_markdown(attempt.brief)
            attempt.score = score_brief(attempt.brief, truth, records)
            attempt.score.arm = arm
        result.arms[arm] = attempt

    return result


def evaluate_all(
    data_root: Path,
    truth_root: Path,
    provider: ModelProvider,
    *,
    clock: datetime | None = None,
    arms: Sequence[str] = (DECISIONLENS, BASELINE),
    only: Sequence[str] = (),
    progress: object = None,
) -> EvaluationRun:
    """Every case under ``data_root`` that has an answer key."""
    run = EvaluationRun(
        provider_id=provider.provider_id,
        model_id=provider.model_id,
    )
    directories = sorted(p for p in data_root.iterdir() if p.is_dir())
    if only:
        wanted = set(only)
        directories = [d for d in directories if d.name in wanted]

    for directory in directories:
        truth_path = truth_root / f"{directory.name}.json"
        if not truth_path.is_file():
            continue
        if callable(progress):
            progress(f"  {directory.name} …")
        result = evaluate_case(directory, truth_path, provider, clock=clock, arms=arms)
        run.cases.append(result)
        if callable(progress):
            progress(f"  {directory.name} — {_one_line(result)}")
    return run


def _one_line(result: CaseResult) -> str:
    if result.error:
        return f"failed: {result.error[:70]}"
    parts = []
    for arm, attempt in result.arms.items():
        if attempt.error:
            parts.append(f"{arm}: failed")
        elif attempt.score is not None:
            recall = attempt.score.contradictions.recall
            shown = "n/a" if recall is None else f"{recall:.0%}"
            parts.append(f"{arm}: contradictions {shown}, {attempt.seconds:.0f}s")
    return " | ".join(parts)
