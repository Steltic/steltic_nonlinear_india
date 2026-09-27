# Vendored from steltic_india

Commit: **69701f6070706e5d2adc6fefaea16b42c9f4e221** [steltic_india main] (branch `fix/2026-09-review`: 0.3.0 release notes plus O1/O2/O3, GOLD-1..7, AUD-1..4,
GOLD-764, GOLD-COLL, AUD-1 Windows, and the corpus wording: no reference to a corpus repository).

Files (byte-identical copies of `steltic_india/steel_engine/<file>`): india_loads.py, india_seismic.py,
india_units.py, india_wind_tables.py, india_combos.py, india_is18168.py, india_seismic_gates.py,
india_omega_is18168.py, preflight.py.

Not vendored (the NL repo does not build frames from JSON and does not run the X01 deck):
frame_build.py, roof_geometry.py, india_flexible_diaphragm.py, multi_unit.py, package_finalize.py,
example_build_ebf.py. The NL reads the HR package (model_opensees.py, design/*.json/csv) instead.

Check: `python scripts/check_vendored.py` ($STELTIC_HR_ROOT, else a sibling steltic_india checkout, else SKIP).
Re-sync: `python scripts/check_vendored.py --sync` prints the cp commands.
