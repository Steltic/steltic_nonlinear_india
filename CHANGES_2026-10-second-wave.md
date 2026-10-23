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

RESULTS_TABLE

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
  its NLRHA / pushover pages and viewer; the IN_Ex15 page (Vmax/VB kept, lower bound, φs·λu below 1 explained).
