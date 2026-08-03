"""The command line, and the case loader beneath it.

Every test pins configuration explicitly. `Settings.load()` searches upward for a
`.env`, and the repository has a real one with a real key in it — a test that let
it resolve normally could pick up a developer's credential and, if their
MODEL_PROVIDER happened to say so, spend their money during `make check`.
"""

from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

import pytest

from decision_lens import cli
from decision_lens.case import CaseError, LoadedCase, load_case
from decision_lens.config import ProviderChoice, Settings
from decision_lens.llm import ModelUnavailable
from tests.scripted import CASE_ID, QUESTION, case_with_cache, write_case

KEY = "sk-ant-api03-REDACTEDTESTVALUE-9xyz"


@pytest.fixture(autouse=True)
def _no_ambient_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a real `.env` reach the CLI during tests."""
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls, **_: Settings()))


def _run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = cli.main(list(argv), stream=out)
    return code, out.getvalue()


# --------------------------------------------------------------------------- #
# Loading a case
# --------------------------------------------------------------------------- #


def test_a_case_runs_from_its_manifest_with_no_arguments(tmp_path: Path) -> None:
    """The difference between a reviewer trying it and reading about it."""
    directory = write_case(tmp_path)
    loaded = load_case(directory)

    assert loaded.case_id == CASE_ID
    assert loaded.request.question == QUESTION
    assert loaded.request.user.product_area == "delivery"
    assert loaded.as_of == date(2026, 8, 2)
    assert loaded.notice


def test_the_question_can_be_overridden(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    loaded = load_case(directory, question="Should we defer this entirely?")
    assert loaded.request.question == "Should we defer this entirely?"


def test_a_missing_directory_is_named(tmp_path: Path) -> None:
    with pytest.raises(CaseError, match="not a directory"):
        load_case(tmp_path / "absent")


def test_a_directory_without_a_manifest_says_what_is_missing(tmp_path: Path) -> None:
    (tmp_path / "bare").mkdir()
    with pytest.raises(CaseError, match="case_manifest.json"):
        load_case(tmp_path / "bare")


def test_a_malformed_manifest_is_rejected(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    (directory / "case_manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CaseError, match="not valid JSON"):
        load_case(directory)


def test_a_manifest_that_is_not_an_object_is_rejected(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    (directory / "case_manifest.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(CaseError, match="JSON object"):
        load_case(directory)


def test_a_case_with_no_question_cannot_be_run(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    manifest = json.loads((directory / "case_manifest.json").read_text())
    manifest["question"] = ""
    (directory / "case_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CaseError, match="not a directory to ask|No question"):
        load_case(directory)


def test_a_statement_is_not_a_decision_question(tmp_path: Path) -> None:
    directory = write_case(tmp_path, question="We should build an AI assistant.")
    with pytest.raises(CaseError, match="ends in"):
        load_case(directory)


def test_an_unreadable_as_of_date_is_rejected(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    manifest = json.loads((directory / "case_manifest.json").read_text())
    manifest["as_of"] = "last tuesday"
    (directory / "case_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CaseError, match="YYYY-MM-DD"):
        load_case(directory)


def test_a_missing_as_of_defaults_to_today(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    manifest = json.loads((directory / "case_manifest.json").read_text())
    del manifest["as_of"]
    (directory / "case_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert load_case(directory).as_of == date.today()


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #


def test_run_produces_a_brief_and_exits_clean(tmp_path: Path) -> None:
    directory, cache = case_with_cache(tmp_path)
    code, out = _run("run", "--case", str(directory), "--cache", str(cache))

    assert code == cli.EXIT_OK
    assert "cached-demo" in out
    assert "# Decision brief" in out
    assert "recommendation: data_quality" in out


def test_run_writes_both_formats(tmp_path: Path) -> None:
    directory, cache = case_with_cache(tmp_path)
    out_dir = tmp_path / "out"
    code, out = _run(
        "run",
        "--case",
        str(directory),
        "--cache",
        str(cache),
        "--out",
        str(out_dir),
        "--format",
        "both",
    )

    assert code == cli.EXIT_OK
    assert (out_dir / f"{CASE_ID}.md").is_file()
    assert (out_dir / f"{CASE_ID}.json").is_file()
    assert "wrote" in out


def test_printed_json_is_pipeable(tmp_path: Path) -> None:
    """`decisionlens run --format json | jq` must receive JSON and nothing else."""
    directory, cache = case_with_cache(tmp_path)
    payload_stream, diagnostics = io.StringIO(), io.StringIO()
    code = cli.main(
        ["run", "--case", str(directory), "--cache", str(cache), "--format", "json"],
        stream=payload_stream,
        err=diagnostics,
    )

    assert code == cli.EXIT_OK
    payload = json.loads(payload_stream.getvalue())
    assert payload["brief"]["id"] == f"DL-{CASE_ID}"
    assert "cached-demo" in diagnostics.getvalue(), "diagnostics still reach the operator"


def test_run_exits_two_when_the_brief_carries_blocking_errors(tmp_path: Path) -> None:
    """A script must be able to tell 'the system said no' from 'it fell over'."""
    directory = write_case(tmp_path)
    empty = tmp_path / "empty.json"
    empty.write_text('{"responses":{}}', encoding="utf-8")

    code, out = _run("run", "--case", str(directory), "--cache", str(empty))
    assert code == cli.EXIT_BLOCKED
    assert "should not be acted on" in out


def test_run_reports_a_bad_case_without_a_traceback(tmp_path: Path) -> None:
    code, out = _run("run", "--case", str(tmp_path / "nope"))
    assert code == cli.EXIT_ERROR
    assert "error:" in out


def test_run_overrides_reach_the_brief(tmp_path: Path) -> None:
    directory, cache = case_with_cache(tmp_path)
    _, out = _run(
        "run",
        "--case",
        str(directory),
        "--cache",
        str(cache),
        "--question",
        "Should we defer this entirely?",
        "--as-of",
        "2027-01-01",
    )
    assert "Should we defer this entirely?" in out


def test_run_surfaces_configuration_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, cache = case_with_cache(tmp_path)
    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(warnings=("MODEL_NAME shadowed",)))
    )
    _, out = _run("run", "--case", str(directory), "--cache", str(cache))
    assert "note: MODEL_NAME shadowed" in out


def test_run_stays_offline_when_a_key_exists_but_the_provider_is_not_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A credential is not consent. Asserted at the CLI as well as the factory."""
    directory, cache = case_with_cache(tmp_path)
    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    code, out = _run("run", "--case", str(directory), "--cache", str(cache))
    assert code == cli.EXIT_OK
    assert "cached-demo" in out
    assert KEY not in out


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #


