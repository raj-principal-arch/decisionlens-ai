"""A small command line for reproducibility.

Deliberately small. The Streamlit interface is the one built for a product
manager; this exists so a run can be repeated exactly, scripted, and diffed —
which is what Phase 10's evaluation needs, and what lets someone who did not
watch a run check the claim made about it.

Three commands:

    run       produce a brief from a case directory
    record    call a real model once and capture the responses for offline replay
    show      print what the demo cache already holds

``run`` never spends money unless the configuration already says to. ``record``
always does, and says how much before it starts: the command name is the consent,
and the preview is there so the amount is not a surprise. There is no flag that
makes ``run`` quietly go live.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import TextIO

from decision_lens import report
from decision_lens.case import BUNDLED_CASE, CaseError, LoadedCase, load_case
from decision_lens.config import ConfigError, ProviderChoice, Settings
from decision_lens.llm import CachedDemoProvider, DemoCache, ModelError, ModelProvider
from decision_lens.llm.anthropic_provider import AnthropicProvider
from decision_lens.llm.cached_provider import DEFAULT_CACHE_PATH
from decision_lens.models import (
    DecisionBrief,
    EvidenceRecord,
    EvidenceRequest,
    ValidationSeverity,
)
from decision_lens.orchestrator import DecisionLens, DecisionLensError
from decision_lens.recorder import (
    LIVE_SKILL_TIMEOUT_SECONDS,
    estimate_run,
    merge_into,
    record_case,
)
from decision_lens.skills import SKILL_TIMEOUT_SECONDS

__all__ = ["EXIT_BLOCKED", "EXIT_ERROR", "EXIT_OK", "build_parser", "main"]

DEFAULT_MODEL = "claude-opus-5"

EXIT_OK = 0
EXIT_ERROR = 1
#: A brief was produced but carries blocking errors. Distinct from a crash so a
#: script can tell "the system said no" from "the system fell over".
EXIT_BLOCKED = 2


def _default_case() -> Path:
    return Path("data") / BUNDLED_CASE


# --------------------------------------------------------------------------- #
# Shared plumbing
# --------------------------------------------------------------------------- #


def _load(args: argparse.Namespace) -> LoadedCase:
    return load_case(
        Path(args.case),
        question=args.question or "",
        desired_outcome=args.outcome or "",
        product_area=args.product_area or "",
        as_of=date.fromisoformat(args.as_of) if args.as_of else None,
    )


def _evidence_of(loaded: LoadedCase) -> tuple[EvidenceRecord, ...]:
    """Retrieve the case's evidence, for sizing a run before committing to it."""
    request = EvidenceRequest(
        requested_by=loaded.request.user,
        product_area=loaded.request.user.product_area,
    )
    return tuple(r for source in loaded.sources for r in source.retrieve(request))


def _write_outputs(
    loaded: LoadedCase,
    brief: DecisionBrief,
    out: Path | None,
    fmt: str,
    stream: TextIO,
    err: TextIO,
) -> None:
    """The artifact goes to `stream`; anything about the run goes to `err`.

    Standard stream hygiene, and load-bearing here: `decisionlens run --format
    json | jq` has to receive JSON and nothing else.
    """
    markdown = report.to_markdown(brief)
    payload = report.to_json(brief)

    if out is None:
        stream.write(payload if fmt == "json" else markdown)
        return

    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if fmt in {"md", "both"}:
        path = out / f"{loaded.case_id}.md"
        path.write_text(markdown, encoding="utf-8")
        written.append(path)
    if fmt in {"json", "both"}:
        path = out / f"{loaded.case_id}.json"
        path.write_text(payload, encoding="utf-8")
        written.append(path)
    for path in written:
        err.write(f"wrote {path}\n")


def _summarise(brief: DecisionBrief, stream: TextIO) -> int:
    errors = [i for i in brief.validation_issues if i.severity is ValidationSeverity.ERROR]
    warnings = [i for i in brief.validation_issues if i.severity is ValidationSeverity.WARNING]

    stream.write(
        f"\n{len(brief.evidence)} records · {len(brief.claims)} claims · "
        f"{len(brief.contradictions)} contradictions · {len(brief.missing_evidence)} gaps · "
        f"{len(brief.alternatives)} alternatives\n"
    )
    if brief.recommendation is not None:
        stream.write(
            f"recommendation: {brief.recommendation.option_kind.value} "
            f"(support: {brief.recommendation.support_level.value})\n"
        )
    else:
        stream.write("recommendation: none produced\n")
    stream.write(f"checks: {len(errors)} error(s), {len(warnings)} warning(s)\n")

    if errors:
        stream.write("\nThis brief should not be acted on as it stands:\n")
        for issue in errors:
            stream.write(f"  ! {issue.code}: {issue.message}\n")
        return EXIT_BLOCKED
    return EXIT_OK


