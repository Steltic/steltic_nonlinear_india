# India nonlinear (steltic_nonlinear_india) -- first-pass review and fix, 2026-09-27

Repo `/home/claude/nl/work/steltic_nonlinear_india`, branch `review-fix-2026-09` (from `usa-sync-2026-09`), commits NL-1 .. NL-24.
HR engine reference: `/home/claude/work/steltic_india` fix/2026-09-review @ 3ec586a. Hub (`steltic_hub_india`) not touched -- no NL
fix needed it (the NLRHA viewer it links now exists, NL-11).

Severity: **Critical** = wrong answers or no run on gold buildings; **High** = wrong basis / dishonest gate or report;
**Medium** = inconsistent or US leftover with moderate effect; **Low** = cosmetic / < 1 %; **Info** = observation, often on the HR side.

## Findings and fixes

| # | Sev | Area | Finding | Status |
|---|-----|------|---------|--------|
| 1 | High | vendoring | Vendored India modules (`snl/vendor_steltic_india`) had drifted from steltic_india; `scripts/check_vendored.py` hard-coded a path and failed when absent. | Fixed NL-1: re-vendored from 3ec586a (VENDORED_FROM.md); root resolved from `--hr`, `$STELTIC_HR_ROOT`, `$STELTIC_INDIA_HR`, sibling `../steltic_india(-main)`, parent of `$STELTIC_ENGINE_DIR`, else `SKIP` (exit 0). |
| 2 | Medium | tests | 4 failing tests: DDM Ex18 USA fixture tests ran against the India engine; India DDM load tests used a pre-contract load_plan. | Fixed NL-2 (USA-engine skip; current contract + gold IN_Ex3 load_plan fixture; refusal test). |
| 3 | High | corpus | IS 18168 missing from `india_collections`; corpus root hard-coded to /workspace. | Fixed NL-3 (IS 18168 map; `$INDIA_CORPUS_ROOT` / `$ENGINEERING_RAG_INDIA` / sibling / fallback). |
| 4 | Critical | package reading | Built-up BOX columns (cfg `custom_sections`) unknown -> KeyError on every box job; fy was one grade for all members (no IS 2062 Table 3 thickness bands, no per-member grade, YSt tube grades, brace process). | Fixed NL-4: box registry with the HR `register_box` formulae, fibre box section, fy per member (EOR plan > HR package record > grade band), IS 1161 tubes, HR roles carried. |
| 5 | Critical | units | Raw replayed HR elements (Truss, ElasticTimoshenkoBeam links, zeroLength springs) kept N-mm values in the kip-in Stage-B model. | Fixed NL-5 (A, E, G, I, J, Av and spring stiffness converted; materials cloned). |
| 6 | High | basis | Single VB/R used for both directions; W not the HR engine's W. | Fixed NL-6: V-bar_B, R, Ta per direction from calc_package `seismic_analysis.scale` / `seismic_calc`; W = `W_by_floor_engine_kN`; per-direction V/V-bar_B in summaries. |
| 7 | High | parameters | `pushover/hinge_params.json` was the USA file (Fy 50 ksi, Ry 1.1, ASCE 41 IO/LS/CP, 16.3.5 damping) used as India default. | Fixed NL-7: India file (IS values or labelled modelling assumptions, no acceptance keys); US file moved to `usa_reference/`; damping cap 5 % IS 1893 7.2.4 (default 2.5 % labelled modelling assumption). |
| 8 | High | collect | `snl collect` gathered one grade only; combined systems got one rotation reference. | Fixed NL-8 (every IS 2062 / IS 1161 grade used; IS 800 12.x and IS 18168 rotation references per system part). |
| 9 | High | collect | No way for an agent to act as the transcriber (LLM-only). | Fixed NL-9: `snl collect JOB --prepare` -> `collect_request.json/.md`; `--answers FILE` runs the same quote/value/engine-constant checks; README and evidence record SCRIPTED + sha256. |
| 10 | Critical | EBF | EBF links (Ex6 92, Ex9 168) were replayed as ELASTIC Timoshenko beams in all three analyses -- the yielding element of an EBF never yielded. | Fixed NL-10: fibre link + IS 18168 11.2 V_pL = fy A_wL/sqrt3 shear aggregator; link rotation recorded vs 0.08 rad (12.3.3.1) reference; DDM links. |
| 11 | Medium | viewer | No India NLRHA viewer; hub and compare.py linked `nlrha_viewer_3d.html` (dangling). | Fixed NL-11 `nlrha/viewer3d_india.py` (levels/records, member and link ratios, no IO/LS/CP, D7 sentence). |
| 12 | Medium | pushover | Pushover kept grinding far down the descending branch (Ex1 X > 35 min after peak). | Fixed NL-12: stop at V <= 0.8 Vmax past peak and beyond the fine-step zone (`--stop-at`). |
| 13 | Critical | DDM | India EQ combinations had NO lateral load (RSA term had no static pattern) and the India combination set was not pruned. | Fixed NL-13: EQ_X/EQ_Y = HR `load_plan.story_forces` x factor; 1.5(DL+LL), EQ families x signs x dirs, storey wind; Ex3 118 -> 25 sweeps. |
| 14 | Critical | gravity | NL gravity was a private idealisation: W_i as equal nodal loads (no beam gravity moments), DDM two-way tributary loads (Ex3 rafter moments 27-35 % of HR); DDM gravity gate compared 0 members (schedule columns renamed) and ignored the IS 875-2 3.2.1 column LL reduction. | Fixed NL-14: `snl/hr_gravity.py` records the HR `static_model.apply_gravity_state` load states (D, L, Lr, S, EV, Lfloor) in a child process and replays them; NL gravity = EV state + top-up to W_i; gate vs `member_combo_forces.json` at the column top. |
| 15 | Critical | gold set | Smoke run of all 15 gold jobs (+4 sub-units): Ex15 zeroLength roof springs crashed the NL build and were dropped by the DDM (all gravity analyses failed); partial snow (IS 875-4 4.3) and crane patterns were not replayed (Ex15 +97 %, Ex14 -63 % column N); Corotational gate picked up catenary tension on 15 m girders (Ex13 -8 %). | Fixed NL-15 (springs; per-pattern states S@.., C@.., EV from Case.meta; unrecorded state refused; gate uses P-Delta like HR). |
| 16 | Medium | DDM gate | +/-5 % ratio failed on near-zero forces (Ex9 stem 8.0 vs 8.6 kN-m). | Fixed NL-16: noise floor 2 % of member M_p / P_y at 250 MPa, flagged `ok_by_floor`. |
| 17 | High | COMPLETE gate / reports | Gate did not check that IS values were collected, that gravity was the HR state, or that declared EBF links were modelled. Pushover plot drew one VB; reports said "literature placeholders"; India design-criteria HTML carried the ASCE 16.1.4/16.5 sealing note; `--params` help said AISC 342 / ASCE 41. | Fixed NL-17. |
| 18 | High | modal / gate | `nlrha.model.modal` asked 12 modes of models with fewer real mass DOFs (IN_Ex5: 6); ARPACK returned zero-mass "modes" at T ~ 6e6 s -> spurious-mode check would block COMPLETE on a sound model. | Fixed NL-18 (eigen request capped at the real mass DOFs). |
| 19 | Medium | snl run | `snl run` passed `--site-class D` and the USA NLRHA default `--plasticity imk --member-nseg 1` to the India CLIs (ignored with a warning); a fresh HR package was not recognised as India by compare. | Fixed NL-19. |
| 20 | Low | tests | `test_panel_zones_scissors_push_plausible` failed standalone (also on the usa-sync base) and passed or failed by test order (India params default, process-wide SNL_* env, last-point comparison under float jitter). | Fixed NL-20. |
| 21 | High | runtime (blocker) | NLRHA is solver-bound (97 % of wall time in `ops.analyze`): IN_Ex1 (575 el., nseg 4 fibre) runs 1.5 steps/s per core -> ~40-60 min per record, 22 records ~ 8-11 h on 2 cores; dt 0.02 is slower (sub-stepping), KrylovNewton no faster, member_nseg 2 is 1.75x faster. | Open -- plan cores (records are independent: `--parallel N`), see runbook. |
| 22 | Medium | viewer | No India pushover 3-D viewer (the USA one is ASCE 41 IO/LS/CP and is not written for India); the viewer bundle shows the pushover tab as missing. | Open. |
| 23 | Low | units | g = 386.4 in/s^2 in NSP (postprocess), GM excitation (vendored `india_units` g_in_s2) vs mass from 386.089 (india_model): 0.08 % force inconsistency. Vendored module is HR-owned. | Open (Low; fix in HR india_units then re-vendor). |
| 24 | Medium | ground motions | Record selection/scaling uses the ASCE 7 Ch.16 rules as METHOD (11 pairs, 0.2T-2T range floor 90 %, orientation check) against the IS elastic spectrum; the records are the USA/NGA library. Labelled "information / method" in reports. IS 1893 7.7.4 only says "appropriate ground motion". | Open (labelled; EOR decision). |
| 25 | Medium | diaphragm | NL models use the HR `rigidDiaphragm` constraints as exported; where the HR design declared a flexible diaphragm (Ex13, IS 1893 7.6.4) the HR export still carries one master per level, so NL is rigid there too. | Open (limitation; stated in runbook). |
| 26 | Low | shared viewer | IO/LS/CP labels remain in the shared (USA) viewer core; India pages use the India viewer. | Open (USA path only). |
| 27 | Low | naming | `design_criteria_16_1_4.docx/.html` file name kept for the hub/loop links; India content and title are IS. | Open (cosmetic). |
| 28 | Info | modal | NL T1 within 0.2-2 % of HR on 13 jobs; Ex2 / Ex12 (9-11 storey SMF) +5 % (P-Delta geometric stiffness under gravity in the NL modal; HR modal has none). | Info. |
| 29 | Info (HR) | seismic weight | HR EV state (IS 1893 7.3 load) differs from the HR W per level: +360 kN/floor Ex1, +1053 Ex6, +867 Ex7 (partitions in the imposed share), -217 kN Ex9 / -72 kN Ex9 stem. NL tops up (or trims) to W_i so mass = gravity = W. | Reported to HR owner. |
| 30 | Info (HR) | column N | HR column design N is read at the top end (own self-weight excluded; Ex3 ~30 % of column N). NL gate compares like with like. | Reported. |
| 31 | Info (HR) | Ex15 | Two HR zeroLength springs (7002025/26) join nodes 3 m apart (OpenSees warns; behaves as a stiff X spring). | Reported. |
| 32 | Info | --site-class | `snl run` passes `--site-class D`; the India path ignores it (NSP C1 'a' = EOR input else 60, disclosed). | Info. |

