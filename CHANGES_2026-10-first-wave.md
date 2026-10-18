# steltic-nonlinear-india — 2026-10: first-wave fixes from the published-examples review (NL-36 … NL-38)

Branch `fix/2026-10-first-wave`. The review of the 24 published nonlinear runs (E_NL) found DDM sweeps reported as
capacities after a numerical runaway (IN_Ex9 λ 5 576 / 106 901 / 1 402 093; IN_Ex18 a 1 615 % storey drift), the
IN_Ex9 rafters buckling out of plane because a rolled-section shed had no purlin / fly-brace restraint in the GMNIA,
and the IN_Ex19 B-1.2 "shortfall" coming from an imposed-load basis the HR design does not use. This change fixes the
three and the presentation items the review listed.

## NL-36 DDM runaway sweeps (`steltic_ddm/solver.py`, `cli.py`, `india_checks.py`, `report_ddm.py`, `nlrha/india_authority.py`)

- A converged step beyond the plausibility bounds is a **numerical runaway**:
  - |λ| > 10;
  - a λ change > 1.0 in one converged step (20 elastic steps of the default dlam 0.05);
  - a drift from the base > 10 % (diaphragm masters; every free node of a portal);
  - a max fibre strain > 1 000 εy.
- What happens to the runaway step:
  - It is **discarded**: not in the curve, the peak, the snapshot or the B-1.2 forces at λ = 1.
  - The sweep stops with termination `runaway` and status **SOLVER_FAILURE**, whatever the strain cap or the tangent
    say. The NL-30 retries then repeat it at dlam / 2 and dlam / 4.
  - A limit point confirmed by ≥ 2 descending converged steps *before* the runaway stands, with λu the pre-runaway peak.
- How this explains the IN_Ex9 "brace B-1.2 2.559":
  - λ jumped from 0.71 to 5 576 in one step. No converged step lay between 0.85 and 1.
  - The NL-25 interpolation therefore took the runaway state scaled by 1 / 5 576 as the forces at λ = 1.
- B-1.2 rows of sweeps that stopped numerically before λ = 1 are **not evaluated** (`ok: null`). They are neither
  satisfied nor a capacity shortfall. `b12_check.ok` is `null` when nothing fails but something was not evaluated.
- **Stored results** (`steltic_ddm report` / `retry`, and the site index builder) are read through the same guard
  (`cli.reclassify_stored_run`):
  - The stored λ history is truncated at the first runaway step and the status re-derived from what precedes it.
  - A B-1.2 row whose λ = 1 bracket is the runaway step is dropped.
  - Hidden runaways found this way:
    - IN_Ex9: −78 892, read as the "descending" step of a LIMIT_POINT.
    - IN_Ex19 main 1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z: −788, read as the post-peak drop.
    - IN_Ex18 1.2DL+1.2LL−1.2W_X: −732 at a "ductility cap".
- The gate and the reports state solver failures; they are never silent:
  - `complete_gate.json` has `checks.ddm_solver_failures` / `ddm_runaway_steps` and `notes`.
  - A runaway gets its own blocking reason.
  - A job that is otherwise COMPLETE but carries NL-31-disclosed stops gets status **`complete_with_solver_stops`**.
  - The DDM report has a solver-failure statement and table above the λ table.
  - Each SOLVER_FAILURE row names its runaway criterion and says "not a capacity".
- `steltic_ddm retry`:
  - `--combos <labels>` also re-runs named combinations on the current code.
  - `--only-listed` re-runs only those.
  - The record goes to `options.ddm_rerun`. An earlier NL-30 `ddm_retry` record is kept.

## NL-37 IS 875 (Part 2) 3.2.1 column imposed-load reduction in the B-1.2 check (`steltic_ddm/imposed_reduction.py`, new)

- What the HR design does (steltic_india `static_model.py`, ~1765):
  - It reduces the **axial-force record** of each column by r × N_LL after the analysis. r is 0 … 0.5 by the floors
    carried; N_LL is the column's force under the floor imposed load alone at the combination's factor.
  - It does this in every combination without earthquake (IS 875 (Part 5) 8.1).
  - Beams, braces and the analysis keep the full imposed load.
- What the DDM did before: the B-1.2 check used the **unreduced** GMNIA column force. Only the gravity-transfer gate
  added the reduction back.
- The DDM now does what the HR does:
  - r per column comes from the HR engine (`snl.hr_gravity` `column_imposed_load_reduction`).
  - N_LL comes from one elastic analysis of the HR 'Lfloor' state on the GMNIA topology.
  - The B-1.2 forces at λ = 1 of every combination without earthquake have each reduced column's compression lowered
    by r × fL × N_LL. The table shows the reduction next to N.
- The sweeps still carry the full imposed load, so λu is for the unreduced load (conservative).
- Why the reduction is not applied as a load: a self-equilibrated axial pair on each column (tried first) changed the
  IN_Ex19 floor-beam moments by up to 19 % (1.5DL+1.5LL WPB550 0.81 of the HR moment). The columns shorten less, and
  the differential shortening bends the rigid beams. The HR reduction is a force-record reduction and is reproduced
  as one.
- The basis is printed in section 2 of the DDM report:
  - "Imposed load: …", whether a reduction applies or not.
  - It is recorded in `options.imposed_load_reduction` / `imposed_load_basis`, in the `ddm_analysis` block and in a
    gate disclosure (`ddm_imposed_load_reduction`).
