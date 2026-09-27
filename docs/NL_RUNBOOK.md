# India NL runbook -- producing a "gold NL solution" for an HR gold building

Repo: `/home/claude/nl/work/steltic_nonlinear_india` branch `review-fix-2026-09` (NL-1..NL-19). For long runs use a frozen
worktree so edits cannot change code under a running job: `git -C <repo> worktree add --detach /home/claude/nl/run_repo review-fix-2026-09`
(then `git -C /home/claude/nl/run_repo checkout --detach review-fix-2026-09` to refresh). All commands below run from that worktree.

## 0. Environment (every command)

```bash
export STELTIC_ENGINE_DIR=/home/claude/work/steltic_india/steel_engine   # HR engine: gravity states, combos, cfg exec (REQUIRED)
export RAG_API_URL=http://127.0.0.1:8765/query                          # India corpus server (keep it running)
export INDIA_CORPUS_ROOT=/home/claude/corpus_srv
export MPLBACKEND=Agg
```
Without `STELTIC_ENGINE_DIR` the NL gravity falls back to an idealisation and the DDM is skipped -> the COMPLETE gate refuses.

## 1. Copy the gold HR job (gold jobs are read-only)

```bash
J=/home/claude/nl/gold_nl/<job>;  cp -r /home/claude/gold/jobs_hr/<job> $J
```
Multi-unit jobs: each unit folder that has its own `cfg.py` + `model_opensees.py` + `design/` is a separate NL job
(IN_Ex8 `units/workshop`, IN_Ex9 `units/stem`, IN_Ex11 `unitB_link`, `unitC_gym`) -- run steps 2-4 on each.

## 2. Collect the IS values (agent as transcriber, NL-9)

```bash
python -m snl collect $J --prepare            # exit 3; writes collect_request.json / .md (the IS passages, fields, answers_template)
# the agent reads collect_request.md and writes $J/collect_answers.json:
#   {"transcriber": "<agent id>", "answers": {group: {field: {"value": v, "quote": "<verbatim passage text>"}}}}
python -m snl collect $J --answers $J/collect_answers.json   # exit 0 -> hinge_params_collected.json (spec_values_collected=true)
```
Every value is checked (quote occurs in the fetched passage, number occurs in the quote, value equals the IS constant the
engines use). A failed group -> `hinge_params_collected.partial.json`, exit 2, fix the answer and re-run. Groups vary by
building (material per grade, IS 1161 tubes, overstrength, deformation_capacity per system part, spectrum for the zone,
damping). Transcription is copying: Ex3 took 6 groups, Ex1 5 groups; the checks run in < 1 s.

## 3. Run the three analyses

```bash
python -m snl run $J --parallel 2 --dt 0.01          # pushover (X, Y) -> NLRHA (DBE + MCE, 11 pairs each) -> DDM -> four_analyses
```
`snl run` picks up `hinge_params_collected.json` automatically. Per-step seconds are in `$J/snl_run.json`, full log in
`$J/snl_run.log`. Useful: `--only pushover|nlrha|ddm`, `--skip ...`; `python -m nlrha run $J --records 1-3 --level DBE` for a trial.

## 4. Report and gate

```bash
python -m snl report $J        # rebuild four_analyses.html + snl_summary.json (input sha256) and complete_gate.json
python -c "import json;g=json.load(open('$J/complete_gate.json'));print(g['status'],g['reasons'])"
```
`snl run` already ends with this; re-run `snl report` after re-running any single step (the gate refuses stale summaries).

## What a gold NL solution folder must contain (COMPLETE = `complete_gate.json` status "complete", reasons [])

| file | content / what the gate checks |
|---|---|
| `hinge_params_collected.json`, `collect_answers.json`, `collect_evidence.json`, `retrieval_log.md` | IS values with sources; transcriber + sha256 |
| `nl_hr_gravity.json` | HR engine gravity states (D, L, Lr, S, EV, Lfloor, S@/C@ patterns), inputs sha256 |
| `pushover/pushover_package.json`, `pushover_report.html`, `curve_X/Y.csv`, `hinge_params_used.json` | both directions; fibre; elastic IS target (no R); mass gate; non-vacuous response; spec_values_collected; gravity_source hr_engine; links when EBF |
| `nlrha/nlrha_package.json`, `nlrha_report.html`, `nlrha_viewer_3d.html`, `nlrha/{DBE,MCE}/nlrha_package.json, nlrha_report.html, gm_scaling.json` | DBE + MCE, all 11 records converged, IS elastic target, mass gate, non-vacuous, no spurious modes, same three NL-17 checks |
| `ddm_results.json`, `ddm_report.html`, `ddm_viewer_3d.html`, `model_gmnia.py` | gravity-transfer gate ok (vs HR `member_combo_forces.json`), every default combination run, lambda_u only at a detected limit / plateau / ductility cap, IS 800 B-1.2 check present |
| `four_analyses.html`, `snl_summary.json`, `complete_gate.json`, `complete_gate_disclosures.json`, `design_criteria_16_1_4.{docx,html}`, `steltic_viewer_bundle.html`, `snl_run.json/.log` | summary fresh (hashes match), status |

