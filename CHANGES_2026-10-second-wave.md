# steltic-nonlinear-india — 2026-10: second wave (review item 15 leftovers and the first-wave re-runs)

Branch `fix/2026-10-second-wave` from `origin/main` (6d8d9a5, the first wave merged). The first wave (NL-36 … NL-38)
fixed the runaway sweeps, the IS 875-2 3.2.1 basis of the B-1.2 check and the rolled-shed restraints, and left the
re-runs and part of the presentation (review E_NL item 15) open. This change finishes both. Nothing here changes an
analysis: the sweeps, the pushover and the NLRHA are as before; what changes is what the reports say, plus a cheaper way
to redo a B-1.2 check after a B-1.2 rule change.

## Record set, record pairs and analyses (`nlrha/record_set.py`, new; `nlrha/report_india.py`, `viewer3d_india.py`, `cli.py`)

- The review found "eleven records" on the site next to "22/22 converged", and no word anywhere on what the records are.
- Every India NLRHA page (the index and the DBE / MCE pages), the NLRHA viewer and the four-analyses page now state:
  - **the record set** — name and source from `records/p695_farfield/index.json` (FEMA P-695 (ATC-63) far-field set,
    PEER NGA files as distributed by the ATC-63 project; public mirror sp3risk.com), the 14 earthquakes with year and
    magnitude, and the earthquakes this run's pairs come from;
  - **what it lacks** — no Indian or Himalayan records (M 6.5–7.6, rupture distance 7.1–26 km, US site-class letters C / D,
    no record flagged as a near-fault pulse), so near-field and long-duration effects of Indian earthquakes are not
    represented; Indian or regional records can be supplied with `--records-set`;
  - **how it is scaled** — read from `nlrha/ground_motions.select_and_scale`: the 11 pairs whose RotD100 spectrum best
    fits the target's shape over the period range; one factor per pair for both components (its geometric-mean fit
    times one common factor, printed) so that the suite mean is ≥ 0.9 × target over the range and ≥ target on average;
    target the IS 1893 elastic spectrum (DBE (Z/2)·I·Sa/g, MCE Z·I·Sa/g, 5 %, no R). IS 1893 7.7.4 is quoted from the
    India corpus transcription; the 0.9 rule is said to be the tool's convention, not IS text;
  - **what was run** — "11 record pairs (two horizontal components each), run at DBE and at MCE: 22 analyses,
    22 converged", and, when the packages show it, that the MCE suite is the DBE suite with every factor × 2.00;
  - the scale-factor ranges, and "no scale-factor bounds were set" (was "Scale-factor bounds: None").
- Wording: "record pairs (converged)" in the NLRHA index table, "Record pairs · converged" and the analyses sentence in
  the viewer (was "22 records").
- New runs write all of this natively (`nlrha run` calls `record_set.refresh_reports` after the index). Stored reports
  get it from `snl report` (below): the block is marked, so a second refresh replaces it in place.

## φs·λu is information, φs is not an IS 800 factor (`steltic_ddm/phi_s.py`, `report_ddm.py`, `snl/compare.py`)

- `phi_s.india_note(phi, λu, φs·λu)`: φs = 0.80 (class HR-G, SSRC 2013 Table 10 at β_T = 3.0; HR-W for gravity + wind)
  is a system resistance factor from US / Australian reliability calibrations, with its sources from `phi_s.SOURCES`,
  not an IS 800 factor and not calibrated for IS 800 Table 4 / IS 875; φs·λu is information only. When the smallest
  φs·λu is below 1.0 the note adds that this does not mean the design fails: the code check is B-1.2 at λ = 1, and
  λu ≥ 1.0 means the collapse load exceeds the IS 800 factored load.
- The DDM report (section 3) carries the note for each φs class used; the four-analyses row names φs, its class and
  "not an IS 800 factor", and the note goes under the table; the site index has `phi_s`, `phi_s_class`,
  `phi_s_source`, `min_phi_lambda_combo` and a longer `min_phi_lambda_note`.

## Vmax/W, not Vmax/VB, on sheds (`snl/shed.py`, new; `scripts/build_site_index.py`, `snl/compare.py`, `pushover/report_india.py`)