def test_show_lists_what_the_cache_holds(tmp_path: Path) -> None:
    _, cache = case_with_cache(tmp_path)
    code, out = _run("show", "--cache", str(cache))

    assert code == cli.EXIT_OK
    assert f"{CASE_ID}::recommendation::v1" in out
    assert "claude-opus-5" in out


def test_show_says_plainly_when_the_cache_is_empty(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text('{"responses":{}}', encoding="utf-8")
    code, out = _run("show", "--cache", str(empty))

    assert code == cli.EXIT_ERROR
    assert "decisionlens record" in out


def test_show_reports_a_missing_cache_file(tmp_path: Path) -> None:
    code, out = _run("show", "--cache", str(tmp_path / "absent.json"))
    assert code == cli.EXIT_ERROR
    assert "no cache at" in out


# --------------------------------------------------------------------------- #
# record — the only command that spends money
# --------------------------------------------------------------------------- #


def test_record_needs_a_key_and_says_which_file_to_edit(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    code, out = _run("record", "--case", str(directory))
    assert code == cli.EXIT_ERROR
    assert ".env" in out


def test_record_previews_the_size_and_stops_without_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command name is the consent; the preview is so the amount is not a surprise."""
    directory = write_case(tmp_path)
    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "_confirm", lambda _stream: False)

    code, out = _run("record", "--case", str(directory))
    assert code == cli.EXIT_OK
    assert "model calls" in out
    assert "will be billed" in out
    assert "Nothing was sent." in out


def test_record_never_prints_the_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = write_case(tmp_path)
    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "_confirm", lambda _stream: False)

    _, out = _run("record", "--case", str(directory))
    assert KEY not in out
    assert out.count("sk-ant-…") == 1


def test_the_provider_choice_enum_is_what_selects_live() -> None:
    assert Settings().provider is ProviderChoice.CACHED
    assert Settings(provider=ProviderChoice.ANTHROPIC).provider is ProviderChoice.ANTHROPIC


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #


def test_every_command_is_registered() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    for command in ("run", "record", "show"):
        assert parser.parse_args([command]).command == command


def test_the_default_case_is_the_bundled_one() -> None:
    args = cli.build_parser().parse_args(["run"])
    assert args.case.endswith("sample_delivery_exceptions")


def test_loaded_case_reports_that_it_is_synthetic(tmp_path: Path) -> None:
    loaded: LoadedCase = load_case(write_case(tmp_path))
    assert loaded.is_synthetic


# --------------------------------------------------------------------------- #
# The live paths, without going live
# --------------------------------------------------------------------------- #


def test_the_bundled_case_directory_is_where_the_sample_lives(tmp_path: Path) -> None:
    from decision_lens.case import bundled_case_dir

    assert bundled_case_dir(tmp_path) == tmp_path / "data" / "sample_delivery_exceptions"
    assert bundled_case_dir().name == "sample_delivery_exceptions"


def test_selecting_anthropic_builds_the_live_provider_for_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`run` honours MODEL_PROVIDER; it does not have a flag of its own."""
    directory, cache = case_with_cache(tmp_path)
    built: dict[str, str] = {}

    class Stub:
        provider_id = "anthropic"
        model_id = "claude-opus-5"

        def __init__(self, key: str, *, model: str) -> None:
            built["key"] = key
            built["model"] = model

        def complete(self, request: object) -> object:
            # Fail like a real provider would: the point of this test is which
            # provider got built, not what it returned.
            raise ModelUnavailable("not making a real call in a test")

    monkeypatch.setattr(
        Settings,
        "load",
        classmethod(
            lambda cls, **_: Settings(
                provider=ProviderChoice.ANTHROPIC,
                anthropic_api_key=KEY,
                model_name="claude-sonnet-5",
            )
        ),
    )
    monkeypatch.setattr(cli, "AnthropicProvider", Stub)

    code, out = _run("run", "--case", str(directory), "--cache", str(cache))

    assert built == {"key": KEY, "model": "claude-sonnet-5"}
    assert "provider=anthropic" in out
    assert KEY not in out, "the key is masked even in the provider line"
    assert code == cli.EXIT_BLOCKED, "every stage failed, so the brief is unusable"


def test_record_writes_the_cache_and_says_the_demo_now_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decision_lens.llm import CachedResponse, DemoCache
    from decision_lens.recorder import RecordingSummary

    directory = write_case(tmp_path)
    target = tmp_path / "written.json"

    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "AnthropicProvider", lambda key, *, model: object())

    def fake_record(request: object, sources: object, provider: object, **kwargs: object) -> object:
        # The CLI has to hand the recorder a working progress callback, or a run
        # that takes tens of minutes shows nothing at all while it happens.
        progress = kwargs["progress"]
        assert callable(progress)
        progress("  [1/8] relevance …")

        cache = kwargs["cache"]
        assert isinstance(cache, DemoCache)
        cache.add(
            CachedResponse(
                key=f"{CASE_ID}::relevance::v1",
                text="{}",
                recorded_from_model="claude-opus-5",
                recorded_at=__import__("datetime").datetime(2026, 8, 1, 12, 0, 0),
            )
        )
        return RecordingSummary(case_id=CASE_ID, keys=[f"{CASE_ID}::relevance::v1"])

    monkeypatch.setattr(cli, "record_case", fake_record)

    code, out = _run("record", "--case", str(directory), "--cache", str(target), "--yes")

    assert code == cli.EXIT_OK
    assert target.is_file()
    assert "1 added, 0 replaced" in out
    assert "make demo" in out
    assert KEY not in out
    assert "[1/8] relevance" in out, "progress reached the operator"


def test_record_reports_a_failure_without_writing_a_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = write_case(tmp_path)
    target = tmp_path / "unwritten.json"

    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "AnthropicProvider", lambda key, *, model: object())

    def boom(*_a: object, **_k: object) -> object:
        raise ModelUnavailable("Anthropic rejected the API key")

    monkeypatch.setattr(cli, "record_case", boom)

    code, out = _run("record", "--case", str(directory), "--cache", str(target), "--yes")
    assert code == cli.EXIT_ERROR
    assert "recording failed" in out
    assert not target.exists()


