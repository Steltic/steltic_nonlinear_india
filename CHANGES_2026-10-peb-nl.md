# steltic-nonlinear-india — 2026-10: PEB sheds in the nonlinear tools (NL-33)

Branch `feat/2026-10-peb-nl`. The PEB release of steltic_india (welded plate I `welded_I` / web-tapered I `tapered_I`
members, `CHANGES_2026-10-peb.md`) was out of scope for the nonlinear tools: there was no welded or tapered section.
This change makes the five PEB sheds (IN_Ex1 ... IN_Ex5) run through pushover, NLRHA and the DDM. Every earlier gold
building is unchanged (the new code paths need a welded / tapered custom section or `calc_package['peb']` chains).

## Sections (pushover, NLRHA, DDM)

- `pushover/india_sections.py`: `welded_I` and `tapered_I` custom sections from `design/cfg_snapshot.json`, with the
  plate formulae of steltic_india `sections.register_welded_I`. A tapered member is the HR engine's stepped model,
  `n_seg` prismatic WI segments at the mid-segment depth (`register_tapered_I`). Undeclared `WI<D>X<bf>X<tf>X<tw>`
  labels are read from the designation.
- `pushover/sections_db.py`, `pushover/fibre_model.py`, `steltic_ddm/sections_fiber.py`: welded I plate fibres
  (flanges and web). There is no residual-stress pattern for welded plates and no local buckling (disclosed).
- `pushover/india_materials.py`, `steltic_ddm/india_checks.py`: Table 10 buckling classes for welded I (zz b / yy c,
  tf > 40 mm c / d). Section class uses the IS 800 Table 2 welded rows. The Annex B-1.2 section capacities use Ze
  (semi-compact) or the 3.7.2(d) effective section A_eff / Ze_eff (slender), as `india_is800.effective_section_3_7_2d`.

## DDM (GMNIA)

- **Releases by geometry** (`model_gmnia.py`). A PEB shed has off-grid nodes (eave and ridge struts, 198xxx), so the
  tag-decoded direction of an eave strut along X could read "Y". Its major pin then released the strut's own torsion
  at both ends, and the stiffness matrix was singular (IN_Ex1 failed with UmfPack "numeric analysis returns 1" and
  ARPACK "starting vector is zero").
  - Horizontal axis-aligned beams keep the global pin. The direction is taken from the coordinates, and it is
    bit-identical for every earlier gold: no released beam there was off-grid.
  - Sloped or skew beams, and released columns (PEB end-wall posts, interior pinned columns; no earlier gold has one),
    get a pin spring on the element's local axes. It releases HR's local rotations exactly.
- **Periods with a single mass node** (`transfer_gate.py`). A PEB shed's roof master carries all the mass (rank 3).
  ARPACK cannot return three modes, and the dense LAPACK fallback is O(neq³) for 4 600–7 000 equations. The HR
  periods now come from an exact static condensation on the mass DOFs. Other models still use ARPACK first.
- **The out-of-plane restraint system** (`peb_restraints.py`, new).
  - The problem: the HR frame model has no purlins, girts or fly braces. The design reads them as member buckling and
    LTB lengths (`cfg['flange_braces']`, peb_build, owner ruling D-T1). The bare frame in a corotational GMNIA buckles
    out of plane at λ ≈ 0.26 under 1.5DL + 1.5LL (IN_Ex1: 10 m columns, 15 m rafter halves).
  - The GMNIA now carries the restraints, at the stations peb_build uses.
  - Fly-brace stations hold both flanges, as the design's Ly. They get a lateral restraint and a torsional restraint.
  - Rafters are tied laterally to the roof's rigid diaphragm, as the HR model ties the eaves (a diaphragm slave plus a
    zeroLength at 1e9 N/mm).
  - Columns are tied to a rigid stud pinned at the column base and tied to its top. The restraint follows the wall's
    racking line and adds no stiffness to the building's own sway.
  - Torsional restraints act on the member axis.
  - Purlin-only and girt-only stations hold one flange. A centroid-line model cannot represent that, so they are not
    modelled (conservative). The count is recorded.
  - Stations inside an HR element become sub-element nodes (no sub-element longer than L / nsub).
  - **Warping.** The fibre beam-columns have no warping degree of freedom. A deep welded I between torsional
    restraints therefore twisted under its own major-axis moment at a fraction of its LTB resistance. In IN_Ex1
    under 1.5DL + 1.5LL, the 1.5 m column top between the last fly brace and the knee twisted 0.03 rad and carried a
    19 kN·m minor moment. That gave a false B-1.2 shortfall of 1.13. The St Venant-only Mcr is about 1 100 kN·m,
    against about 15 000 kN·m with warping.
    - Every welded I element now carries G J + π² E Cw / L_t² as its torsional stiffness, the warping term of the
      elastic LTB moment, where L_t is the spacing of the torsional restraints bounding it (`warping_length`). With
      it the twist is under 2·10⁻⁴ rad and the minor moment 0.2 kN·m.
    - The IN_Ex3 crane gravity sweep that stopped numerically at λ 1.538 (three attempts, about 30 min) now reaches
      its ductility cap at λ 1.72 in 20 s.
  - Recorded in `ddm_results.json` `options.peb_restraints`, the DDM report (section 2) and the COMPLETE-gate
    disclosures.
- Gates on the five sheds with the restraints:
  - Transfer gate: T1 within 0.1 %, T2 / T3 within 2.1 %, roof displacements within 4 %.
  - Gravity transfer gate: 0 members outside ±5 %.
  - IN_Ex1 1.5DL + 1.5LL now passes λ = 1 (λ 1.2, 0.5 s per step). Before the restraints it was limited at 0.26.

## Gate disclosures (`nlrha/india_authority.py`)

- `peb_welded_plate_fibres`: plate fibres without residual stress or local buckling. Slender webs keep their gross
  plates in the fibres, while B-1.2 uses the effective section.
- `peb_ddm_restraints`: the restraint idealisation above.

## Batch

- `scripts/run_gold_batch.sh`: the five PEB sheds join `JOBS_DEFAULT` by size (the `element(` count the order test
  uses), making 24 job folders; `tests/test_nl23_gold_batch.py` expects 24.
- `DDM_CODE` stays `NL-26`: no earlier gold's DDM result changes, so no refresh pass is due.

## Tests

- `tests/test_nl33_peb_welded_sections.py` covers the HR reference values for WI / TI properties, the effective
  section and the B-1.2 class, plus fibre A and I.
- `tests/test_nl33_peb_gmnia_releases.py` covers:
  - geometric direction and local axes;
  - condensed periods against the cantilever closed form;
  - IN_Ex3 non-singular, with periods against the HR;
  - pre-PEB gold pins unchanged;
  - the restraint plan against peb_build's stations;
  - IN_Ex3 gravity to λ = 1, with the studs on the racking line;
  - the disclosures.
- Gold-package tests skip without the HR gold jobs. Suite result: see the PR.