## Gold-set status after NL-17/18 (smoke: build + gravity + modal; DDM: combos + gravity gate)

All 15 jobs and the 4 sub-units (Ex8 workshop, Ex9 stem, Ex11 unitB_link / unitC_gym): mass gate ok, gravity converged,
no spurious modes (Ex5 after NL-18), T1 vs HR within 5.5 %, DDM gravity-transfer gate 0 members outside +/-5 % (Ex9 stem: 6 within the noise floor).

## Cost reduction (NL-21..23, lead decision 2026-09-27)

| # | Sev | Area | Finding | Status |
|---|-----|------|---------|--------|
| 33 | High | runtime | Full-fidelity NLRHA ~150-200 h for the 15 buildings at 2 cores. | Fixed NL-21: gravity-only members elastic with a first-yield check / promotion / gate refusal, records trimmed to 5-95 % Arias (+1 s, +5 s tail); validated (NL_RUNBOOK.md); batch estimate ~55 h. |
| 34 | Medium | residual drift | Residual drift was the instantaneous value at the end of the run, i.e. mostly the vibration still decaying. | Fixed NL-21: averaged over the last max(2 T1, 1 s). |
| 35 | Medium | pushover + elastic gravity | Beyond the NSP targets the gravity columns yield (Ex1: 48 members up to ratio 6 at the descending branch); an elastic-only check up to the target over-stated Vmax by 2.4 / 3.9 %. | Fixed NL-21: the pushover check covers the whole curve; promotion restores Vmax exactly. |
| 36 | High | collect | Decimal values with trailing zeros in the quote (Z = 0.10, zone II) were rejected: 4 gold jobs could not collect. | Fixed NL-22. |
| 37 | Info | batch | Resumable batch script, 19 folders, smallest first, agent-transcribed answers for all 19 (all collected ok). | NL-23; running. |