Every report carries: "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information."
No verdict, no ASCE 41 / AISC acceptance; IS 800 12.x / IS 18168 rotations are references only.

How to judge a solution beyond the gate: mass gate W = HR W; NL T1 within ~5 % of HR (P-Delta may add ~5 % on tall SMF);
DDM gravity gate 0 outside +/-5 %; pushover curves have a peak or reach 10 % drift; NLRHA drifts plausible for the system;
DBE/MCE means scale roughly x2 while elastic.

## Measured runtimes (this container, 2 cores; `--parallel 2`, dt 0.01, fibre nseg 4)

| job | collect | pushover (X+Y) | NLRHA (2 x 11 records) | DDM | total |
|---|---|---|---|---|---|
| IN_Ex3 portal (1 level, 33 el.) | < 1 s | 24 s | 1181 s (47-179 s/record) | 81 s (25 sweeps) | 22 min -- COMPLETE |
| IN_Ex1 SCBF (5 levels, 575 el.) | < 1 s | 890 s (both directions to 0.8 Vmax past peak) | 2.2-2.3 steps/s per worker: Chi-Chi CHY101 8143 steps 3539 s, Imperial Valley 9152 steps 4171 s (0 fails); ~7-9 h for 22 | ~170-210 s/sweep measured (4 sweeps), 61 sweeps / 2 workers ~ 1.5-3 h | ~10-12 h |

IN_Ex1 proof run: collect done (5 groups ok), pushover done; `snl run $J --skip pushover --parallel 2 --dt 0.01` started
2026-09-27 03:31 (+07) from /home/claude/nl/run_repo @ a08744b, log `$J/snl_run.log`, stdout `/home/claude/nl/gold_nl/ex1_run2.out`;
expected to finish ~12:00-13:00 (+07) and write `$J/complete_gate.json`. Do not move the run_repo worktree while it runs.
Resume after an interruption: `snl run $J --skip pushover` (or `--only ddm`), then `snl report $J`.

NLRHA is solver-bound (97 % of wall time inside `ops.analyze`). Levers: more cores (records are independent;
`--parallel N` with N cores gives ~N x), `--member-nseg 2` (1.75x faster, coarser plasticity -- disclose), dt 0.02 is
SLOWER (sub-stepping) and KrylovNewton is no faster. Smoke (build + HR gravity + modal) of all 15 jobs + 4 units: 1-18 s
each; DDM gravity gate 0.2-16 s each.

Planning estimate for the 15 buildings at 2 cores (NLRHA ~ 11 record-slots x ~4.5 s x elements; +DDM +pushover):
Ex3, Ex5, Ex11(+2 units), Ex13, Ex14, Ex15 ~1-2 h each; Ex8 (+workshop) ~4-5 h; Ex1, Ex2, Ex12 ~10-12 h; Ex4, Ex10 ~13-16 h;
Ex6, Ex7, Ex9 (+stem) ~17-25 h. Total on the order of 150-200 h at 2 cores -- use more cores or run the NLRHA of
different buildings on different machines.

## Known limitations (see NL_REVIEW.md)
Ground-motion selection/scaling follows the ASCE 7 Ch.16 rules as method (NGA library, labelled information);
NL uses the HR export's rigid diaphragm constraints even where the HR design declared a flexible diaphragm;
no India pushover 3-D viewer (bundle tab empty); NSP is the ASCE 41 coefficient method (C1 'a' = EOR input else 60).

## Fast India defaults (NL-21, lead decision 2026-09-27) and the gold batch

