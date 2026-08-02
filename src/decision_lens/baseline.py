"""The strong single-call baseline.

One model call, given the same question, the same evidence, the same output schema
and a deliberately strong prompt. What it does not get is the controlled workflow:
no separate stages, no challenger, no deterministic provenance check.

Three decisions that keep the comparison honest:

*   **The model returns analysis, never evidence.** `DecisionLens` assembles the
    brief around the real records the connector retrieved. If the model could emit
    its own `EvidenceRecord`s it could invent evidence and then cite it, and
    citation checking would measure nothing.
*   **The baseline is not validated.** Hallucinated citations are left in place.
    Stripping them here would be applying DecisionLens's provenance stage to the
    baseline, which is the very thing under test. The baseline must be free to
    fail the unsupported-claim metric.
*   **One repair attempt is allowed.** A single-call baseline that dies on one
    formatting slip is weaker than a real one, and a strawman proves nothing. The
    repair is recorded as its own trace stage so the cost is visible.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from decision_lens.llm import (
    ModelError,
    ModelOutputError,
    ModelProvider,
    ModelRequest,
    parse_structured,
)
from decision_lens.models import (
    Alternative,
    Claim,
    Contradiction,
    DecisionBrief,
    DecisionRequest,
    EvidenceRecord,
    MissingEvidence,
    PriorityException,
    Recommendation,
    RunStage,
    RunTrace,
)
from decision_lens.prompts.baseline import BASELINE_REPAIR_V1, BASELINE_V1
from decision_lens.rendering import render_criteria, render_evidence

#: Generous by design. The baseline does in one call what DecisionLens spreads
#: across many, so holding it to a per-stage timeout would handicap it.
BASELINE_TIMEOUT_SECONDS = 180.0

SKILL = "baseline"


class BaselineError(RuntimeError):
    """The baseline could not produce a brief.

    Carries the partial run trace so a failed run is still reportable: an
    evaluation that silently drops failures overstates the results it keeps.
    """

    def __init__(self, message: str, trace: RunTrace) -> None:
        super().__init__(message)
        self.trace = trace


class BaselineOutput(BaseModel):
    """What the model is asked to return.

    Composed from the real domain models rather than parallel copies, so the
    baseline and DecisionLens are held to a literally identical output schema and
    the same field validators.
    """

    # Lenient on top-level extras: failing the baseline because it added a helpful
    # field would handicap it, and the comparison is about workflow, not schema
    # pedantry. The nested domain models remain strict, so structural parity with
    # DecisionLens output is preserved where it matters.
    model_config = ConfigDict(extra="ignore")

    claims: tuple[Claim, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    missing_evidence: tuple[MissingEvidence, ...] = ()
    priority_exceptions: tuple[PriorityException, ...] = ()
    alternatives: tuple[Alternative, ...] = ()
    recommendation: Recommendation


class StrongBaseline:
    """One well-prompted model call, for comparison against the controlled workflow.

    Args:
        provider: Any `ModelProvider`. Tests use mocks and the cached provider;
            nothing here reaches the network on its own.
        allow_repair: Whether one schema-repair retry is permitted.
        timeout_seconds: Per-call deadline, enforced by the provider base class.
        clock: Injected so a run is reproducible in tests.
    """

    def __init__(
        self,
        provider: ModelProvider,
        *,
        allow_repair: bool = True,
        timeout_seconds: float = BASELINE_TIMEOUT_SECONDS,
        clock: datetime | None = None,
    ) -> None:
        self.provider = provider
        self.allow_repair = allow_repair
        self.timeout_seconds = timeout_seconds
        self._clock = clock

    # -- prompt construction ------------------------------------------------ #

    @staticmethod
    def _schema_text() -> str:
        return json.dumps(BaselineOutput.model_json_schema(), separators=(",", ":"))

    def _first_request(
        self, request: DecisionRequest, evidence: Sequence[EvidenceRecord]
    ) -> ModelRequest:
        return ModelRequest(
            skill=SKILL,
            prompt_version=BASELINE_V1.version,
            prompt_fingerprint=BASELINE_V1.fingerprint,
            case_id=request.id,
            system=BASELINE_V1.system,
            user=BASELINE_V1.render(
                question=request.question,
                desired_outcome=request.desired_outcome or "(not stated)",
                criteria=render_criteria(request),
                evidence=render_evidence(evidence),
                schema=self._schema_text(),
            ),
            timeout_seconds=self.timeout_seconds,
        )

    def _repair_request(
        self,
        request: DecisionRequest,
        evidence: Sequence[EvidenceRecord],
        previous: str,
        error: str,
    ) -> ModelRequest:
        return ModelRequest(
            skill=f"{SKILL}-repair",
            prompt_version=BASELINE_REPAIR_V1.version,
            prompt_fingerprint=BASELINE_REPAIR_V1.fingerprint,
            case_id=request.id,
            system=BASELINE_REPAIR_V1.system,
            user=BASELINE_REPAIR_V1.render(
                original=self._first_request(request, evidence).user,
                schema=self._schema_text(),
                error=error,
                previous=previous,
            ),
            timeout_seconds=self.timeout_seconds,
        )

    # -- execution ---------------------------------------------------------- #

    def run(self, request: DecisionRequest, evidence: Sequence[EvidenceRecord]) -> DecisionBrief:
        """Produce a decision brief from one model call, plus at most one repair."""
        started = self._clock or datetime.now()
        stages: list[RunStage] = []

        output = self._attempt(
            self._first_request(request, evidence), "baseline", stages, request, evidence
        )

        trace = RunTrace(
            run_id=f"baseline-{request.id}",
            request_id=request.id,
            stages=tuple(stages),
            started_at=started,
            ended_at=self._clock or datetime.now(),
        )
        return self._assemble(request, evidence, output, trace, started)

    def _attempt(
        self,
        model_request: ModelRequest,
        stage_name: str,
        stages: list[RunStage],
        request: DecisionRequest,
        evidence: Sequence[EvidenceRecord],
    ) -> BaselineOutput:
        try:
            response = self.provider.complete(model_request)
        except ModelError as exc:
            stages.append(
                RunStage(
                    name=stage_name, prompt_version=model_request.prompt_version, error=str(exc)
                )
            )
            raise BaselineError(
                f"Baseline call failed at stage {stage_name!r}: {exc}",
                RunTrace(
                    run_id=f"baseline-{request.id}", request_id=request.id, stages=tuple(stages)
                ),
            ) from exc

        try:
            output = parse_structured(response, BaselineOutput)
        except ModelOutputError as exc:
            stages.append(response.to_stage(stage_name, error=str(exc)))
            if not self.allow_repair or stage_name.endswith("-repair"):
                raise BaselineError(
                    f"Baseline output did not match the schema and no repair attempt "
                    f"remains: {exc}",
                    RunTrace(
                        run_id=f"baseline-{request.id}", request_id=request.id, stages=tuple(stages)
                    ),
                ) from exc
            return self._attempt(
                self._repair_request(request, evidence, response.text, str(exc)),
                f"{stage_name}-repair",
                stages,
                request,
                evidence,
            )

        stages.append(response.to_stage(stage_name))
        return output

    # -- assembly ----------------------------------------------------------- #

    @staticmethod
    def _assemble(
        request: DecisionRequest,
        evidence: Sequence[EvidenceRecord],
        output: BaselineOutput,
        trace: RunTrace,
        generated_at: datetime,
    ) -> DecisionBrief:
        """Wrap the model's analysis around the real evidence.

        `validation_issues` is deliberately left empty. The baseline is the
        unvalidated arm of the comparison; running DecisionLens's provenance check
        over it here would erase the difference the evaluation exists to measure.
        """
        return DecisionBrief(
            id=f"BASELINE-{request.id}",
            request=request,
            generated_at=generated_at,
            evidence=tuple(evidence),
            claims=output.claims,
            contradictions=output.contradictions,
            missing_evidence=output.missing_evidence,
            priority_exceptions=output.priority_exceptions,
            alternatives=output.alternatives,
            recommendation=output.recommendation,
            validation_issues=(),
            run_trace=trace,
        )
