# Vendored from steltic_india

Commit: **69701f6070706e5d2adc6fefaea16b42c9f4e221** [steltic_india main] (branch `fix/2026-09-review`: 0.3.0 release notes plus O1/O2/O3, GOLD-1..7, AUD-1..4,
GOLD-764, GOLD-COLL, AUD-1 Windows, and the corpus wording: no reference to a corpus repository).

**2026-10 re-sync:** the vendored files were rewritten together with `steltic_india` branch `fix/2026-10-peb-briefs` (the 2026-10 renumbering of the example briefs: brief ids in comments, docstrings and one message string; no logic change). Merged steltic_india commit: **083a500845e04566a3b3dfc5be79e494498c3ef1**.

**2026-10 PEB re-sync:** `india_combos.py` rewritten together with `steltic_india` branch `fix/2026-10-peb-tapered` (a member-wind pattern's `nodal_loads`, the attached-canopy wind, is carried into its combinations; no change for patterns without them). Merged steltic_india commit: **083a500845e04566a3b3dfc5be79e494498c3ef1**.

Files (byte-identical copies of `steltic_india/steel_engine/<file>`): india_loads.py, india_seismic.py,
india_units.py, india_wind_tables.py, india_combos.py, india_is18168.py, india_seismic_gates.py,
india_omega_is18168.py, preflight.py.

**Section tables (NL-35, 2026-10-16):** `steltic_ddm/data/is808_shapes.csv` and `steltic_ddm/data/is1161_tubes.csv` are
byte-identical copies of the same files in `steltic_india/steel_engine` (steltic_india main **e340df8**). They are
the fallback when `$STELTIC_ENGINE_DIR` is not set; with it set (every documented run) the HR tables are read
directly. The bundled copies dated from the install-from-git merge and had drifted: the NPB750X270X145.29,
WPB500X300X187.34 and WPB650X300X224.78 rows had their J / Zx / Zy / Sx / Sy columns shifted, and later HR
corrections (rx / ry, Cw, one renamed WPB) were missing. `check_vendored.py` now checks them too.

Not vendored (the NL repo does not build frames from JSON and does not run the X01 deck):
frame_build.py, roof_geometry.py, india_flexible_diaphragm.py, multi_unit.py, package_finalize.py,
example_build_ebf.py. The NL reads the HR package (model_opensees.py, design/*.json/csv) instead.

Check: `python scripts/check_vendored.py` ($STELTIC_HR_ROOT, else a sibling steltic_india checkout, else SKIP).
Re-sync: `python scripts/check_vendored.py --sync` prints the cp commands.

**2026-10 first-wave re-sync:** `india_seismic.py` (the D8 importance-factor row in plain words) and
`india_seismic_gates.py` (pipeline-level open reasons such as the IS 1893 7.6.4 flexible-deck comparison are
counted by `design_status`) copied from `steltic_india` branch `fix/2026-10-first-wave`, commit
**54e7463343f1b6ba19429c5aa28c169118fd3bc3**. The other vendored files are unchanged by that branch.
