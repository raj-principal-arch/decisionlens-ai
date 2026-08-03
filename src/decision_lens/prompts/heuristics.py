"""Judgment both arms are given, held in one place so it cannot diverge.

These are the reading heuristics a competent product manager applies to an
evidence pack: an executive's preference is not a finding, a percentage from
fifteen people is not a population rate, a figure quoted in prose may be a stale
copy of a number that has since moved.

They live here for one reason, and it is about the evaluation rather than the
product. DecisionLens is measured against a single well-prompted call, and that
comparison is only about *structure* if both arms are told the same things. When
the guidance was written separately, it drifted: the DecisionLens prompts warned
about seniority, staleness, stale figures and segment-scoped claims while the
baseline prompt did not. Eight reading cues reached one arm and not the other,
so the baseline was left to notice them unaided. Any margin measured under that
asymmetry would partly
have been a difference in briefing, not a difference in workflow — and a
baseline that was told less is the strawman the specification forbids.

Sharing the text makes the fairness structural instead of remembered. A test
asserts every block below reaches both arms.

A separate and unresolved concern: these heuristics were written after the
bundled case was designed, and they map onto hazards planted in it. That is
in-sample. It is not fixed by sharing them — both arms are now equally
well-briefed on this case — and the only honest measure of generalisation is a
case built after the prompts were frozen. See docs/04-evaluation.md.
"""

from __future__ import annotations

__all__ = [
    "ASSESSMENT_STATES",
    "CITING",
    "FINDING_GAPS",
    "READING_EVIDENCE",
    "SPOTTING_CONFLICTS",
    "STATING_SUPPORT",
]

#: How a citation must be formed, and why a wrong one is worse than none.
CITING = (
    "Every citation must name an evidence id from the list and quote text VERBATIM from "
    "that record. Never paraphrase inside a quote. A citation that cannot be found in the "
    "evidence will be rejected, so omit a claim rather than invent support for it.\n\n"
    "The id and the quote must come from the SAME block. Copy the id from the header of "
    "the block the quoted line actually appears in — with dozens of records it is easy to "
    "quote one record accurately and label it with a neighbour's id, and that is rejected "
    "just as an invented quote would be."
)

#: A schema rule, not a judgment — but both arms emit the same schema, so both
#: have to know it. Three live runs were thrown away for breaking it unwarned.
ASSESSMENT_STATES = (
    "  assessed      - you MUST include at least one citation. No exceptions: an\n"
    "                  assessment with nothing behind it is rejected outright and\n"
    "                  the whole option set is thrown away.\n"
    "  cannot_assess - use this whenever you cannot cite evidence, and say what is\n"
    "                  missing. It is the correct answer far more often than it looks."
)

#: Telling a finding from a belief. Every line here is a way a confident-sounding
#: statement turns out not to be evidence.
READING_EVIDENCE = (
    "- A stakeholder recalling a result confidently is an opinion, not a fact. If the "
    "underlying measurement disagrees with them, they are still an opinion.\n"
    "- An executive's preference is an opinion. Seniority does not convert it.\n"
    "- A vendor figure with no stated method, sample or baseline is an opinion.\n"
    "- A percentage from a small or self-selected sample is not a fact about the "
    "population. Check the denominator before labelling it.\n"
    "- A figure from an older document may have been a fact when written and not now. "
    "Prefer the dated measurement over the prose that quotes it."
)

#: The two disagreements that look like errors and are not.
SPOTTING_CONFLICTS = (
    "- A figure quoted in prose that matches an older row in a data series is not "
    "wrong, it is stale. Say which period it belongs to.\n"
    "- Two statements about a 'largest' or 'leading' cause may both be true of "
    "different segments. Say which segment each describes."
)

#: What absence looks like. Gaps are easy to miss precisely because nothing is there.
FINDING_GAPS = (
    "- A population with no evidence at all, when options depend on it.\n"
    "- A study or pilot that could not measure its own effect. That is an unmeasured "
    "result, not a small one.\n"
    "- A cost, effort or volume figure nobody has produced.\n"
    "- A breakdown that exists along one dimension but not another that matters.\n"
    "- A field that exists but was never populated. Blank is not zero."
)

#: Restraint. Each line is a way a recommendation claims more than it holds.
STATING_SUPPORT = (
    "- If the strongest support is a single small or non-randomised study, that is not "
    "strong support.\n"
    "- If a key input has not been measured or costed, say so in the recommendation "
    "rather than only in the gaps section.\n"
    "- If the evidence supports the option only for one segment, say which. A claim "
    "that is true of apartments and asserted of everything is wrong.\n"
    "- Stakeholder preference is not support. If the only backing for an option is that "
    "somebody senior wants it, say that plainly."
)
