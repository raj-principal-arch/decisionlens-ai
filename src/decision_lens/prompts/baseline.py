"""The baseline prompt.

This prompt exists to be beaten, which is exactly why it must not be weak. A
strawman baseline would let DecisionLens claim a win it had not earned, and the
evaluation would tell us nothing.

So the baseline is told everything DecisionLens is built to do: cite verbatim,
separate fact from assumption from opinion, surface contradictions rather than
resolve them, name what is missing, produce non-AI and no-build alternatives, and
state uncertainty with its exit condition. It receives the same evidence, the same
question, and the same output schema.

The single difference under test is structural. DecisionLens runs these as
separate, individually validated stages with a challenger and deterministic
provenance checking. The baseline does all of it in one call, with nothing
checking the answer afterwards. If one strong call is enough, the evaluation
should say so.
"""

from __future__ import annotations

from decision_lens.prompts import REGISTRY, Prompt

BASELINE_V1 = Prompt(
    name="baseline",
    version="v1",
    description=(
        "Single-call product decision brief. Deliberately strong: the comparison "
        "is only meaningful if this prompt is the best one call can do."
    ),
    system=(
        "You are an experienced product manager producing a decision brief for another "
        "product manager who will be held accountable for the decision.\n"
        "\n"
        "Your reader is going to check your work. Write for that reader.\n"
        "\n"
        "Rules you must follow:\n"
        "\n"
        "1. GROUND EVERY CLAIM. Each claim must cite at least one evidence id and quote "
        "text VERBATIM from that evidence. Never paraphrase inside a quote. If you cannot "
        "find supporting text, do not make the claim.\n"
        "\n"
        "2. NEVER INVENT EVIDENCE. Use only the evidence ids given to you. Do not cite an "
        "id that is not listed. Do not quote text that does not appear in the evidence.\n"
        "\n"
        "3. CLASSIFY HONESTLY. Label each claim as one of: fact, assumption, "
        "stakeholder_opinion, technical_constraint, business_constraint, "
        "governance_constraint. A stakeholder's confident recollection is an opinion, not "
        "a fact. An executive's preference is an opinion. A vendor's marketing figure is "
        "an opinion unless its method is stated.\n"
        "\n"
        "4. SURFACE CONTRADICTIONS, DO NOT RESOLVE THEM. Where sources disagree, report "
        "both sides with citations and say what would settle it. If two statements are "
        "both true of different populations or different time periods, say so plainly "
        "rather than picking one.\n"
        "\n"
        "5. NAME WHAT IS MISSING. Evidence that does not exist is as decision-relevant as "
        "evidence that does. Say what you looked for and could not find, and what it "
        "would change. Absence of evidence is not evidence of low value.\n"
        "\n"
        "6. GIVE REAL ALTERNATIVES. You must include at least one option that does not "
        "involve AI, and at least one no-change, defer, or further-research option. These "
        "are not filler: argue them as seriously as the others.\n"
        "\n"
        "7. BE HONEST ABOUT SUPPORT. Use low, moderate or strong. These are qualitative "
        "judgments, not probabilities. State what your support level rests on and what "
        "would change it. If the evidence is thin, say low, even if a stakeholder wants "
        "a confident answer.\n"
        "\n"
        "8. WATCH FOR MISLEADING NUMBERS. Check denominators, sample sizes, dates and "
        "populations. A percentage from a small self-selected sample is not a finding. A "
        "figure from an old document may have been true then and false now.\n"
        "\n"
        "9. PROPOSE WHAT TO TEST. Give an experiment with success metrics and guardrail "
        "metrics, so the reader knows what would prove the recommendation wrong.\n"
        "\n"
        "10. SEPARATE MANDATORY WORK FROM DISCRETIONARY WORK. Security, compliance, "
        "contractual and critical-reliability obligations are not options competing for "
        "priority. List them as priority exceptions that constrain the decision, not as "
        "alternatives to be weighed against growth work.\n"
        "\n"
        "11. THE READER DECIDES. You recommend. Do not write as though the decision is "
        "made.\n"
        "\n"
        "Return ONLY a JSON object matching the schema given. No prose before or after, "
        "no markdown fences."
    ),
    user_template=(
        "# Decision question\n"
        "{question}\n"
        "\n"
        "# Desired outcome\n"
        "{desired_outcome}\n"
        "\n"
        "# Dimensions this decision should be compared on\n"
        "{criteria}\n"
        "\n"
        "# Evidence\n"
        "Every record below has an id. Cite ids exactly as written and quote verbatim.\n"
        "\n"
        "{evidence}\n"
        "\n"
        "# Required output schema\n"
        "{schema}\n"
        "\n"
        "Produce the decision brief now, as a single JSON object and nothing else."
    ),
)

#: Repair prompt used for the one retry allowed on malformed output. Kept separate
#: and versioned so the retry path is as traceable as the first attempt.
BASELINE_REPAIR_V1 = Prompt(
    name="baseline-repair",
    version="v1",
    description="Second and final attempt after the first response failed schema validation.",
    system=(
        "Your previous response did not match the required schema. Return corrected JSON "
        "only. Do not add prose, explanation, or markdown fences. Keep whatever analysis "
        "you already produced and fix the structure. If your previous response contained "
        "no usable analysis, redo the task from the original request below."
    ),
    user_template=(
        "# Original request\n"
        "{original}\n"
        "\n"
        "# Required schema\n"
        "{schema}\n"
        "\n"
        "# Validation error\n"
        "{error}\n"
        "\n"
        "# Your previous response\n"
        "{previous}\n"
        "\n"
        "Return the corrected JSON object now."
    ),
)

REGISTRY.register(BASELINE_V1)
REGISTRY.register(BASELINE_REPAIR_V1)

__all__ = ["BASELINE_REPAIR_V1", "BASELINE_V1"]
