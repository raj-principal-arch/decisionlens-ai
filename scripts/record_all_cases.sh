#!/usr/bin/env bash
# Record every evaluation case, both arms, against a live model.
#
# Cases run CONCURRENTLY. They are completely independent — different evidence,
# different question, no shared state — so queueing them turns a 25-minute job
# into a four-hour one for no reason. The only thing that forced sequencing was
# a shared cache file, and that is solved by giving each case its own.
#
# Each case writes evals/recordings/<case_id>.json. They are merged into one
# cache at the end; the per-case files are kept, because when a run is
# interrupted they are the record of what was already bought.
#
# Resumable by construction. Every case is recorded with --resume, so re-running
# this command after an interruption, a rate-limit, or a bad response costs
# nothing for the stages that already landed. Re-running it is the intended
# recovery for almost any failure.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${OUT_DIR:-evals/recordings}"
DATA="${DATA:-data}"
# Concurrency. All eleven at once is usually fine; lower it if the provider
# starts refusing. A refused call is not lost money, it is a stage the next run
# picks up, but it is wasted wall-clock.
JOBS="${JOBS:-11}"
# Seconds between launches. Eleven simultaneous connection opens is the shape
# of traffic that trips a rate limiter hardest, and the provider is configured
# with no automatic retry, so a stagger is cheaper than a retry storm.
STAGGER="${STAGGER:-3}"

mkdir -p "$OUT_DIR" logs

cases=()
for dir in "$DATA"/*/; do
  name="$(basename "$dir")"
  [ -f "evals/ground_truth/${name}.json" ] || continue
  cases+=("$name")
done

echo "cases       : ${#cases[@]}"
echo "concurrency : $JOBS"
echo "recordings  : $OUT_DIR/<case>.json"
echo "logs        : logs/<case>.log"
echo
echo "Each case is one live run of both arms. Progress appears in the logs;"
echo "watch one with:  tail -f logs/${cases[0]}.log"
echo

started_all=$(date +%s)
running=0

for name in "${cases[@]}"; do
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 2; done
  (
    PYTHONPATH=src .venv/bin/python -m decision_lens.cli record \
      --case "$DATA/$name" \
      --cache "$OUT_DIR/$name.json" \
      --resume --yes
    status=$?
    # Exit 2 means the brief carried blocking errors: a real outcome that was
    # still recorded, not a failed run.
    if [ $status -eq 0 ] || [ $status -eq 2 ]; then
      echo "DONE $name"
    else
      echo "FAIL $name (exit $status)"
    fi
  ) > "logs/$name.log" 2>&1 &
  running=$((running + 1))
  echo "  started $name  (${running}/${#cases[@]})"
  sleep "$STAGGER"
done

echo
echo "all launched; waiting…"
wait

total=$(( $(date +%s) - started_all ))
echo
echo "──────────────────────────────────────────────────────────────"
printf 'finished in %dm %ds\n\n' $((total / 60)) $((total % 60))

# Completeness is counted from the cache, not from exit codes. The recorder
# treats a partial run as a real outcome and exits 0, which is correct for it
# and useless here: an earlier version of this summary called every case "ok"
# while 43% of stages were missing, because the processes had all exited
# cleanly after the API ran out of credit. Ask the artifact, not the process.
failed=()
python3 - "$OUT_DIR" <<'PYEOF'
import json, pathlib, sys
WANT = {"relevance", "classification", "contradictions", "missing_evidence",
        "alternatives", "recommendation", "challenger", "baseline"}
out = pathlib.Path(sys.argv[1])
total = done = 0
for f in sorted(out.glob("*.json")):
    if f.stem.startswith("_"):
        continue  # scratch files, e.g. a merged cache built for scoring
    try:
        keys = json.loads(f.read_text()).get("responses", {})
    except Exception as exc:
        print(f"  UNREADABLE {f.name}: {exc}")
        continue
    have = {k.split("::")[1] for k in keys}
    missing = sorted(WANT - have)
    total += len(WANT)
    done += len(have & WANT)
    mark = "ok  " if not missing else "PART"
    print(f"  {mark} {f.stem:30} {len(have & WANT)}/{len(WANT)}"
          + (f"   missing: {', '.join(missing)}" if missing else ""))
pct = (done / total * 100) if total else 0
print(f"\n  {done}/{total} stages recorded ({pct:.0f}%)")
sys.exit(0 if done == total else 3)
PYEOF
complete=$?

if [ $complete -ne 0 ]; then
  echo
  echo "Recording is INCOMPLETE. Nothing can be scored until every stage is present."
  echo "Why a stage is missing is in its log — do not guess at it:"
  echo "    grep -A4 '^  ! ' logs/<case>.log"
  echo "Seen so far: spend limit reached, credit exhausted, output truncated"
  echo "mid-JSON, and citations that would not resolve. Only the first two are"
  echo "about billing. Re-running is safe either way: recorded stages are"
  echo "reused, not re-bought."
  exit 1
fi

echo
echo "All cases recorded. Merge and score with:  make eval"
