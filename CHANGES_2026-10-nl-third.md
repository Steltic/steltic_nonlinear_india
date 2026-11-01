# steltic-nonlinear-india — 2026-10/11: third wave (EBF link model, engine version, presentation, resumable re-runs)

Branch `fix/2026-10-third-nl` from `origin/main` (4e58945, the check fixes merged). Handoff items P1, P2 and P10, the
stage-2 tooling, IN_Ex21 support and the fixes of the independent review (`briefs/NL_REVIEW.md`, section "Review
fixes" below). The branch carries code, tests and this file only: no result files (none were ever committed on it).

What changes results, so that stage 2 refreshes ALL NL results on the owner's "go":
- the EBF link model (every EBF pushover, NLRHA and DDM);
- the NSP initial stiffness Ki (review M2): Te and the IS-DBE / IS-MCE target displacements of EVERY pushover change;
- the pushover headline (review M1) and the page wording, on every building.
Non-EBF analysis models are otherwise built exactly as before. The full re-runs were not started (owner hold).

## Status of the building-level runs (owner hold, 2026-11-01 19:03: no further nonlinear runs until the owner says go)

Done, on sandbox copies (before the review; the review changed no part of the link that the proof is about -- the
false converged state -- but see the notes under the IN_Ex15 table):
- the IN_Ex15 Y link-fix proof (main push, 3,860 s; table under P1);
- the gravity regression against HR main for IN_Ex9, IN_Ex11, IN_Ex15 and IN_Ex1, plus the 00336f6 branch;
- the IN_Ex9 and IN_Ex11 pushover X + Y regression against HR main.

Pending (the commands are below; none were started after the hold):
- the IN_Ex19 stem Y and IN_Ex19 main Y link-fix proofs;
- the IN_Ex11 DDM B-1.2 refresh against HR main;
- the IN_Ex19 earthquake DDM combination with the fixed link;
- the IN_Ex21 nonlinear runs (stage 2);
- the full re-runs of every EBF analysis (pushover, NLRHA, DDM) and of the other buildings, when the designs are
  final.

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
  - the spring acts on the link's local z (vertical), with V_pL = fy_w A_wL / √3 (IS 18168:2023 11.2 a) and
    K = G A_wL / e; fy_w is the IS 2062 band of the WEB (review L4) and a box link has two webs (L5);
  - the post-yield slope (review L6) is calibrated so the spring reaches Sh × V_pL at 0.08 rad of inelastic rotation:
    Sh = 1.25 for I-shaped and 1.4 for box links (IS 18168:2023 12.3.2.2), 0.08 rad the 12.3.3.1 limit. That is
    b = c / (1 + c), c = (Sh − 1) / (0.08 √3 G / fy_w): 0.59 % of K for fy_w = 250 MPa (it was 0.5 %, a bare
    assumption, reaching 1.21 V_pL). Kinematic hardening only (Steel01), no isotropic part and no degradation past
    0.08 rad (cyclic tests reach 1.3–1.5 V_pL); and the model's steel is the characteristic fy × the design engineer's
    expected factor (default 1.0), so the 12.3.2.2 Ry (Table 1: 1.4 for E250, 1.2 for E350) is NOT in the spring --
    capacity-protected members' NLRHA forces are below the IS 18168 overstrength demand by that factor;
  - it is rigid on every other DOF;
  - a single spring has no false mode.
- The link rotation is the INELASTIC rotation (review L2, IS 18168 12.3.3.1: "the inelastic angle between the link and
  the beam outside of the link"): the spring deformation less V / K, over e. The shear ductility γ/γy stays on the
  total. The flexural rotation at the ends of the halves is not in it; for a short link it is small:
  - e V_pL / M_pL is checked against 1.6 (11.3) when the spring is built; a longer link is flagged in the log and
    the section record;
  - every current gold link is short (e V_pL / M_pL 0.70–1.16 in IN_Ex15 and IN_Ex19, the reviewer's check), with end
    moments below the flange-only M_p.
- Not modelled (review L3): the 11.2 shear–axial reduction for Pu/Py > 0.15 and any shear–moment interaction on the
  spring. Right for links inside a rigid diaphragm (N = 0, verified); a link outside one would need it.
- A link the model cannot carry is refused loudly (review L7): a released link in the DDM, or a link that is not the
  HR model's unreleased ElasticTimoshenkoBeam in the pushover (every gold link is one: 92 in IN_Ex15, 168 in IN_Ex19,
  72 in the stem).
- The halves keep the parent tag and SEG_ELE_BASE + tag·100 + 1, so the HR gravity replay finds them. The NLRHA gives
  the halves stiffness-proportional damping and not the spring.
- The DDM GMNIA model uses the same link (`GMNIAModel._add_link`). It gives links no rigid end stubs (review L8):
  the stubs model a beam framing into a column; a link frames into the beam and the braces, and the HR models have no
  rigid end offsets (no -jntOffset in any gold model). The India DDM default for the stubs is off (WP4.9), so the
  stored India EBF sweeps had none on their links either (ddm_results.json `rigid_end_offset: false`).
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

**Re-runs (proof, sandbox copies).**
`scripts/link_proof.py` (new, read-only) prints the evidence below for any EBF job.
Main push only (`--tail none`), Y direction, the frozen HR engine e340df8 as in October, so that only the link
model differs. The October package is the reference; `scripts/link_proof.py <job> Y <L/e> pushover_proof` reads both.

| IN_Ex15 Y (L/e = 10) | October (one-element link) | Link fix |
|---|---|---|
| Largest one-step loss of base shear | 16 % (126 → 137 mm) | none |
| Link rotation at the IS-DBE target, against (L/e) × drift | 0.398 rad against 0.023 | 0.007 against 0.015 |
| Link rotation at the IS-MCE target, against (L/e) × drift | 0.434 rad against 0.048 | 0.044 against 0.053 |
| Te / T1 | 0.870 / 0.871 s | 0.871 / 0.871 s |
| V / VB at the IS-DBE / IS-MCE target | 1.83 / 2.00 | 2.33 / 2.58 |
| Base shear at the IS-MCE target δt (both curves still rising there: not a strength, review M1) | 8,773 kN | 11,333 kN (δt = 93 mm) |
| End of the main push | 17,404 kN peak at 1,229 mm | 19,170 kN peak at 999 mm; numerical stop at 1,014 mm |

- The run took 3,860 s.
- The rotations are now of the order of (L/e) × drift. Near the DBE target they are below it, because part of the
  drift there is still elastic; (L/e) × drift is the kinematics of the plastic mechanism.
- The proof ran before the review: its link rotations are the TOTAL shear rotation (the inelastic one is about
  γy = 0.0018 rad less), its spring had the 0.5 % slope and the flange-band fy, and its δt came from the old Ki
  (review M2). None of this bears on the finding -- the false state and the one-step losses are gone -- but the
  stage-2 re-run gives the published values.

- **Pending (owner hold):** the same proof for the IN_Ex19 stem (L/e = 9.44; its main push took about 12 min in the
  OOM-stopped run, and was smooth to 109 in with no step loss) and for IN_Ex19 main Y (about an hour expected).
  Command, from this checkout with `STELTIC_ENGINE_DIR` = the e340df8 steel_engine (or HR main for the official
  re-run):
  `PYTHONHASHSEED=0 python -m pushover run <job> --params <job>/hinge_params_collected.json --plasticity fibre
  --member-nseg 4 --dirs Y --tail none --out <job>/pushover_proof --checkpoint-dir <job>/nl_checkpoints/pushover_proof
  --chunk-seconds 3300` (a resumable run refuses to start without a fixed PYTHONHASHSEED, review L12).
  Exit 75 means not finished: run the same command again. Then `python scripts/link_proof.py <job> Y <L/e>
  pushover_proof`, the same reading as for IN_Ex15.

- The IN_Ex19 stem pushover with the default tail (fine steps, then arc length) grew to 5 GB in the arc-length tail
  and was stopped by the box's memory limit (rc 137) after its main push had finished cleanly. The re-run of the stem
  needs about 6 GB free, or the tail run alone. The proofs above use the main push only.

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
  india_combos, roof_geometry). `ensure()` re-records when the engine differs. If recording fails with an engine
  present it raises `GravityRecordFailed` (review L10): neither the earlier engine's record nor the NL idealisation is
  used in its place. The fingerprint of the gravity used is written into the outputs (pushover package
  `gravity_engine`, NLRHA numerics `gravity_engine`).
- **Regression.** States recorded with HR main against the October records (`scratch/grav_regress.log`):
  - IN_Ex9, IN_Ex11 and IN_Ex15: every state identical, element by element;
  - the current gold IN_Ex1 (collateral 0.15 kN/m²): D and EV gain 337.5 kN (0.15 × the roof area), and Dp equals
    the old D.
- The column in-span moment branch (steltic_india fix/2026-10-column-span-moment, 00336f6) changes static_model's
  member records, not the gravity states. Its records are identical to HR main's for IN_Ex15 and IN_Ex1; only the
  fingerprint differs, so a re-record follows. The 9 vendored modules and 2 section tables are byte-identical to both
  44b74de and 00336f6.
- Analyses against HR main:
  - IN_Ex9 and IN_Ex11 pushover X + Y (this branch at f011521, HR main 44b74de): the curve CSVs are byte-identical to
    the October packages, and T1, Vmax and the targets are equal.
  - This holds for the analysis MODELS of the final code -- IN_Ex9 and IN_Ex11 have no links, angles or truss
    members. It does not hold for their NSP targets: the review's Ki fix (M2) changes Te and δt of every pushover,
    and stage 2 refreshes them.
  - Correction (review L1): the brace r_min change was not angle-only as first committed -- it took the mm r_min
    whenever it was below the 4-decimal inch rx / ry, which moved five WPB brace sections by 7e-6 to 2.4e-5 (rounding)
    in IN_Ex10, IN_Ex13, IN_Ex14, IN_Ex15, IN_Ex17 and IN_Ex19 (not IN_Ex9 or IN_Ex11, so their byte-identity stood).
    It is now applied only to IS 808 angles and only for a real reduction (r_min < 0.99 r): NO brace of the lead's gold
    moves (21 brace sections, none an angle). The angles that move are IN_Ex21's: ISA60X60X6 18.4 → 11.8 mm,
    ISA70X70X6 21.6 → 13.9 mm, ISA80X80X8 24.5 → 15.8 mm, ISA90X90X8 27.7 → 17.8 mm (−36 %, the v-v axis).
  - Pending (owner hold): the IN_Ex11 DDM B-1.2 refresh against HR main:
    `python -m steltic_ddm retry <job> --workers 1 --b12-only --no-block --combos 1.5DL+1.5LL 1.2DL+1.2LL+1.2W_X
    1.2DL+1.2LL-1.2W_X 1.2DL+1.2LL+1.2W_Y 1.2DL+1.2LL-1.2W_Y`.
- New section families: an IS 808 angle brace (ISA) now buckles about its v-v axis (`r_min_mm` of the IS 808 table)
  in the brace strengths and the backbone slenderness (angles only, review L1). MB / MC / CHS labels of HR main's tables resolve. A channel (MC)
  fibre section is built as an equal-flange I-section (same area, strong-axis inertia and plastic modulus): a modelling
  simplification for strong-axis bending.

## P10 — presentation (`pushover/vmax_policy.py` new; `snl/compare.py`, `scripts/build_site_index.py`, `pushover/report_india.py`, `viewer3d_india.py`, `snl/public_text.py`, `steltic_ddm/report_ddm.py`, `viewer3d.py`, `india_checks.py`, `cli.py`)

**The pushover headline, read up to the IS-MCE target (review M1).** The headline is read on the curve from zero to
the IS-MCE target displacement δt (interpolated at δt), and it says what kind of number it is (`vmax_policy.kind`):
- `peak`: the curve peaks before δt -- "Vmax up to the IS-MCE target", a strength; Vmax/VB, Vmax/W;
- `at_target`: the curve is still rising at δt -- "Base shear at the IS-MCE target δt", a demand governed by
  stiffness, NOT a strength and not "≥"; its ratios are V(δt)/VB and V(δt)/W, never Vmax/VB (the first P10 version
  called this value the strength: IN_Ex15 Y 11,333 kN at δt = 93 mm, where the curve rises to 19,170 kN at 999 mm;
  the PEB test shed's V/W 0.189 against its 1.972 curve peak);
- `ended`: the curve ended (numerical stop) before δt -- its computed peak; "≥" only if it was still rising at its end.
- Separately, always: the peak of the analysed curve with its roof displacement (information; beyond δt it is beyond
  what the hazard asks, and "the strength is at least this" when the curve ended in a numerical stop still rising).
- Where it shows:
  - four-analyses row "Pushover strength Vmax up to the IS-MCE target" when every direction peaks before δt, else
    "Pushover headline up to the IS-MCE target" with the kind and its qualifier; the ratios labelled per kind;
  - pushover report: the marked table "Pushover headline, read up to the IS-MCE target displacement" (headline, value,
    roof u, the labelled ratios); the old line becomes "peak of the analysed curve (information)";
  - viewer: the headline row with its label and qualifier, "Peak of the analysed curve (information)", the ratio row
    labelled Vmax/V-bar_B or V(δt)/V-bar_B (data key `headline_mce`, which also triggers the one-time rebuild);
  - site index: `headline_kind_x/y`, `headline_text_x/y`; `vmax_vb/w(_text)_x/y` hold a STRENGTH only (None for the
    base shear at δt); `v_target_vb/w(_text)_x/y` the base shear at δt; `mce_target_mm_x/y`, `peak_analysed_text_x/y`
    (these replace the first version's `vmax_target_mm_*` / `vmax_beyond_text_*`, never consumed), `vmax_basis`;
  - four-analyses summary JSON: `pushover.<dir>.headline_to_target` (was `vmax_to_target`);
  - meta line: "Pushover Vmax/VB up to the IS-MCE target …" for strengths, "Pushover V(δt)/VB …" (or per direction
    when they differ).
- On the stored gold packages (read, not re-run): IN_Ex15 X and Y and the IN_Ex1 PEB shed both directions are
  `at_target` -- every one still rising at its target.

**Effective period and the NSP initial stiffness (review M2).**
- Ki of Te = Ti √(Ki / Ke) (ASCE 41-17 7.4.3.2.5, Eq. 7-27: "Ki = elastic lateral stiffness of the building in the
  direction under consideration") is now the slope of the curve over its first converged steps (least squares with an
  intercept: some plans carry a base shear from gravity at the start of the push, IN_Ex15 Y about 94 kN, and a curve
  may start with a near-zero point). It was the secant at 0.3 × the WHOLE-curve Vmax, which falls on a softened part
  of the curve when the peak lies far beyond the target (IN_Ex10 X: 303 against an initial 536 kN/mm, Te 0.166 s
  against T1 0.220 s). ASCE 41 is not in the India corpus; the clause is quoted as the module's existing ASCE 41-17
  references are (`pushover/postprocess.py` header: to be confirmed against ASCE 41-23 before a stamped report).
- With Ki the elastic stiffness, Te ≥ T1. Flagged on every page and in the index (`te_below_t1_x/y`,
  `te_far_above_t1_x/y`, `te_note_x/y`): Te < T1 (a package computed before this fix) and Te > 1.5 T1 (Ke below
  0.44 Ki: the curve softens early and δt is sensitive to the fit; 1.5 is a review threshold, not a code value).
- **Targets change:** Te and the IS-DBE / IS-MCE δt of every pushover change with Ki, and with them the response at
  δt and the headline. The stored packages keep their old targets until the stage-2 re-run refreshes them.

**No role keys or solver words on public pages.**
- `public_text.words / words_html` translate keys and solver tokens, idempotently. `words_html` changes the TEXT of a
  page only: not `<script>` / `<style>` (the viewer data keys) and not tag attributes -- class, id and data-* values
  keep their keys (review L11):
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
- The India design-criteria draft (`nlrha/design_criteria.py`: docx, and html for the hub) now says "design
  engineer". "No limit point" and the plan settings are in words instead of a status key and key paths, and the page
  passes through `scrub_html`. The ASCE 7 (US) variant keeps "engineer of record", the term of that standard.
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
- Finished pieces are stored whole and are not replayed: a whole DDM sweep (its `_worker` result, returned before
  anything is ingested or built -- review H1: the first version restored the rung but then classified it against a
  model that was never built, `AttributeError: _bt`, on every sweep finished in an earlier chunk), a DDM step-size
  rung, a pushover direction.
- Keys (review M4 / M5, `checkpoint.run_key`): the analysis code (`code_key`, now including `pushover/postprocess.py`,
  `pushover/cli.py`, `nlrha/cli.py`, `nlrha/india_hazard.py`, the DDM worker `steltic_ddm/cli.py`, the B-1.2 check
  and the imposed-load reduction; report-only modules excluded), the HR engine fingerprint, the SNL_* model knobs
  (member subdivisions, fibre settings, gravity-elastic members, plasticity, DDM options, record trimming), an outside
  --params file, the package model / gravity / params files, `nl_plan.json` (DDM) and the run options. The NLRHA
  record cache also hashes the record's acceleration data (it held only the lengths).
- A fixed PYTHONHASHSEED is required for a resumable run (review L12): without it the CLI stops with a message.
- The replay fingerprint covers every node (review L9; it read the first 400 node tags).
- A resume recomputes the converged steps only. Review M3, no-progress guards (exit 76, NoProgress, with the reason):
  - a piece whose converged steps alone exceed 80 % of a full chunk (`progress_possible`, checked when it begins);
  - a replay that runs out of a chunk it started with (nearly) whole -- the budget is checked during the replay, so
    the process exits instead of being killed by the timeout every chunk; one that started late resumes (75);
  - a piece whose replay diverges again after one live restart (one per piece, over all chunks);
  - an NLRHA record that already had (nearly) a whole chunk and did not finish (`nlrha/attempts.json` in the cache).
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
- Measured again with REAL failed calls (review, weak tests): the one-bay EBF push with a first attempt that fails
  after yield and the pushover's own fallback ladder (6 failed calls of 16), interrupted after 7 calls and resumed:
  the curve agrees with the uninterrupted one to about 1e-15 relative, not bit for bit -- the same limit.

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
- `next --queue Q --budget 6900` runs ready steps until its own budget is spent. Each runs under `heavy` through
  `nl_orchestrate.py _exec`, which fixes the chunk's deadline when the slot is granted (the wait for a slot is not
  analysis time), stamps it, and applies the timeout:
  - a step that exits 75 stays queued (`resume`); a timeout (124) resumes from the last journal save;
  - review M3: the queue stores each chunk's progress (finished pieces, journaled calls; cached records) and the
    analysis time it really had. A step goes `stalled`, with its reason, after exit 76, after a chunk with at least
    10 min of analysis time that kept nothing new, or after 24 chunks; a stalled step is not run again, and the other
    jobs go on.
- `status` prints the queue and any stall reason. Q.runtime.log gets one line per chunk; Q.lock allows one `next` at a
  time. The queue sets PYTHONHASHSEED=0.
- Commands are the October re-run commands, with the checkpoint options added.

**IN_Ex19 earthquake combination (1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z).** Not run (owner hold). What it needs:
- The October result does not stand either way.
  - The combination loads the Y-direction EBF links, and its numerical runaway at λ 1.318 matches the P1 symptom: a
    probable cause, which the re-run will confirm or not.
  - It must be re-run from the first step size with the fixed link.
- The NL-30 ladder: Δλ 0.05 / 0.025 / 0.0125, with 2,400 / 4,800 / 9,600 s and 250 / 500 / 1,000 steps. The worst
  case is 16,800 s on one core.
- In chunks (the orchestrator's DDM step does the same):
  - run `PYTHONHASHSEED=0 python -m steltic_ddm retry <job> --workers 1 --combos "1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z"
    --only-listed --checkpoint-dir <job>/nl_checkpoints/ddm --chunk-seconds 3300 --no-block` again while it exits 75,
    then `python -m snl report <job>`; exit 76 means it cannot advance in chunks (the reason is printed);
  - each finished step size is stored;
  - a step size longer than a chunk resumes by replay. In the October retry the converged steps were cheap: steps
    1–50 in 108 s of the sweep's 2,592 s, the rest in step cuts near the end. So a replay costs little, unless it
    diverges at a near-singular step; that rung then restarts live in its chunk once, as IN_Ex15 did at call 86, and a
    second divergence stops it with exit 76 (review M3).
- If a step size has to run whole: a process with no 2-hour cap (the owner's PC), with `STELTIC_ENGINE_DIR` = HR
  main's steel_engine. Run `python -m steltic_ddm retry <job> --workers 1 --combos "1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z"
  --only-listed`, then `python -m snl report <job>`: up to 4.7 h.

## IN_Ex21 angle-truss shed support (stage 2; MSME CHANGES_2026-10-msme-shed.md)

The new gold IN_Ex21_MSME_angle_truss_shed_Hosur (knee-braced Pratt angle trusses on MB columns, Zone II) builds and
runs gravity in all three analyses. Checked on the MSME gold with the MSME engine (`STELTIC_EX21_JOB`,
`STELTIC_ENGINE_DIR`; the tests skip when the job is absent):
- 36 columns, 180 beam elements and 208 braces;
- 165 nonlinear axial members: 73 verticals, 70 diagonals, 14 knee braces and 8 wall braces;
- the gravity analysis converges in 5 s;
- the DDM gravity-transfer gate passes (48 comparisons, none outside ±5 %, worst ratio 1.027).

- **Member kind `truss`** (diagonals, verticals and knee braces) is a nonlinear axial member exactly as `brace`: the
  brace backbone in the pushover / NLRHA (`fibre_model.AXIAL_KINDS`, `nonlinear_model`). So the knee braces are the
  yielding / buckling members across the span, as the design intends; the chords stay fibre beam-columns.
- **Double angles** (TABLE D custom sections, `2ISA…`, cfg `custom_sections` type `double_angle`):
  - `india_sections.double_angle_props_mm` uses the steltic_india formulae: A, both I, the plastic and elastic
    moduli, J = 2 J1, r_min;
  - 2ISA70X70X6 on an 8 mm gusset gives A 1,630 mm², I 760,000 / 1,667,845 mm⁴, the HR element properties;
  - an undeclared `2ISA…` label is read with no gap and flagged VERIFY;
  - IS 800 buckling class c; brace strengths with r_min;
  - fibre sections of leg strips scaled to the catalogue area (`FiberSectionBuilder.double_angle`). The outstanding
    legs are put at the top: an assumption, since the HR record does not fix up or down, and the elastic properties
    do not depend on it.
- **Single angles in the DDM** (`FiberSectionBuilder.single_angle`):
  - the GMNIA models braces as fibre members and had no angle section;
  - the legs run from the heel, so the inclined principal axes, and buckling about v-v, follow from the fibre
    positions (v-v within 6 % of A r_min²);
  - torsional-flexural buckling of an angle (shear centre at the heel, no warping DOF) is not represented. The
    design's IS 800 7.5.1.2 equivalent slenderness covers it.
- **Truss chord restraints in the DDM** (`peb_restraints._truss_chords`):
  - the HR model ties only the eaves, so a GMNIA of the bare trusses would buckle the 18 m chords out of plane
    between the eaves;
  - the chords are now tied laterally (the horizontal direction normal to the truss) to the roof diaphragm, as the
    NL-33 rafter purlins are. A compact angle chord is held whole by a purlin cleat or a tie: lateral restraint only,
    no torsional spring;
  - top chord: every panel point when the roof plane declares `purlins_at_nodes`. That is 11 per inner truss; the
    HR model already ties the two gable trusses at every node;
  - bottom chord: a declared `bottom_chord_ties_mm` (on the roof plane or in cfg `truss_restraints`), else every Ly of
    the design's `member_overrides` for the bottom chord. The IN_Ex21 cfg publishes only Ly = 4,500 mm, giving ties at
    4.5 / 9.0 / 13.5 m. These are the design's stations, but MSME may prefer to publish the list
    (`ROOF_PLANE["bottom_chord_ties_mm"] = BC_TIES`), which is then used.
  - Assumptions, stated (review L13): the ties are RIGID lateral restraints to the roof diaphragm; a flexible tie or
    end-bay bracing would restrain less, which matters under uplift (the bottom chord in compression). Without a
    published list the ties are placed every Ly from the first eave only.
- The column girts / fly braces (3.0 / 4.75 m) were already read by the NL-33 plan: 36 stations. Packages without
  truss chord roles are unchanged.
- Not modelled: the knee-brace connection check (connections designed for 1.2 × the brace strength) is a design check,
  not an analysis item.
- The pushover / NLRHA chords use Linear transformations with no imperfections, so they need no chord restraints.
- **Queue:** `scripts/nl_orchestrate.py plan --queue Q --jobs <copy of the IN_Ex21 job> --engine <HR steel_engine with
  the MSME custom sections>` plans gravity, pushover, NLRHA, DDM and report (dry run checked). The engine must carry
  the MSME changes: `register_truss_member` and the double-angle custom sections.

## Review fixes (briefs/NL_REVIEW.md: findings, fix, test)

| Finding | Fix | Test (`tests/test_third_wave_2026_10.py`) |
|---|---|---|
| H1 DDM resume crashes on every sweep finished in an earlier chunk | `_worker` journals its whole result per sweep (`TASK_DONE`) and returns it before ingesting / building | `test_ddm_resume_returns_finished_sweeps_whole_and_builds_nothing`: a gravity combination with four imperfection cases + a lateral one; chunk 1 finishes two, expires inside the third; chunk 2 identical results (mechanism, member state), nothing built for the finished two; fails on the old code with the reviewer's `_bt` error |
| M1 V(δt) headlined as strength | `vmax_policy` kinds peak / at_target / ended; pages, viewer, index, meta line, JSON keys | `test_headline_kinds_up_to_the_mce_target` (incl. a point exactly at δt), `test_site_index_headline_fields`; gold page tests updated to the new facts |
| M2 Ki the secant at 0.3 × whole-curve Vmax | Ki = initial slope (ASCE 41-17 Eq. 7-27); Te ≫ T1 flag | `test_ki_is_the_initial_slope`, `test_te_flags_below_and_far_above_t1` |
| M3 no no-progress guard | NoProgress (exit 76): up-front `progress_possible`, budget during replay, one restart per piece, NLRHA record guard; orchestrator `stalled`, `_exec` in the slot | `test_a_replay_longer_than_a_chunk_stops_with_a_reason`, `test_the_budget_is_checked_during_a_replay`, `test_a_piece_diverging_again_after_a_restart_stops`, `test_nlrha_record_longer_than_a_chunk_is_not_retried_forever`, `test_orchestrator_marks_a_step_without_progress_stalled` |
| M4 / M5 incomplete keys | `run_key`: code incl. postprocess.py / pushover cli.py, engine, SNL_* knobs, outside --params, hash seed; record data hashed | `test_cache_and_journal_keys_cover_every_input` (each input changes the NLRHA, pushover and DDM keys) |
| L1 r_min not angle-only | angles only, r_min < 0.99 r; gold braces listed (none move) | `test_double_angle_properties_are_the_hr_ones` (r_min), the gold scan in this file |
| L2 total rotation; no length class | inelastic rotation (total − V/K); e V_pL / M_pL < 1.6 checked | `test_link_spring_reaches_the_is18168_overstrength_at_the_rotation_limit` |
| L3 interaction not modelled | disclosed (P1) | — |
| L4 V_pL on the flange band | `link_web_fy`: the web band, pushover and DDM | `test_link_shear_strength_takes_the_web_band` |
| L5 box links one web | box from the section: two webs, Sh 1.4 | in the overstrength test (box case) |
| L6 kinematic 0.5 % | slope calibrated to Sh V_pL at 0.08 rad (IS 18168 12.3.2.2 / 12.3.3.1, both in the corpus); kinematic and no Ry, disclosed | the overstrength test (1.25 I, 1.4 box, ±1 %) |
| L7 released link loses its spring | refused loudly (DDM released; pushover non-Timoshenko) | `test_a_link_the_models_cannot_carry_is_refused` |
| L8 link stubs | none, documented (HR models have no rigid offsets; India default off) | — |
| L9 fingerprint 400 nodes | all nodes | `test_replay_fingerprint_covers_every_node` |
| L10 failed re-record kept the old gravity | `GravityRecordFailed`; gravity engine in the outputs | `test_a_failed_gravity_record_fails_loudly` |
| L11 attribute values rewritten | text nodes only | `test_words_html_keeps_attribute_values` |
| L12 PYTHONHASHSEED | required for resumable runs; set in the commands; the queue sets 0 | the key test (sets it); the CLI message |
| L13 tie assumptions | stated; a published list preferred | `test_bottom_chord_ties_read_from_the_design` |
| Weak tests | the pushover CLI restore path; a chunked pushover with real failed OpenSees calls | `test_pushover_cli_restores_a_finished_direction`, `test_chunked_pushover_with_real_failed_steps_repeats_the_uninterrupted_one` |

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
  - a real chunked EBF pushover without failed calls (bit for bit) and one with real failed calls (to 1e-12);
  - the orchestrator; the review fixes (table above);
  - IN_Ex21: double-angle registry values, fibre stiffness in and out of plane, the single-angle v-v stiffness,
    `truss` members, bottom-chord tie reading, and the gold package build, restraint plan and DDM gate (skip-able);
  - the India design-criteria page in public words.
- Full suite with the HR main engine: **496 passed, 6 skipped** in 330 s (baseline 470 / 4).
  - The 6 skips are the 4 of the baseline and the 2 IN_Ex21 gold tests, because the job is not yet in
    /home/claude/gold.
  - Against the MSME gold and engine (`STELTIC_EX21_JOB`, `STELTIC_ENGINE_DIR`), all 28 tests of the third-wave file
    pass.
