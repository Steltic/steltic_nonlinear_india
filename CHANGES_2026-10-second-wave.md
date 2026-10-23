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

---

# Check fixes, 2026-10-23 (independent review of the second-wave publish)

Branch `fix/2026-10-check-fixes` from `origin/main` (0fec0c5, the second wave merged). The review (findings 1–14) checked
the published pages; this repo takes findings 1–4, 6, the NL items of 14 and the NL items of 5. Report-only: no
analysis was re-run; every number below is read from the stored packages.

## Finding 1 — a pushover target the curve did not reach (`snl/compare.py`, `pushover/report_india.py`, `snl/gate_reason.py`, `scripts/build_site_index.py`)

- IN_Ex19 main, push Y: the curve ends at 86 mm in a numerical stop; the IS-MCE target is 179.7 mm. The four-analyses
  row printed "δt = 179.7 mm; V/VB = 2.19; max storey drift 0.408 %" — the values at the curve end, as if at the target.
- Now, wherever such a row is printed:
  - four-analyses: "δt = 179.7 mm: target NOT reached — the curve ended in a numerical stop at 86 mm, so the values
    that follow are at the curve end, not at the target: …";
  - pushover report (refresh of the stored page): section 2 "reached: NO — the curve ended at 86 mm", section 3 the
    row "IS-MCE (curve end: the 179.7 mm target was not reached; values at the curve end)" and the member-group heading;
  - completeness gate notes and reason, site index `mce_target_text_x/y` and the flag line.
- Only IN_Ex19 main Y misses a target among the 24 runs (scanned from the stored packages).
- The gate status is unchanged (the miss is stated, not counted as a new blocking reason).

## Finding 2 — a lower-bound Vmax reads "≥" (`snl/compare.py`, `pushover/report_india.py`, `pushover/viewer3d_india.py`, `scripts/build_site_index.py`)

- A direction whose curve ended in a numerical stop (the existing rule: tail `lower_bound` or a solver stop) prints
  "≥" before Vmax, Vmax/W and Vmax/VB:
  - four-analyses: "≥ 30385 kN / ≥ 8815 kN", "Vmax/W: ≥ 0.516 / ≥ 0.150", with "≥ marks a lower bound (X, Y: the curve
    ended in a numerical stop before it lost strength, so the peak is not established)";
  - pushover report section 3: "Vmax ≥ 8815 kN (Vmax/VB ≥ 2.19, Vmax/W ≥ 0.150) — a lower bound: …";
  - pushover viewer (direction table; `annotate()` adds `lower_bound`, the unreached targets and the review summary
    from the stored package; a viewer written before is rebuilt once, from the same stored data);
  - site index: `vmax_vb_text_x/y`, `vmax_w_text_x/y` ("≥ 4.8"), `vmax_lower_bound_note`, and the meta line.
- 13 directions in 9 runs, as the review counted. The lead fixes india.html; the index now carries the texts.

## Finding 3 — the completeness gate in plain words (`snl/gate_reason.py`, new; `nlrha/india_authority.py`, `snl/compare.py`, `scripts/build_site_index.py`, `steltic_ddm/report_ddm.py`)

- `gate_reason(job)` builds, from the stored results only, what stopped, in which combination, at which λ, whether a
  capacity is reported, whether its B-1.2 check was made, and why the stop does or does not block COMPLETE.
- Where it is printed:
  - a box at the top of every four-analyses page ("Completeness gate: PARTIAL. …");
  - `complete_gate.json` (`label`, `reason_text`, notes in words);
  - the site index (`gate_label`, `gate_reason_text`).
- IN_Ex19 main, PARTIAL: 1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z stopped at λ = 1.318 in a numerical runaway (the next step
  returned λ = −787.9, discarded); no capacity is reported; λ = 1 was passed, so its B-1.2 check is made and satisfied
  (0.854). It blocks COMPLETE because the method re-runs a stopped sweep at Δλ, Δλ/2 and Δλ/4 before it may state the
  stop instead, and 2 of the 3 sizes have been run.
- IN_Ex19 stem, COMPLETE WITH SOLVER STOPS: 1.2DL+1.2LL−1.2EQ_Y[ea]+0.3EQ_Z stopped at λ = 1.337 at all three sizes
  (0.05, 0.025, 0.0125). It is an earthquake combination (information only, no φs pass/fail) past λ = 1, so it is
  stated, not blocking; its B-1.2 check is satisfied (0.863).
