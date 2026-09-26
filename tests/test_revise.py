"""`snl revise` — re-issuing the reports with the IS corpus behind them.

The analysis run queries nothing, so its reports mark every clause UNVERIFIED. This step re-asks the IS
corpus and replaces the placeholder wording with a citation. The tests that matter are about what it
refuses to claim -- and, on the India fork, that it never looks for (or cites) a foreign hinge table:
IS 800 / IS 1893 / IS 18168 tabulate no backbone, so the groups are modelling assumptions (D3 / D7).
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from snl import revise                      # noqa: E402
import india_nl_job                         # noqa: E402


def test_it_will_not_run_without_the_review():
    with pytest.raises(SystemExit) as e:
        revise.run("/nonexistent-project-xyz")
    assert "review.md" in str(e.value) and "Review tab" in str(e.value)


def test_an_empty_review_is_refused(tmp_path):
    (tmp_path / "review.md").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        revise.run(str(tmp_path))
    assert "empty" in str(e.value)


# --- the relevance gates: a citation to the wrong clause is worse than none ---------------------
def _res(*hits):
    return {"ok": True, "results": list(hits)}


def test_a_passage_must_be_the_table_and_name_the_component():
    gusset = {"section": "10.5", "title": "Gusset plates",
              "text": "The region of gusset boundary to the beam, column, and brace shall be detailed"}
    table = {"section": "X.1", "title": "Modelling parameters", "page": 78,
             "text": "Table X Modelling Parameters for Nonlinear Analysis - Beams"}
    assert revise._relevant_hit(_res(gusset), ("beam",)) is None
    assert revise._relevant_hit(_res(gusset, table), ("beam",)) is table
    assert revise._relevant_hit(_res(table), ("brace",)) is None
    assert revise._relevant_hit({"ok": False, "results": [table]}, ("beam",)) is None


def test_a_clause_is_only_grounded_by_a_passage_from_the_document_asked():
    is800 = {"source": "IS_800_2007", "section": "12.6", "text": "12.6 Storey Drift ..."}
    is1893 = {"source": "IS_1893_Part_1_2016", "section": "7.11.1.1", "text": "7.11.1.1 Storey drift ... 0.004 times ..."}
    assert revise._first_real_hit(_res(is800), "IS1893") is None          # the ladder's any-document rung
    assert revise._first_real_hit(_res(is800, is1893), "IS1893") is is1893
    assert revise._first_real_hit(_res(is800), "IS800") is is800


def test_the_citation_carries_the_document_clause_and_page():
    assert revise._cite({"section": "7.11.1.1", "page": 22}, "IS1893") == "[IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 22]"
    assert revise._cite({"section": "", "page": None}, "IS800") == "[IS 800:2007]"


# --- what it writes back ------------------------------------------------------------------------
def test_grounding_is_recorded_but_verified_is_never_flipped(tmp_path):
    (tmp_path / "pushover").mkdir()
    prm = tmp_path / "pushover" / "hinge_params_used.json"
    prm.write_text(json.dumps({"verified": False, "source": "placeholder -- from memory",
                               "beam_flexure": {"basis": "x"}}), encoding="utf-8")
    ev = {"asked": "2026-09-26T10:00:00",
          "groups": {"beam_flexure": {"grounded": False, "status": "modelling assumption", "note": revise.HINGE_NOTE}},
          "clauses": {"7.11.1.1": {"grounded": True, "citation": "[IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 22]"}}}
    out = revise.annotate_params(str(tmp_path), ev, log=lambda *a: None)
    got = json.loads(prm.read_text(encoding="utf-8"))
    # the record carries a fingerprint of the modelling parameters, so the analysis run copying a plain params
    # file back over this one does not lose the citation -- and a DIFFERENT parameter set cannot inherit it
    from snl import grounding as _G
    assert out["path"] == str(prm) and out["fingerprint"] == _G.fingerprint(got)
    assert got["verified"] is False, "retrieving a clause is not reconciling the numbers"
    assert got["grounding"]["clauses"]["7.11.1.1"] == "[IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 22]"
    assert got["grounding"]["groups"] == {}                                   # nothing grounds a backbone on this fork
    assert got["grounding"]["modelling_assumptions"]["groups"] == ["beam_flexure"]
    assert got["source"] == "placeholder -- from memory"                     # no citation to claim for the backbone
    assert got["beam_flexure"] == {"basis": "x"}, "nothing else in the file is touched"


def test_no_params_file_is_reported_not_crashed(tmp_path):
    msgs = []
    assert revise.annotate_params(str(tmp_path), {"groups": {}}, log=msgs.append) is None
    assert any("hinge_params_used.json" in m for m in msgs)


def test_the_groups_search_nothing_and_the_clauses_are_is_only():
    for gid, what, words, tries in revise.GROUPS:
        assert words and all(w.islower() for w in words), gid
        assert tries == [], "India: no IS hinge table to search (D3); a foreign table is never cited"
    assert "modelling assumption" in revise.HINGE_NOTE and "never an acceptance criterion" in revise.HINGE_NOTE
    for cid, doc_key, query in revise.CLAUSES:
        assert doc_key in revise.rag.DOCUMENTS and doc_key.startswith("IS")
    job = india_nl_job.make(outputs=False)
    assert revise.system_clauses(job) == [("12.8.1", "IS800", "joint rotation 0.04 rad")]      # SCBF: IS 800 12.8.1


def test_without_a_standards_server_the_groups_are_still_labelled(monkeypatch):
    monkeypatch.delenv("RAG_API_URL", raising=False)
    ev = revise.probe(log=lambda *a: None)
    assert "engineering_rag_india" in ev["note"] and ev["clauses"] == {}


def test_revise_patches_the_india_reports_in_place_and_records_the_state(monkeypatch):
    """The whole step on a finished India job, against a fake IS corpus: the pushover report's banner is
    replaced by the grounded block, the packages carry the state, no number moves, `verified` stays false."""
    from test_review import FakeRAG, _Server, _rag_env
    from snl import grounding as G, rag
    job = india_nl_job.make()
    open(os.path.join(job, "review.md"), "w", encoding="utf-8").write("# review\n")
    before = open(os.path.join(job, "pushover", "pushover_report.html"), encoding="utf-8").read()
    R = _Server(FakeRAG)
    try:
        _rag_env(R)
        r = revise.run(job, log=lambda *a: None)
    finally:
        R.close(); os.environ.pop("RAG_API_URL", None); rag._status_cache = None
    ev = json.load(open(r["evidence"], encoding="utf-8"))
    assert ev["clauses"]["7.11.1.1"]["grounded"] and ev["params"]["fingerprint"]
    assert all(g["status"] == "modelling assumption" for g in ev["groups"].values())
    html = open(os.path.join(job, "pushover", "pushover_report.html"), encoding="utf-8").read()
    assert html != before and 'data-provenance="grounded"' in html and "UNVERIFIED" not in html and "7.11.1.1" in html
    pk = json.load(open(os.path.join(job, "pushover", "pushover_package.json"), encoding="utf-8"))
    assert pk["params_state"] == G.GROUNDED and "7.11.1.1" in pk["params_clauses"]
    lv = json.load(open(os.path.join(job, "nlrha", "MCE", "nlrha_package.json"), encoding="utf-8"))
    assert lv["params_state"] == G.GROUNDED
    prm = json.load(open(os.path.join(job, "pushover", "hinge_params_used.json"), encoding="utf-8"))
    assert prm["verified"] is False and prm["beam_flexure"] == json.load(open(os.path.join(ROOT, "pushover", "hinge_params.json"), encoding="utf-8"))["beam_flexure"]
