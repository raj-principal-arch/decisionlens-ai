"""Loading a case directory into something runnable.

A "case" is a folder of evidence plus a manifest naming the decision it belongs
to. The manifest already carries the question, the desired outcome, the product
area and the date staleness is measured against, so running the bundled demo
takes no arguments at all — which is the difference between a reviewer trying it
and a reviewer reading about it.

Shared by the CLI, the Streamlit interface and (in Phase 10) the evaluation
harness, so all three run a case the same way. If loading lived in the CLI, the
UI would grow a second implementation and the two would drift.

Every field can be overridden. A PM asking a different question of the same
evidence is the normal use, not an edge case.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from decision_lens.connectors import LocalFileEvidenceSource
from decision_lens.connectors.base import EvidenceSource
from decision_lens.models import (
    DecisionCriteria,
    DecisionRequest,
    Dimension,
    DimensionCriterion,
    UserContext,
)

__all__ = ["CaseError", "LoadedCase", "bundled_case_dir", "load_case"]

MANIFEST_NAME = "case_manifest.json"

#: The case that ships with the repository.
BUNDLED_CASE = "sample_delivery_exceptions"


class CaseError(RuntimeError):
    """A case directory could not be loaded."""


def bundled_case_dir(root: Path | None = None) -> Path:
    """Where the shipped sample case lives, relative to the repository root."""
    return (root or Path.cwd()) / "data" / BUNDLED_CASE


@dataclass(frozen=True)
class LoadedCase:
    """A case directory, resolved into the pieces a run needs."""

    case_id: str
    directory: Path
    request: DecisionRequest
    sources: tuple[EvidenceSource, ...]
    as_of: date
    notice: str

    @property
    def is_synthetic(self) -> bool:
        return bool(self.notice)


def _read_manifest(directory: Path) -> dict[str, object]:
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        raise CaseError(
            f"No {MANIFEST_NAME} in {directory}. A case directory needs one: it names the "
            "decision the evidence belongs to, and without it there is nothing to ask."
        )
    try:
        loaded = json.loads(manifest.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise CaseError(f"{manifest} is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise CaseError(f"{manifest} must contain a JSON object.")
    return loaded


def _as_text(manifest: dict[str, object], key: str, default: str = "") -> str:
    value = manifest.get(key, default)
    return value if isinstance(value, str) else default


def load_case(
    directory: Path,
    *,
    question: str = "",
    desired_outcome: str = "",
    product_area: str = "",
    user: UserContext | None = None,
    criteria: DecisionCriteria | None = None,
    as_of: date | None = None,
) -> LoadedCase:
    """Load a case, letting the caller override anything the manifest supplies.

    Raises:
        CaseError: The directory, the manifest, or the question is unusable.
    """
    if not directory.is_dir():
        raise CaseError(f"{directory} is not a directory.")

    manifest = _read_manifest(directory)
    case_id = _as_text(manifest, "case_id", directory.name)

    resolved_question = (question or _as_text(manifest, "question")).strip()
    if not resolved_question:
        raise CaseError(
            f"No question for {case_id}. Put one in {MANIFEST_NAME} or pass it explicitly — "
            "DecisionLens answers a stated decision, not a directory."
        )
    if not resolved_question.endswith("?"):
        raise CaseError(
            f"The question for {case_id} is not phrased as a question: "
            f"{resolved_question!r}. A decision question ends in '?'."
        )

    resolved_as_of = as_of or _parse_date(_as_text(manifest, "as_of"), case_id)
    area = product_area or _as_text(manifest, "product_area")

    request = DecisionRequest(
        id=case_id,
        question=resolved_question,
        desired_outcome=desired_outcome or _as_text(manifest, "desired_outcome"),
        user=user
        or UserContext(user_id="pm-local", display_name="Local reviewer", product_area=area),
        criteria=criteria or DecisionCriteria(),
    )

    return LoadedCase(
        case_id=case_id,
        directory=directory,
        request=request,
        sources=(LocalFileEvidenceSource(directory),),
        as_of=resolved_as_of,
        notice=_as_text(manifest, "notice"),
    )


def _parse_date(raw: str, case_id: str) -> date:
    """A case without a date is measured against today, and says so by defaulting."""
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise CaseError(
            f"{case_id} has an unreadable as_of date {raw!r}; expected YYYY-MM-DD."
        ) from exc


def criteria_for(
    selected: set[Dimension], *, require_non_ai: bool = True, require_no_build: bool = True
) -> DecisionCriteria:
    """Build criteria from a set of chosen dimensions.

    Used by the interface, where a PM ticks the dimensions that apply. A
    dimension left unticked is marked inapplicable rather than dropped, so the
    brief can still say it was considered and set aside.
    """
    return DecisionCriteria(
        dimensions=tuple(DimensionCriterion(dimension=d, applies=d in selected) for d in Dimension),
        require_non_ai_alternative=require_non_ai,
        require_no_build_alternative=require_no_build,
    )
