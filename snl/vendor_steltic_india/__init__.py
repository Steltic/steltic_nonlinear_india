"""Shared India modules vendored BYTE-IDENTICALLY from steltic_india (work/hr/steel_engine) -- WP1.14.

Do not edit here: fix in steltic_india and re-vendor.  `scripts/check_vendored.py` sha256-compares every file
against the HR copy and fails on drift.  The modules import each other by bare name (india_loads, india_seismic,
...), so this package directory is added to sys.path by `shared()`.

Files: india_loads, india_seismic, india_units, india_wind_tables, india_combos, india_is18168,
india_seismic_gates, india_omega_is18168, preflight (India block = preflight.india_checks).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("india_loads.py", "india_seismic.py", "india_units.py", "india_wind_tables.py", "india_combos.py",
         "india_is18168.py", "india_seismic_gates.py", "india_omega_is18168.py", "preflight.py")
HR_SOURCE_COMMIT = "steltic_india (work/hr) -- see scripts/check_vendored.py"


def shared(name):
    """Import one shared module (e.g. shared('india_seismic')) from the vendored copies."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import importlib
    return importlib.import_module(name)