- `snl/shed.py`: a run is a shed when the HR package says so — one floor level in the HR seismic weight table
  (`load_plan.json` seismic_summary.W_by_floor_kN), or a cfg `building_type` / occupancy use naming industrial,
  warehouse, shed, workshop or crane use. The basis sentence names the field. Sheds: IN_Ex1–Ex10, IN_Ex11 workshop,
  IN_Ex12 unitC (the review's list Ex 1, 3–5, 7–9, 12-C, plus Ex2, Ex6, Ex10 and the workshop).
- On a shed: the site index meta line shows "Pushover Vmax/W …" only (was "Vmax/VB 91.6 / 128.1 (Vmax/W …)"), with
  `shed`, `shed_basis`, `headline: vmax_w` and `vmax_vb_note` in the results; the four-analyses page shows V/W in the
  pushover and NLRHA rows and explains VB in a note; the pushover report puts Vmax/W first with a note above section 3;
  the NLRHA index adds the suite-mean V/W. Multi-storey runs keep Vmax/VB with Vmax/W beside it.
- The four-analyses page has a new "Pushover strength Vmax" row (kN, Vmax/W, Vmax/VB off sheds) that marks a direction
  whose curve ended in a numerical stop as a lower bound.
- PEB summary headers: checked on the five PEB runs; they read "design VB 29.9 / 39.8 kN (X / Y), W 956 kN, R 4 / 3
  (X / Y)" etc. (the first-wave fix), never "VB — kN, W 0.0, R None".

## Report-only refresh of stored pages (`snl report`)

- `snl report <job>` (which the site build runs on every run) now also refreshes, from the stored packages and without
  re-analysis, the NLRHA reports and viewer (record set, record pairs) and the pushover report (stop messages in mm —
  the first-wave fix had reached only re-run pushovers — and, on a shed, Vmax/W first). Idempotent.

## Smaller fixes found on the way

- The completeness gate (`nlrha/india_authority.py`) reads stored DDM results through the NL-36 runaway guard, as the
  report and the site index already did: the 2026-10-04 IN_Ex18 package stores its −732 step as a "ductility cap", and
  `snl report` wrote "complete" for it while the index counted a solver failure.
- B-1.1 text: "design engineer's statement required" also for results stored before the first wave (they say "EOR").
- The out-of-plumb basis no longer prints a literal "0.5 %%" (a string that was never %-formatted) and says "design
  engineer to confirm"; stored results are cleaned on display. "Unless the design engineer sets one" for the
  expected-strength factor.
- `retry` log lines say which combinations are SOLVER_FAILURE and which are named, and the old status of a replaced run;
  the code version is taken at the start of the re-run.

## DDM: `retry --b12-only` and the chunked re-run record (`steltic_ddm/cli.py`, `solver.py`)

- `retry --b12-only --combos …` (India): redoes only the IS 800 B-1.2 check at λ = 1 of the named combinations after a
  B-1.2 rule change (NL-37 changes nothing else). Each stored governing sweep — same combination, imperfection case and
  load step (the last NL-30 rung where it was retried) — is repeated only until λ = 1 is passed
  (`solver.sweep(stop_after_lambda1=True)`); the new B-1.2 row replaces the stored one only when the new curve repeats the
  stored curve step by step (`curve_prefix_match`, 5e-4 on λ and relative displacement), so the stored λu, status and
  curve stand. Otherwise the stored row is kept and a full `retry --combos` is required. Recorded per run
  (`b12_refresh`) and in `options.ddm_b12_refresh(_history)`; the DDM report says so under each refreshed row.
- Why: IN_Ex15 1.5DL+1.5LL needs all three NL-30 rungs (3 540 + 3 550 + 2 325 s in 2026-09, per imperfection case),
  which no 2 h process can hold; up to λ = 1 it is 70 steps.
- A re-run split into one-combination `retry` calls (to keep each process under the box's 2 h limit) keeps every
  call's record (`options.ddm_rerun_history`), with the NL commit used (`code_version`).
- The DDM report states which B-1.2 rows of combinations without earthquake still carry the unreduced imposed load
  (stored before NL-37), instead of the blanket "in every combination without earthquake".

## Re-runs (published copies in /home/claude/nl_rerun/<id>)

Before = the published first-wave site index; after = this branch's results. Gravity λu is unchanged everywhere (the
sweeps did not change). "Refresh" = `retry --b12-only` (B-1.2 redone from the stored governing sweep repeated to λ = 1;
every curve repeated the stored one exactly, max |Δλ| 0); "full" = `retry --combos … --only-listed`.

| Run | How (seconds) | Gate before → after | Gravity λu | B-1.2 worst before → after |
|---|---|---|---|---|
| IN_Ex19 stem | full, 5 combinations in 4 chunks (2 715 + 932 + 1 850 + 2 055) | complete_with_capacity_shortfall → **complete_with_solver_stops** (the NL-31-disclosed seismic stop kept) | 1.041 → 1.041 | **1.034 FAIL** gravity col BOX400X400X28, 1.5DL+1.5LL → **0.878** same column, 1.2DL+1.2LL+1.2EQ_Z+0.36EQ_Y (no reduction with earthquake); under 1.5DL+1.5LL 1.034 → 0.837 (r × fL × N_LL = 1 788 kN) |
| IN_Ex19 main | no new DDM run (the 2026-10-18 first-wave LL re-run, reports regenerated) | complete_with_capacity_shortfall → **partial** (the stored runaway in 1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z, stated) | 1.041 → 1.041 | 1.035 FAIL → 0.875 BOX400X400X28, 1.2DL+1.2LL+1.2EQ_Z+0.36EQ_X |
| IN_Ex11 | refresh, 5 combinations (86) | complete → complete | 1.214 | 0.887 gravity col WPB300X300X100.85 → 0.857 roof NPB450X190X67.16 (the column 0.887 → 0.782) |
| IN_Ex15 | refresh, 5 combinations (424; 1.5DL+1.5LL at Δλ 0.0125, the third NL-30 rung of its stored sweep, 71 steps) | complete → complete | 1.173 | 0.902 gravity col WPB360X370X165.35 → 0.831 roof NPB550X210X105.52 (the column 0.902 → 0.755) |
| IN_Ex17 | refresh, 5 combinations (859) | complete → complete | 1.306 | 0.908 floor WPB500X300X187.34 → 0.908 (a floor beam governs; the worst column 0.820 → 0.728) |
| IN_Ex20 | refresh, 5 combinations (458) | complete → complete | 1.217 | 0.992 lateral col WPB400X400X239.62 → 0.929 floor WPB550X300X199.44 (the column 0.992 → 0.825) |
| IN_Ex18 | full NL-30 `retry` of the stored runaway 1.2DL+1.2LL−1.2W_X (3 101): Δλ 0.05 → SOLVER_FAILURE, the runaway caught live at λ 1.668 (1 534 s); Δλ 0.025 → NO_LIMIT_POINT, post-peak budget at λ 1.669 (1 563 s), like its twin +W_X | complete (stale file; the index already counted 1 solver failure) → complete, solver failures 1 → 0 | 1.334 | 0.899 floor NPB600X220X154.47, 1.2DL+1.2LL+1.2EQ_Y[ea] → 0.899 (no 3.2.1 reduction in the Ex18 design) |

Validation of the refresh: on a copy of IN_Ex19 main, whose five LL combinations were fully re-run on 2026-10-18,
the refresh reproduced all 870 B-1.2 values (5 combinations × 29 member groups × N, M, M, D/C, V/Vd, N reduction) and
the λ = 1 brackets exactly (/home/claude/nl_work/validate/IN_Ex19_main_b12refresh).

IN_Ex19 main, 1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z — left as the stated solver stop:
- No checkpoint: the OpenSees state lives in the sweep's process, `solver.sweep` has no save / restore and `retry`
  writes ddm_results.json only at its end, so a sweep cannot be resumed in a second process.
- The method's ladder only gets smaller: Δλ 0.05 → 0.025 → 0.0125, time limit 2 400 × k s. Its stored rungs:
  0.05 stopped (step_exhausted, λ 1.330) after 5 668 s; 0.025 ran into the −788 runaway at λ 1.318 after 2 592 s. A
  re-run repeats both (≈ 8 300 s) before the third rung, and the third rung's own time limit is 9 600 s, longer than
  the 7 200 s a background process may run; a sweep step can also overrun its limit (the first rung ran 5 668 s against
  2 400 s). Neither the whole ladder nor the third rung alone can be fitted honestly; skipping the stored rungs or
  cutting the time limit would change the method.
- The combination's B-1.2 is evaluated (λ = 1 was passed before the runaway): satisfied, 0.854. Its converged steps
  reached λ 1.318 (and 1.330 in the first rung), so whatever the third rung found would not be below that; its
  siblings (1.2DL+1.2LL±1.2EQ_Y[ea]−0.3EQ_Z) ended NO_LIMIT_POINT on the clock at λ 1.36 and its mirror
  (−EQ_Y+0.3EQ_Z) at a ductility cap at λ 1.354. The gate stays **partial** and says why.

## Site build

The site build's nonlinear step (scratchpad `sitebuild/build_nl.sh`) works unchanged with this code. A second-wave
variant, /home/claude/nl_work/build_nl2.sh, also copies the refreshed `nlrha/` and `pushover/` pages, rebuilds every
run's ddm_report.html from its ddm_results.json into a temporary folder (`steltic_ddm report --out`, so the φs note
reaches the runs that were not re-run, without rewriting stored results) and takes the PEB runs from a copy of the PEB
gold set (`snl report` now rewrites the stored NLRHA / pushover HTML in place). Run into a scratch folder it built all
24 runs and the index (24 examples) in about a minute.

