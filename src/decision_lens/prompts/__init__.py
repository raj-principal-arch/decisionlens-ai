"""Versioned prompts.

A brief is only reproducible if the prompt that produced it can be named. Every
prompt therefore carries an explicit `version` and a content `fingerprint`:

*   **version** is declared by a human and appears in the run trace. Bump it when
    the prompt changes in a way that should invalidate comparisons.
*   **fingerprint** is derived from the text. It catches the case a human forgets:
    prompt edited, version left alone. The cached provider compares fingerprints
    and warns when a recorded response predates the current wording.

This package is a skeleton at Phase 5. Baseline prompts arrive in Phase 6 and
skill prompts in Phase 7; the registry below is what they register into.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Prompt", "PromptRegistry", "REGISTRY"]


class Prompt(BaseModel):
    """One versioned prompt: a system message and a user template."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    system: str = ""
    user_template: str = Field(min_length=1)
    description: str = ""

    @property
    def fingerprint(self) -> str:
        """Hash of the prompt's text. Changes whenever the wording changes."""
        payload = f"{self.system}\x00{self.user_template}".encode()
        return hashlib.sha256(payload).hexdigest()

    def render(self, **values: Any) -> str:
        """Fill the user template.

        Raises on a missing placeholder rather than emitting a prompt containing
        a literal `{evidence}`, which a model would answer anyway and no one
        would notice until the output was wrong.
        """
        try:
            return self.user_template.format(**values)
        except KeyError as exc:
            raise KeyError(
                f"Prompt {self.name!r} {self.version} needs a value for {exc.args[0]!r}"
            ) from exc


class PromptRegistry:
    """Name-and-version lookup for prompts.

    Registration is explicit and refuses to overwrite: two prompts claiming the
    same name and version would make a run trace ambiguous about which one ran.
    """

    def __init__(self) -> None:
        self._prompts: dict[tuple[str, str], Prompt] = {}

    def register(self, prompt: Prompt) -> Prompt:
        key = (prompt.name, prompt.version)
        if key in self._prompts:
            raise ValueError(f"Prompt {prompt.name!r} {prompt.version} is already registered")
        self._prompts[key] = prompt
        return prompt

    def get(self, name: str, version: str) -> Prompt:
        try:
            return self._prompts[(name, version)]
        except KeyError:
            known = ", ".join(f"{n} {v}" for n, v in sorted(self._prompts)) or "(none registered)"
            raise KeyError(f"No prompt {name!r} {version}. Known: {known}") from None

    def latest(self, name: str) -> Prompt:
        """Highest registered version of a prompt, by natural string order."""
        versions = sorted(v for n, v in self._prompts if n == name)
        if not versions:
            raise KeyError(f"No prompt registered under {name!r}")
        return self._prompts[(name, versions[-1])]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted({n for n, _ in self._prompts}))

    def __len__(self) -> int:
        return len(self._prompts)


#: Process-wide registry. Phases 6 and 7 register into this.
REGISTRY = PromptRegistry()