- `steltic_ddm run --imposed-load-reduction off` runs the unreduced check for information. It is disclosed.

## NL-38 out-of-plane restraints of rolled-section sheds (`steltic_ddm/peb_restraints.py`, `model_gmnia.py`, `sections_fiber.py`)

- The NL-33 restraint plan was built only for PEB packages. The IN_Ex9 rolled NPB600 rafters (true slope,
  Corotational) were therefore free out of plane for 12.4 m:
  - 1.5DL+1.5LL+1.5SL limited at λ 0.61 with the roof yielding at 0.60.
  - The HR roof D/C is 0.81.
- `peb_restraints.rolled_source` builds the same kind of plan for a non-PEB India package from the HR cfg.
- Rafters (every sloped beam of a `cfg['roof_planes']` plane, chained per frame line):
  - Fly braces at `LLT_hog_mm['roof']` (the design's bottom-flange LTB length) along the slope from each eave. They
    hold both flanges: a lateral tie to the roof diaphragm and a torsional restraint.
  - A lateral tie at the apex where the HR model has none. The IN_Ex9 apex nodes are tied in X only.
  - Purlins (top flange only) are counted, not modelled (conservative), as NL-33.
- Columns:
  - Every column element whose role has `K_factors` Ky < 1 gets a lateral restraint at k × Ky × L from its foot (the
    design's out-of-plane buckling length).
  - The restraint is a rigid stud on the element's chord. A stud standing on a roof / floor node is tied to it and held
    vertically at its foot.
  - No torsional restraint is added: the HR column LTB check uses the element length (no LLT for columns).
- Rolled I members of these chains carry G J + π² E Cw / L_t² as their torsional stiffness (`w_shape(warping_length=…)`),
  as the welded I members of NL-33.
- Spacings come from the HR cfg (`LLT_hog_mm`, `secondary_members` purlin / girt `spacing_mm`, `LLT_sag_mm`). When the
  cfg declares none, the brief's spacing is used (`BRIEF_SPACINGS`, quoted) and the report and the plan basis say so.
- Which jobs get a plan:
  - IN_Ex9: 9 rafter lines, 27 column elements.
  - IN_Ex10: 16 SCBF wall columns at the 2.375 m girts.
  - None for IN_Ex6, Ex7, Ex8 and Ex12 unitC (flat roofs inside the diaphragm are P-Delta deck beams, and their column
    Ky ≥ 1), and none for the multi-storey buildings.
  - PEB plans are unchanged (bit-identical code path).
- Gate disclosure `rolled_ddm_restraints`; report section 2 describes the idealisation and the sources.

## Presentation

- `snl/compare.py`, four-analyses header:
  - It now reads the design basis from `load_plan.json` `seismic_summary` (then `seismic_calc.json`, `calc_package`,
    the pushover basis).
  - Before, every current package printed "design VB — kN, W 0.0 kN, R None", the PEB packages included.
  - It now prints, e.g., "design VB 29.9 / 39.8 kN (X / Y), W 956 kN, R 4 / 3 (X / Y)".
  - The DDM rows give gravity λu as the headline and min φs·λu as information (3 decimals, rounded down), the solver
    failures, the imposed-load basis, B-1.2 (with "not evaluated") and the B-1.1 preconditions.
- `pushover/report_india.py` `stop_reason_mm`, applied in `pushover/cli.py` (India): stop messages in mm
  ("u = 439 mm", was "u=17.27 in"). Published pushover pages keep inches until the pushover is re-run.
- `scripts/build_site_index.py` (new; nothing in the repo built the site index): rebuilds
  `solutions_india/nl/index.json` from the run folders. Per run it records:
  - per-level record pairs / converged (DBE and MCE) and the record set "FEMA P-695 far-field set, amplitude-scaled to
    the IS 1893 spectrum";
  - Vmax/W next to Vmax/VB per direction, with lower-bound and MCE-target flags;
  - gravity λu as the headline, with min φs·λu kept as information;
  - solver-failure and runaway counts, and `b11_met` (compact sections and a design engineer's full-lateral-restraint
    statement, `nl_plan.json` `b11_lateral_restraint`);
  - margins rounded down and D/C rounded up to 3 decimals, with `*_text` strings (IN_Ex10 0.997, never 1.00).
- B-1.1 text: "design engineer's statement required (not checked)" (was "EOR statement …").
- README: 24 nonlinear runs on 24 of the 39 worked designs (was 19).

## Tests

`tests/test_first_wave_2026_10.py` covers the following (package tests skip without the gold jobs):
- the runaway bounds and the status rules;
- a real sweep (IN_Ex12 unitC) with a forced runaway step;
- the stored IN_Ex9 / IN_Ex18 runaways;
- B-1.2 "not evaluated" and its summary;
- the gate status and reasons;
- the 3.2.1 rule (the EQ test, force reduction, B-1.2 table, the IN_Ex19 plan from the HR engine);
- the rolled plan (IN_Ex9 stations, IN_Ex10 / Ex19 / Ex8 / Ex6);
- no stud mechanism (ARPACK periods of the restrained IN_Ex9);
- the IN_Ex9 snow gravity sweep above λ 1.2 with B-1.2 satisfied;
- the rolled-I warping term;
- the header, the mm stop messages, rounding, the index builder and the README counts.

`tests/test_nl33_peb_gmnia_releases.py::test_no_plan_for_earlier_golds` now expects IN_Ex10 to get the NL-38
column-only plan and IN_Ex19 none.
