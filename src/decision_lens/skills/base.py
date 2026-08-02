"""The analysis-skill contract.

A skill interprets evidence that has already been retrieved. It never reaches a
data source, and it never calls another skill — the orchestrator sequences them.
That constraint is what keeps each step separately runnable and separately
testable, which is what makes the reasoning auditable rather than merely fluent.

Every skill is hybrid by design:

*   **Computed where computable.** Staleness is date arithmetic. Whether a
    citation resolves is string matching. Whether a set of alternatives contains
    a non-AI option is an enum check. Those are done in code, where they cannot
    be hallucinated and can be tested without a model at all.
*   **Model-judged where judgment is needed.** Which claims matter, how to read a
    stakeholder's confidence, what evidence is missing.

Each skill declares its own hard requirements through `violations()`. If the
model breaks one, the skill re-prompts once naming the broken rule, then fails.
It never fills the gap itself: DecisionLens authoring content and presenting it
as analysis is the fabrication this product exists to prevent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from decision_lens.llm import (
    ModelError,
    ModelOutputError,
    ModelProvider,
    ModelRequest,
    parse_structured,
)
from decision_lens.models import Citation, DecisionRequest, EvidenceRecord, RunStage
from decision_lens.prompts import Prompt

T = TypeVar("T", bound=BaseModel)

#: Per-skill deadline. Lower than the baseline's because each skill does one
#: narrow job, and a stage that hangs should not hold up the whole workflow.
SKILL_TIMEOUT_SECONDS = 90.0


class SkillError(RuntimeError):
    """A skill could not produce usable output.

    Carries whatever stages ran so a partial failure is still reportable. The
    orchestrator records the failed stage and continues; a brief missing one
    analysis is more useful than no brief, provided the gap is visible.
    """

    def __init__(self, message: str, stages: Sequence[RunStage] = ()) -> None:
        super().__init__(message)
        self.stages = tuple(stages)


class SkillViolation(SkillError):
    """The model broke a hard requirement twice, so the skill gave up."""


class SkillContext(BaseModel):
    """Everything a skill is allowed to see.

    There is no provider here and no way to fetch anything. A skill works from
    the evidence it was handed, which is what stops interpretation quietly
    becoming retrieval.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    request: DecisionRequest
    evidence: tuple[EvidenceRecord, ...]

    @property
    def case_id(self) -> str:
        return self.request.id

    def by_id(self) -> dict[str, EvidenceRecord]:
        return {e.id: e for e in self.evidence}

    def resolves(self, citation: Citation) -> bool:
        """Whether a citation points at real text in real evidence."""
        record = self.by_id().get(citation.evidence_id)
        return record is not None and record.contains(citation.quote)

    def unresolvable(self, citations: Sequence[Citation]) -> tuple[Citation, ...]:
        return tuple(c for c in citations if not self.resolves(c))


@dataclass(frozen=True)
class SkillRun(Generic[T]):
    """A skill's output plus what it cost to produce."""

    output: T
    stages: tuple[RunStage, ...]
    warnings: tuple[str, ...] = ()

    @property
    def retried(self) -> bool:
        return len(self.stages) > 1


class Skill(ABC, Generic[T]):
    """Base for every analysis skill.

    Subclasses supply a name, a versioned prompt, an output model, the values to
    render into that prompt, and their own hard requirements. Everything else —
    calling, parsing, retrying, tracing — happens here, so no skill can forget it.
    """

    def __init__(
        self,
        provider: ModelProvider,
        *,
        allow_retry: bool = True,
        timeout_seconds: float = SKILL_TIMEOUT_SECONDS,
    ) -> None:
        self.provider = provider
        self.allow_retry = allow_retry
        self.timeout_seconds = timeout_seconds

    # -- subclass responsibilities ------------------------------------------ #

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name, used in the run trace and as the cache key."""

    @property
    @abstractmethod
    def prompt(self) -> Prompt: ...

    @property
    @abstractmethod
    def output_model(self) -> type[T]: ...

    @abstractmethod
    def render_values(self, context: SkillContext) -> dict[str, str]:
        """Values for the prompt template."""

    def violations(self, output: T, context: SkillContext) -> tuple[str, ...]:
        """Hard requirements this skill enforces deterministically.

        Return one message per broken rule. Anything checkable in code belongs
        here rather than in the prompt: an instruction can be ignored, a check
        cannot.
        """
        return ()

    def refine(self, output: T, context: SkillContext) -> tuple[T, tuple[str, ...]]:
        """Apply deterministic corrections the model should not be asked to make.

        Returns the refined output and any warnings. Used for things that are
        computed rather than judged - staleness from dates, for instance. It must
        never add analysis; only replace a guess with a calculation.
        """
        return output, ()

    # -- shared execution --------------------------------------------------- #

    def run(self, context: SkillContext) -> SkillRun[T]:
        stages: list[RunStage] = []
        request = self._request(context)
        output = self._attempt(request, self.name, context, stages, attempt=1)
        refined, warnings = self.refine(output, context)
        return SkillRun(output=refined, stages=tuple(stages), warnings=warnings)

    def _request(self, context: SkillContext, *, extra: str = "") -> ModelRequest:
        user = self.prompt.render(**self.render_values(context))
        return ModelRequest(
            skill=self.name,
            prompt_version=self.prompt.version,
            prompt_fingerprint=self.prompt.fingerprint,
            case_id=context.case_id,
            system=self.prompt.system,
            user=user if not extra else f"{user}\n\n{extra}",
            timeout_seconds=self.timeout_seconds,
        )

    def _attempt(
        self,
        request: ModelRequest,
        stage_name: str,
        context: SkillContext,
        stages: list[RunStage],
        *,
        attempt: int,
    ) -> T:
        try:
            response = self.provider.complete(request)
        except ModelError as exc:
            stages.append(
                RunStage(name=stage_name, prompt_version=request.prompt_version, error=str(exc))
            )
            raise SkillError(f"Skill {self.name!r} failed: {exc}", stages) from exc

        problem = ""
        output: T | None = None
        try:
            output = parse_structured(response, self.output_model)
        except ModelOutputError as exc:
            problem = str(exc)

        if output is not None:
            broken = self.violations(output, context)
            if broken:
                problem = "The response broke these requirements:\n- " + "\n- ".join(broken)

        if not problem:
            stages.append(response.to_stage(stage_name))
            assert output is not None  # noqa: S101 - narrowed by the guard above
            return output

        stages.append(response.to_stage(stage_name, error=problem))

        if not self.allow_retry or attempt >= 2:
            error = SkillViolation if output is not None else SkillError
            raise error(
                f"Skill {self.name!r} did not produce usable output after "
                f"{attempt} attempt(s): {problem}",
                stages,
            )

        return self._attempt(
            self._request(
                context,
                extra=(
                    "# Your previous response was rejected\n"
                    f"{problem}\n\n"
                    "Return corrected JSON only. Do not add prose or markdown fences."
                ),
            ),
            f"{stage_name}-retry",
            context,
            stages,
            attempt=attempt + 1,
        )
