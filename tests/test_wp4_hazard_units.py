"""WP4.1 / WP4.2 / WP4.6: IS 1893 elastic NL targets (D6), strict hazard inputs, rotational mass bridge."""
from __future__ import annotations
import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FIX = os.path.join(ROOT, "tests", "fixtures")

from nlrha import india_hazard as IH  # noqa: E402


@pytest.mark.parametrize("R", [5.0, 3.0, None])
def test_elastic_plateau_dbe_mce_independent_of_R(R):
    hz = IH.build_india_site_hazard(zone="III", soil="II", I=1.0, R=R, T1x=0.3)
    dbe = max(hz["targets"]["is1893_elastic_DBE"]["sa"])
    mce = max(hz["targets"]["is1893_elastic_MCE"]["sa"])
    assert abs(dbe - 0.200) < 1e-9 and abs(mce - 0.400) < 1e-9
    assert hz["targets"]["is1893_elastic_DBE"]["spectrum_meta"]["R"] is None
    p, sa, label = IH.target_from_india_hazard(hz, level="MCE")
    assert abs(max(sa) - 0.4) < 1e-9 and "no R" in label


def test_elastic_sa_values():
    assert abs(IH.elastic_sa(0.3, zone="IV", I=1.0, soil="II", level="DBE") - 0.30) < 1e-12
    assert abs(IH.elastic_sa(2.153, zone="III", I=1.0, soil="II", level="DBE") - 0.08 * 1.36 / 2.153) < 1e-12
    assert IH.elastic_sa(1.0, zone="II", I=1.5, soil="III", level="MCE") == pytest.approx(0.10 * 1.5 * 1.67)


def test_r_reduced_target_refused():
    hz = IH.build_india_site_hazard(zone="III", soil="II", I=1.0, R=5.0, T1x=1.0)
    hz["targets"]["is1893_elastic_DBE"]["spectrum_meta"]["R"] = 5.0
    with pytest.raises(ValueError):
        IH.target_from_india_hazard(hz, level="DBE")
    old = {"targets": {"is1893_design": {"periods": [0.1, 1.0], "sa": [0.04, 0.02]}}}
    with pytest.raises(ValueError):
        IH.target_from_india_hazard(old)


def test_missing_soil_I_T1_raise_and_cfg_honoured():
    with pytest.raises(ValueError):
        IH.build_india_site_hazard(zone="III", I=1.0, T1x=1.0)            # no soil
    with pytest.raises(ValueError):
        IH.build_india_site_hazard(zone="III", soil="II", T1x=1.0)        # no I
    with pytest.raises(ValueError):
        IH.build_india_site_hazard(zone="III", soil="II", I=1.0)          # no T1 (no 1.0 s default)
    with pytest.raises(ValueError):
        IH.normalize_soil("D")                                              # ASCE letter: no IS mapping
    hz = IH.build_india_site_hazard(cfg={"seismic_zone": "V", "soil_type": "III", "importance_factor": 1.5, "R": 4.0},
                                    T1x=1.0)
    assert hz["site"]["soil_type"] == "III" and hz["site"]["importance_I"] == 1.5
    assert hz["site"]["response_reduction_R"] == 4.0
    assert IH.normalize_soil("medium / stiff (Type II)") == "II"


def test_site_specific_floor_6_4_7():
    ps = [0.1, 0.5, 1.0, 2.0]
    low = dict(level="DBE", periods=ps, sa_g=[0.01] * 4)
    hz = IH.build_india_site_hazard(zone="III", soil="II", I=1.0, T1x=0.5, periods=ps, site_specific_spectrum=low)
    t = hz["targets"]["is1893_elastic_DBE"]
    assert t["spectrum_meta"]["floored"] is True
    assert t["sa"] == pytest.approx([IH.elastic_sa(T, zone="III", I=1.0, soil="II") for T in ps])


def test_rot_mass_conversion():
    from snl import india_units as U
    assert U.rot_mass_tonne_mm2_to_kip_s2_in(6.9524e10) == pytest.approx(6.153e5, rel=1e-3)


def test_package_reader_india_basis_no_sds():
    from pushover import package_reader as PR
    pkg = PR.load(os.path.join(FIX, "IN_Ex1_pkg"))
    b = pkg.basis
    assert b.jurisdiction == "india"
    assert b.SDS is None and b.SD1 is None and b.Cd is None and b.Om0 is None
    assert b.india["Z"] == 0.24 and b.india["I"] == 1.0 and IH.normalize_soil(b.india["soil"]) == "II"
    assert b.W_kip == pytest.approx(14770.8 / 4.4482216152605)
    # WP4.8 mass = W gate
    g = pkg.calc["_is_mass_gate"]
    assert g["ok"] and g["rel_error"] < 0.01
    # WP4.2: rotational mass converted (tonne·mm² -> kip·s²·in)
    master = max(pkg.model.masses)
    assert pkg.model.masses[master][5] < 1e7


def test_ex2_modal_no_spurious_torsion_1p5s():
    from pushover import package_reader as PR, hinge_models as HM, nonlinear_model as NM
    from nlrha import model as MD
    pkg = PR.load(os.path.join(FIX, "IN_Ex2_pkg"), apply_is_mass=False)     # HR mass, to compare with the HR modal
    NM.build_nonlinear(pkg, HM.load_params(), {}, verbose=False)
    m = MD.modal(pkg, 12)
    assert max(x["T"] for x in m["modes"]) < 10.0
    assert m["T_torsion"] == pytest.approx(1.5, rel=0.10)
    assert m["T90"] is not None and m["participation_sum_ok"] and m["spurious_ok"]