def test_record_that_captures_nothing_leaves_the_cache_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decision_lens.recorder import RecordingSummary

    directory = write_case(tmp_path)
    target = tmp_path / "untouched.json"

    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "AnthropicProvider", lambda key, *, model: object())
    monkeypatch.setattr(
        cli, "record_case", lambda *a, **k: RecordingSummary(case_id=CASE_ID, keys=[])
    )

    code, out = _run("record", "--case", str(directory), "--cache", str(target), "--yes")
    assert code == cli.EXIT_ERROR
    assert "cache was left alone" in out
    assert not target.exists()


def test_a_partial_recording_exits_blocked_rather_than_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decision_lens.recorder import RecordingSummary

    directory = write_case(tmp_path)
    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "AnthropicProvider", lambda key, *, model: object())
    monkeypatch.setattr(
        cli,
        "record_case",
        lambda *a, **k: RecordingSummary(
            case_id=CASE_ID, keys=["k"], failures=["decisionlens/contradictions: down"]
        ),
    )

    code, _ = _run("record", "--case", str(directory), "--cache", str(tmp_path / "c.json"), "--yes")
    assert code == cli.EXIT_BLOCKED


def test_a_model_error_is_reported_without_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    """`build_parser` runs inside `main`, so patching the handler here takes effect."""

    def boom(*_a: object, **_k: object) -> int:
        raise ModelUnavailable("provider unreachable")

    monkeypatch.setattr(cli, "cmd_run", boom)

    code, out = _run("run")
    assert code == cli.EXIT_ERROR
    assert "model error: provider unreachable" in out


