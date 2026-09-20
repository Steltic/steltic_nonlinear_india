"""WP4.13: summaries record the sha256 of the packages they read; the COMPLETE gate flags stale summaries."""
from __future__ import annotations
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_summary_freshness(tmp_path):
    from snl import compare
    from nlrha import india_authority as IA
    job = tmp_path
    (job / "pushover").mkdir(); (job / "nlrha").mkdir()
    (job / "seismic_calc.json").write_text(json.dumps({"Z": 0.24, "I": 1.0, "R": 4.5, "VB_kN": 984.7, "W_kN": [3164.4]}))
    po = {"jurisdiction": "india", "plasticity": "fibre", "fibre_eles": 10, "directions": {}}
    (job / "pushover" / "pushover_package.json").write_text(json.dumps(po))
    (job / "nlrha" / "nlrha_package.json").write_text(json.dumps({"jurisdiction": "india", "levels": {}}))
    compare.build(str(job))
    summ = json.load(open(job / "snl_summary.json"))
    assert summ["verdict"] is None and "no acceptance criteria" in summ["statement"]
    assert set(summ["inputs_sha256"]) == {"pushover/pushover_package.json", "nlrha/nlrha_package.json"}
    gate = IA.artefact_gate(str(job))
    assert not any("STALE" in r for r in gate["reasons"])
    po["fibre_eles"] = 11                                                     # a re-run changes the package ...
    (job / "pushover" / "pushover_package.json").write_text(json.dumps(po))
    gate = IA.artefact_gate(str(job))                                          # ... and the old summary is stale
    assert any("STALE" in r for r in gate["reasons"]) and not gate["ok"]
    html = open(job / "four_analyses.html").read()
    assert "MCE<sub>R</sub>" not in html and "BPON" not in html and "no R" in html
