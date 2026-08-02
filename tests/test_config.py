"""Configuration: env parsing, provider selection, credential handling.

The load-bearing tests here are the ones about the credential — that a key alone
never selects a paid provider, and that the key cannot reach a printable surface.
Both are properties a reader has to be able to trust without auditing call sites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision_lens.config import (
    ANTHROPIC_KEY_PREFIX,
    DEFAULT_ANTHROPIC_MODEL,
    ConfigError,
    ProviderChoice,
    Settings,
    find_env_file,
    load_env_file,
    parse_env_file,
)

KEY = f"{ANTHROPIC_KEY_PREFIX}api03-REDACTEDTESTVALUE-9xyz"


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def test_parse_reads_pairs_and_ignores_comments_and_blanks() -> None:
    values, problems = parse_env_file(
        "# a comment\n"
        "\n"
        "MODEL_PROVIDER=anthropic\n"
        "   \n"
        "  MODEL_NAME = claude-opus-5  \n"
        "# trailing comment\n"
    )
    assert values == {"MODEL_PROVIDER": "anthropic", "MODEL_NAME": "claude-opus-5"}
    assert problems == ()


def test_parse_strips_export_prefix_and_matching_quotes() -> None:
    values, problems = parse_env_file(
        'export ANTHROPIC_API_KEY="quoted-value"\n'
        "export MODEL_NAME='single'\n"
        "LOG_LEVEL=\"mismatched'\n"
    )
    assert values["ANTHROPIC_API_KEY"] == "quoted-value"
    assert values["MODEL_NAME"] == "single"
    # Mismatched quotes are left alone rather than half-stripped.
    assert values["LOG_LEVEL"] == "\"mismatched'"
    assert problems == ()


def test_parse_keeps_equals_signs_inside_the_value() -> None:
    values, _ = parse_env_file("ANTHROPIC_API_KEY=abc=def==\n")
    assert values["ANTHROPIC_API_KEY"] == "abc=def=="


def test_parse_reports_unreadable_lines_instead_of_dropping_them() -> None:
    """A mistyped line that silently does nothing wastes someone's afternoon."""
    values, problems = parse_env_file("MODEL_PROVIDER anthropic\n=orphan\nMODEL_NAME=ok\n")
    assert values == {"MODEL_NAME": "ok"}
    assert len(problems) == 2
    assert "line 1" in problems[0]
    assert "line 2" in problems[1]
    assert "empty key" in problems[1]


def test_parse_allows_an_empty_value() -> None:
    values, problems = parse_env_file("MODEL_PROVIDER=\n")
    assert values == {"MODEL_PROVIDER": ""}
    assert problems == ()


# --------------------------------------------------------------------------- #
# Locating and reading the file
# --------------------------------------------------------------------------- #


def test_find_env_file_searches_upward_from_a_subdirectory(tmp_path: Path) -> None:
    _write(tmp_path / ".env", "MODEL_NAME=x\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_env_file(nested) == (tmp_path / ".env").resolve()


def test_find_env_file_prefers_the_nearest_one(tmp_path: Path) -> None:
    _write(tmp_path / ".env", "MODEL_NAME=outer\n")
    nested = tmp_path / "a"
    nested.mkdir()
    _write(nested / ".env", "MODEL_NAME=inner\n")
    assert find_env_file(nested) == (nested / ".env").resolve()


def test_find_env_file_returns_none_when_there_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Forced rather than assumed: a stray .env above the temp directory would
    # otherwise make this pass or fail depending on the machine.
    monkeypatch.setattr(Path, "is_file", lambda _self: False)
    assert find_env_file(tmp_path) is None


def test_load_env_file_treats_a_missing_file_as_empty(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "absent") == ({}, ())
    assert load_env_file(None) == ({}, ())


def test_load_env_file_prefixes_problems_with_the_path(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "nonsense\n")
    _, problems = load_env_file(path)
    assert len(problems) == 1
    assert str(path) in problems[0]


def test_load_env_file_reports_an_unreadable_file_rather_than_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / ".env", "MODEL_NAME=x\n")

    def boom(*_args: object, **_kwargs: object) -> str:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", boom)
    values, problems = load_env_file(path)
    assert values == {}
    assert "could not be read" in problems[0]


# --------------------------------------------------------------------------- #
# Provider selection
# --------------------------------------------------------------------------- #


def test_default_is_cached_even_when_a_key_is_present(tmp_path: Path) -> None:
    """The rule the whole module exists for.

    Developers commonly export ANTHROPIC_API_KEY globally. Finding one is not
    permission to start spending money.
    """
    settings = Settings.load(environ={"ANTHROPIC_API_KEY": KEY}, env_path=tmp_path / "absent")
    assert settings.provider is ProviderChoice.CACHED
    assert settings.anthropic_api_key == KEY


