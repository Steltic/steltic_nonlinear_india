"""SI NL wave 3: Stage A display_scale + Stage B N-mm package bridge (analysis stays kip-in)."""
from __future__ import annotations
import csv, json, os, sys, tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from snl import india_units as U  # noqa: E402


def test_display_scale_si_from_kip_engine():
    """Stage A: SI display labels while ANALYSIS_UNITS remains kip-in."""
    U.activate_kip_in()
    sc = U.display_scale({"units": "N-mm"})
    assert sc["si"] is True
    assert sc["analysis"] == "kip-in"
    assert sc["force_lbl"] == "kN"
    assert sc["moment_lbl"] == "kN·m"
    assert sc["stress_lbl"] == "MPa"
    assert sc.get("bridged_display") is True
    # 1 kip → ~4.448 kN  (value / force_div)
    assert abs(1.0 / sc["force_div"] - U.KIP_TO_N / 1000.0) < 1e-9


def test_display_scale_legacy_kip():
    sc = U.display_scale({"units": "kip-in", "force_kip_in": True})
    assert sc["si"] is False
    assert sc["force_lbl"] == "kip"
    assert sc["stress_lbl"] == "ksi"
    assert abs(sc["moment_div"] - 12.0) < 1e-9


def test_fmt_force_moment_si_display():
    cfg = {"units": "N-mm"}
    assert "kN" in U.fmt_force(1.0, cfg)  # 1 kip → kN
    assert "kN·m" in U.fmt_moment(U.KNM_TO_KIPIN, cfg)  # 1 kN·m expressed in kip-in


def test_demand_field_names_si():
    fn = U.demand_field_names({"units": "metric"})
    assert fn["P_comp"] == "P_comp_N"
    assert fn["Mx_display"] == "Mx_kNm"
    assert fn["length"] == "length_mm"


def test_schedule_row_si_to_kip():
    row = U.schedule_row_to_kip_in({
        "member": "col", "section": "MB300",
        "length_mm": 3500, "P_comp_N": 2.0e6, "Mx_kNm": 250,
        "governing_combo": "1.5DL",
    })
    assert abs(row["length_in"] - 3500 * U.MM_TO_IN) < 1e-9
    assert abs(row["P_comp_kip"] - 2.0e6 / U.KIP_TO_N) < 1e-9
    assert abs(row["Mx_kipft"] - 250 * U.KNM_TO_KIPFT) < 1e-9


def test_detect_si_signals():
    sig = U.detect_package_si_signals(
        schedule_fieldnames=["ele_tag", "length_mm", "P_comp_N", "Mx_kNm"],
        sample_E=200000.0,
        max_node_coord=12000.0,
        cfg_units="N-mm",
    )
    assert sig["likely_si"] is True
    sig2 = U.detect_package_si_signals(
        schedule_fieldnames=["ele_tag", "length_in", "P_comp_kip", "Mx_kipft"],
        sample_E=29000.0,
        max_node_coord=2160.0,
        cfg_units="kip-in",
    )
    assert sig2["likely_si"] is False


def test_ex22_stays_kip_in_no_bridge():
    from pushover import package_reader as PR
    pkg = PR.load(os.path.join(ROOT, "examples", "Ex22_SMF"))
    assert (pkg.basis.package_units or "kip-in") == "kip-in"
    assert not (pkg.calc or {}).get("_nl_unit_bridge")
    assert abs(pkg.model.elements[0]["E"] - 29000.0) < 1e-6
    assert pkg.schedule[1]["P_comp_kip"] > 0


def test_si_package_bridge_at_ingest():
    from pushover import package_reader as PR
    td = Path(tempfile.mkdtemp(prefix="si_pkg_"))
    (td / "design").mkdir()
    (td / "model_opensees.py").write_text(
        "import openseespy.opensees as ops\n"
        "ops.wipe()\n"
        "ops.model('basic', '-ndm', 3, '-ndf', 6)\n"
        "ops.node(1, 0.0, 0.0, 0.0)\n"
        "ops.node(2, 6000.0, 0.0, 0.0)\n"
        "ops.node(3, 6000.0, 0.0, 3500.0)\n"
        "ops.fix(1, 1,1,1,1,1,1)\n"
        "ops.mass(3, 50.0, 50.0, 50.0, 0,0,0)\n"
        "ops.geomTransf('Linear', 1, 0, 1, 0)\n"
        "ops.element('elasticBeamColumn', 1, 1, 3, 15000.0, 200000.0, 76923.0, 1e8, 2e8, 3e8, 1)\n"
    )
    with open(td / "design" / "member_schedule.csv", "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["ele_tag", "member", "section", "length_mm", "P_comp_N", "Mx_kNm", "governing_combo"],
        )
        w.writeheader()
        w.writerow(dict(
            ele_tag=1, member="col", section="MB300", length_mm=3500,
            P_comp_N=2.0e6, Mx_kNm=250, governing_combo="1.5DL+1.5LL",
        ))
    (td / "design" / "calc_package.json").write_text(json.dumps({
        "building": "SI_stub", "units": "N-mm", "members": [],
    }))
    (td / "cfg.py").write_text("units = 'N-mm'\nheights = [3500, 3500]\nsystem = 'SMF'\n")
    (td / "report.html").write_text(
        "<html>Seismic weight W = 60000 kN Base shear ΣF = 2400 kN "
        "design period T = min(1.0, 1.2) = 1.00</html>"
    )
    pkg = PR.load(td)
    br = pkg.calc["_nl_unit_bridge"]
    assert br["from"] == "N-mm" and br["to"] == "kip-in" and br["stage"] == "B"
    assert abs(pkg.model.nodes[2][0] - 6000 * U.MM_TO_IN) < 1e-9
    assert abs(pkg.model.elements[0]["E"] - 200000 * U.MPA_TO_KSI) < 1e-3
    assert abs(pkg.schedule[1]["length_in"] - 3500 * U.MM_TO_IN) < 1e-9
    assert abs(pkg.basis.W_kip - 60000 * U.KN_TO_KIP) < 1e-6
    assert abs(pkg.basis.V_design_kip - 2400 * U.KN_TO_KIP) < 1e-6
    assert abs(pkg.basis.heights_in[0] - 3500 * U.MM_TO_IN) < 1e-9