## Tests

`tests/test_second_wave_2026_10.py` (package tests skip without the NL gold sets):
- the chunked re-run record and the code version;
- `curve_prefix_match`, the stop-after-λ = 1 flag and the `--b12-only` option;
- the record-set facts against `records/p695_farfield/index.json` (and that no Indian or Himalayan event is in it),
  the analyses sentence, the disclosure (set, source, what it lacks, scaling, 7.7.4 quoted from the corpus page), a
  user-supplied set;
- the shed rule; the shed meta line without Vmax/VB;
- the φs note; the DDM report notes and the per-combination imposed-load basis;
- the IN_Ex1 PEB four-analyses page (header, V/W, record pairs, analyses, record set, φs) and the idempotent refresh of
  its NLRHA / pushover pages and viewer; the IN_Ex15 page (Vmax/VB kept, lower bound, φs·λu below 1 explained);
- the gate reading the stored IN_Ex18 runaway; the cleaned out-of-plumb basis text.

Full suite (STELTIC_ENGINE_DIR = the frozen HR engine e340df8, STELTIC_HR_ROOT = an export of steltic_india
origin/main 251496d, under /home/claude/bin/heavy): **456 passed, 4 skipped, 0 failed** (first wave: 420 passed, 23
skipped). The 4 skips: the two USA Ex18_R3 DDM fixtures (need the USA engine) and two NL-33 tests looking for an
IN_Ex10 gold job under their own default path.