def test_provider_is_selected_only_by_model_provider(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", f"MODEL_PROVIDER=anthropic\nANTHROPIC_API_KEY={KEY}\n")
    settings = Settings.load(environ={}, env_path=path)
    assert settings.provider is ProviderChoice.ANTHROPIC


def test_provider_name_is_case_insensitive(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "MODEL_PROVIDER=Anthropic\n")
    assert Settings.load(environ={}, env_path=path).provider is ProviderChoice.ANTHROPIC


def test_blank_provider_means_cached(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "MODEL_PROVIDER=\n")
    assert Settings.load(environ={}, env_path=path).provider is ProviderChoice.CACHED


def test_an_unknown_provider_is_rejected_by_name(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "MODEL_PROVIDER=openai\n")
    with pytest.raises(ConfigError, match="not a provider DecisionLens has"):
        Settings.load(environ={}, env_path=path)


def test_the_env_file_wins_over_the_environment_and_says_so(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "MODEL_NAME=from-file\n")
    settings = Settings.load(environ={"MODEL_NAME": "from-environment"}, env_path=path)
    assert settings.model_name == "from-file"
    assert any("MODEL_NAME is set in both" in w for w in settings.warnings)


def test_no_warning_when_the_two_sources_agree(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "MODEL_NAME=same\n")
    settings = Settings.load(environ={"MODEL_NAME": "same"}, env_path=path)
    assert settings.warnings == ()


def test_the_environment_is_used_when_the_file_omits_a_value(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "MODEL_PROVIDER=\n")
    settings = Settings.load(environ={"MODEL_NAME": "claude-opus-5"}, env_path=path)
    assert settings.model_name == "claude-opus-5"
    assert settings.warnings == ()


def test_parse_problems_reach_the_settings_warnings(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "garbage\n")
    assert Settings.load(environ={}, env_path=path).warnings


def test_log_level_is_normalised(tmp_path: Path) -> None:
    path = _write(tmp_path / ".env", "LOG_LEVEL=debug\n")
    assert Settings.load(environ={}, env_path=path).log_level == "DEBUG"


def test_load_discovers_the_file_when_no_path_is_given(tmp_path: Path) -> None:
    _write(tmp_path / ".env", "MODEL_NAME=discovered\n")
    assert Settings.load(environ={}, search_from=tmp_path).model_name == "discovered"


def test_load_falls_back_to_os_environ_when_no_mapping_is_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_NAME", "from-os-environ")
    settings = Settings.load(env_path=tmp_path / "absent")
    assert settings.model_name == "from-os-environ"


# --------------------------------------------------------------------------- #
# Credential handling
# --------------------------------------------------------------------------- #


def test_a_missing_key_names_the_file_to_edit() -> None:
    settings = Settings(provider=ProviderChoice.ANTHROPIC)
    with pytest.raises(ConfigError, match=r"\.env"):
        settings.require_anthropic_key()


def test_a_malformed_key_fails_before_anything_is_sent() -> None:
    settings = Settings(provider=ProviderChoice.ANTHROPIC, anthropic_api_key="paste-key-here")
    with pytest.raises(ConfigError, match="Nothing was sent"):
        settings.require_anthropic_key()


def test_a_well_formed_key_is_returned() -> None:
    settings = Settings(provider=ProviderChoice.ANTHROPIC, anthropic_api_key=KEY)
    assert settings.require_anthropic_key() == KEY


def test_masked_key_shows_four_characters() -> None:
    settings = Settings(anthropic_api_key=KEY)
    masked = settings.masked_key
    assert masked.endswith(KEY[-4:])
    assert KEY not in masked


def test_masked_key_when_unset() -> None:
    assert Settings().masked_key == "(not set)"


def test_the_key_cannot_reach_repr_or_a_dump() -> None:
    """Anything printable is a place a credential can leak. This closes both."""
    settings = Settings(provider=ProviderChoice.ANTHROPIC, anthropic_api_key=KEY)

    assert KEY not in repr(settings)
    assert KEY not in str(settings)
    assert "anthropic_api_key" not in settings.model_dump()
    assert KEY not in json.dumps(settings.model_dump(mode="json"))
    assert KEY not in settings.model_dump_json()
    assert KEY not in settings.describe()


def test_describe_names_the_cached_provider_plainly() -> None:
    assert "cached-demo" in Settings().describe()


def test_describe_reports_the_live_model_and_a_masked_key() -> None:
    described = Settings(provider=ProviderChoice.ANTHROPIC, anthropic_api_key=KEY).describe()
    assert DEFAULT_ANTHROPIC_MODEL in described
    assert described.endswith(KEY[-4:])


def test_describe_reports_an_overridden_model() -> None:
    described = Settings(
        provider=ProviderChoice.ANTHROPIC, anthropic_api_key=KEY, model_name="claude-sonnet-5"
    ).describe()
    assert "claude-sonnet-5" in described