def test_the_confirmation_prompt_reads_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    out = io.StringIO()
    monkeypatch.setattr("builtins.input", lambda: "y")
    assert cli._confirm(out) is True
    monkeypatch.setattr("builtins.input", lambda: "")
    assert cli._confirm(out) is False


def test_an_unanswerable_prompt_declines(monkeypatch: pytest.MonkeyPatch) -> None:
    """No tty, no consent. Never default to spending money."""

    def eof() -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert cli._confirm(io.StringIO()) is False


def test_resume_previews_what_will_be_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The saving has to be visible before consenting, like the cost is."""
    directory, cache = case_with_cache(tmp_path)
    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "_confirm", lambda _stream: False)

    _, out = _run("record", "--case", str(directory), "--cache", str(cache), "--resume")

    assert "will be reused, not called" in out
    assert f"~ {CASE_ID}::relevance::v1" in out
    assert "Delete an entry from the cache to force it" in out
    assert "Nothing was sent." in out


def test_without_resume_nothing_is_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory, cache = case_with_cache(tmp_path)
    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "_confirm", lambda _stream: False)

    _, out = _run("record", "--case", str(directory), "--cache", str(cache))
    assert "will be reused" not in out


def test_the_real_api_key_reaches_the_provider_when_resuming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the resume preview looped over `key`, clobbering the credential.

    The preview printed cache keys with `for key in already:`, rebinding the
    name that held the API key. The provider was then constructed with
    'sample_delivery_exceptions::relevance::v1' and Anthropic answered 401 —
    which reads exactly like a revoked key, and was diagnosed as one twice.

    Nothing type-checks this: both values are `str`. Only asserting the value
    catches it.
    """
    directory, cache = case_with_cache(tmp_path)
    got: dict[str, str] = {}

    class Spy:
        provider_id = "anthropic"
        model_id = "claude-opus-5"

        def __init__(self, api_key: str, *, model: str) -> None:
            got["api_key"] = api_key
            got["model"] = model

        def complete(self, request: object) -> object:
            raise ModelUnavailable("no calls in tests")

    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "AnthropicProvider", Spy)

    _run("record", "--case", str(directory), "--cache", str(cache), "--resume", "--yes")

    assert got["api_key"] == KEY, "the credential, not a cache key"
    assert "::" not in got["api_key"], "a cache key was passed as the credential"
    assert got["model"] == "claude-opus-5"


