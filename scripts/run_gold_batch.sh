#!/bin/bash
# run_gold_batch.sh -- the India gold NL batch (NL-21): 19 job folders (15 gold buildings + 4 units), sequentially,
# smallest first, each: collect (agent-transcribed answers file) -> pushover -> NLRHA -> DDM -> report + gate.
#
#   nohup scripts/run_gold_batch.sh > /home/claude/nl/gold_nl/batch_nohup.out 2>&1 &
#
# Resumable: every finished step leaves <job>/.batch_step_<step> and a finished job <job>/batch_done.json; a re-start
# skips both (delete the marker to redo a step). Run it from a FROZEN worktree of this repo (edits to the code under a
# running batch would change the analyses half-way). Settings: fast India defaults -- gravity-only members elastic with
# the yield check / promotion, NLRHA records trimmed to 5-95 % Arias (+1 s pre-pad, 5 s free vibration), 11 pairs per
# level, DBE + MCE, --parallel 2, dt 0.01.
#
# Env: GOLD_NL (job root, default /home/claude/nl/gold_nl), ANSWERS (default $GOLD_NL/answers),
#      STELTIC_ENGINE_DIR, RAG_API_URL, INDIA_CORPUS_ROOT, PARALLEL (2), ONLY_JOBS (space-separated subset).
#
# NL-27: the DDM step marker records DDM_CODE (the last commit that changed DDM results). A DDM marker without the
# current DDM_CODE is stale: an unfinished job re-runs its DDM in the main loop; a finished job (batch_done.json)
# re-runs `--only ddm` + report in the refresh pass at the END of the batch (old DDM kept in _ddm_before_<code>/).
# Clean stop: `touch $GOLD_NL/STOP_BATCH` -> the batch exits before its next step (a running step completes).
# NL-28: $GOLD_NL/SKIP_JOBS lists job folders (one per line, as in JOBS_DEFAULT; '#' comments) that this batch must not
# run -- e.g. jobs offloaded to another machine. Read before every job and in the DDM refresh pass (edits take effect
# at the next job without a restart).
# NL-29: STEPS (default "pushover nlrha ddm") restricts the analysis steps (e.g. STEPS=pushover for a trial slice);
# a job is only marked done when all three step markers exist. NL_REV (if set) stamps the markers instead of
# `git rev-parse` -- the owner's PC package is a plain copy without .git.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GOLD_NL="${GOLD_NL:-/home/claude/nl/gold_nl}"
ANSWERS="${ANSWERS:-$GOLD_NL/answers}"
LOG="${LOG:-$GOLD_NL/batch_progress.log}"
PARALLEL="${PARALLEL:-2}"
export STELTIC_ENGINE_DIR="${STELTIC_ENGINE_DIR:-/home/claude/work/steltic_india/steel_engine}"
export RAG_API_URL="${RAG_API_URL-http://127.0.0.1:8765/query}"      # NL-29: set-but-empty stays empty (no corpus server)
export INDIA_CORPUS_ROOT="${INDIA_CORPUS_ROOT-/home/claude/corpus_srv}"
export MPLBACKEND=Agg
PY="${PY:-python3}"
STEPS="${STEPS:-pushover nlrha ddm}"
REV="${NL_REV:-$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || true)}"; REV="${REV:-unknown}"
DDM_CODE="NL-26"            # bump when a commit changes DDM results; stale DDM markers are re-run
STOP="$GOLD_NL/STOP_BATCH"
SKIPF="$GOLD_NL/SKIP_JOBS"

# smallest first (elements in the HR model_opensees.py)
JOBS_DEFAULT="IN_Ex11_SMF_3levels_Zplan_school_Chandigarh/unitC_gym
IN_Ex3_SMF_portal_Chennai_wind
IN_Ex11_SMF_3levels_Zplan_school_Chandigarh/unitB_link
IN_Ex11_SMF_3levels_Zplan_school_Chandigarh
IN_Ex5_OMRF_warehouse_mezzanine_Hyderabad
IN_Ex14_Crane_bay_OMRF_OCBF_Vizag
IN_Ex8_OCBF_4levels_splitlevel_Jaipur/units/workshop
IN_Ex13_SCBF_bigbox_flexdiaphragm_Indore
IN_Ex15_Gable_warehouse_SMF_SCBF_snow_Shimla
IN_Ex8_OCBF_4levels_splitlevel_Jaipur
IN_Ex9_EBF_12levels_Tplan_Guwahati/units/stem
IN_Ex12_SMF_podium_11levels_Kochi
IN_Ex1_SCBF_5levels_Delhi
IN_Ex2_SMF_office_Mumbai
IN_Ex4_SCBF_hospital_Kolkata
IN_Ex10_SCBF_18levels_slender_Noida
IN_Ex6_EBF_8levels_Lplan_Pune
IN_Ex7_SCBF_10levels_Ahmedabad
IN_Ex9_EBF_12levels_Tplan_Guwahati"
JOBS="${ONLY_JOBS:-$JOBS_DEFAULT}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] $*" | tee -a "$LOG"; }
skipped() { [ -f "$SKIPF" ] && sed 's/#.*//; s/[[:space:]]*$//; s/^[[:space:]]*//' "$SKIPF" | grep -qxF "$1"; }
stop_check() { if [ -f "$STOP" ]; then log "STOP_BATCH found -- batch stopped cleanly before: $*"; exit 0; fi; }
ddm_current() { [ -f "$1/.batch_step_ddm" ] && grep -q "\"ddm_code\": \"$DDM_CODE\"" "$1/.batch_step_ddm"; }
mark() {   # mark <job> <step> <seconds>
  echo "{\"seconds\": $3, \"finished\": \"$(date -Iseconds)\", \"rev\": \"$REV\", \"ddm_code\": \"$DDM_CODE\"}" > "$1/.batch_step_$2"
}

