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
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GOLD_NL="${GOLD_NL:-/home/claude/nl/gold_nl}"
ANSWERS="${ANSWERS:-$GOLD_NL/answers}"
LOG="${LOG:-$GOLD_NL/batch_progress.log}"
PARALLEL="${PARALLEL:-2}"
export STELTIC_ENGINE_DIR="${STELTIC_ENGINE_DIR:-/home/claude/work/steltic_india/steel_engine}"
export RAG_API_URL="${RAG_API_URL:-http://127.0.0.1:8765/query}"
export INDIA_CORPUS_ROOT="${INDIA_CORPUS_ROOT:-/home/claude/corpus_srv}"
export MPLBACKEND=Agg
PY="${PY:-python3}"

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

cd "$REPO" || exit 1
log "batch start: repo $REPO @ $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null) | jobs $(echo $JOBS | wc -w) | parallel $PARALLEL"

for rel in $JOBS; do
  J="$GOLD_NL/$rel"
  name="${rel//\//__}"
  if [ ! -f "$J/cfg.py" ]; then log "SKIP $rel: no job folder at $J"; continue; fi
  if [ -f "$J/batch_done.json" ]; then log "SKIP $rel: already done ($(cat "$J/batch_done.json" | tr -d '\n' | cut -c1-120))"; continue; fi
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
  for step in pushover nlrha ddm; do
    if [ -f "$J/.batch_step_$step" ]; then log "JOB $rel $step already done"; continue; fi
    t0=$(date +%s)
    log "JOB $rel $step start"
    $PY -m snl run "$J" --only $step --parallel "$PARALLEL" --dt 0.01 >> "$J/batch.log" 2>&1
    rc=$?
    dt=$(( $(date +%s) - t0 ))
    log "JOB $rel $step end rc=$rc (${dt} s)"
    if [ $rc -eq 0 ]; then echo "{\"seconds\": $dt, \"finished\": \"$(date -Iseconds)\"}" > "$J/.batch_step_$step"; fi
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
log "batch end"
