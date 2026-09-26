"""NL-16: the DDM gravity-transfer gate's +/-5 % ratio band gets a noise floor of 2 % of the member's plastic capacity
at 250 MPa, so near-zero forces (IN_Ex9 stem floor beams, 8.0 vs 8.6 kN-m) do not fail the gate while a real load-
transfer error on the same member still does."""
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from steltic_ddm import india_checks as IC  # noqa: E402


def _row(des, got, sec="WPB320X300X126.66", q="M (kN·m)"):
    return dict(combo="1.5DL+1.5LL", ele=1, kind="beam", role="floor", section=sec, quantity=q, design=des, gmnia=got,
                ratio=round(got / des, 3), ok=abs(got / des - 1) <= 0.05)


def test_capacity_is_250_times_plastic_modulus_or_area():
    assert IC.section_capacity_250("WPB320X300X126.66", "M (kN·m)") == pytest.approx(535.0, rel=0.01)
    assert IC.section_capacity_250("WPB320X300X126.66", "P top (kN)") == pytest.approx(4025.0, rel=0.01)
    assert IC.section_capacity_250("NOT_A_SECTION", "M (kN·m)") == 0.0


def test_small_force_passes_by_floor_but_real_error_does_not():
    rows = [_row(8.64, 8.01), _row(300.0, 270.0), _row(100.0, 101.0)]
    n = IC.apply_noise_floor(rows, 0.02)
    assert n == 1 and rows[0]["ok"] and rows[0]["ok_by_floor"]
    assert rows[1]["ok"] is False                      # 30 kN-m > 2 % x 535 kN-m
    assert rows[2]["ok"] and "ok_by_floor" not in rows[2]


def test_gold_ex9_stem_gate_passes():
    eng = os.environ.get("STELTIC_ENGINE_DIR", "")
    src = os.path.join(os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr"),
                       "IN_Ex9_EBF_12levels_Tplan_Guwahati", "units", "stem")
    if not (os.path.isdir(src) and os.path.exists(os.path.join(eng, "static_model.py"))):
        pytest.skip("gold IN_Ex9 stem or $STELTIC_ENGINE_DIR not available")
    return _run(src, eng)


def _run(src, eng, tmp=None):
    import tempfile
    d = tempfile.mkdtemp()
    job = os.path.join(d, "stem")
    shutil.copytree(src, job, ignore=shutil.ignore_patterns("figs", "report.html", "viewer_3d.html"))
    from steltic_ddm import ingest, loads
    nm = ingest.load_package(job, eng)
    g = IC.gravity_gate(nm, nm.cfg, loads.prune(loads.steltic_combos(nm.cfg, nm=nm)))
    assert g["ok"], g["summary"]
    assert g["n_ok_by_floor"] <= 10
    shutil.rmtree(d, ignore_errors=True)
