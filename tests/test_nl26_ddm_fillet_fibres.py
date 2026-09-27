"""NL-26: DDM (GMNIA) fibre I-sections carry the root fillets, so A, Ix and Zp equal the IS 808 catalogue values the HR
design uses. The plate model (d, tw, bf, tf only) was 2-6 % low on NPB / WPB shapes and IN_Ex5 failed the DDM elastic
transfer gate (roof X 1.053 > 1.05; 1.001 with the fillets). The pushover / NLRHA fibre sections (same builder,
fillets=False by default) are unchanged.
"""
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SECTIONS = ["NPB400X180X57.38", "NPB700X250X143.42", "NPB750X270X145.29", "WPB200X200X42.26", "WPB300X300X100.85",
            "WPB600X300X211.92"]


class _Ops:
    """Records the fibres a builder places (y, z, area); every other OpenSees call is a no-op."""
    def __init__(self):
        self.fibres = []

    def fiber(self, y, z, A, mat):
        self.fibres.append((y, z, A))

    def __getattr__(self, name):
        return lambda *a, **k: None


def _fibre_props(label, fillets):
    from steltic_ddm.sections_fiber import FiberSectionBuilder
    o = _Ops()
    FiberSectionBuilder(o, Fy=250.0, units="N-mm", fillets=fillets).w_shape(1, label, axis="z")
    A = sum(a for _, _, a in o.fibres)
    Iy, Iz = sum(a * y * y for y, _, a in o.fibres), sum(a * z * z for _, z, a in o.fibres)
    # major axis = the larger second moment; the section is doubly symmetric, so the plastic neutral axis is at 0
    if Iy >= Iz:
        return A, Iy, sum(a * abs(y) for y, _, a in o.fibres)
    return A, Iz, sum(a * abs(z) for _, z, a in o.fibres)


@pytest.mark.parametrize("label", SECTIONS)
def test_fibre_section_matches_is808_within_1_percent(label):
    from pushover import india_materials as IM
    sp = IM.section_props_mm(label)                      # IS 808 table (the HR engine's catalogue)
    A, I, Zp = _fibre_props(label, fillets=True)
    assert A == pytest.approx(sp["A"], rel=0.01)
    assert I == pytest.approx(sp["Ix"], rel=0.01)
    assert Zp == pytest.approx(sp["Zx"], rel=0.01)


def test_plate_model_without_fillets_is_the_old_section_and_low():
    """fillets=False (the pushover / NLRHA default) keeps the plate model: A, I, Zp 2-6 % below the catalogue."""
    from pushover import india_materials as IM
    from steltic_ddm.sections_fiber import FiberSectionBuilder
    import inspect
    assert inspect.signature(FiberSectionBuilder.__init__).parameters["fillets"].default is False
    sp = IM.section_props_mm("NPB400X180X57.38")
    A, I, Zp = _fibre_props("NPB400X180X57.38", fillets=False)
    assert 0.93 < A / sp["A"] < 0.97 and 0.93 < I / sp["Ix"] < 0.97 and 0.93 < Zp / sp["Zx"] < 0.97


def test_gmnia_uses_fillets_on_the_india_path_only(monkeypatch):
    from steltic_ddm.model_gmnia import GMNIAModel
    g = GMNIAModel.__new__(GMNIAModel)
    g.cfg = {"load_plan": {"jurisdiction": "india"}}
    monkeypatch.delenv("SNL_DDM_FILLETS", raising=False)
    assert g._fillets() is True
    monkeypatch.setenv("SNL_DDM_FILLETS", "0")
    assert g._fillets() is False
    monkeypatch.delenv("SNL_DDM_FILLETS", raising=False)
    g.cfg = {}
    assert g._fillets() is False


def test_pushover_fibre_model_does_not_request_fillets():
    import inspect
    from pushover import fibre_model
    assert "fillets" not in inspect.getsource(fibre_model)
