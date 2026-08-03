"""Score every recorded case and write the results the documentation quotes.

Deliberately separate from recording. Recording costs money and takes hours;
scoring is free, offline, and deterministic, so it can be re-run any time an
answer key is corrected without re-buying a single call. That split is what let
a defect found in the answer keys be fixed without touching the recordings.

Writes two artifacts to evals/results/:

  results.json   every measurement, per case and per arm, machine readable
  summary.md     the tables docs/04 quotes, so no number in the documentation
                 is typed by hand

Run with: make eval
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_lens.evaluation.harness import (  # noqa: E402
    BASELINE,
    DECISIONLENS,
    evaluate_case,
)
from decision_lens.llm import CachedDemoProvider, DemoCache  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TRUTH = ROOT / "evals" / "ground_truth"
RECORDINGS = ROOT / "evals" / "recordings"
RESULTS = ROOT / "evals" / "results"

#: Fixed so a re-score is byte-identical. The recordings already fix the model
#: output; this fixes everything else.
CLOCK = datetime(2026, 8, 3, 9, 0, 0)

#: The one case designed before the prompts existed. Reported separately, because
#: an average that mixes it with the ten written afterwards hides the only part
#: of the sample that is out-of-sample.
IN_SAMPLE = "sample_delivery_exceptions"

SUPPORT_ORDER = ("low", "moderate", "strong")


def _merge_recordings() -> Path:
    merged = DemoCache()
    for path in sorted(RECORDINGS.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        merged.responses.update(DemoCache.load(path).responses)
    out = RECORDINGS / "_merged.json"
    merged.save(out)
    return out


def _arm_row(score: object) -> dict[str, object]:
    s = score  # narrow name, wide use
    contradictions = s.contradictions  # type: ignore[attr-defined]
    claimed = s.support_claimed  # type: ignore[attr-defined]
    ceiling = s.support_ceiling  # type: ignore[attr-defined]
    calibration = "unknown"
    if claimed in SUPPORT_ORDER and ceiling in SUPPORT_ORDER:
        delta = SUPPORT_ORDER.index(claimed) - SUPPORT_ORDER.index(ceiling)
        calibration = "over" if delta > 0 else "under" if delta < 0 else "at_ceiling"
    return {
        "contradictions_found": len(contradictions.found),
        "contradictions_graded": contradictions.graded,
        "contradictions_missed": list(contradictions.missed),
        "contradictions_unadjudicated": contradictions.unadjudicated,
        "gaps_reported": s.gaps_reported,  # type: ignore[attr-defined]
        "citations_total": s.citations_total,  # type: ignore[attr-defined]
        "citations_resolved": s.citations_resolved,  # type: ignore[attr-defined]
        "claims_total": s.claims_total,  # type: ignore[attr-defined]
        "claims_uncited": s.claims_uncited,  # type: ignore[attr-defined]
        "alternatives": s.alternatives,  # type: ignore[attr-defined]
        "has_non_ai_option": s.has_non_ai_option,  # type: ignore[attr-defined]
        "has_no_build_option": s.has_no_build_option,  # type: ignore[attr-defined]
        "support_claimed": claimed,
        "support_ceiling": ceiling,
        "calibration": calibration,
        "actionable": s.actionable,  # type: ignore[attr-defined]
        "blocking_errors": s.blocking_errors,  # type: ignore[attr-defined]
        "warnings": s.warnings,  # type: ignore[attr-defined]
        "failed_stages": list(s.failed_stages),  # type: ignore[attr-defined]
        "notes": list(s.notes),  # type: ignore[attr-defined]
    }


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    provider = CachedDemoProvider(_merge_recordings())

    cases = sorted(p.name for p in DATA.iterdir() if p.is_dir())
    rows: list[dict[str, object]] = []
    for case in cases:
        truth_path = TRUTH / f"{case}.json"
        if not truth_path.is_file():
            continue
        result = evaluate_case(DATA / case, truth_path, provider, clock=CLOCK)
        row: dict[str, object] = {"case_id": case, "records": result.records, "arms": {}}
        if result.error:
            row["error"] = result.error
        for arm in (DECISIONLENS, BASELINE):
            attempt = result.arm(arm)
            if attempt is None:
                continue
            if attempt.score is None:
                row["arms"][arm] = {"failed": attempt.error}  # type: ignore[index]
            else:
                row["arms"][arm] = _arm_row(attempt.score)  # type: ignore[index]
        rows.append(row)
        print(f"  scored {case}")

    payload = {
        "generated_from": "evals/recordings/",
        "cases": len(rows),
        "in_sample_case": IN_SAMPLE,
        "note": (
            "Single live run per case. No variance measurement exists, so a margin "
            "smaller than run-to-run variation cannot be distinguished from noise."
        ),
        "results": rows,
    }
    (RESULTS / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "summary.md").write_text(_summary(rows), encoding="utf-8")
    print(f"\nwrote evals/results/results.json and summary.md ({len(rows)} cases)")
    return 0


def _totals(rows: list[dict[str, object]], arm: str, only: str = "") -> dict[str, int]:
    keys = (
        "contradictions_found",
        "contradictions_graded",
        "citations_total",
        "citations_resolved",
        "claims_total",
        "claims_uncited",
        "alternatives",
    )
    out = dict.fromkeys(keys, 0)
    out.update(dict.fromkeys(("over", "under", "at_ceiling", "actionable", "cases"), 0))
    for row in rows:
        case = str(row["case_id"])
        if only == "held_out" and case == IN_SAMPLE:
            continue
        if only == "in_sample" and case != IN_SAMPLE:
            continue
        data = row["arms"].get(arm)  # type: ignore[union-attr]
        if not isinstance(data, dict) or "failed" in data:
            continue
        out["cases"] += 1
        for key in keys:
            out[key] += int(data[key])  # type: ignore[arg-type]
        out[str(data["calibration"])] = out.get(str(data["calibration"]), 0) + 1
        out["actionable"] += int(bool(data["actionable"]))
    return out


def _pct(part: int, whole: int) -> str:
    """Never round a near-miss up to a clean number.

    967/969 printed as "100%" reads as a perfect score and is not one. Anything
    short of the whole is shown to a decimal, so the two missing citations are
    visible rather than rounded away.
    """
    if not whole:
        return "n/a"
    if part == whole:
        return "100%"
    return f"{part / whole:.1%}"


def _summary(rows: list[dict[str, object]]) -> str:
    lines = [
        "# Evaluation results",
        "",
        "Generated by `make eval` from the recordings in `evals/recordings/`.",
        "Every number here is computed, not typed. Do not edit by hand.",
        "",
        f"Cases measured: **{len(rows)}**. "
        f"One (`{IN_SAMPLE}`) was designed before the prompts were written and is "
        "reported separately below.",
        "",
        "## Per case",
        "",
        "| Case | Arm | Contradictions | Citations valid | Claims uncited | Options | "
        "Support vs ceiling | Actionable |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        for arm in (DECISIONLENS, BASELINE):
            data = row["arms"].get(arm)  # type: ignore[union-attr]
            if not isinstance(data, dict):
                continue
            if "failed" in data:
                lines.append(f"| {row['case_id']} | {arm} | FAILED | — | — | — | — | — |")
                continue
            lines.append(
                f"| {row['case_id']} | {arm} | "
                f"{data['contradictions_found']}/{data['contradictions_graded']} | "
                f"{data['citations_resolved']}/{data['citations_total']} | "
                f"{data['claims_uncited']}/{data['claims_total']} | "
                f"{data['alternatives']} | "
                f"{data['support_claimed']} vs {data['support_ceiling']} "
                f"({data['calibration']}) | {'yes' if data['actionable'] else 'NO'} |"
            )

    for label, scope in (
        ("All cases", ""),
        ("Held-out only", "held_out"),
        ("In-sample only", "in_sample"),
    ):
        lines += [
            "",
            f"## {label}",
            "",
            "| Metric | DecisionLens | Baseline |",
            "| --- | --- | --- |",
        ]
        dl = _totals(rows, DECISIONLENS, scope)
        bl = _totals(rows, BASELINE, scope)
        lines += [
            f"| Cases | {dl['cases']} | {bl['cases']} |",
            f"| Contradiction recall | {dl['contradictions_found']}/{dl['contradictions_graded']}"
            f" ({_pct(dl['contradictions_found'], dl['contradictions_graded'])}) | "
            f"{bl['contradictions_found']}/{bl['contradictions_graded']}"
            f" ({_pct(bl['contradictions_found'], bl['contradictions_graded'])}) |",
            f"| Citation validity | {dl['citations_resolved']}/{dl['citations_total']}"
            f" ({_pct(dl['citations_resolved'], dl['citations_total'])}) | "
            f"{bl['citations_resolved']}/{bl['citations_total']}"
            f" ({_pct(bl['citations_resolved'], bl['citations_total'])}) |",
            f"| Uncited claims | {dl['claims_uncited']}/{dl['claims_total']} | "
            f"{bl['claims_uncited']}/{bl['claims_total']} |",
            f"| Options generated | {dl['alternatives']} | {bl['alternatives']} |",
            f"| Overstates support | {dl['over']}/{dl['cases']} | {bl['over']}/{bl['cases']} |",
            f"| At the ceiling | {dl['at_ceiling']}/{dl['cases']}"
            f" | {bl['at_ceiling']}/{bl['cases']} |",
            f"| Understates support | {dl['under']}/{dl['cases']} | {bl['under']}/{bl['cases']} |",
            f"| Actionable brief | {dl['actionable']}/{dl['cases']}"
            f" | {bl['actionable']}/{bl['cases']} |",
        ]

    lines += [
        "",
        "## What these numbers cannot tell you",
        "",
        "- **One run per case.** No variance was measured, so no margin here has an",
        "  error bar and none should be read as reproducible.",
        "- **Recall denominators are small.** Fifty graded contradictions across eleven",
        "  cases; a difference of a few items is not a result.",
        "- **The corpus is synthetic and single-authored**, and the prompts were written",
        "  by the same person. Ten of eleven cases were written after the prompts were",
        "  frozen, which is checkable but weaker than a genuine held-out set.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