def _report_settings_warnings(settings: Settings, stream: TextIO) -> None:
    """Surface configuration warnings rather than letting them sit unread.

    A `.env` value shadowing an exported variable is exactly the kind of thing
    someone loses twenty minutes to when nothing mentions it.
    """
    for warning in settings.warnings:
        stream.write(f"note: {warning}\n")


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #


def _provider_for_run(settings: Settings, cache_path: Path, stream: TextIO) -> ModelProvider:
    if settings.provider is ProviderChoice.ANTHROPIC:
        stream.write(f"provider: {settings.describe()}\n")
        return AnthropicProvider(
            settings.require_anthropic_key(), model=settings.model_name or DEFAULT_MODEL
        )
    stream.write("provider: cached-demo (recorded output, offline, free)\n")
    return CachedDemoProvider(cache_path)


def cmd_run(args: argparse.Namespace, stream: TextIO, err: TextIO) -> int:
    loaded = _load(args)
    settings = Settings.load()
    _report_settings_warnings(settings, err)

    live = settings.provider is ProviderChoice.ANTHROPIC
    provider = _provider_for_run(settings, Path(args.cache), err)

    err.write(f"case: {loaded.case_id} ({loaded.directory})\n")
    err.write(f"question: {loaded.request.question}\n")
    if loaded.notice:
        err.write(f"notice: {loaded.notice}\n")

    lens = DecisionLens(
        provider,
        loaded.sources,
        as_of=loaded.as_of,
        timeout_seconds=LIVE_SKILL_TIMEOUT_SECONDS if live else SKILL_TIMEOUT_SECONDS,
    )
    brief = lens.run(loaded.request)

    out = Path(args.out) if args.out else None
    _write_outputs(loaded, brief, out, args.format, stream, err)
    return _summarise(brief, err)


# --------------------------------------------------------------------------- #
# record
# --------------------------------------------------------------------------- #


def _confirm(stream: TextIO) -> bool:
    stream.write("Continue? [y/N] ")
    stream.flush()
    try:
        answer = input().strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def cmd_record(args: argparse.Namespace, stream: TextIO, err: TextIO) -> int:
    """Call a real model and capture the responses.

    Live by virtue of being this command. ``MODEL_PROVIDER`` is not consulted:
    typing ``record`` is the explicit act the provider-selection rule exists to
    require, and demanding an environment variable as well — for a command whose
    only purpose is to go live — is friction without safety.
    """
    loaded = _load(args)
    settings = Settings.load()
    _report_settings_warnings(settings, stream)

    api_key = settings.require_anthropic_key()
    model = args.model or settings.model_name or DEFAULT_MODEL
    total_calls = 7 if args.no_baseline else 8
    resume_from: DemoCache | None = None
    already: list[str] = []
    if args.resume and Path(args.cache).is_file():
        resume_from = DemoCache.load(Path(args.cache))
        already = sorted(k for k in resume_from.responses if k.startswith(f"{loaded.case_id}::"))
    estimate = estimate_run(_evidence_of(loaded), calls=max(0, total_calls - len(already)))

    stream.write(f"\ncase:  {loaded.case_id}\nmodel: {model}\nkey:   {settings.masked_key}\n")
    stream.write(f"{estimate.describe()}\n")
    if already:
        stream.write(
            f"\nResuming: {len(already)} stage(s) already recorded will be reused, not called.\n"
        )
        # Not `key` — that name holds the API key, and rebinding it here sent a
        # cache key as the credential. Cost two failed runs and an accusation
        # that Anthropic had revoked a working key.
        for cached_key in already:
            stream.write(f"  ~ {cached_key}\n")
        stream.write("  Delete an entry from the cache to force it to be recorded again.\n")
    stream.write("\nThis calls a real model and will be billed to that key.\n")

    if not args.yes and not _confirm(stream):
        stream.write("Nothing was sent.\n")
        return EXIT_OK

    def report(line: str) -> None:
        """Flush every line.

        Without this the whole run buffers and prints at the end, which is the
        same as having no progress at all — the point is to be readable while
        the thing nobody can see is still happening.
        """
        stream.write(line + "\n")
        stream.flush()

    stream.write("\nRecording. Each stage is one call to the model.\n")
    cache = DemoCache()
    try:
        summary = record_case(
            loaded.request,
            loaded.sources,
            AnthropicProvider(api_key, model=model),
            cache=cache,
            as_of=loaded.as_of,
            include_baseline=not args.no_baseline,
            progress=report,
            resume_from=resume_from,
        )
    except (DecisionLensError, ModelError) as exc:
        stream.write(f"\nrecording failed: {exc}\n")
        return EXIT_ERROR

    stream.write("\n" + summary.describe() + "\n")
    if not summary.keys:
        stream.write("Nothing was recorded, so the cache was left alone.\n")
        return EXIT_ERROR

    added, replaced, removed = merge_into(cache, Path(args.cache), drop=summary.dropped)
    stream.write(f"\n{args.cache}: {added} added, {replaced} replaced, {removed} removed\n")
    stream.write("The offline demo now works with no key. Run `make demo`.\n")
    return EXIT_OK if summary.succeeded else EXIT_BLOCKED


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #


