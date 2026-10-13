# steltic-nonlinear-india — 2026-10: PEB release (vendored HR re-sync)

Branch `fix/2026-10-peb-tapered`, one PR with the 2026-10 renumbering commit before it (`CHANGES_2026-10-peb-briefs.md`,
prepared as `fix/2026-10-peb-briefs`, never pushed on its own). It goes with the steltic_india PEB release.

- **`snl/vendor_steltic_india/india_combos.py`** is re-synced byte-identically with steltic_india
  `fix/2026-10-peb-tapered`. A member-wind pattern's `nodal_loads` (the attached-canopy wind of a PEB) is carried
  into its combinations. Nothing changes for patterns without them. `check_vendored.py`: all 9 shared modules are
  byte-identical. Recorded in `VENDORED_FROM.md`.
- **Out of scope.** Web-tapered (PEB) frames cannot yet be analysed by the nonlinear tools: there is no tapered fibre
  section (docs/PEB_TAPERED_SCOPE.md section 9 in steltic_india). The hub's variations metrics mark them
  not representable.
- **Tests.** No test changes. The suite is 379 passed, 11 skipped with `STELTIC_ENGINE_DIR` pointing at a
  steltic_india `steel_engine/`. Without it, `test_fibre_section_matches_is808_within_1_percent[NPB750X270X145.29]`
  fails, on `main` as well: the bundled `steltic_ddm/data/is808_shapes.csv` row for that section disagrees with the
  IS 808 table. That data fix is not part of this release.