cd "$REPO" || exit 1
log "batch start: repo $REPO @ $REV | jobs $(echo $JOBS | wc -w) | parallel $PARALLEL | steps $STEPS"

for rel in $JOBS; do
  J="$GOLD_NL/$rel"
  name="${rel//\//__}"
  if skipped "$rel"; then log "SKIP $rel: listed in $SKIPF (not run here)"; continue; fi
  if [ ! -f "$J/cfg.py" ]; then log "SKIP $rel: no job folder at $J"; continue; fi
  if [ -f "$J/batch_done.json" ]; then log "SKIP $rel: already done ($(cat "$J/batch_done.json" | tr -d '\n' | cut -c1-120))$(ddm_current "$J" || echo " -- DDM refresh queued at the end")"; continue; fi
  t_job=$(date +%s)
  log "JOB $rel start"
  # 1 collect (agent-transcribed answers; the program re-checks every value against the passages)
  if [ ! -f "$J/hinge_params_collected.json" ]; then
    $PY -m snl collect "$J" --prepare >> "$J/batch.log" 2>&1
    if [ -f "$ANSWERS/$name.json" ]; then
      $PY -m snl collect "$J" --answers "$ANSWERS/$name.json" >> "$J/batch.log" 2>&1
    fi
    if [ ! -f "$J/hinge_params_collected.json" ]; then log "JOB $rel collect FAILED (no answers file $ANSWERS/$name.json or a value was rejected) -- job skipped"; continue; fi
    log "JOB $rel collect ok"
  fi
  # 2-4 the analyses, one step at a time (resumable)
  for step in $STEPS; do
    if [ -f "$J/.batch_step_$step" ]; then
      if [ "$step" != ddm ] || ddm_current "$J"; then log "JOB $rel $step already done"; continue; fi
      log "JOB $rel ddm marker predates $DDM_CODE -- DDM re-run"
    fi
    stop_check "$rel $step"
    t0=$(date +%s)
    log "JOB $rel $step start"
    $PY -m snl run "$J" --only $step --parallel "$PARALLEL" --dt 0.01 >> "$J/batch.log" 2>&1
    rc=$?
    dt=$(( $(date +%s) - t0 ))
    log "JOB $rel $step end rc=$rc (${dt} s)"
    if [ $rc -eq 0 ]; then mark "$J" "$step" "$dt"; fi
  done
  # 5 report + gate
  $PY -m snl report "$J" >> "$J/batch.log" 2>&1
  status=$($PY -c "import json,sys; g=json.load(open(sys.argv[1])); print(g.get('status'), '|', '; '.join(g.get('reasons') or [])[:300])" "$J/complete_gate.json" 2>/dev/null)
  secs=$(( $(date +%s) - t_job ))
  if [ -f "$J/.batch_step_pushover" ] && [ -f "$J/.batch_step_nlrha" ] && [ -f "$J/.batch_step_ddm" ]; then
    $PY -c "import json,sys; json.dump(dict(status=sys.argv[1], seconds=int(sys.argv[2])), open(sys.argv[3],'w'))" "${status%% |*}" "$secs" "$J/batch_done.json"
  fi
  log "JOB $rel done in ${secs} s: gate $status"
done
# 6 NL-27 DDM refresh: finished jobs whose DDM predates $DDM_CODE -> --only ddm + report (queued at the end)
for rel in $JOBS; do
  J="$GOLD_NL/$rel"
  skipped "$rel" && continue
  [ -f "$J/batch_done.json" ] || continue
  ddm_current "$J" && continue
  stop_check "$rel ddm refresh"
  bk="$J/_ddm_before_$DDM_CODE"; mkdir -p "$bk/design"
  for f in ddm_results.json ddm_report.html ddm_viewer_3d.html model_gmnia.py complete_gate.json snl_summary.json batch_done.json .batch_step_ddm; do
    [ -f "$J/$f" ] && cp -p "$J/$f" "$bk/"
  done
  [ -f "$J/design/calc_package.json" ] && cp -p "$J/design/calc_package.json" "$bk/design/"
  t0=$(date +%s)
  log "JOB $rel ddm refresh start (DDM predates $DDM_CODE)"
  $PY -m snl run "$J" --only ddm --parallel "$PARALLEL" --dt 0.01 >> "$J/batch.log" 2>&1
  rc=$?
  dt=$(( $(date +%s) - t0 ))
  log "JOB $rel ddm refresh end rc=$rc (${dt} s)"
  if [ $rc -eq 0 ]; then mark "$J" ddm "$dt"; fi
  $PY -m snl report "$J" >> "$J/batch.log" 2>&1
  status=$($PY -c "import json,sys; g=json.load(open(sys.argv[1])); print(g.get('status'), '|', '; '.join(g.get('reasons') or [])[:300])" "$J/complete_gate.json" 2>/dev/null)
  $PY -c "import json,sys; d=json.load(open(sys.argv[1])); d.update(status=sys.argv[2], ddm_refresh=sys.argv[3]); json.dump(d, open(sys.argv[1],'w'))" "$J/batch_done.json" "${status%% |*}" "$DDM_CODE rc=$rc"
  log "JOB $rel ddm refresh done: gate $status"
done
log "batch end"
