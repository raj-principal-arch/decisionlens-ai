"""The one evidence connector the prototype implements.

Reads a directory of local files and normalizes them into `EvidenceRecord`s. It
retrieves; it does not interpret. No support level, no ranking, no conclusion.

Design decisions worth knowing before reading the code:

*   **IDs are stable across runs.** An id is derived from the relative path, the
    locator, and a hash of the content. The same file always produces the same
    id, so a citation in an older brief still resolves. Editing a file changes
    its id, which correctly signals that the cited text may no longer exist.

*   **A CSV row is a record.** A 200-row ticket export becomes 200 citable
    records, not one. A PM verifying a claim should land on the exact ticket, not
    on a spreadsheet.

*   **Failures degrade, they do not abort.** An unreadable file is skipped and
    *recorded* in `diagnostics`. Silently returning less evidence would be the
    worst possible behaviour for a product about traceability.

*   **Search here is coarse.** Keyword matching only, of the kind a Jira query
    does. Judging what is actually relevant is a Phase 7 skill, and the number of
    records a query removed is reported so the filtering is never invisible.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterator, Sequence
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from decision_lens.connectors.base import BaseEvidenceSource, EvidenceSourceError
from decision_lens.models import (
    EvidenceExcerpt,
    EvidenceRecord,
    EvidenceRequest,
    EvidenceType,
    SourceSystem,
)

TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
CSV_SUFFIXES = frozenset({".csv"})
JSON_SUFFIXES = frozenset({".json"})
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | CSV_SUFFIXES | JSON_SUFFIXES

DEFAULT_MANIFEST_NAME = "case_manifest.json"

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


class _Report(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SkippedFile(_Report):
    """A file the connector could not turn into evidence, and why.

    Surfaced rather than swallowed. "We found 40 records" means something
    different when six files failed to parse.
    """

    path: str
    reason: str


class RetrievalDiagnostics(_Report):
    """What happened during a retrieval, beyond the records themselves."""

    files_seen: int = 0
    files_read: int = 0
    records_built: int = 0
    records_filtered_out: int = 0
    skipped: tuple[SkippedFile, ...] = ()

    @property
    def had_failures(self) -> bool:
        return bool(self.skipped)


class LocalFileEvidenceSource(BaseEvidenceSource):
    """Retrieve evidence from a directory of local files.

    Supports Markdown, plain text, CSV and JSON. PDF is deliberately out of scope.

    Args:
        root: Directory to read. Searched recursively.
        default_evidence_type: Used when the manifest does not classify a file.
            A real connector learns type from the source system; for local files
            the manifest is that source, so this is only a fallback.
        manifest_name: Optional JSON file holding per-file metadata. It is
            metadata *about* evidence and is never returned as evidence.
        retrieved_at: Fixed retrieval timestamp. Injected so runs are reproducible
            and tests deterministic; defaults to now.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        default_evidence_type: EvidenceType = EvidenceType.OPERATIONAL_RECORD,
        manifest_name: str = DEFAULT_MANIFEST_NAME,
        retrieved_at: datetime | None = None,
    ) -> None:
        self.root = Path(root)
        self.default_evidence_type = default_evidence_type
        self.manifest_name = manifest_name
        self._retrieved_at = retrieved_at
        self._diagnostics = RetrievalDiagnostics()

    @property
    def source_system(self) -> SourceSystem:
        return SourceSystem.LOCAL_FILE

    @property
    def diagnostics(self) -> RetrievalDiagnostics:
        """Result of the most recent retrieval. Feeds the run trace in Phase 8."""
        return self._diagnostics

    # -- retrieval --------------------------------------------------------- #

    def _retrieve(self, request: EvidenceRequest) -> Sequence[EvidenceRecord]:
        if not self.root.exists():
            raise EvidenceSourceError(f"Evidence directory does not exist: {self.root}")
        if not self.root.is_dir():
            raise EvidenceSourceError(f"Evidence path is not a directory: {self.root}")

        manifest = self._load_manifest()
        stamp = self._retrieved_at or datetime.now()

        skipped: list[SkippedFile] = []
        records: list[EvidenceRecord] = []
        seen_ids: set[str] = set()
        files_seen = 0
        files_read = 0

        for path in self._iter_files():
            files_seen += 1
            rel = path.relative_to(self.root).as_posix()

            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                skipped.append(SkippedFile(path=rel, reason=f"unsupported file type {path.suffix}"))
                continue

            try:
                text = self._read_text(path)
            except OSError as exc:
                skipped.append(SkippedFile(path=rel, reason=f"unreadable: {exc}"))
                continue

            if not text.strip():
                skipped.append(SkippedFile(path=rel, reason="file is empty"))
                continue

            meta = manifest.get(rel, {})
            try:
                built = list(self._build_records(path, rel, text, meta, stamp))
            except ValueError as exc:
                skipped.append(SkippedFile(path=rel, reason=str(exc)))
                continue

            files_read += 1
            for record in built:
                if record.id in seen_ids:
                    skipped.append(
                        SkippedFile(path=rel, reason=f"duplicate of an earlier record {record.id}")
                    )
                    continue
                seen_ids.add(record.id)
                records.append(record)

        built_count = len(records)
        matched = [r for r in records if self._matches(r, request)]

        self._diagnostics = RetrievalDiagnostics(
            files_seen=files_seen,
            files_read=files_read,
            records_built=built_count,
            records_filtered_out=built_count - len(matched),
            skipped=tuple(skipped),
        )
        return matched

    def _iter_files(self) -> Iterator[Path]:
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            if path.name == self.manifest_name:
                continue  # metadata about evidence, not evidence
            if path.name.startswith("."):
                continue
            yield path

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        path = self.root / self.manifest_name
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise EvidenceSourceError(f"Manifest {path} is not valid JSON: {exc}") from exc
        files = raw.get("files", raw)
        if not isinstance(files, dict):
            raise EvidenceSourceError(f"Manifest {path} must map file paths to metadata objects")
        return {str(k): dict(v) for k, v in files.items() if isinstance(v, dict)}

    @staticmethod
    def _read_text(path: Path) -> str:
        """Read as UTF-8, falling back to a lossy decode rather than failing.

        A file with a stray byte is still evidence. Losing it entirely would be a
        worse outcome than losing one character, and `contains()` still resolves
        quotes taken from the decoded text.
        """
        data = path.read_bytes()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")

    # -- normalization ----------------------------------------------------- #

    def _build_records(
        self,
        path: Path,
        rel: str,
        text: str,
        meta: dict[str, Any],
        stamp: datetime,
    ) -> Iterator[EvidenceRecord]:
        suffix = path.suffix.lower()
        if suffix in CSV_SUFFIXES:
            yield from self._csv_records(rel, text, meta, stamp)
        elif suffix in JSON_SUFFIXES:
            yield from self._json_records(rel, text, meta, stamp)
        else:
            yield self._text_record(path, rel, text, meta, stamp)

    def _text_record(
        self, path: Path, rel: str, text: str, meta: dict[str, Any], stamp: datetime
    ) -> EvidenceRecord:
        excerpts: tuple[EvidenceExcerpt, ...] = ()
        if path.suffix.lower() in {".md", ".markdown"}:
            excerpts = self._markdown_sections(text)
        return self._record(
            rel=rel,
            locator="",
            title=meta.get("title") or path.stem.replace("_", " "),
            content=text,
            meta=meta,
            stamp=stamp,
            excerpts=excerpts,
        )

    @staticmethod
    def _markdown_sections(text: str) -> tuple[EvidenceExcerpt, ...]:
        """Split on headings so a skill can cite a section rather than a file.

        Structural, not interpretive: text is preserved verbatim and nothing is
        summarized or judged.

        Locators are the full heading path — `§Constraints > Driver app` — because
        a bare leaf name is ambiguous the moment a document reuses it. If a path
        still repeats, later occurrences are suffixed. An ambiguous locator sends
        a reader to the wrong passage, which is worse than no locator at all.
        """
        excerpts: list[EvidenceExcerpt] = []
        stack: list[tuple[int, str]] = []
        buffer: list[str] = []
        used: dict[str, int] = {}

        def flush() -> None:
            body = "\n".join(buffer).strip()
            if not body or not stack:
                return
            path = " > ".join(title for _, title in stack)
            used[path] = used.get(path, 0) + 1
            suffix = f" ({used[path]})" if used[path] > 1 else ""
            excerpts.append(EvidenceExcerpt(text=body, locator=f"§{path}{suffix}"))

        for line in text.splitlines():
            match = _HEADING.match(line)
            if match:
                flush()
                level = len(match.group(1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, match.group(2).strip()))
                buffer = []
            else:
                buffer.append(line)
        flush()
        return tuple(excerpts)

    def _csv_records(
        self, rel: str, text: str, meta: dict[str, Any], stamp: datetime
    ) -> Iterator[EvidenceRecord]:
        reader = csv.DictReader(StringIO(text))
        if reader.fieldnames is None:  # pragma: no cover - empty input is caught earlier
            raise ValueError("CSV has no header row")

        row_number = 0
        for row in reader:
            row_number += 1
            rendered = "\n".join(
                f"{key}: {value}" for key, value in row.items() if key and str(value or "").strip()
            )
            if not rendered.strip():
                continue  # blank row: nothing to cite
            yield self._record(
                rel=rel,
                locator=f"row {row_number}",
                title=f"{Path(rel).stem.replace('_', ' ')} row {row_number}",
                content=rendered,
                meta=meta,
                stamp=stamp,
            )

    def _json_records(
        self, rel: str, text: str, meta: dict[str, Any], stamp: datetime
    ) -> Iterator[EvidenceRecord]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc

        if isinstance(payload, list):
            for index, item in enumerate(payload):
                content = json.dumps(item, indent=2, sort_keys=True)
                yield self._record(
                    rel=rel,
                    locator=f"[{index}]",
                    title=f"{Path(rel).stem.replace('_', ' ')} [{index}]",
                    content=content,
                    meta=meta,
                    stamp=stamp,
                )
        else:
            yield self._record(
                rel=rel,
                locator="",
                title=meta.get("title") or Path(rel).stem.replace("_", " "),
                content=json.dumps(payload, indent=2, sort_keys=True),
                meta=meta,
                stamp=stamp,
            )

    # -- record construction ----------------------------------------------- #

    def _record(
        self,
        *,
        rel: str,
        locator: str,
        title: str,
        content: str,
        meta: dict[str, Any],
        stamp: datetime,
        excerpts: tuple[EvidenceExcerpt, ...] = (),
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=self._make_id(rel, locator, content),
            source_system=self.source_system,
            source_id=rel,
            source_reference=str(self.root / rel) + (f"#{locator}" if locator else ""),
            title=title,
            content=content,
            evidence_type=self._evidence_type(meta),
            created_at=_as_date(meta.get("created_at")),
            updated_at=_as_date(meta.get("updated_at")),
            owner=str(meta.get("owner", "")),
            retrieved_at=stamp,
            product_area=str(meta.get("product_area", "")),
            permission_scope=str(meta.get("permission_scope", "")),
            labels=tuple(str(t) for t in meta.get("labels", ())),
            excerpts=excerpts,
        )

    def _evidence_type(self, meta: dict[str, Any]) -> EvidenceType:
        raw = meta.get("evidence_type")
        if raw is None:
            return self.default_evidence_type
        try:
            return EvidenceType(str(raw))
        except ValueError as exc:
            raise ValueError(f"unknown evidence_type {raw!r} in manifest") from exc

    @staticmethod
    def _make_id(rel: str, locator: str, content: str) -> str:
        """Stable across runs: same path, same position, same text, same id."""
        digest = hashlib.sha256(f"{rel}::{locator}::{content}".encode()).hexdigest()
        return f"EV-{digest[:8]}"

    # -- coarse search ------------------------------------------------------ #

    @staticmethod
    def _matches(record: EvidenceRecord, request: EvidenceRequest) -> bool:
        if (
            request.product_area
            and record.product_area
            and record.product_area.lower() != request.product_area.lower()
        ):
            return False
        if request.labels and not set(request.labels) & set(record.labels):
            return False

        terms = [t for t in request.query.lower().split() if len(t) > 2]
        if not terms:
            return True
        haystack = f"{record.title}\n{record.content}".lower()
        return any(term in haystack for term in terms)


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):  # pragma: no cover - JSON never yields a date object
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid date {value!r} in manifest") from exc
