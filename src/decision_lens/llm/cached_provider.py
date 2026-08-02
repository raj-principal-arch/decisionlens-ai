"""Deterministic offline provider.

Replays recorded model output so a reviewer can run the prototype with no API key
and get the same result every time.

Two rules it will not bend:

*   **It never claims to be live.** `provider_id` is ``cached-demo``, `is_cached`
    is always true, every response carries a warning naming the model and date the
    output was recorded from, and all of that reaches the run trace.
*   **A miss is an error, not a placeholder.** If no recorded response exists the
    run stops with a message naming the missing key. Emitting a plausible stub
    would put unverifiable content into a decision brief, which is the precise
    failure this product exists to prevent.

A recorded response also stores the fingerprint of the prompt that produced it.
If the prompt has changed since, the response is still served — the demo does not
break on a typo fix — but the drift is reported as a warning rather than hidden.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from decision_lens.llm.base import (
    BaseModelProvider,
    ModelError,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)

PROVIDER_ID = "cached-demo"

#: Ships with the package so the offline demo works from a fresh clone.
DEFAULT_CACHE_PATH = Path(__file__).parent / "demo_cache.json"


class CacheMissError(ModelError):
    """No recorded response exists for this request."""


class CachedResponse(BaseModel):
    """One recorded model response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    text: str = Field(min_length=1)
    recorded_from_model: str = Field(min_length=1)
    recorded_at: datetime
    prompt_fingerprint: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    note: str = ""


class DemoCache(BaseModel):
    """The on-disk cache: metadata plus responses keyed by request identity."""

    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    notice: str = (
        "Recorded model output replayed offline. These are not live model results. "
        "Every response served from this file is labelled cached in the run trace."
    )
    responses: dict[str, CachedResponse] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> DemoCache:
        if not path.is_file():
            raise CacheMissError(
                f"No demo cache at {path}. Record one before running offline, "
                f"or pass an explicit cache_path."
            )
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CacheMissError(f"Demo cache at {path} is not readable: {exc}") from exc

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")

    def add(self, response: CachedResponse) -> None:
        """Record a response. Used by the recording path in later phases."""
        self.responses[response.key] = response


class CachedDemoProvider(BaseModelProvider):
    """Serves recorded responses. Requires no credentials and reaches no network.

    Args:
        cache_path: Where recorded responses live. Defaults to the packaged cache.
        cache: A pre-loaded cache, mainly for tests.
    """

    def __init__(self, cache_path: Path | None = None, *, cache: DemoCache | None = None) -> None:
        self._cache_path = cache_path or DEFAULT_CACHE_PATH
        self._cache = cache if cache is not None else DemoCache.load(self._cache_path)

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def model_id(self) -> str:
        """Reports replay, not a model name.

        Claiming a model id here would let a run trace read as though that model
        had been called. The model each response was recorded from is reported
        per-response instead.
        """
        return "recorded-replay"

    @property
    def serves_cached_responses(self) -> bool:
        return True

    @property
    def cache_path(self) -> Path:
        return self._cache_path

    def known_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._cache.responses))

    def _complete(self, request: ModelRequest) -> tuple[str, ModelUsage, tuple[str, ...]]:
        entry = self._cache.responses.get(request.cache_key)
        if entry is None:
            raise CacheMissError(
                f"No recorded response for {request.cache_key!r}.\n"
                f"  skill          : {request.skill}\n"
                f"  case           : {request.case_id or '(none)'}\n"
                f"  prompt version : {request.prompt_version}\n"
                f"  cache          : {self._cache_path}\n"
                f"  known keys     : {', '.join(self.known_keys()) or '(cache is empty)'}\n"
                "Record this response before running offline. A placeholder is not "
                "substituted: unverifiable content must never reach a decision brief."
            )

        warnings = [
            f"Replayed from cache; recorded from {entry.recorded_from_model} on "
            f"{entry.recorded_at.date().isoformat()}. Not a live model result."
        ]
        if (
            request.prompt_fingerprint
            and entry.prompt_fingerprint
            and request.prompt_fingerprint != entry.prompt_fingerprint
        ):
            warnings.append(
                "The prompt has changed since this response was recorded "
                f"(recorded {entry.prompt_fingerprint[:12]}, current "
                f"{request.prompt_fingerprint[:12]}). The cached answer may no longer "
                "reflect what the prompt would produce."
            )

        usage = ModelUsage(input_tokens=entry.input_tokens, output_tokens=entry.output_tokens)
        return entry.text, usage, tuple(warnings)

    def complete(self, request: ModelRequest) -> ModelResponse:
        response = super().complete(request)
        entry = self._cache.responses[request.cache_key]
        return response.model_copy(update={"recorded_at": entry.recorded_at})
