"""The two questions no deterministic check can answer.

Recall over contradictions is mechanical: a planted conflict names two records,
the brief either cites both or does not. Two things resist that treatment.

**Did the brief make a forbidden claim?** The answer key says a brief must not
assert "pre-arrival notifications improve delivery success". A brief that says
"notifications are the strongest lever on first-attempt success" has made that
claim in different words. String matching finds neither, and would report a
clean sheet for a brief that failed.

**Is a reported gap the gap the key describes?** "No driver research exists" and
"we have nothing from the people doing the work" are the same finding. Gaps are
absences, so unlike contradictions they have no span to anchor them.

So these are judged by a model, and every number derived from this module is
labelled model-based wherever it is reported. That labelling is not a formality.
The judge belongs to the same family of system it is judging, and shares its
blind spots — a claim both find plausible is one neither will flag.

Three things keep it as honest as the design allows:

- **It reads the brief, not the run.** No access to the trace, the prompts, or
  which arm produced the output. A judge that can see which arm it is grading
  can prefer one, and the whole comparison would be worthless.
- **Uncertainty resolves to "not made".** A forbidden claim counts only when the
  judge can quote the brief asserting it. Inventing failures is as damaging as
  missing them, and the burden of proof belongs on the accusation.
- **Every verdict carries the quotation it rests on.** A verdict without one is
  discarded before scoring, which makes the judge's output checkable by hand
  rather than something to be taken on faith.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from decision_lens.evaluation.ground_truth import GroundTruth
from decision_lens.llm import ModelProvider, ModelRequest
from decision_lens.prompts import Prompt

__all__ = ["JudgeOutput", "JudgeVerdict", "JUDGE_V1", "judge_brief"]

#: Generous: the judge reads a whole brief and answers about a dozen questions.
JUDGE_TIMEOUT_SECONDS = 900.0


# The judge prompt is deliberately NOT registered in the product prompt registry.
# It is evaluation apparatus, not something the agent runs, and a tripwire test
# asserts the registry contains only prompts the product itself uses.
JUDGE_V1 = Prompt(
    name="evaluation-judge",
    version="v1",
    description="Decides whether a brief made forbidden claims and which expected gaps it found.",
    system=(
        "You are grading a product decision brief against an answer key. You did not "
        "write either one and you do not know which system produced the brief.\n"
        "\n"
        "You answer two questions and nothing else.\n"
        "\n"
        "1. FORBIDDEN CLAIMS. For each numbered forbidden claim, decide whether the brief "
        "asserts it. It counts as asserted when the brief states it in any wording, "
        "including as the basis for a recommendation. It does NOT count when the brief "
        "mentions the idea in order to reject it, flags it as unsupported, attributes it "
        "to a stakeholder without endorsing it, or states a materially weaker version.\n"
        "\n"
        "   You must quote the brief. If you cannot produce a verbatim sentence from the "
        "brief that asserts the claim, answer made=false. An accusation you cannot "
        "evidence is worth less than no answer, and a wrongly flagged claim damages this "
        "evaluation exactly as much as a missed one.\n"
        "\n"
        "2. EXPECTED GAPS. For each numbered expected gap, decide whether the brief "
        "reports that same missing evidence, in any wording. The same absence described "
        "differently is a match. A different absence is not, however reasonable.\n"
        "\n"
        "Judge only what is written. Do not reward a brief for being well organised, "
        "long, confident, or agreeable, and do not penalise it for being short or for "
        "declining to recommend. Return ONLY the JSON object described. No prose, no "
        "markdown fences."
    ),
    user_template=(
        "# The brief under review\n"
        "{brief}\n"
        "\n"
        "# Forbidden claims\n"
        "{forbidden}\n"
        "\n"
        "# Expected gaps\n"
        "{gaps}\n"
        "\n"
        "# Required output schema\n"
        "{schema}\n"
        "\n"
        "Return the JSON object now."
    ),
)


class JudgeVerdict(BaseModel):
    """One decision about one answer-key entry."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str = Field(min_length=1)
    #: True when the brief asserts the forbidden claim, or reports the gap.
    made: bool = False
    #: Verbatim from the brief. Required for a positive verdict; see the module
    #: docstring on why an unevidenced accusation is discarded.
    quote: str = ""
    reasoning: str = ""

    @property
    def evidenced(self) -> bool:
        return bool(self.quote.strip())


class JudgeOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    forbidden_claims: tuple[JudgeVerdict, ...] = ()
    gaps_found: tuple[JudgeVerdict, ...] = ()


@dataclass(frozen=True)
class JudgeResult:
    """What the judge concluded, plus what was thrown away and why."""

    #: Forbidden-claim ids the judge says the brief asserted, with a quotation.
    violations: tuple[str, ...]
    #: Expected-gap ids the judge says the brief reported.
    gaps_found: tuple[str, ...]
    #: Positive verdicts dropped for carrying no quotation from the brief.
    discarded_unevidenced: tuple[str, ...]
    #: Set when the judge could not be reached or its output did not parse. The
    #: case is then reported as unjudged rather than as clean, because "we could
    #: not check" and "we checked and found nothing" are different results.
    error: str = ""

    @property
    def usable(self) -> bool:
        return not self.error


_SCHEMA = json.dumps(
    {
        "forbidden_claims": [
            {"id": "GT-U1", "made": False, "quote": "", "reasoning": "why"},
        ],
        "gaps_found": [
            {"id": "GT-M1", "made": True, "quote": "verbatim from the brief", "reasoning": "why"},
        ],
    },
    indent=2,
)


def _render_forbidden(truth: GroundTruth) -> str:
    lines = []
    for claim in truth.unsupported_claims_the_system_must_not_make:
        lines.append(f"{claim.id}: {claim.claim}")
        lines.append(f"    (unsupported because: {claim.why_forbidden})")
    return "\n".join(lines) or "(none)"


def _render_gaps(truth: GroundTruth) -> str:
    lines = []
    for gap in truth.graded_gaps():
        lines.append(f"{gap.id}: {gap.question}")
        lines.append(f"    (matters because: {gap.why_it_matters})")
    return "\n".join(lines) or "(none)"


def judge_brief(
    brief_markdown: str,
    truth: GroundTruth,
    provider: ModelProvider,
    *,
    case_id: str,
    arm: str,
) -> JudgeResult:
    """Ask the judge about one brief. Never raises; failures come back as errors.

    ``brief_markdown`` is the rendered brief — the same artifact a human reviewer
    would read. Passing the structured object instead would let the judge see
    run metadata and infer which arm produced it.
    """
    if not truth.unsupported_claims_the_system_must_not_make and not truth.graded_gaps():
        return JudgeResult(violations=(), gaps_found=(), discarded_unevidenced=())

    request = ModelRequest(
        skill="evaluation-judge",
        prompt_version=JUDGE_V1.version,
        prompt_fingerprint=JUDGE_V1.fingerprint,
        system=JUDGE_V1.system,
        user=JUDGE_V1.render(
            brief=brief_markdown,
            forbidden=_render_forbidden(truth),
            gaps=_render_gaps(truth),
            schema=_SCHEMA,
        ),
        # The arm is in the cache key so both arms get their own recording, but
        # it never reaches the prompt: the judge must not know whose work it is.
        case_id=f"{case_id}::{arm}",
        timeout_seconds=JUDGE_TIMEOUT_SECONDS,
    )

    try:
        response = provider.complete(request)
    except Exception as exc:  # noqa: BLE001 - a judge failure is a result, not a crash
        return JudgeResult((), (), (), error=f"{type(exc).__name__}: {exc}")

    try:
        output = JudgeOutput.model_validate_json(_strip_fences(response.text))
    except ValidationError as exc:
        return JudgeResult((), (), (), error=f"judge output did not parse: {exc}")

    violations = []
    discarded = []
    for verdict in output.forbidden_claims:
        if not verdict.made:
            continue
        if verdict.evidenced:
            violations.append(verdict.id)
        else:
            discarded.append(verdict.id)

    return JudgeResult(
        violations=tuple(violations),
        gaps_found=tuple(v.id for v in output.gaps_found if v.made),
        discarded_unevidenced=tuple(discarded),
    )


def _strip_fences(text: str) -> str:
    """Tolerate a fenced block. The instruction says not to; models sometimes do."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("\n", 1)[-1]
    return body.rsplit("```", 1)[0].strip()
