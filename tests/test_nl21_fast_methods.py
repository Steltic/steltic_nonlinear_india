"""NL-21: disclosed cost-cutting method choices for the India gold runs.

  * gravity-only members elastic (pushover.elastic_gravity) with a first-yield P-M check, promotion to fibre, and a
    COMPLETE-gate refusal while a member above first yield is still elastic;
  * NLRHA records trimmed to the 5-95 % Arias significant duration (1 s pre-pad, free-vibration tail);
  * both disclosed in the packages and in complete_gate_disclosures.
"""
import json
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pushover import elastic_gravity as EG  # noqa: E402

GOLD = os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr")


def test_split_releases():
    assert EG.split_releases(["-releasey", 3]) == (["-releasey", 1], ["-releasey", 2])
    assert EG.split_releases(["-releasez", 1]) == (["-releasez", 1], [])
    assert EG.split_releases(["-releasey", 2, "-releasez", 3]) == (["-releasez", 1], ["-releasey", 2, "-releasez", 2])
    assert EG.split_releases(None) == ([], [])


def test_first_yield_ratio_is_linear_p_m_at_either_end():
    c = dict(Py=100.0, My_maj=1000.0, My_min=200.0, i_maj=5)
    f = [10.0, 0, 0, 0, 20.0, 300.0] + [-5.0, 0, 0, 0, 0.0, -600.0]
    assert EG.ratio_of(f, c) == pytest.approx(max(0.1 + 0.3 + 0.1, 0.05 + 0.6))
    c4 = dict(c, i_maj=4)                                   # major moment in slot My (index 4)
    assert EG.ratio_of([0, 0, 0, 0, 500.0, 0] + [0] * 6, c4) == pytest.approx(0.5)


def test_summary_flags_members_above_one():
    s = EG.summary({1: 0.4, 2: 1.2, 3: 0.99}, meta={2: dict(section="NPB300", kind="beam")})
    assert s["flagged_elastic"] == [2] and s["max_ratio"] == pytest.approx(1.2) and s["top"][0]["section"] == "NPB300"


def test_plan_overlap_separates_braced_bay_from_neighbour_bay():
    beam_braced = ((0, 0, 3), (6, 0, 3)); beam_next = ((6, 0, 3), (12, 0, 3)); brace = ((0, 0, 0), (6, 0, 3))
    assert EG._plan_overlap(*beam_braced, *brace) == pytest.approx(6.0)
    assert EG._plan_overlap(*beam_next, *brace) == pytest.approx(0.0)
    assert EG._plan_overlap((0, 0, 3), (0, 6, 3), *brace) == 0.0          # perpendicular beam at the brace node
    assert EG._collinear((6, 0, 3), (12, 0, 3), (12, 0, 3), (13, 0, 3))    # a beam in line with an EBF link


def test_promote_file_round_trip(tmp_path):
    import types
    EG.promote(tmp_path, [5, 3], why="t1", analysis="pushover")
    cur = EG.promote(tmp_path, [3, 9], why="t2", analysis="pushover")
    assert cur == [3, 5, 9]
    EG.promote(tmp_path, [42], why="t3")                                  # all analyses
    d = json.load(open(tmp_path / EG.PROMOTE_FILE))
    assert [h["why"] for h in d["history"]] == ["t1", "t2", "t3"]
    pkg = types.SimpleNamespace(root=str(tmp_path))
    assert EG.promoted(pkg, "pushover") == {3, 5, 9, 42}
    assert EG.promoted(pkg, "nlrha") == {42}                              # a pushover promotion does not slow the NLRHA


def test_enabled_defaults(monkeypatch):
    import types
    monkeypatch.delenv("SNL_GRAVITY_ELASTIC", raising=False)
    ind = types.SimpleNamespace(basis=types.SimpleNamespace(jurisdiction="india"))
    usa = types.SimpleNamespace(basis=types.SimpleNamespace(jurisdiction="usa"))
    assert EG.enabled(ind) and not EG.enabled(usa)
    monkeypatch.setenv("SNL_GRAVITY_ELASTIC", "0")
    assert not EG.enabled(ind)


def test_gold_ex1_classification_and_promotion(tmp_path, monkeypatch):
    import shutil
    src = os.path.join(GOLD, "IN_Ex1_SCBF_5levels_Delhi")
    if not os.path.isdir(src):
        pytest.skip("gold IN_Ex1 not available")
    monkeypatch.delenv("SNL_GRAVITY_ELASTIC", raising=False)
    job = tmp_path / "ex1"
    shutil.copytree(src, job, ignore=shutil.ignore_patterns("figs", "report.html", "viewer_3d.html"))
    from pushover import package_reader as PR, hinge_models as HM
    pkg = PR.load(str(job))
    c = EG.classify(pkg, HM.load_params())
    cols = [t for t, r in c.items() if r == "HR role gravity_col"]
    beams = [t for t, r in c.items() if r != "HR role gravity_col"]
    assert len(cols) == 60 and len(beams) == 155            # 90 braced-bay beams (18 bays x 5 levels) stay fibre
    assert not any((pkg.schedule.get(t) or {}).get("role") == "lateral_col" for t in c)
    EG.promote(job, [beams[0], cols[0]], analysis="pushover")
    monkeypatch.setenv("SNL_ANALYSIS", "pushover")
    c2 = EG.classify(pkg, HM.load_params())
    assert beams[0] not in c2 and cols[0] not in c2 and len(c2) == len(c) - 2
    monkeypatch.setenv("SNL_ANALYSIS", "nlrha")
    assert len(EG.classify(pkg, HM.load_params())) == len(c)


