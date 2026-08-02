"""Runtime configuration: which provider answers, and with what credential.

DecisionLens runs from recorded output by default. Going live is an explicit act,
and this module is where that line is drawn. Three rules it enforces rather than
documents:

*   **Selection is explicit; a key is never a trigger.** Finding
    ``ANTHROPIC_API_KEY`` in the environment does not switch DecisionLens to a
    paid provider. Developers commonly export that variable globally, and a tool
    that starts billing because it noticed one is doing something the operator did
    not ask for. ``MODEL_PROVIDER`` must say ``anthropic`` as well.
*   **No silent fallback in either direction.** Asking for live without a usable
    key fails with instructions. It does not quietly serve cached output and let a
    reviewer believe they saw a live run.
*   **The key is not printable.** It is excluded from ``repr`` and from
    ``model_dump``, so it cannot reach a log line, a run trace, or a decision brief
    by accident. :meth:`Settings.masked_key` is the only way to show it, and shows
    four characters.

The ``.env`` reader here is deliberately hand-rolled. It parses five keys, and a
dependency whose whole job is ``split("=", 1)`` is not worth the supply chain.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

#: Real Anthropic keys carry this prefix. Checking it costs nothing and turns a
#: pasted placeholder into an immediate, obvious error instead of a 401 that
#: arrives after the run has already started.
ANTHROPIC_KEY_PREFIX = "sk-ant-"

#: Used when MODEL_NAME is blank. Named here rather than in the adapter so the
#: default a run used is visible in configuration, not buried in a call site.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"

ENV_FILENAME = ".env"


class ConfigError(RuntimeError):
    """Configuration is missing or malformed. Raised before any network call."""


class ProviderChoice(StrEnum):
    """The providers a run may select.

    ``openai`` is deliberately absent. The abstraction is vendor-neutral and an
    OpenAI adapter would slot in, but none exists, and offering a choice that
    resolves to nothing is worse than not offering it.
    """

    CACHED = "cached"
    ANTHROPIC = "anthropic"


def find_env_file(start: Path | None = None) -> Path | None:
    """Locate the nearest ``.env``, searching upward from ``start``.

    Walking up means ``make demo`` behaves the same from the repository root and
    from a subdirectory, which is where a reviewer is as likely to be.
    """
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_env_file(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """Parse ``KEY=VALUE`` lines. Returns the values and any complaints.

    Handles comments, blank lines, an ``export`` prefix, and surrounding quotes.
    A line it cannot read is reported rather than skipped: a mistyped key that
    silently does nothing is how someone spends ten minutes wondering why their
    credential is being ignored.
    """
    values: dict[str, str] = {}
    problems: list[str] = []

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            problems.append(f"line {number} is not KEY=VALUE and was ignored: {raw.strip()!r}")
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if not name:
            problems.append(f"line {number} has an empty key and was ignored")
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[name] = value

    return values, tuple(problems)


def load_env_file(path: Path | None) -> tuple[dict[str, str], tuple[str, ...]]:
    """Read and parse an env file. A missing file is not an error."""
    if path is None or not path.is_file():
        return {}, ()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - unreadable file is environmental
        return {}, (f"{path} could not be read: {exc}",)
    values, problems = parse_env_file(text)
    return values, tuple(f"{path}: {p}" for p in problems)


class Settings(BaseModel):
    """Resolved configuration for one run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: ProviderChoice = ProviderChoice.CACHED
    #: Excluded from repr and from model_dump so it cannot reach a log or a brief.
    anthropic_api_key: str = Field(default="", repr=False, exclude=True)
    model_name: str = ""
    log_level: str = ""
    #: Configuration problems worth surfacing but not worth failing on.
    warnings: tuple[str, ...] = ()

    @classmethod
    def load(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        env_path: Path | None = None,
        search_from: Path | None = None,
    ) -> Settings:
        """Resolve settings from ``.env`` and the process environment.

        The file wins over the process environment when both set a value. That is
        the opposite of the usual convention, and deliberate: someone who edited
        ``.env`` expects the thing they just typed to take effect, not to be
        shadowed by an export they set up months ago and forgot. When the two
        disagree the shadowing is reported rather than resolved silently.
        """
        environ = os.environ if environ is None else environ
        path = env_path if env_path is not None else find_env_file(search_from)
        file_values, warnings = load_env_file(path)

        collected: list[str] = list(warnings)

        def resolve(name: str) -> str:
            from_file = file_values.get(name, "").strip()
            from_env = environ.get(name, "").strip()
            if from_file and from_env and from_file != from_env:
                collected.append(
                    f"{name} is set in both {path} and the environment; the value from "
                    f"{ENV_FILENAME} is being used."
                )
            return from_file or from_env

        raw_provider = resolve("MODEL_PROVIDER").lower()
        if raw_provider and raw_provider not in set(ProviderChoice):
            allowed = ", ".join(sorted(ProviderChoice))
            raise ConfigError(
                f"MODEL_PROVIDER={raw_provider!r} is not a provider DecisionLens has. "
                f"Choose one of: {allowed}. Leave it blank to use the recorded demo."
            )

        return cls(
            provider=ProviderChoice(raw_provider) if raw_provider else ProviderChoice.CACHED,
            anthropic_api_key=resolve("ANTHROPIC_API_KEY"),
            model_name=resolve("MODEL_NAME"),
            log_level=resolve("LOG_LEVEL").upper(),
            warnings=tuple(collected),
        )

    # -- credential handling ------------------------------------------------- #

    @property
    def masked_key(self) -> str:
        """A form of the key that is safe to print."""
        if not self.anthropic_api_key:
            return "(not set)"
        return f"{ANTHROPIC_KEY_PREFIX}…{self.anthropic_api_key[-4:]}"

    def require_anthropic_key(self) -> str:
        """Return a key that looks usable, or explain exactly what to do.

        Shape is checked here so a typo fails in milliseconds rather than after a
        round trip, and so the failure names the file to edit.
        """
        key = self.anthropic_api_key
        if not key:
            raise ConfigError(
                "MODEL_PROVIDER=anthropic needs an API key, and none is set.\n"
                f"  Put one on the ANTHROPIC_API_KEY line of your {ENV_FILENAME} file.\n"
                "  Or unset MODEL_PROVIDER to run the recorded demo, which needs no key."
            )
        if not key.startswith(ANTHROPIC_KEY_PREFIX):
            raise ConfigError(
                f"ANTHROPIC_API_KEY does not look like an Anthropic key: it should start "
                f"with {ANTHROPIC_KEY_PREFIX!r}. Nothing was sent. Check the value in your "
                f"{ENV_FILENAME} file."
            )
        return key

    def describe(self) -> str:
        """A one-line summary safe to print in a footer or a log."""
        if self.provider is ProviderChoice.CACHED:
            return "provider=cached-demo (recorded output, offline, free)"
        return (
            f"provider={self.provider.value} model="
            f"{self.model_name or DEFAULT_ANTHROPIC_MODEL} key={self.masked_key}"
        )
