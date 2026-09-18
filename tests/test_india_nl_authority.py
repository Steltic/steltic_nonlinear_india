"""Wave 1: India NL RAG gates — ch16 scaffolding, nl_plan, drift-relief found:false."""
from __future__ import annotations
import copy, json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from nlrha import india_authority as IA  # noqa: E402


def test_ch16_params_stamped_non_authoritative():
    ch16 = IA.load_ch16_params()
    assert ch16.get("india_authoritative") is False
    assert ch16.get("verified") is False
    assert ch16.get("authority") == "asce_scaffolding_only"
    assert ch16.get("jurisdiction") == "india"
    # scaffolding body still present for engine wiring
    assert "transient_drift" in ch16 and "n_motions" in ch16


def test_asce_gaps_are_found_false():
    ids = {g["id"] for g in IA.ASCE_GAPS}
    assert "asce_41_nsp" in ids
    assert "asce_7_ch16_suite_acceptance" in ids
    assert "asce_16_1_2_drift_relief" in ids
    assert all(g["found"] is False for g in IA.ASCE_GAPS)


def test_is_anchors_include_time_history_and_drift():
    assert IA.IS_ANCHORS["time_history_method"]["clause"] == "7.7.4"
    assert IA.IS_ANCHORS["storey_drift_limit"]["limit_ratio"] == 0.004
    assert IA.IS_ANCHORS["storey_drift_limit"]["found"] is True


def test_validate_nl_plan_missing_is_warn():
    findings = IA.validate_nl_plan({})
    assert any(s == "WARN" and "nl_plan missing" in m for s, m in findings)


def test_validate_nl_plan_requires_1893_retrieval():
    bad = {
        "jurisdiction": "india",
        "retrieval": [{"stem": "IS_800_2007", "query": "T4", "found": True, "cite": "T4"}],
    }
    findings = IA.validate_nl_plan({"nl_plan": bad})
    assert any(s == "ERROR" and "IS_1893" in m for s, m in findings)

    good = {
        "jurisdiction": "india",
        "retrieval": [
            {"stem": "IS_1893_Part_1_2016", "query": "7.7.4", "found": True, "cite": "7.7.4"},
            {"stem": "IS_1893_Part_1_2016", "query": "7.11.1", "found": True, "cite": "7.11.1.1"},
        ],
    }
    findings = IA.validate_nl_plan({"nl_plan": good})
    assert not any(s == "ERROR" for s, m in findings)


def test_drift_relief_analogue_default_found_false():
    d = IA.drift_relief_analogue()
    assert d["found"] is False
    assert d["usa_gap"]["id"] == "asce_16_1_2_drift_relief"
    assert d["is_anchor_instead"]["clause"] == "7.11.1.1"


def test_drift_relief_analogue_honours_retrieved_plan(tmp_path=None):
    plan = {
        "jurisdiction": "india",
        "retrieval": [
            {"stem": "IS_1893_Part_1_2016", "query": "drift", "found": True, "cite": "7.11.1"},
        ],
        "drift_relief_analogue": {
            "found": True,
            "stem": "IS_1893_Part_1_2016",
            "clause": "TEST.ONLY",
            "cite": "synthetic for unit test",
            "note": "not a real waiver — tests honouring found:true path",
        },
    }
    d = IA.drift_relief_analogue({"nl_plan": plan})
    assert d["found"] is True and d["clause"] == "TEST.ONLY"


def test_find_nl_plan_from_job_file():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "nl_plan.json")
        json.dump({
            "jurisdiction": "india",
            "retrieval": [
                {"stem": "IS_1893_Part_1_2016", "query": "7.7.4", "found": True, "cite": "7.7.4"},
            ],
        }, open(path, "w"))
        plan = IA.find_nl_plan(job_dir=td)
        assert plan and plan["jurisdiction"] == "india"


def test_india_collections_stems():
    from snl import india_collections as IC
    assert IC.stem_for_collection("IS1893") == "IS_1893_Part_1_2016" or \
           IC.COLLECTION_TO_STEM.get("IS1893") == "IS_1893_Part_1_2016"
    assert "IS_1893_Part_1_2016" in IC.STEM_TO_COLLECTION