def test_trim_record_to_significant_duration(monkeypatch):
    from nlrha import run as RN
    dt = 0.01
    t = np.arange(0, 40, dt)
    a = np.where((t > 10) & (t < 20), np.sin(2 * np.pi * t), 0.0) + 1e-4 * np.sin(t)
    monkeypatch.setenv("SNL_RECORD_TRIM", "arias5-95")
    ax, ay, info = RN.trim_record(a, 0.5 * a, dt)
    assert info["method"] == "arias5-95"
    assert 10.0 < info["t5_s"] < 11.0 and 19.0 < info["t95_s"] < 20.0
    assert info["t_cut_s"] == pytest.approx(info["t5_s"] - 1.0, abs=dt)       # 1 s pre-pad
    assert len(ax) * dt == pytest.approx(info["t95_s"] - info["t_cut_s"], abs=2 * dt)
    assert info["t_sig_window"][0] == pytest.approx(1.0, abs=dt)
    monkeypatch.setenv("SNL_RECORD_TRIM", "none")
    ax2, _, info2 = RN.trim_record(a, a, dt)
    assert len(ax2) == len(a) and info2["method"] == "none"
    monkeypatch.setenv("SNL_RECORD_TRIM", "arias5-95")
    b = np.where(t < 3, np.sin(2 * np.pi * t), 0.0)                          # strong motion at the start: no pad
    _, _, info3 = RN.trim_record(b, b, dt)
    assert info3["t_cut_s"] == 0.0


def test_gate_refuses_flagged_elastic_member_and_discloses_methods():
    import india_nl_job
    from nlrha import india_authority as IA
    job = india_nl_job.make()
    em = dict(n_elastic=12, max_ratio=1.3, flagged_elastic=[101], basis=EG.BASIS)
    for rel in ("pushover/pushover_package.json", "nlrha/DBE/nlrha_package.json", "nlrha/MCE/nlrha_package.json"):
        p = os.path.join(job, rel); d = json.load(open(p)); d.update(elastic_members=em, spec_values_collected=True,
                                                                     gravity_source="hr_engine",
                                                                     record_trim=dict(method="arias5-95", free_vib_s=5.0, basis="t"))
        json.dump(d, open(p, "w"))
    r = IA.artefact_gate(job)["reasons"]
    assert any("exceed first yield" in x and "101" in x for x in r)
    rows = {x["id"]: x for x in IA.complete_gate_disclosures(job_dir=job)}
    assert rows["gravity_members_elastic"]["flagged_elastic"] == [101]
    assert rows["record_trimming"]["method"] == "arias5-95"
    for rel in ("pushover/pushover_package.json", "nlrha/DBE/nlrha_package.json", "nlrha/MCE/nlrha_package.json"):
        p = os.path.join(job, rel); d = json.load(open(p)); d["elastic_members"]["flagged_elastic"] = []
        json.dump(d, open(p, "w"))
    assert not any("exceed first yield" in x for x in IA.artefact_gate(job)["reasons"])


def test_snl_flagged_elastic_reads_the_step_packages(tmp_path):
    from snl import cli
    (tmp_path / "nlrha" / "DBE").mkdir(parents=True); (tmp_path / "nlrha" / "MCE").mkdir(parents=True)
    json.dump({"elastic_members": {"flagged_elastic": [7, 3]}}, open(tmp_path / "nlrha" / "DBE" / "nlrha_package.json", "w"))
    json.dump({"elastic_members": {"flagged_elastic": [3, 11]}}, open(tmp_path / "nlrha" / "MCE" / "nlrha_package.json", "w"))
    assert cli.flagged_elastic(str(tmp_path), "nlrha") == [3, 7, 11]
    assert cli.flagged_elastic(str(tmp_path), "pushover") == []


def test_residual_drift_averages_out_the_remaining_vibration():
    from nlrha import run as RN
    t = np.linspace(0, 2, 201)
    offset, amp = 1e-4, 1e-3                                   # permanent 0.01 % + a 0.1 % vibration still decaying
    series = offset + amp * np.sin(2 * np.pi * t / 0.4)
    acc = np.array([[series.sum(), 0.0, series.sum(), 0.0]])
    r = RN.residual_drift(acc, len(t), [amp], True)
    assert r[0] == pytest.approx(offset, rel=0.05)             # the instantaneous value could be anywhere in +-amp
    assert RN.residual_drift(acc, 0, [0.5], True)[0] == 0.5