def test_the_real_api_key_reaches_the_provider_without_resuming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = write_case(tmp_path)
    got: dict[str, str] = {}

    class Spy:
        provider_id = "anthropic"
        model_id = "claude-opus-5"

        def __init__(self, api_key: str, *, model: str) -> None:
            got["api_key"] = api_key

        def complete(self, request: object) -> object:
            raise ModelUnavailable("no calls in tests")

    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "AnthropicProvider", Spy)

    _run("record", "--case", str(directory), "--cache", str(tmp_path / "c.json"), "--yes")
    assert got["api_key"] == KEY


def test_the_preview_counts_only_what_will_really_be_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A preview that over-promises is worse than none — it is consented to.

    Listing every cached entry claimed savings the run would not deliver:
    anything downstream of a gap is re-recorded, so it is not reused.
    """
    from decision_lens.llm import DemoCache

    directory, cache = case_with_cache(tmp_path)
    # Remove a stage in the middle of the chain. `challenger` stays in the file
    # but depends on it, so it must not be counted as reusable.
    loaded_cache = DemoCache.load(cache)
    del loaded_cache.responses[f"{CASE_ID}::recommendation::v1"]
    loaded_cache.save(cache)

    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "_confirm", lambda _stream: False)

    _, out = _run("record", "--case", str(directory), "--cache", str(cache), "--resume")

    # The fixture caches the seven DecisionLens stages and no baseline, so
    # removing `recommendation` leaves five reusable: the chain up to the gap.
    assert "5 stage(s) already recorded will be reused" in out
    assert f"~ {CASE_ID}::alternatives::v1" in out, "before the gap"
    assert f"~ {CASE_ID}::challenger::v1" not in out, "downstream of the gap"
    assert "3 model calls" in out, "recommendation, challenger, and the baseline"


def test_another_case_in_the_same_cache_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One cache file can hold several cases. Only this case's entries count.

    A neighbouring case's `relevance` recording is not this case's coverage, and
    counting it would preview a saving the run cannot deliver.
    """
    from decision_lens.llm import DemoCache

    directory, cache = case_with_cache(tmp_path)
    loaded_cache = DemoCache.load(cache)
    borrowed = loaded_cache.responses[f"{CASE_ID}::relevance::v1"]
    del loaded_cache.responses[f"{CASE_ID}::relevance::v1"]
    loaded_cache.responses["a_different_case::relevance::v1"] = borrowed
    loaded_cache.save(cache)

    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "_confirm", lambda _stream: False)

    _, out = _run("record", "--case", str(directory), "--cache", str(cache), "--resume")

    # relevance is the head of the chain, so losing it makes everything after it
    # unusable too: nothing is reused and the full run is quoted.
    assert "will be reused, not called" not in out
    assert "a_different_case" not in out
    assert "8 model calls" in out


def test_a_stage_cached_under_an_old_prompt_version_is_quoted_as_a_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug that previewed "0 model calls" and then billed one.

    The recorder looks up the whole cache key, version included, so a recording
    made under a superseded prompt is a miss. The preview has to agree with it.
    """
    from decision_lens.llm import DemoCache

    directory, cache = case_with_cache(tmp_path)
    loaded_cache = DemoCache.load(cache)
    stale = loaded_cache.responses[f"{CASE_ID}::challenger::v1"]
    del loaded_cache.responses[f"{CASE_ID}::challenger::v1"]
    loaded_cache.responses[f"{CASE_ID}::challenger::v0"] = stale
    loaded_cache.save(cache)

    monkeypatch.setattr(
        Settings, "load", classmethod(lambda cls, **_: Settings(anthropic_api_key=KEY))
    )
    monkeypatch.setattr(cli, "_confirm", lambda _stream: False)

    _, out = _run("record", "--case", str(directory), "--cache", str(cache), "--resume")

    assert f"~ {CASE_ID}::challenger::v0" not in out, "a superseded entry is not coverage"
    assert f"~ {CASE_ID}::challenger::v1" not in out, "and it is not silently upgraded either"
    assert "6 stage(s) already recorded will be reused" in out
    assert "2 model calls" in out, "the challenger, and the baseline"