## Gold batch findings (NL-24, 2026-09-27)

| # | Sev | Area | Finding | Status |
|---|-----|------|---------|--------|
| 38 | Critical | DDM model | Horizontal beams inside a rigid diaphragm were Corotational: the constraint holds their ends at a fixed plan distance, so the sag of a pinned gravity girder became catenary tension (and, in Ex14, weak-axis bending) that the fin-plate connections, the HR design (Linear beams) and the NL pushover / NLRHA (HR transformations) do not have. Ex11 NPB700 floor girders (HR elastic D/C 0.983) yielded at lambda 0.95 and 1.5DL+1.5LL stopped at 0.977; gym NPB700 roof girder +335 kN -> B-1.2 D/C 1.018 (HR 0.960); Ex14 NPB750 roof B-1.2 1.08 (N 278 kN, M_minor 65 kN-m); after yield, catenary action inflated lateral-case lambdas (gym lambda 4-8.8). | Fixed NL-24: those beams use P-Delta (transf 6, India; `$SNL_DDM_BEAM_TRANSF` overrides). Ex11 1.5DL+1.5LL DUCTILITY_CAP 1.232 (first yield 1.049, 0 failed steps); gym NPB700 M = 996.7 kN-m vs HR 996.6, N 61 kN (post-yield centroid shift of the residual-stress section restrained by the diaphragm), B-1.2 0.975; Ex14 governing crane case NPB750 0.51, PLASTIC_PLATEAU 2.61. Changes every India DDM result (all 19 jobs have such beams). |
| 39 | High | DDM solver / honesty | One KrylovNewton retry then six step cuts; a numerical stop was reported NO_LIMIT_POINT and only blocked below lambda 1 for gravity / wind. | Fixed NL-24: ladder at the failed step (KrylovNewton, NewtonLineSearch, ModifiedNewton -initial 200 it., tolerances 1e-5 / 1e-4), step cuts, then arc-length rescue (MinUnbalDispNorm -det); a numerical stop with tangent >= 10 % of elastic is SOLVER_FAILURE and blocks the COMPLETE gate (any kind, any lambda); at a near-zero tangent it stays NO_LIMIT_POINT. Runs record `ladder_used`, `control_mode`, `stop_tangent_ratio`. Only failing steps see the ladder -- converged sweeps are unchanged by this part. |
| 40 | Info | DDM material | Checked: GMNIA fibres use the characteristic IS 2062 Table 3 fy by thickness band from the HR package (E250 NPB700 / BOX 25 mm 240 MPa, WPB200 250 MPa), expected-strength factor 1.0 (no nl_plan); gamma_m0 = 1.10 appears only in the B-1.2 capacities (Md = Zp fy / 1.10). | Confirmed (tested). |
| 41 | High | DDM transfer gate | IN_Ex5 DDM refused: elastic roof displacement X GMNIA / HR 1.053 > 1.05 (fibre I-sections omit the root fillets: A 2.4-6 %, Ix 3-6 % low on NPB/WPB). | Open -- lead decision. Candidate on branch `wip/nl26-ddm-fillets` (fillet fibres, A and Ix = catalogue): Ex5 gate 1.001, T1-T3 1.000-1.008. DDM-only (pushover / NLRHA fibres stay plate-only) and changes every I-section DDM result; not on this branch, no test yet. |

Gold NL after NL-24 (DDM re-run from `/home/claude/nl/run_repo2` @ c200e13, outputs copied into gold_nl, pre-fix DDM kept in
`<job>/_ddm_df041ec/`): Ex11 COMPLETE (57 DUCTILITY_CAP + 4 PLASTIC_PLATEAU, 2 ladder steps, B-1.2 max 0.962), Ex11 unitB_link
COMPLETE (B-1.2 0.930), Ex11 unitC_gym COMPLETE (B-1.2 0.975) -- no capacity shortfall remains. Every other batch job ran the
DDM at df041ec and needs `--only ddm` again (runbook).

