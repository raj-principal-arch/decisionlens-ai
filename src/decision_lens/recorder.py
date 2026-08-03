"""Capturing a live run so it can be replayed offline.

This is what makes the offline demo honest. The alternative — hand-writing
plausible model output into the cache — would put invented analysis in front of a
reviewer under the label of a recorded result, which is precisely the fabrication
this product exists to prevent. Every response in the shipped cache was produced
by a real model on a real call, and carries the model name and date it came from.

The design is deliberately thin: :class:`RecordingProvider` wraps whatever
provider it is given and writes each response into a :class:`DemoCache` on the
way past. Neither the orchestrator nor the baseline knows it is being recorded,
so what gets captured is exactly what a real run produces — not a special
recording path that could drift from the one under test.

Recording is always an explicit act. There is no code path that records as a side
effect of an ordinary run, because writing a cache entry silently would make the
provenance of the demo unverifiable.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from decision_lens.baseline import BaselineError, StrongBaseline
from decision_lens.connectors.base import EvidenceSource
from decision_lens.llm import (
    CachedResponse,
    DemoCache,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from decision_lens.models import (
    DecisionBrief,
    DecisionRequest,
    EvidenceRecord,
    EvidenceRequest,
)
from decision_lens.orchestrator import DecisionLens
from decision_lens.prompts import REGISTRY

__all__ = [
    "CHAINED_STAGES",
    "EXPECTED_STAGES",
    "INDEPENDENT_STAGES",
    "LIVE_SKILL_TIMEOUT_SECONDS",
    "ProgressFn",
    "RecordingProvider",
    "RecordingSummary",
    "current_stage_versions",
    "estimate_run",
    "merge_into",
    "record_case",
    "stages_worth_reusing",
]

#: A live model reasoning over a full evidence corpus is far slower than replaying
#: a recorded string. The cached-mode default is sized for replay; using it live
#: would time out a call that was going to succeed.
#:
#: Sized against the output ceiling rather than guessed, and asserted by a test:
#: a response near `DEFAULT_MAX_OUTPUT_TOKENS` needs roughly half an hour at a
#: pessimistic 40 tokens per second, and a shorter deadline would convert a
#: response that was going to arrive into a timeout. Raise both together or
#: neither.
#:
#: This is a ceiling on a stage that has gone wrong, not an expectation. A
#: healthy stage returns in single-digit minutes; this only decides how long a
#: wedged one is tolerated before it is abandoned.
LIVE_SKILL_TIMEOUT_SECONDS = 1_900.0

#: Rough characters-per-token, used only for the pre-run size preview. Deliberately
#: not presented as a token count: the real number comes back in the run summary,
#: measured rather than guessed.
_CHARS_PER_TOKEN = 4


#: Called with one line of progress. A callback rather than a stream so the
#: recorder does not care whether it is writing to a terminal, a log, or nothing.
ProgressFn = Callable[[str], None]

#: The DecisionLens stages, in the order they run. Each is fed by the ones before
#: it: alternatives sees the classified claims, the recommendation sees the
#: alternatives, the challenger sees all of it. Re-recording any of them makes
#: every later one stale.
CHAINED_STAGES: tuple[str, ...] = (
    "relevance",
    "classification",
    "contradictions",
    "missing_evidence",
    "alternatives",
    "recommendation",
    "challenger",
)

#: One well-prompted call over the same evidence, depending on none of the above.
#: Safe to reuse however much of the chain was re-recorded.
INDEPENDENT_STAGES: tuple[str, ...] = ("baseline",)

#: The stages a full recording makes, in order, for the progress counter.
EXPECTED_STAGES: tuple[str, ...] = CHAINED_STAGES + INDEPENDENT_STAGES


def current_stage_versions() -> dict[str, str]:
    """The prompt version each stage will ask for on the next run.

    A resumed run reuses a cached response only when the whole key matches,
    version included. Anything that previews a resume has to resolve the version
    the same way, or it promises a saving the run then does not deliver: the CLI
    preview once split the key on `::` and kept only the stage name, so a cache
    holding `baseline::v1` was read as "baseline is covered". It printed nothing
    to record and no cost, then billed a real call for `baseline::v2`.

    Reading from the registry rather than restating a table here means the
    answer cannot drift from the prompts themselves. A test pins the one
    assumption that makes it valid: every stage runs its latest registered
    prompt, so `latest` is what the run will actually request.
    """
    import decision_lens.prompts.baseline  # noqa: F401  registers the baseline prompt
    import decision_lens.prompts.decisionlens  # noqa: F401  registers the skill prompts

    return {stage: REGISTRY.latest(stage).version for stage in EXPECTED_STAGES}


def stages_worth_reusing(cached: set[str]) -> set[str]:
    """Which cached stages a resumed run may serve, given what is missing.

    Everything up to the first gap in the chain, plus the independent stages.
    A stage after the gap was produced from different upstream state — reusing
    it stitches together a brief whose parts never saw each other, which is
    exactly how a recommendation selecting nothing ended up beside eleven
    perfectly good options.
    """
    usable = set(INDEPENDENT_STAGES) & cached
    for stage in CHAINED_STAGES:
        if stage not in cached:
            break
        usable.add(stage)
    return usable


class RecordingProvider:
    """Delegates to a real provider and keeps a copy of every response.

    Args:
        inner: The provider actually being called.
        cache: Where responses accumulate. Mutated in place; the caller decides
            when and whether to write it to disk.
        clock: Fixed timestamp, so a recording is reproducible in tests.
        progress: Called as each call starts and finishes. A live recording takes
            tens of minutes with nothing written to disk until the end, so
            without this the only honest thing anyone can say about a run in
            flight is "it has not crashed".
        total: How many calls are expected, for the counter. Retries push the
            count past it, which is worth seeing rather than hiding.
    """

    def __init__(
        self,
        inner: ModelProvider,
        cache: DemoCache,
        *,
        clock: datetime | None = None,
        progress: ProgressFn | None = None,
        total: int = len(EXPECTED_STAGES),
        resume_from: DemoCache | None = None,
    ) -> None:
        self.inner = inner
        self.cache = cache
        self._clock = clock
        self._progress = progress
        self._total = total
        self._resume_from = resume_from
        self._chain_broken = False
        self._calls = 0
        self.recorded: list[str] = []
        self.reused: list[str] = []
        self.input_tokens = 0
        self.output_tokens = 0

    def _say(self, line: str) -> None:
        if self._progress is not None:
            self._progress(line)

    @property
    def provider_id(self) -> str:
        return self.inner.provider_id

    @property
    def model_id(self) -> str:
        return self.inner.model_id

    def _replay(self, request: ModelRequest) -> ModelResponse | None:
        """Serve an earlier recording instead of paying for it again.

        Only when the caller explicitly asked to resume. A recording run costs
        real money and most of it is usually stages that already worked; making
        someone re-buy those to fix one is waste. Every reuse is announced, so
        this cannot quietly serve something stale.
        """
        if self._resume_from is None:
            return None
        entry = self._resume_from.responses.get(request.cache_key)
        if entry is None:
            return None
        if request.skill in CHAINED_STAGES and self._chain_broken:
            self._say(
                f"  [{self._calls}/{self._total}] {request.skill} — recording again: an "
                "earlier stage it depends on was re-recorded"
            )
            return None

        self.cache.add(entry)
        if request.cache_key not in self.recorded:
            self.recorded.append(request.cache_key)
        if request.cache_key not in self.reused:
            self.reused.append(request.cache_key)
        self._say(
            f"  [{self._calls}/{self._total}] {request.skill} — reused an earlier "
            f"recording from {entry.recorded_at.date().isoformat()}, not called"
        )
        return ModelResponse(
            text=entry.text,
            provider=self.provider_id,
            model=entry.recorded_from_model,
            prompt_version=request.prompt_version,
            skill=request.skill,
            latency_ms=0,
            usage=ModelUsage(input_tokens=entry.input_tokens, output_tokens=entry.output_tokens),
            is_cached=True,
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        self._calls += 1
        reused = self._replay(request)
        if reused is not None:
            return reused

        started = time.perf_counter()
        self._say(f"  [{self._calls}/{self._total}] {request.skill} …")

        try:
            response = self.inner.complete(request)
        except Exception as exc:
            elapsed = time.perf_counter() - started
            self._say(
                f"  [{self._calls}/{self._total}] {request.skill} — failed after "
                f"{elapsed:.0f}s: {type(exc).__name__}"
            )
            raise

        if request.skill in CHAINED_STAGES:
            self._chain_broken = True

        elapsed = time.perf_counter() - started
        self._say(
            f"  [{self._calls}/{self._total}] {request.skill} — {elapsed:.0f}s, "
            f"{response.usage.input_tokens or 0:,} in / "
            f"{response.usage.output_tokens or 0:,} out"
        )

        # Only successful responses reach here, so a stage that needed a retry
        # records the attempt that worked. Replay therefore succeeds first time,
        # which is correct: the cache holds outcomes, not the path to them.
        self.cache.add(
            CachedResponse(
                key=request.cache_key,
                text=response.text,
                recorded_from_model=response.model,
                recorded_at=self._clock or datetime.now(),
                prompt_fingerprint=request.prompt_fingerprint,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                note=f"Recorded from {response.provider}/{response.model}.",
            )
        )
        if request.cache_key not in self.recorded:
            self.recorded.append(request.cache_key)
        self.input_tokens += response.usage.input_tokens or 0
        self.output_tokens += response.usage.output_tokens or 0
        return response


@dataclass(frozen=True)
class RunEstimate:
    """What a live run is about to cost, in the units that can be known up front."""

    calls: int
    evidence_records: int
    approx_input_tokens: int

    def describe(self) -> str:
        # "1 model calls" reads as a bug in the thing about to spend money, which
        # is the worst possible moment to look careless.
        calls = "1 model call" if self.calls == 1 else f"{self.calls} model calls"
        return (
            f"{calls} over {self.evidence_records} evidence records, "
            f"roughly {self.approx_input_tokens:,} input tokens (a character-based "
            "estimate, not a measurement). Output tokens and cost depend on the model."
        )


@dataclass
class RecordingSummary:
    """What a recording run actually did."""

    case_id: str
    keys: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    failures: list[str] = field(default_factory=list)
    #: Cache keys discarded because the stage that produced them was rejected.
    dropped: list[str] = field(default_factory=list)
    #: Cache keys served from an earlier recording instead of being called again.
    reused: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return bool(self.keys) and not self.failures

    def describe(self) -> str:
        minutes, seconds = divmod(int(self.elapsed_seconds), 60)
        lines = [
            f"Recorded {len(self.keys)} response(s) for {self.case_id} in {minutes}m {seconds}s.",
            f"Tokens: {self.input_tokens:,} in, {self.output_tokens:,} out (measured).",
        ]
        lines += [f"  {'~' if key in self.reused else '+'} {key}" for key in self.keys]
        if self.reused:
            lines.append(f"({len(self.reused)} marked ~ were reused, not called.)")
        if self.dropped:
            lines.append(f"{len(self.dropped)} response(s) discarded as unusable:")
            lines += [f"  - {key}" for key in self.dropped]
        if self.failures:
            lines.append(f"{len(self.failures)} stage(s) did not complete:")
            lines += [f"  ! {f}" for f in self.failures]
        return "\n".join(lines)


def estimate_run(records: Sequence[EvidenceRecord], *, calls: int = 8) -> RunEstimate:
    """Size a live run before committing to it.

    Eight calls by default: seven DecisionLens stages plus one baseline. Retries
    and the baseline's repair attempt are not counted, because they may not
    happen — this is a floor, and it says so.
    """
    characters = sum(len(r.content) + len(r.title) for r in records)
    return RunEstimate(
        calls=calls,
        evidence_records=len(records),
        approx_input_tokens=(characters // _CHARS_PER_TOKEN) * calls,
    )


def record_case(
    request: DecisionRequest,
    sources: Sequence[EvidenceSource],
    provider: ModelProvider,
    *,
    cache: DemoCache,
    as_of: date | None = None,
    clock: datetime | None = None,
    include_baseline: bool = True,
    timeout_seconds: float = LIVE_SKILL_TIMEOUT_SECONDS,
    progress: ProgressFn | None = None,
    resume_from: DemoCache | None = None,
) -> RecordingSummary:
    """Run both arms against a live provider and capture every response.

    Both arms on purpose. The demo is a comparison — the controlled workflow
    beside one well-prompted call on the same question and the same evidence —
    and a cache holding only one of them can only show half the argument. Phase
    10 needs the pair for the same reason.

    A stage that fails is recorded as a failure and does not stop the recording:
    the responses that did come back are still worth keeping, and a partial cache
    with a named gap is more useful than none.
    """
    recording = RecordingProvider(
        provider,
        cache,
        clock=clock,
        progress=progress,
        total=len(EXPECTED_STAGES) - (0 if include_baseline else 1),
        resume_from=resume_from,
    )
    summary = RecordingSummary(case_id=request.id)
    started = time.perf_counter()

    lens = DecisionLens(
        recording,
        sources,
        as_of=as_of,
        clock=clock,
        timeout_seconds=timeout_seconds,
    )
    brief = lens.run(request)
    if brief.run_trace is not None:
        summary.failures.extend(
            f"decisionlens/{s.name}: {s.error}" for s in brief.run_trace.failed_stages
        )
        _discard_rejected(cache, recording, brief, request.id, summary)

    if include_baseline:
        evidence = brief.evidence
        if not evidence:
            evidence = _retrieve_for_baseline(request, sources)
        baseline = StrongBaseline(recording, timeout_seconds=timeout_seconds, clock=clock)
        try:
            baseline.run(request, evidence)
        except BaselineError as exc:
            summary.failures.append(f"baseline: {exc}")
            # Same rule as the DecisionLens stages: a response its own arm
            # rejected must not be cached. The baseline runs outside the
            # orchestrator's trace, so it is dropped here rather than above.
            for key in list(cache.responses):
                if key.startswith(f"{request.id}::baseline"):
                    del cache.responses[key]
                    summary.dropped.append(key)
                    if key in recording.recorded:
                        recording.recorded.remove(key)

    summary.keys = list(recording.recorded)
    summary.input_tokens = recording.input_tokens
    summary.output_tokens = recording.output_tokens
    summary.reused = list(recording.reused)
    summary.elapsed_seconds = time.perf_counter() - started
    return summary


def _discard_rejected(
    cache: DemoCache,
    recording: RecordingProvider,
    brief: DecisionBrief,
    case_id: str,
    summary: RecordingSummary,
) -> None:
    """Remove responses whose own stage refused them.

    The wrapper records every call that came back over HTTP, which is the right
    place to sit — but a response can arrive intact and still be rejected by the
    skill that asked for it, for citing text that is not in the evidence or for
    naming a claim that does not exist. Caching one of those would ship a known
    bad answer under the label of a recorded result, and every later replay would
    fail the same check for the same reason.

    Found the hard way: the first real recording run cached a challenger response
    that had already been rejected for inventing claim ids.
    """
    if brief.run_trace is None:  # pragma: no cover - guarded by the caller
        return

    failed_skills = {stage.name.removesuffix("-retry") for stage in brief.run_trace.failed_stages}
    for skill in sorted(failed_skills):
        for key in list(cache.responses):
            if key.startswith(f"{case_id}::{skill}::"):
                del cache.responses[key]
                summary.dropped.append(key)
                if key in recording.recorded:
                    recording.recorded.remove(key)


def _retrieve_for_baseline(
    request: DecisionRequest, sources: Sequence[EvidenceSource]
) -> tuple[EvidenceRecord, ...]:
    """Fetch evidence for the baseline when the orchestrator ended up with none.

    Only reached when the DecisionLens run produced an empty brief. Both arms
    must see the same evidence for the comparison to mean anything, so this is a
    fallback rather than a second retrieval path.
    """
    evidence_request = EvidenceRequest(
        requested_by=request.user,
        product_area=request.user.product_area,
        time_period=request.time_period,
        labels=request.labels,
    )
    records: list[EvidenceRecord] = []
    for source in sources:
        records.extend(source.retrieve(evidence_request))
    return tuple(records)


def merge_into(cache: DemoCache, path: Path, *, drop: Sequence[str] = ()) -> tuple[int, int, int]:
    """Write a cache to disk, preserving entries this run did not touch.

    Returns ``(added, replaced, removed)``. Recording one case must not silently
    discard the recordings of another — a cache that loses entries every time it
    is written would make the demo depend on the order someone happened to run
    things in.

    ``drop`` removes keys from the file as well as omitting them. A stage that
    succeeded once and was rejected on a later run would otherwise leave the
    older, known-bad response in place, and re-recording would look like it had
    fixed something it had not.
    """
    existing = DemoCache.load(path) if path.is_file() else DemoCache()

    removed = 0
    for key in drop:
        if existing.responses.pop(key, None) is not None:
            removed += 1

    added = replaced = 0
    for key, entry in cache.responses.items():
        if key in existing.responses:
            replaced += 1
        else:
            added += 1
        existing.responses[key] = entry

    existing.save(path)
    return added, replaced, removed
