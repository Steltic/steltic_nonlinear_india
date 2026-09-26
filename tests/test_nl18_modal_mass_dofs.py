"""NL-18: the modal analysis asks for no more modes than the model has real mass DOFs. The NL builders put a numerical
mass (1e-8 x the smallest storey mass) on every DOF; asking 12 modes of the 2-level IN_Ex5 (6 real mass DOFs) went
into those local modes, ARPACK did not converge and returned zero-mass "modes" at T ~ 6e6 s that the spurious-mode
check flagged, blocking COMPLETE on a sound model."""
import os
import shutil
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_n_mass_dofs_ignores_numerical_mass():
    import openseespy.opensees as ops
    from nlrha import model as MD
    ops.wipe(); ops.model("basic", "-ndm", 3, "-ndf", 6)
    ops.node(1, 0.0, 0.0, 0.0); ops.node(2, 0.0, 0.0, 3.0); ops.node(3, 1.0, 0.0, 3.0)
    tiny = 1e-8
    ops.mass(1, *([tiny] * 6)); ops.mass(3, *([tiny] * 6))
    ops.mass(2, 1.0 + tiny, 1.0 + tiny, tiny, tiny, tiny, 50.0)
    assert MD.n_mass_dofs() == 3
    ops.wipe()


def test_gold_ex5_has_no_spurious_modes():
    eng = os.environ.get("STELTIC_ENGINE_DIR", "")
    src = os.path.join(os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr"), "IN_Ex5_OMRF_warehouse_mezzanine_Hyderabad")
    if not (os.path.isdir(src) and os.path.exists(os.path.join(eng, "static_model.py"))):
        pytest.skip("gold IN_Ex5 or $STELTIC_ENGINE_DIR not available")
    d = tempfile.mkdtemp(); job = os.path.join(d, "ex5")
    shutil.copytree(src, job, ignore=shutil.ignore_patterns("figs", "report.html", "viewer_3d.html"))
    try:
        from pushover import package_reader as PR, hinge_models as HM, nonlinear_model as NM
        from nlrha import model as MD
        pkg = PR.load(job); prm = HM.load_params()
        loads, _ = NM.gravity_loads(pkg, prm)
        NM.build_nonlinear(pkg, prm, NM.column_gravity_axials(pkg, loads), verbose=False)
        NM._apply_gravity(loads)
        m = MD.modal(pkg, 12)
        assert m["n_modes"] == 6 and m["spurious_ok"], m["spurious_modes"]
        assert m["cum_x"] > 0.99 and m["cum_y"] > 0.99
        assert abs(m["T1y"] - 0.712) / 0.712 < 0.05                     # HR T1y 0.712 s
    finally:
        shutil.rmtree(d, ignore_errors=True)
