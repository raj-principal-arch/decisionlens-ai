"""The model-provider contract.

Vendor-neutral by design. DecisionLens must be able to swap Anthropic for OpenAI
for a deterministic offline stub without any analysis skill noticing, because the
thing under test is the workflow, not the model behind it.

Three properties the contract enforces rather than suggests:

*   **A response always says where it came from.** Provider, model, prompt version
    and cached-or-live are fields, not optional metadata. A brief that cannot say
    which model produced it is not reproducible, and reproducibility is the whole
    argument.
*   **Cached output is never silently cached.** `is_cached` has no default that
    hides it, and `ModelResponse.to_stage()` carries it into the run trace.
*   **Structured output is validated, not trusted.** `parse_structured` raises on
    malformed output rather than returning a half-populated object.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime
from enum import Enum
from typing import Protocol, TypeVar, get_args, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from decision_lens.models import RunStage

T = TypeVar("T", bound=BaseModel)

DEFAULT_TIMEOUT_SECONDS = 60.0


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ModelError(RuntimeError):
    """Base for every provider failure.

    The orchestrator catches these and records a failed stage. One dead provider
    degrades a brief; it does not abort the run.
    """


class ModelTimeout(ModelError):
    """The provider did not answer within the request's timeout."""


class ModelUnavailable(ModelError):
    """The provider could not be reached, or refused the request."""


class ModelOutputError(ModelError):
    """The provider answered, but the answer did not match the expected shape."""


# --------------------------------------------------------------------------- #
# Request and response
# --------------------------------------------------------------------------- #


class ModelRequest(_Frozen):
    """One call to a model.

    `skill`, `case_id` and `prompt_version` are not provider configuration — they
    are what makes a call identifiable after the fact. A live provider ignores
    them except when writing the trace; the cached provider uses them as its key.
    """

    skill: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    system: str = ""
    user: str = Field(min_length=1)
    case_id: str = ""
    prompt_fingerprint: str = ""  # hash of the prompt that built this request
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    timeout_seconds: float = Field(default=DEFAULT_TIMEOUT_SECONDS, gt=0)

    @property
    def cache_key(self) -> str:
        """Stable identity of this call, independent of prompt wording.

        Deliberately excludes the prompt text. Keying on the rendered prompt would
        invalidate every cached response on a typo fix and silently break the
        offline demo; the fingerprint is recorded separately so drift stays
        visible without being fatal.
        """
        return f"{self.case_id or 'default'}::{self.skill}::{self.prompt_version}"


class ModelUsage(_Frozen):
    """Token accounting, where the provider reports it."""

    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)


class ModelResponse(_Frozen):
    """What a provider returned, and everything needed to reproduce it."""

    text: str
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    skill: str = Field(min_length=1)
    latency_ms: int = Field(ge=0)
    usage: ModelUsage = ModelUsage()
    is_cached: bool
    recorded_at: datetime | None = None
    warnings: tuple[str, ...] = ()

    def to_stage(self, name: str, *, error: str = "") -> RunStage:
        """Contribute this call to the run trace.

        The trace is what makes a brief reproducible: provider, model and prompt
        version pinned, plus whether the answer came from cache, plus whatever
        the provider warned about. Dropping the warnings here is how a cached
        provider could say "the prompt has changed since this was recorded" into
        a void for an entire evening.
        """
        return RunStage(
            name=name,
            provider=self.provider,
            model=self.model,
            prompt_version=self.prompt_version,
            input_tokens=self.usage.input_tokens,
            output_tokens=self.usage.output_tokens,
            latency_ms=self.latency_ms,
            error=error,
            warnings=self.warnings,
        )


# --------------------------------------------------------------------------- #
# The contract
# --------------------------------------------------------------------------- #


