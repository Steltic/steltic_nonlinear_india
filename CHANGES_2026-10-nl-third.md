# steltic-nonlinear-india — 2026-10/11: third wave (EBF link model, engine version, presentation, resumable re-runs)

Branch `fix/2026-10-third-nl` from `origin/main` (4e58945, the check fixes merged). Handoff items P1, P2 and P10 and
the stage-2 tooling. This change alters one analysis model, the EBF link, so every EBF result (IN_Ex15, IN_Ex19,
the IN_Ex19 stem: pushover, NLRHA and DDM) is due a re-run. Non-EBF models are built exactly as before. The full
re-runs of all buildings were not started; the designs are still changing. The orchestrator below is for that re-run.

## P1 — EBF link model (`pushover/fibre_model.py`, `member_response.py`, `steltic_ddm/model_gmnia.py`, `sections_fiber.py`)

**What was wrong.** The Y-direction links of IN_Ex15, IN_Ex19 and the stem rotated 0.40–0.50 rad at 0.2–1.1 % storey
drift, where L/e × drift gives 0.02–0.10 rad. The Y pushovers lost 12–52 % of base shear in one step.

**Cause.**
- Every link was ONE force-based element (forceBeamColumn, 5 Lobatto sections). The IS 18168 11.2 shear yielding was
  aggregated on each section (Steel01 on Vz, hardening 0.5 %).
- Since NL-14 the HR gravity replay puts the floor load on the link, so the shear varies along it.
- Once the link yields, the element's local iteration can accept a false state:
  - the end sections yield in opposite directions (about +0.39 / −0.39 rad) while the middle section stays elastic;
  - their shear strains cancel in the element end deformations, so the element's convergence test (an energy norm on
    the element deformations) passes;
  - the sections are then out of equilibrium by about 2 V_pL;
  - the element carries almost no shear: the frame loses strength in one step, and the reported "link rotation" (the
    largest section shear strain) is the false end-section value.
- The Y direction: in IN_Ex15 the Y beams and links carry the floor load (EV state 29 N/mm on the links). The X links
  carry only their self-weight (4.2 N/mm).

**Evidence.**
- IN_Ex15 Y, the old model (a diagnostic push to 2 in):
  - at u = 1.38 in the base shear falls from 1,620 to 1,493 kip;
  - links 375 / 380 / 607 / 612 jump from 0.0014 to 0.39 rad;
  - their section shears read −286 / −285 / 11 / 308 / 309 kip, where the element's end moments give an equilibrium
    shear of about 12 kip.
- The same push with the link loads lumped to the link end nodes is physical:
  - the links yield at about 1.6 in;
  - γ = 0.033 rad at 0.42 % drift, about (L/e) × the plastic drift;
  - no loss of strength, and 15 s instead of 176 s.
- A one-storey, one-bay EBF (L/e = 10) with 30 N/mm on the link, pushed in 20 steps to 1 % drift with the old model:
  - at 0.1 % drift V = 33 kip instead of 321 kip, and a "link rotation" of 0.33 rad;
  - in 100 steps it does not trigger, so it depends on the step size.

**Fix.**
- Each link is two flexural fibre halves (same section, same transformation) joined at mid-length by ONE zeroLength
  shear spring:
  - the spring acts on the link's local z (vertical), with V_pL = fy A_wL / √3 (IS 18168:2023 11.2) and K = G A_wL / e;
  - the post-yield slope is 0.5 % of K, as before (a modelling assumption);
  - it is rigid on every other DOF;
  - a single spring has no false mode.
- The link rotation is the spring deformation / e: the same quantity as before (total shear rotation, reference
  0.08 rad of IS 18168 12.3.3.1).
- The halves keep the parent tag and SEG_ELE_BASE + tag·100 + 1, so the HR gravity replay finds them. The NLRHA gives
  the halves stiffness-proportional damping and not the spring.
