"""Finding the exact source text a near-verbatim quote was taken from.

A citation must quote its source verbatim. That rule is the product's central
promise and it is not negotiable: a brief whose quotes cannot be found in the
evidence is exactly the artifact DecisionLens exists to argue against.

The rule survives contact with a language model badly, and always in the same
direction. A live run was thrown away because a quote read

    First attempt success in the pilot group was 88.1%, against

where the evidence says

    First-attempt success in the pilot group was 88.1%, against 87.6% ...

The record was right, the sentence was right, the figure was right, and one
hyphen was missing. Thirty minutes of recording was discarded over a character
nobody would notice reading it.

There are two ways to respond to that and only one of them is honest. Relaxing
the check — accepting a quote that merely resembles the source — would leave
text in the brief that appears nowhere in the evidence, and a reader who went
looking for it would not find it. Instead this module *locates* the source span
and hands back the real characters, so the citation is rewritten to be genuinely
verbatim. The invariant is unchanged; what changes is that a near miss becomes a
correction rather than a discarded run.

Two properties keep this a correction rather than a guess:

- **Only typography is forgiven.** Case, whitespace runs, and the various dashes
  and quote marks that a model substitutes freely. Never a word, never a digit,
  never a negation. `"88.1%"` cannot become `"87.6%"` here.
- **Only when unambiguous.** One match, in one record. A phrase occurring in two
  places has no single correct source, so nothing is repaired and the citation
  is rejected as it was before.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["QuoteMatch", "find_quote", "normalise"]

#: Every dash a model reaches for when the source used a plain hyphen, plus the
#: reverse. `First-attempt` and `First attempt` differ by one of these and by
#: nothing that changes meaning.
_DASHES = "-‐‑‒–—―−"

#: Likewise for quote marks: source text with a straight apostrophe comes back
#: with a typographic one often enough to matter.
_QUOTES = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "«": '"',
    "»": '"',
}


def _fold(char: str) -> str:
    """Lowercase a character without changing its length.

    ``str.casefold`` maps 'ß' to 'ss', which would slide every index after it
    and make the recovered span wrong by a character. Length has to be preserved
    because the whole point is mapping a position back to the original string.
    """
    lowered = char.lower()
    return lowered if len(lowered) == 1 else char


def normalise(text: str) -> tuple[str, list[int]]:
    """Fold typography, and remember where each surviving character came from.

    Returns the folded text alongside, for each of its characters, the index in
    ``text`` it originated at. That index list is what lets a match in folded
    space be handed back as the exact original characters.
    """
    folded: list[str] = []
    origin: list[int] = []
    previous_was_space = False

    for index, char in enumerate(text):
        if char.isspace() or char in _DASHES:
            if previous_was_space:
                continue
            previous_was_space = True
            folded.append(" ")
            origin.append(index)
            continue
        previous_was_space = False
        folded.append(_fold(_QUOTES.get(char, char)))
        origin.append(index)

    return "".join(folded), origin


@dataclass(frozen=True)
class QuoteMatch:
    """Where a quote really came from, in the source's own characters."""

    #: The record the text was found in.
    evidence_id: str
    #: The exact substring of that record. This is what the citation becomes.
    text: str
    #: True when the model's quote already matched the source character for
    #: character, so nothing needs rewriting.
    exact: bool


def _spans(haystack: str, needle: str) -> list[tuple[int, int]]:
    """Every occurrence of ``needle``, as (start, end) index pairs."""
    found: list[tuple[int, int]] = []
    start = haystack.find(needle)
    while start != -1:
        found.append((start, start + len(needle)))
        start = haystack.find(needle, start + 1)
    return found


def find_quote(quote: str, records: dict[str, str]) -> QuoteMatch | None:
    """Locate ``quote`` in ``records`` (an id-to-content mapping).

    Returns ``None`` when the quote cannot be placed, and — just as importantly
    — when it could be placed in more than one way. Ambiguity is not resolved by
    preference here; a phrase that appears in two records has no single correct
    source, and picking one would be inventing provenance.
    """
    wanted = quote.strip()
    if not wanted:
        return None

    exact = [rid for rid, content in records.items() if wanted in content]
    if len(exact) == 1:
        return QuoteMatch(evidence_id=exact[0], text=wanted, exact=True)
    if len(exact) > 1:
        return None

    folded_quote, _ = normalise(wanted)
    folded_quote = folded_quote.strip()
    if not folded_quote:
        return None

    matches: list[QuoteMatch] = []
    for rid, content in records.items():
        folded_content, origin = normalise(content)
        for start, end in _spans(folded_content, folded_quote):
            # `end - 1` is the last folded character; origin maps it back to the
            # last original character, so the slice has to run one past it.
            matches.append(
                QuoteMatch(
                    evidence_id=rid,
                    text=content[origin[start] : origin[end - 1] + 1],
                    exact=False,
                )
            )
            if len(matches) > 1:
                return None

    return matches[0] if len(matches) == 1 else None