@runtime_checkable
class ModelProvider(Protocol):
    """Structural contract every provider satisfies.

    A Protocol so an adapter around an existing client need not inherit from
    DecisionLens. As with `EvidenceSource`, `isinstance` checks attribute presence
    only — signature conformance is mypy's job, not the runtime's.
    """

    @property
    def provider_id(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    def complete(self, request: ModelRequest) -> ModelResponse: ...


class BaseModelProvider(ABC):
    """Optional base carrying the plumbing every provider needs.

    Owns latency measurement and response stamping so no implementation can
    forget to record which model answered, or report a cached response as live.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def model_id(self) -> str: ...

    @property
    def serves_cached_responses(self) -> bool:
        """Whether this provider replays recorded output rather than calling a model."""
        return False

    @abstractmethod
    def _complete(self, request: ModelRequest) -> tuple[str, ModelUsage, tuple[str, ...]]:
        """Return the raw text, usage, and any warnings. Timing is handled here."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()
        text, usage, warnings = self._complete(request)
        elapsed = time.perf_counter() - started

        # Enforced here rather than left as an unread field. This is detection,
        # not cancellation: Python cannot interrupt a synchronous call already in
        # flight, so an adapter must ALSO pass the timeout to its transport. What
        # this guarantees is that an overrunning response is never used, and that
        # a provider quietly ignoring its deadline is caught rather than trusted.
        if elapsed > request.timeout_seconds:
            raise ModelTimeout(
                f"{self.provider_id}/{self.model_id} took {elapsed:.2f}s for skill "
                f"{request.skill!r}, exceeding its {request.timeout_seconds}s timeout. "
                "The response was discarded. Adapters should also pass the timeout to "
                "their transport so the call is cancelled, not merely detected."
            )

        latency_ms = max(0, int(elapsed * 1000))
        return ModelResponse(
            text=text,
            provider=self.provider_id,
            model=self.model_id,
            prompt_version=request.prompt_version,
            skill=request.skill,
            latency_ms=latency_ms,
            usage=usage,
            is_cached=self.serves_cached_responses,
            warnings=warnings,
        )


# --------------------------------------------------------------------------- #
# Structured output
# --------------------------------------------------------------------------- #


def _field_key(name: str) -> str:
    """Fold a field name to what it means, ignoring how it was punctuated."""
    return "".join(c for c in name.lower() if c.isalnum())


def _repair_keys(value: object, schema: type[BaseModel]) -> object:
    """Snap near-miss field names onto the ones the schema declares.

    A live run lost an entire stage — every contradiction it had found — because
    the model wrote ``how_to resolve`` with a space instead of an underscore.
    One character, and the work was discarded.

    Rejecting that is defensible but pointless. The name is unambiguous: exactly
    one declared field folds to the same letters, and no judgment is involved in
    identifying it. So it is corrected here rather than thrown away. What is NOT
    done is inventing a value, dropping an unrecognised key, or guessing between
    two plausible fields — a name that folds onto two candidates, or onto none,
    is left exactly as it arrived and fails validation as before.

    Only key spelling is touched. Every value passes through untouched, so this
    cannot turn malformed content into content that merely looks valid.
    """
    if isinstance(value, list):
        return [_repair_keys(v, schema) for v in value]
    if not isinstance(value, dict):
        return value

    declared = {_field_key(n): n for n in schema.model_fields}
    # A folded name shared by two declared fields identifies neither.
    ambiguous = {
        k for k in declared if sum(1 for n in schema.model_fields if _field_key(n) == k) > 1
    }

    out: dict[str, object] = {}
    for key, item in value.items():
        target = key
        if key not in schema.model_fields:
            folded = _field_key(key)
            if folded in declared and folded not in ambiguous:
                target = declared[folded]
        field = schema.model_fields.get(target)
        nested = _nested_model(field.annotation) if field is not None else None
        out[target] = _repair_keys(item, nested) if nested is not None else item
    return out


def _nested_model(annotation: object) -> type[BaseModel] | None:
    """The BaseModel inside ``X``, ``X | None``, ``tuple[X, ...]``, ``list[X]``."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        found = _nested_model(arg)
        if found is not None:
            return found
    return None


def _enum_values(annotation: object) -> tuple[str, ...]:
    """The string values of an Enum inside ``X``, ``X | None``, ``tuple[X, ...]``."""
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return tuple(str(m.value) for m in annotation)
    for arg in get_args(annotation):
        found = _enum_values(arg)
        if found:
            return found
    return ()


def _closest_enum(written: str, allowed: tuple[str, ...]) -> str | None:
    """The one allowed value a near-miss unambiguously means, or None.

    A live stage was lost three times, retry included, because the model wrote
    `would_change_scope` where the vocabulary offers `would_change_recommendation`,
    `would_change_support_level` and `would_refine_scope`. The prompt lists all
    three explicitly. It still happened, so this is corrected rather than
    re-explained.

    Plain word overlap cannot do it — every candidate shares exactly two words
    with what was written. What identifies the intended value is that `scope`
    occurs in only one of them, while `would` occurs in all three and carries no
    information. So each shared word is weighted by how rare it is across the
    vocabulary, and two conditions must both hold before anything is changed:

    - one candidate scores strictly highest, and
    - the match includes a word unique to that candidate.

    The second condition is what stops a value being snapped on the strength of
    filler alone. `would_change_everything` shares only `would` and `change`
    with two candidates and is refused, which is correct: nobody can say which
    was meant, and guessing would put a fabricated impact rating into a brief.
    """
    if not allowed or written in allowed:
        return None
    # Exact match once punctuation is ignored — `wouldRefineScope` for
    # `would_refine_scope`. Same rule as field names, and equally safe: the
    # letters are identical, only the separators moved.
    folded = {_field_key(v): v for v in allowed}
    counts = Counter(_field_key(v) for v in allowed)
    key = _field_key(written)
    if key in folded and counts[key] == 1:
        return folded[key]

    words = {w for w in re.split(r"[^a-z0-9]+", written.lower()) if w}
    if not words:
        return None

    frequency = Counter(
        w for value in allowed for w in set(re.split(r"[^a-z0-9]+", value.lower())) if w
    )
    scored: list[tuple[float, bool, str]] = []
    for value in allowed:
        shared = words & {w for w in re.split(r"[^a-z0-9]+", value.lower()) if w}
        if not shared:
            continue
        score = sum(1.0 / frequency[w] for w in shared)
        distinctive = any(frequency[w] == 1 for w in shared)
        scored.append((score, distinctive, value))

    if not scored:
        return None
    scored.sort(reverse=True)
    best_score, distinctive, best = scored[0]
    if not distinctive:
        return None
    if len(scored) > 1 and abs(scored[1][0] - best_score) < 1e-9:
        return None
    return best


def _repair_enums(value: object, schema: type[BaseModel]) -> object:
    """Snap near-miss enum values onto the vocabulary the schema declares."""
    if isinstance(value, list):
        return [_repair_enums(v, schema) for v in value]
    if not isinstance(value, dict):
        return value

    out: dict[str, object] = {}
    for key, item in value.items():
        field = schema.model_fields.get(key)
        if field is None:
            out[key] = item
            continue
        nested = _nested_model(field.annotation)
        if nested is not None:
            out[key] = _repair_enums(item, nested)
            continue
        allowed = _enum_values(field.annotation)
        if allowed and isinstance(item, str):
            out[key] = _closest_enum(item, allowed) or item
        else:
            out[key] = item
    return out


def parse_structured(response: ModelResponse, schema: type[T]) -> T:
    """Validate a response into a typed model.

    Raises rather than returning a partially-populated object. A skill that
    silently accepts malformed output would put unverified content into a brief,
    which is the failure this product exists to prevent.
    """
    # One branch, not two: pydantic reports malformed JSON and a missing field
    # through the same ValidationError, so a separate "not valid JSON" handler
    # would be unreachable.
    try:
        return schema.model_validate_json(response.text)
    except ValidationError:
        pass

    # Second chance, for punctuation only. If the text is not even JSON this
    # raises again below with the original kind of message.
    try:
        repaired = _repair_enums(_repair_keys(json.loads(response.text), schema), schema)
        return schema.model_validate(repaired)
    except (ValidationError, json.JSONDecodeError, TypeError):
        pass

    try:
        return schema.model_validate_json(response.text)
    except ValidationError as exc:
        raise ModelOutputError(
            f"{response.provider}/{response.model} returned output that does not match "
            f"{schema.__name__} for skill {response.skill!r}. Malformed JSON and missing "
            f"fields both arrive here: {exc}"
        ) from exc