- The DDM GMNIA model uses the same link (`GMNIAModel._add_link`).
- `FiberSectionBuilder.link_aggregator` is kept for its unit test but is no longer used by a model.
- DDM: the spring's rigid DOFs are 1000 × the half link's own axial and flexural stiffness.
  - The model-wide K_TRANS / K_ROT (1e9 / 1e10) are rigid in kip-in, but not in the India N-mm GMNIA: 4EI/(e/2) of a
    900 mm WPB400 link is 1e12 N·mm/rad.
  - With them the spring was a hinge at mid-link. The IN_Ex19 stem gravity-transfer gate caught it: link M 0.28 × HR,
    70 of 396 comparisons outside ±5 %.
  - The gate now passes as in October.
  - The pushover / NLRHA model runs in kip-in, where RIGID_T / RIGID_R are 1e4 × these stiffnesses.

**Tests.** `tests/test_third_wave_2026_10.py`:
- the one-bay EBF along X and along Y, in 20 and 100 steps:
  - link rotation within 0.8–1.0 × (L/e) × drift at 1 % drift;
  - dγ/dθ = L/e ± 10 % after yield;
  - no step loss of base shear;
  - the spring at V_pL plus hardening;
- the X and Y frames are identical;
- the gravity chain of the halves;
- the GMNIA links (two halves plus one spring, V_pL), on the IN_Ex15 gold when present.

**Re-runs (proof, sandbox copies):** RESULTS_P1

## Engine version (P2): NL against current HR main (`snl/hr_gravity.py`)

- NL reads the HR engine for:
  - the gravity states (static_model.build_static / apply_gravity_state);
  - the cfg and the combinations;
  - the section tables.
- The October runs used e340df8 (before the first wave). Between e340df8 and HR main 44b74de only `static_model.py`
  and `engine3d.py` changed, for one thing: roof collateral and rooftop PV (cfg `D_roof_collateral`, `D_roof_pv`).
  - They are dead load in every combination with a dead-load factor ≥ 1.0 and in the seismic weight.
  - They are left off the IS 800 Table 4 0.9 DL rows (`engine3d.nonpermanent_factor`).
- `hr_gravity` now records, when the cfg declares collateral or PV, a state **Dp**: the dead load without them.
  - `combine()` applies a dead-load factor below 1.0 to Dp instead of D, as the HR engine does.
  - Records without collateral are unchanged.
- Each record now carries the engine fingerprint (`engine_sha`: sha256 of static_model, engine3d, india_loads,
  india_combos, roof_geometry). `ensure()` re-records when the engine differs, and keeps the old record if re-recording
  fails.
- **Regression.** States recorded with HR main against the October records (`scratch/grav_regress.log`):
  - IN_Ex9, IN_Ex11 and IN_Ex15: every state identical, element by element;
  - the current gold IN_Ex1 (collateral 0.15 kN/m²): D and EV gain 337.5 kN (0.15 × the roof area), and Dp equals
    the old D.
- The column in-span moment branch (steltic_india fix/2026-10-column-span-moment, 00336f6) changes static_model's
  member records, not the gravity states. Its records are identical to HR main's for IN_Ex15 and IN_Ex1; only the
  fingerprint differs, so a re-record follows. The 9 vendored modules and 2 section tables are byte-identical to both
  44b74de and 00336f6.
- Analyses against HR main: RESULTS_ENGINE
- New section families: an IS 808 angle brace (ISA) now buckles about its v-v axis (`r_min_mm` of the IS 808 table)
  in the brace strengths and the backbone slenderness. MB / MC / CHS labels of HR main's tables resolve. A channel (MC)
  fibre section is built as an equal-flange I-section (same area, strong-axis inertia and plastic modulus): a modelling
  simplification for strong-axis bending.