Method choices (disclosed in every report and in `complete_gate_disclosures.json`):
- **Gravity-only members elastic**: HR `gravity_col` columns and beams pinned at both ends outside braced / EBF bays are
  two elasticBeamColumn sub-elements (HR properties, releases, loads, mass). First-yield check
  |N|/Py + |Mmaj|/My,maj + |Mmin|/My,min recorded per member (pushover: whole curve; NLRHA: max over the records);
  `snl run` promotes members above 1.0 to fibre for that analysis (`<job>/nl_promote_fibre.json`) and re-runs; the gate
  refuses while any flagged member is elastic. Switch: `--gravity-elastic on|off`.
- **Records trimmed** to 5-95 % Arias (1 s pre-pad, 5 s free vibration); 11 pairs per level, DBE + MCE. Switch
  `--trim arias5-95|none`. Residual drift = drift averaged over the last max(2 T1, 1 s) of the free vibration.

Validation (2 cores):

| check | full | fast | diff |
|---|---|---|---|
| Ex3 NLRHA mean of 11, peak storey drift DBE / MCE | 0.1435 / 0.2871 % | 0.1440 / 0.2879 % | +0.29 % |
| Ex3 peak roof DBE / MCE | 9.39 / 18.79 mm | 9.43 / 18.86 mm | +0.39 % |
| Ex3 base shear DBE / MCE | 279.6 / 559.2 kN | 281.6 / 563.1 kN | +0.69 % |
| Ex3 residual drift DBE / MCE | 0.00050 / 0.00100 % | 0.00045 / 0.00091 % | -9 % (noise: 0.04 mm on 8 m) |
| Ex3 NLRHA wall time | 1214 s | 617 s | 2.0x |
| Ex1 pushover Vmax X / Y (after whole-curve promotion of 48 gravity columns) | 18042 / 14842 kN | 18042 / 14842 kN | 0.00 % (curve to peak within 0.9 %) |
| Ex1 pushover Vmax without promotion | | 18468 / 15425 kN | +2.4 / +3.9 % -> hence the whole-curve check |
| Ex1 NLRHA CHY101 drift X/Y, roof | 0.13 / 0.10 %, 0.6 / 0.5 in | 0.131 / 0.099 %, 0.58 / 0.48 in | equal at log precision; 3539 -> 786 s |
| Ex1 NLRHA Imperial Valley drift X/Y, roof | 0.10 / 0.15 %, 0.5 / 0.7 in | 0.099 / 0.146 %, 0.46 / 0.65 in | equal at log precision; 4171 -> 1335 s |

Reference outputs: `/home/claude/nl/gold_nl/_reference/` (Ex3 full-fidelity COMPLETE, Ex1 full pushover + 2 records).

Batch: `nohup /home/claude/nl/run_repo/scripts/run_gold_batch.sh > /home/claude/nl/gold_nl/batch_nohup.out 2>&1 &`
(refresh the worktree first: `git -C /home/claude/nl/run_repo checkout --detach review-fix-2026-09`). Progress:
`/home/claude/nl/gold_nl/batch_progress.log`; per job `<job>/batch.log`, `<job>/batch_done.json`, step markers
`<job>/.batch_step_{pushover,nlrha,ddm}`. Re-starting skips finished jobs/steps. Answers files (agent transcription):
`/home/claude/nl/gold_nl/answers/<job>.json` (generator `make_answers.py`, values read from the passages).
Started 2026-09-27 06:38 (+07) at df041ec. Estimated durations (fast, 2 cores; +-50 %):

| job | est. h | job | est. h |
|---|---|---|---|
| Ex11 unitC_gym | 0.3 | Ex9 stem | 4.5 |
| Ex3 | 0.3 | Ex12 | 3.7 |
| Ex11 unitB_link | 0.5 | Ex1 | 4.0 |
| Ex11 | 0.9 | Ex2 | 3.6 |
| Ex5 | 1.0 | Ex4 | 4.1 |
| Ex14 | 0.9 | Ex10 | 7.7 |
| Ex8 workshop | 0.6 | Ex6 | 5.4 |
| Ex13 | 0.4 | Ex7 | 5.2 |
| Ex15 | 1.0 | Ex9 | 10.6 |
| Ex8 | 1.4 | total | ~55 h (finish ~2026-09-29 14:00 +07) |

Per job the NLRHA dominates, then the DDM (61-sweep jobs: Ex1, Ex9, Ex10, Ex11, Ex14, Ex15); a pushover promotion
round adds one pushover re-run.