- No ticket ids in public text:
  - gate notes ("disclosed (NL-31)", "(NL-36)");
  - the four-analyses row "numerical stops (NL-24 / NL-36)" → "sweeps that stopped numerically (not a structural
    limit)";
  - the DDM report (NL-24, NL-26, NL-33, NL-36, NL-38; "second wave, NL <sha>" → "code version <sha>"; "the
    completeness gate states them" → "… on the four-analyses page states each stop and whether it blocks");
  - the index `reclassified_note`;
  - the NLRHA reports ("Modelling disclosures (NL-21)", the trimming basis "(NL-21)").
- `snl/public_text.py` (new): `scrub` / `scrub_html` remove them (and "EOR", the old hinge note, the sf-bounds key)
  from text written by older code. The four-analyses cells, every string of an index entry and the refreshed NLRHA /
  pushover pages pass through it.

## Finding 4 — IN_Ex19 stem, push Y: not physically credible, put under review (`pushover/review.py`, `scripts/pushover_review.py`, new)

What the stored results show (no re-run):
- At 50 → 57 mm of roof displacement the base shear falls from 2,276 kN to 1,103 kN in one step (−52 %). At the next
  reported point (the IS-DBE target) no brace has buckled and no beam or column fibre has yielded; only links have.
- The EBF link rotations at the targets are 0.42 rad (IS-DBE, 0.61 % storey drift) and 0.50 rad (IS-MCE, 1.07 %),
  five to six times the 0.08 rad reference of IS 18168 12.3.3.1.
  - A mid-span link of length e in a bay of length L rotates about L / e times the storey drift. Here L / e =
    8 500 / 900 = 9.4, so about 0.06 / 0.10 rad.
  - In X the same model gives 0.012 rad at 0.23 % drift, in line with that.
  - The Y link rotations are not compatible with the frame's drift.
- After the drop the curve rises almost linearly to 3,476 mm (8.8 % of the 39.4 m height); Vmax 8,834 kN
  (Vmax/VB 6.3) is reached at 3,401 mm, 3.9 times the 2,276 kN before the drop.
- The bilinear fit takes Ki as the secant at 0.3 Vmax, which lies after the drop: 8.3 kN/mm against an initial slope of
  45.3 kN/mm (Ki / Ke 0.18). So Te = 0.421 s (IS-DBE) and 0.722 s (IS-MCE) are below T1 = 0.984 s — the review's
  "Te below T1". The targets (95.6 / 185.3 mm) and V/VB at them (0.99 / 1.37) come from that fit.

The same signature in the other EBF runs. A scan of all 24 runs' stored packages found no other link pattern and no
other one-step loss above 4 %. Te below T1 (Ki / Ke 0.57–0.76) also occurs in Ex1–Ex5 X, Ex7 Y, Ex9 Y, Ex10 X and Y,
the Ex11 workshop X and Y and the stem X, where Vmax lies far out on a hardening curve; that is noted for the NL owner
and not flagged.
- IN_Ex19 main Y: a 12 % one-step loss at 45 mm, then the numerical stop at 86 mm (finding 1); links 0.43 / 0.44 rad at
  0.39 / 0.41 % drift (kinematic about 0.04 rad).
- IN_Ex15 Y: links 0.40 / 0.43 rad at 0.23 / 0.48 % drift (L / e = 9 000 / 900 = 10, kinematic 0.02 / 0.05 rad); a 16 %
  one-step loss at 137 mm, after the IS-MCE target; Vmax at 1,229 mm after that loss.
- The NLRHA link rotations of the three runs show the same pattern: up to 0.43–0.48 rad at peak storey drifts of
  0.54–1.47 %.
- The HR model's link elements use the same transformation in X and Y (local z vertical), so the cause is not that;
  it is not established from the stored results.

What changed:
- `scripts/pushover_review.py <job> --direction Y --l-over-e … --nlrha` computes the evidence above from the stored
  packages and writes `<job>/pushover/pushover_review.json` (written for the three runs, 2026-10-23).
- Where the flag shows:
  - four-analyses: "UNDER REVIEW" on the Y rows and the Vmax row, and the findings as a note;
  - pushover report: a red note at the top and "(UNDER REVIEW …)" on the Y line;
  - pushover viewer: an "UNDER REVIEW" row;
  - gate reason and notes;
  - site index: `under_review_y`, `review_y`, `vmax_*_text_y` "under review", the meta and flag lines.
- `--clear` removes the record, and the next `snl report` removes the flags.
- The NL owner should find the cause (the Y-direction EBF links of the NL models) before these curves, the NLRHA link
  results and the numbers derived from them are quoted again.

## Finding 6 and the NL items of 5 — "EOR", file names and keys (`snl/public_text.py`, `snl/grounding.py`, `nlrha/report_india.py`, `nlrha/record_set.py`, `pushover/report_india.py`, `steltic_ddm/report_ddm.py`, `steltic_ddm/peb_restraints.py`, `snl/shed.py`)

- The hinge note on 72 pages read "The hinge backbones in hinge_params_used.json are modelling assumptions
  (information / EOR input)". It now reads "The hinge backbones used in these analyses are modelling assumptions
  (information / design engineer's input)". Stored pages are refreshed.
- On the four-analyses page:
  - the "Inputs (sha256): {…}" line is gone; the fingerprints stay in snl_summary.json for the gate's freshness check;
  - "the engineer may set nl_plan.gm_selection.sf_bounds" → "the design engineer may set them" (also on the NLRHA
    pages).
- NLRHA section 6: damping and accidental torsion were printed as raw JSON. They now read in words, e.g. "ξ = 2.5 %
  (cap 5 %); Rayleigh … (modelling assumption); …; accidental torsion eccentricity 0.05 b, + in X and + in Y (IS 1893
  7.8.2 …)".
- Pushover reports:
  - "None" in the steel table (YSt 310 tubes have no IS 2062 thickness band) → "—";
  - the footer "hinge_params verified=False; IS specification values collected=True" in words.
- "collected by snl collect" → "collected from the IS corpus".
- "(nlrha ground_motions.select_and_scale)" → "(the tool's selection rule)".
- "supplied with --records-set" → "can be supplied in place of this one".
- The shed basis "(HR cfg building_type 'industrial')" → "(building type 'industrial' in the HR design input)".
- DDM report:
  - "vs member_schedule" → "vs the HR design's member forces";
  - "combinations from load_plan" → "of the HR design's load plan";
  - the restraint summary stored in ddm_results.json ("PEB restraints (NL-33, cfg['flange_braces'] as peb_build /
    D-T1)", "Rolled-section restraints (NL-38, from the HR cfg …)", and the sources "cfg['LLT_hog_mm']['roof']" …) in
    words, with the ruling and its meaning ("Steltic design ruling D-T1, lateral-torsional buckling checked segment by
    segment between restraints", as peb_restraints.py describes it); new runs write it that way.

## Finding 14 — rounding (`snl/compare.py`, `steltic_ddm/report_ddm.py`)

- IN_Ex19 stem: the four-analyses DDM row showed 1.5DL+1.5LL λu = 1.042 against the headline 1.041 (rounded down).
- Every λu, λ reached and φs·λu on the four-analyses page and in the DDM report is now rounded down to 3 decimals, like
  the headline and the index. B-1.2 ratios are rounded up.
- Many DDM rows therefore read 0.001 lower than before. No value changed.

## Site build (/home/claude/nl_work/build_nl2.sh; the earlier version kept as build_nl2.sh.bak_2026-10-23)

- The re-run runs' ddm_report.html is now rebuilt from ddm_results.json like the others. It used to be copied as
  stored, so the text fixes would not have reached it; the rebuilt text is otherwise identical apart from the
  timestamp. Their stored DDM viewer is copied as before.
- After the build, every published page (viewers excluded) and index.json are scanned for ticket ids, "EOR", JSON
  file names and keys, "Inputs (sha256)", `cfg[` and "None".
- Into a scratch folder: 24 examples, the same 202 files as the published set, 0 hits.

## Tests

`tests/test_check_fixes_2026_10.py` (14 tests; the gold-based one skips without the NL gold set):
- `scrub` / `scrub_html`: ticket ids, "EOR", the old hinge note and the sf-bounds key go; images and a second pass are
  untouched; the hinge note in every provenance state;
- `gate_reason`: PARTIAL (a runaway with 2 of 3 step sizes: named, λ, no capacity, B-1.2 0.854 rounded up, why it
  blocks), COMPLETE WITH SOLVER STOPS (all 3 sizes, earthquake combination past λ = 1: stated), the shortfall text and
  COMPLETE;
- the review evidence and text on a synthetic package (a one-step loss, links against L / e, the X comparison);
- the pushover report refresh: "≥" only on the lower-bound direction, the unreached target in sections 2 and 3, "—" for
  "None", no "EOR" / ticket ids / file names; the review note added once, idempotent, and removed with the record;
- the index fields (`vmax_*_text`, `mce_target_text`, `under_review`, `review`, the meta and flag lines);
- the DDM report: rounding down, no ticket ids in the India builder, the restraint summary and sources in words; the
  restraint summary new runs write;
- the NLRHA damping / torsion in words (and the refresh of a stored paragraph), the pushover footer, the shed basis,
  the viewer annotations;
- the IN_Ex15 gold run end to end: gate box, "≥", review flags, no sha256 line, no ticket ids, complete_gate.json
  reason, the index entry.

Changed assertions (new wording, same facts):
- `test_peb_four_analyses_page`: "Vmax/W: 1.972 / ≥ 1.847";
- `test_multistorey_four_analyses_keeps_vmax_vb`: "Vmax/VB: ≥ ";
- `test_rolled_plan_ex9`: "Rolled-section restraints (from the HR design input";
- `test_site_index_builder`: the mini Ex10 run's flag now states its unreached IS-MCE target.

Full suite (same set-up as above, under /home/claude/bin/heavy): **470 passed, 4 skipped, 0 failed** (second wave:
456 passed, 4 skipped; the same 4 skips).