## P10 — presentation (`pushover/vmax_policy.py` new; `snl/compare.py`, `scripts/build_site_index.py`, `pushover/report_india.py`, `viewer3d_india.py`, `snl/public_text.py`, `steltic_ddm/report_ddm.py`, `viewer3d.py`, `india_checks.py`, `cli.py`)

**Vmax only up to the IS-MCE target.**
- The headline pushover strength is the largest base shear from zero to the IS-MCE target displacement δt, with the
  curve interpolated at δt.
- "≥" is printed only when the curve ended in a numerical stop before δt. Most earlier "≥" flags go, because the
  targets were reached long before the stop.
- The rest of the curve is still drawn, and its peak is a sentence of information ("beyond the IS-MCE target … the
  curve continues to … kN at … mm — information, not the pushover strength").
- Where it shows:
  - four-analyses row "Pushover strength Vmax up to the IS-MCE target", plus the basis note;
  - pushover report: a marked headline table in section 3, and the old line becomes "whole-curve peak (information)";
  - viewer: "Vmax up to the IS-MCE target (headline)" and "Peak of the whole curve (information)";
  - site index: `vmax_vb_*`, `vmax_w_*` and their texts now hold the capped values;
  - new index fields `vmax_target_mm_x/y`, `vmax_beyond_text_x/y` and `vmax_basis`;
  - meta line "Pushover Vmax/VB up to the IS-MCE target …".
- Example, the IN_Ex10 shed:
  - Vmax/W up to the target is 0.362 / 0.359 (δt about 8 mm);
  - the whole curve peaks at 8,277 kN at 316 mm.

**Te < T1 flagged.** When the NSP effective period is more than 1 % below T1, the four-analyses page, the pushover
report, the viewer and the index (`te_below_t1_x/y`, `te_note_x/y`) say: "the effective period cannot be shorter than
the elastic one; the bilinear fit took its initial stiffness from a softened part of the curve, so the target
displacement from it is uncertain (shown as computed)". IN_Ex10, for example, has Te 0.166 s against T1 0.220 s.

**No role keys or solver words on public pages.**
- `public_text.words / words_html` translate keys and solver tokens, idempotently. `words_html` leaves `<script>`
  and `<style>` alone, where the viewer data keys live:
  - role keys: lateral_col → lateral column, gravity_col → gravity column, eave_strut, crane_girder, …;
  - sweep statuses: LIMIT_POINT → limit point, NO_LIMIT_POINT → no limit point, PLASTIC_PLATEAU, DUCTILITY_CAP,
    SOLVER_FAILURE → numerical stop;
  - terminations: time_limit, post_peak_budget, step_exhausted, too_many_failures, max_steps, disp_cap, runaway,
    plateau;
  - corpus group keys: material@E350 → material (E350), tube_material@YST310, deformation_capacity.
- Applied through `scrub` / `scrub_html`, so the pushover report, the NLRHA refresh, the gate texts and the index
  texts get it. The DDM report and the four-analyses page are also passed through it.
- DDM report section 6:
  - was the "Solver log" (raw status, termination and the solver's own log lines);
  - now "How each sweep ended" (combination, imperfection, result, what ended the sweep, load steps, failed steps) in
    words;
  - the log lines stay in ddm_results.json.
- DDM report footer "engineer of record" → "design engineer".
- DDM viewer: roles shown in words (`role_labels`) and the mechanism text in words; colours are still keyed by role.
- Meta line: the gravity status is in words.

**Member forces at λ = 1 stored.**
- Every DDM run that reaches λ = 1 now stores its GMNIA member forces there in `ddm_results.json`:
  - `runs[].forces_at_1`: N_abs, N_comp, N_top, M_major, M_minor and V per member, in kN / kN·m at 0.1 resolution;
  - these are the forces before the IS 875-2 3.2.1 reduction, with the λ bracket;
  - a top-level `member_index` gives the kind, role and section.
- `india_checks.b12_from_stored(run, index, fy_fn, llr_plan, fL, meta)` re-applies the current B-1.2 rule without a
  sweep. The B-1.2 refresh stores the forces too.

## P2 / stage 2 — resumable full re-runs

**`snl/checkpoint.py` (new): deterministic replay.** The analyses keep their state inside one OpenSees process and
cannot be saved half-way, but they are deterministic, and a failed `analyze` reverts to the last commit.
- The journal records, for every `analyze` call: its outcome, the load factor, a displacement fingerprint and the
  elapsed time.
- A later process runs the same code from the start against the journal:
  - a journaled failure returns at once, without computing;
  - a journaled convergence is recomputed and must land on the same state, else ReplayDiverged;
  - the run's clock reads the journaled times, so time-limit decisions repeat exactly;
  - past the end of the journal the run continues live.
- A process stops at its budget (`--chunk-seconds`, or the orchestrator's `$SNL_DEADLINE`) with exit 75. The journal
  is saved there and every 5 min.
- Finished pieces are stored whole and are not replayed: a DDM sweep rung, a pushover direction.
- Keys: the analysis source files (`code_key`; report-only modules are excluded), the package model, gravity and
  params files, and the run options.
- A resume recomputes the converged steps only. A run whose converged steps alone take longer than a chunk cannot
  progress this way.
- **Limit found.** A failed `analyze` is not perfectly state-neutral in OpenSees:
  - on the one-bay EBF with forced failures, the replayed curve differs from the uninterrupted one by 4.5e-13
    (relative);
  - on IN_Ex15 Y, at a near-singular step (u ≈ 1,000 mm, 9 step halvings), the NewtonLineSearch attempt that
    converged after three failed attempts in the original failed in the replay (journal call 86).
- The fingerprint check catches this (ReplayDiverged). The rung, or the pushover direction, then restarts live in the
  same chunk (`Journal.restart_live`): correct, but that chunk gains nothing. So the journal carries a run across a
  chunk boundary only when its hard steps come after the boundary; otherwise it is a safe no-op.
- An exact state checkpoint was tried with OpenSees' own `database File` + `save` / `restore` on the same EBF: the
  save works, but the restore fails ("database failed to restore state").

**Options.**
- `python -m pushover run … --checkpoint-dir D --chunk-seconds S`
- `python -m steltic_ddm run|retry … --checkpoint-dir D --chunk-seconds S` (nothing is merged into ddm_results.json
  until every sweep has finished)
- `python -m nlrha run … --record-cache D --chunk-seconds S --parallel 1`: finished records are kept, keyed by the
  code, the model and the record's inputs; a chunk stops before a record that would not fit (the longest record so
  far).

**`scripts/nl_orchestrate.py` (new): the queue.**
- `plan --queue Q --jobs …` writes, per job: the gravity record (with the queue's engine), the pushover (X + Y,
  journaled), the NLRHA (record cache), the DDM (journaled) and the report.
- `next --queue Q --budget 6900` runs ready steps, each under `heavy` with `timeout`, the chunk budget and the
  deadline, until its own budget is spent:
  - a step that exits 75 stays queued (`resume`);
  - a timeout (124) resumes from the last journal save.
- `status` prints the queue. Q.runtime.log gets one line per chunk; Q.lock allows one `next` at a time.
- Commands are the October re-run commands, with the checkpoint options added.

**IN_Ex19 earthquake combination (1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z).** RESULTS_EX19

## Tests

- New file: `tests/test_third_wave_2026_10.py`. It covers:
  - P1;
  - the GMNIA link;
  - Vmax up to the target;
  - Te < T1;
  - the site-index fields;
  - public words;
  - stored forces and B-1.2 re-application;
  - the Dp state;
  - the engine fingerprint;
  - angle braces;
  - the journal (fake OpenSees: failed calls skipped, divergence refused);
  - a real chunked EBF pushover repeating the uninterrupted one bit for bit;
  - the orchestrator.
- Full suite: RESULTS_SUITE
