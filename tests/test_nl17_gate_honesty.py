"""NL-17: COMPLETE-gate honesty. An India analysis package counts toward COMPLETE only when the IS specification
values were collected (`snl collect`), its gravity is the HR engine's own load state, and -- when the HR package
declares EBF links -- the links were modelled. The pushover curve plot draws each direction's design V-bar_B, and
the India reports / design-criteria draft carry no 'literature placeholder' or ASCE 16.1.4 / 16.5 wording."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import india_nl_job  # noqa: E402
from nlrha import india_authority as IA  # noqa: E402
from pushover import report_india as RI  # noqa: E402


def _edit(path, **kw):
    d = json.load(open(path, encoding="utf-8")); d.update(kw)
    json.dump(d, open(path, "w", encoding="utf-8"))


def _packages(job):
    yield os.path.join(job, "pushover", "pushover_package.json")
    for lv in ("DBE", "MCE"):
        yield os.path.join(job, "nlrha", lv, "nlrha_package.json")


def test_gate_refuses_uncollected_and_idealised_gravity():
    job = india_nl_job.make()
    r = IA.artefact_gate(job)["reasons"]
    assert any("pushover ran without collected IS specification values" in x for x in r)
    assert any("NLRHA DBE gravity is not the HR engine" in x for x in r)
    for p in _packages(job):
        _edit(p, spec_values_collected=True, gravity_source="hr_engine", links=0)
    r = IA.artefact_gate(job)["reasons"]
    assert not any("collected IS specification" in x or "gravity is not the HR" in x for x in r), r


def test_gate_requires_links_when_package_declares_them():
    job = india_nl_job.make()
    for p in _packages(job):
        _edit(p, spec_values_collected=True, gravity_source="hr_engine", links=0)
    os.makedirs(os.path.join(job, "design"), exist_ok=True)
    with open(os.path.join(job, "design", "member_schedule.csv"), "w", encoding="utf-8") as f:
        f.write("ele_tag,member,role,section\n1,beam,link,NPB400X180X57.38\n2,col,lateral_col,WPB300X300X100.85\n")
    r = IA.artefact_gate(job)["reasons"]
    assert any("declares EBF links but the model has no nonlinear links" in x for x in r)
    for p in _packages(job):
        _edit(p, links=92)
    assert not any("EBF links" in x for x in IA.artefact_gate(job)["reasons"])


def test_gravity_source():
    assert RI.gravity_source([{"W_kN": 1.0, "HR_EV_kN": 0.9}]) == "hr_engine"
    assert RI.gravity_source([{"W_kN": 1.0}]) == "idealised"
    assert RI.gravity_source([]) == "idealised"


def test_curve_plot_draws_each_direction_design_shear(monkeypatch):
    import types
    lines = []
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.axes
    real = matplotlib.axes.Axes.axhline

    def spy(self, y=0, *a, **k):
        lines.append((round(y, 1), k.get("label")))
        return real(self, y, *a, **k)
    monkeypatch.setattr(matplotlib.axes.Axes, "axhline", spy)
    run = {"rec": {"u": [0.0, 1.0], "V": [0.0, 100.0]}}
    res = {"nsp": {"IS-DBE": {"target_disp_in": 0.5}}}
    basis = types.SimpleNamespace(V_design_kip=200.0, india={"VB_kN": 984.7, "VB_x_kN": 984.7, "VB_y_kN": 812.3})
    RI._png_curve({"X": run, "Y": run}, {"X": res, "Y": res}, basis)
    assert (984.7, "design V̄B X (IS 1893 7.7.3)") in lines and (812.3, "design V̄B Y (IS 1893 7.7.3)") in lines


def test_no_placeholder_or_asce_wording_in_india_texts():
    src = open(os.path.join(ROOT, "pushover", "report_india.py"), encoding="utf-8").read()
    assert "literature placeholders" not in src
    dc = open(os.path.join(ROOT, "nlrha", "design_criteria.py"), encoding="utf-8").read()
    i = dc.index("if india:                                          # NL-17")
    india_block = dc[dc.index("\n", i):dc.index("else:", i)]          # the code after the marker comment
    assert "16.5" not in india_block and "16.1.4" not in india_block
    assert "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information." in india_block