def cmd_show(args: argparse.Namespace, stream: TextIO, err: TextIO) -> int:
    path = Path(args.cache)
    if not path.is_file():
        stream.write(f"no cache at {path}\n")
        return EXIT_ERROR

    cache = DemoCache.load(path)
    if not cache.responses:
        stream.write(
            f"{path} holds no recorded responses.\n"
            "Run `decisionlens record` once with an API key to populate it.\n"
        )
        return EXIT_ERROR

    stream.write(f"{path}: {len(cache.responses)} recorded response(s)\n\n")
    for key in sorted(cache.responses):
        entry = cache.responses[key]
        stream.write(
            f"  {key}\n"
            f"      from {entry.recorded_from_model} on "
            f"{entry.recorded_at.date().isoformat()} · {len(entry.text):,} chars\n"
        )
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def _add_case_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case", default=str(_default_case()), help="case directory")
    parser.add_argument("--question", help="override the manifest's question")
    parser.add_argument("--outcome", help="override the desired outcome")
    parser.add_argument("--product-area", dest="product_area", help="override the product area")
    parser.add_argument("--as-of", dest="as_of", help="date staleness is measured against")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH), help="recorded-response file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="decisionlens",
        description="Evidence-grounded decision support. Runs offline from recorded output.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser(
        "run", help="produce a brief; offline unless MODEL_PROVIDER says otherwise"
    )
    _add_case_args(run)
    run.add_argument("--out", help="directory to write the brief into; omit to print")
    run.add_argument("--format", choices=("md", "json", "both"), default="md")
    run.set_defaults(handler=cmd_run)

    record = sub.add_parser("record", help="call a real model and capture responses for replay")
    _add_case_args(record)
    record.add_argument("--model", help=f"model id; defaults to {DEFAULT_MODEL}")
    record.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    record.add_argument(
        "--no-baseline", action="store_true", help="record only the DecisionLens arm"
    )
    record.add_argument(
        "--resume",
        action="store_true",
        help="reuse stages already in the cache instead of paying for them again",
    )
    record.set_defaults(handler=cmd_record)

    show = sub.add_parser("show", help="list what the demo cache already holds")
    show.add_argument("--cache", default=str(DEFAULT_CACHE_PATH))
    show.set_defaults(handler=cmd_show)

    return parser


def main(
    argv: list[str] | None = None,
    stream: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run one command.

    Two streams: `stream` carries the artifact, `err` carries everything about
    the run. Tests pass the same buffer for both when they want to read it all
    together; on a terminal they are stdout and stderr, so piping works.
    """
    out = stream or sys.stdout
    diagnostics = err if err is not None else (sys.stderr if stream is None else out)
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args, out, diagnostics))
    except (CaseError, ConfigError, DecisionLensError) as exc:
        diagnostics.write(f"\nerror: {exc}\n")
        return EXIT_ERROR
    except ModelError as exc:
        diagnostics.write(f"\nmodel error: {exc}\n")
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
