"""SI NL wave 5: grid beam_udl N-mm twin, IMK/Ch.16 found:false, report labels, India default."""
from __future__ import annotations
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from snl import india_units as U  # noqa: E402


def _tag(i, j, k):
    return k * 100000 + i * 100 + j


def test_imk_and_ch16_found_false():
    imk = U.imk_hinge_si_status()
    assert imk["found"] is False
    assert "fibre" in imk["analysis_when_nmm"].lower() or "fiber" in imk["analysis_when_nmm"].lower()
    ch = U.ch16_live_si_status()
    assert ch["found"] is False
    assert "psf" in ch["note"].lower()


def test_report_force_length_labels_si():
    ul = U.report_force_length_labels({"units": "N-mm"})
    assert ul["si"] is True
    assert ul["force"] == "kN"
    assert ul["length"] in ("mm", "m")
    ul_kip = U.report_force_length_labels({"units": "kip-in", "force_kip_in": True})
    assert ul_kip["si"] is False
    assert ul_kip["force"] == "kip"


def test_india_jurisdiction_defaults_native_nmm():
    U.set_analysis_units("kip-in")
    assert U.wants_native_nmm_analysis({"jurisdiction": "india", "units": "N-mm"}) is True
    assert U.wants_native_nmm_analysis({"units": "N-mm"}) is False
    assert U.wants_native_nmm_analysis({"jurisdiction": "india", "units": "N-mm", "force_kip_in": True}) is False
    assert U.wants_native_nmm_analysis({"units": "kip-in"}) is False
    U.set_analysis_units("kip-in")


def test_grid_beam_udl_nmm_dual_path():
    from steltic_ddm import loads as L

    class M:
        kind = "beam"
        dirn = "X"
        n1 = _tag(1, 1, 1)
        n2 = _tag(2, 1, 1)

    class NM:
        nodes = {M.n1: (0.0, 0.0, 3500.0), M.n2: (6000.0, 0.0, 3500.0)}

    i, j, k = 1, 1, 1
    present = {k: {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)}}
    cfg = {
        "_nl_analysis_units": "N-mm",
        "units": "N-mm",
        "native_nmm": True,
        "heights": [3500.0, 3500.0],  # two levels so k=1 is floor not roof
        "SX": 6000.0,
        "SY": 5000.0,
        "D_floor": 0.5,
        "D_roof": 0.4,
        "L_floor": 0.75,
        "snow": 0.0,
        "clad": 0.0,
    }
    U.set_analysis_units("N-mm")
    w = L.beam_udl(cfg, NM(), present, M(), 0, 1, 1.0, 0.0, 0.0)
    # width = min(3000, 3000, 2500) = 2500 mm; nb=1; p=0.5 → 1.25 N/mm
    assert abs(w - 1.25) < 1e-9, w
    U.set_analysis_units("kip-in")


def test_grid_beam_udl_kip_legacy_unchanged():
    from steltic_ddm import loads as L

    class M:
        kind = "beam"
        dirn = "X"
        n1 = _tag(1, 1, 1)
        n2 = _tag(2, 1, 1)

    class NM:
        nodes = {M.n1: (0.0, 0.0, 144.0), M.n2: (240.0, 0.0, 144.0)}

    i, j, k = 1, 1, 1
    present = {k: {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)}}
    cfg = {
        "heights": [144.0, 144.0],
        "SX": 240.0,
        "SY": 300.0,
        "D_floor": 50.0,
        "D_roof": 20.0,
        "L_floor": 50.0,
        "snow": 20.0,
        "clad": 0.0,
    }
    U.set_analysis_units("kip-in")
    w = L.beam_udl(cfg, NM(), present, M(), 0, 1, 1.0, 0.0, 0.0)
    assert abs(w - 50.0 * (120.0 / 12.0) / 12000.0) < 1e-12


def test_hinge_unit_system_note_found_false():
    from pushover.hinge_models import hinge_unit_system_note
    st = hinge_unit_system_note("N-mm")
    assert st["found"] is False


def test_report_html_helpers_emit_si_labels():
    from pushover.report_supplement import _ul as pul
    from nlrha.report import _ul as nul
    assert pul({"units": "N-mm"})["force"] == "kN"
    assert nul({"units": "N-mm"})["force"] == "kN"
    assert pul({"units": "kip-in", "force_kip_in": True})["force"] == "kip"
