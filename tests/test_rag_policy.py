"""The retrieval policy as the tool applies it (India: the IS corpus bridge's own fields).

HR Steel (steltic_india) puts every standards call into policy form before it goes on the wire: ONE IS
document, an EXACT id when the provision is known, full text only to NAVIGATE to an id. These tests pin
the policy, not the ladder -- and that the policy strips IS designations, not US ones, from a query.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from snl import rag, review                 # noqa: E402


def test_an_exact_type_is_sent_as_the_id_alone():
    p = rag.policy_plan("7.11.1.1", qtype="exact_section")
    assert p["exact"] == [("exact_section", "7.11.1.1")] and not p["nav"]
    p = rag.policy_plan("Table 3", qtype="exact_table")
    assert p["exact"] == [("exact_table", "Table 3")] and "exact_table Table 3" in p["label"]


def test_an_id_buried_in_a_sentence_is_asked_for_as_an_id_first():
    """The failure this exists to prevent: a nine-word query at a corpus indexed by id."""
    p = rag.policy_plan("IS 1893 (Part 1):2016 clause 7.11.1.1 storey drift 0.004 times the storey height")
    assert ("id", "7.11.1.1") in p["exact"]                 # the id goes first...
    assert "storey drift" in p["nav"]                       # ...and the words are kept to navigate with
    assert "1893" not in p["nav"] and "2016" not in p["nav"]   # the IS designation is not a search term
    assert p["label"].startswith("exact-id 7.11.1.1")
    p = rag.policy_plan("IS800:2007 12.8.1 joint rotation of at least 0.04 radians")
    assert p["exact"][0] == ("id", "12.8.1") and "800" not in p["nav"]


def test_a_bare_id_typed_into_query_is_not_full_text_searched():
    for q in ("7.11.1.1", "6.4.2", "12.11.1", "Table 3", "Table 8"):
        p = rag.policy_plan(q)
        assert p["exact"] and p["exact"][0][1] == q and not p["nav"], q


def test_a_clause_given_separately_is_still_asked_for_first():
    p = rag.policy_plan("time history method", clause="7.7.4")
    assert p["exact"][0] == ("id", "7.7.4")
    assert p["nav"] == "time history method"
    # and when the model chose navigation itself, an id it also gave is not thrown away
    p = rag.policy_plan("storey drift", clause="7.11.1.1", qtype="fts")
    assert p["exact"] == [("id", "7.11.1.1")] and p["nav"] == "storey drift"


def test_prose_with_no_id_navigates_and_asks_for_nothing_exact():
    p = rag.policy_plan("damping percent of critical damping")
    assert p["exact"] == [] and p["nav"].startswith("damping")
    assert p["label"].startswith("fts")


def test_the_same_id_is_not_asked_for_twice():
    p = rag.policy_plan("clause 7.11.1.1 and 7.11.1.1 again", clause="7.11.1.1")
    assert [i for _k, i in p["exact"]] == ["7.11.1.1"]


def test_the_review_tool_offers_the_policys_own_fields():
    """The model cannot follow the policy through a tool that has nowhere to put an exact type."""
    props = review.TOOLS[0]["function"]["parameters"]["properties"]
    for k in ("type", "document", "query", "clause", "chapter", "purpose", "want_commentary", "context_neighbors"):
        assert k in props, k
    assert set(props["type"]["enum"]) >= {"exact_section", "exact_table", "fts"}
    assert props["top_k"]["maximum"] == 20                  # the server's cap, not an arbitrary 8
    assert "RETRIEVAL POLICY" in review.SYSTEM and "engineering_rag_india" in review.SYSTEM
    assert "ONE document per call" in review.SYSTEM
    assert '"IS1893" | "IS800" | "IS18168"' in review.SYSTEM and "no ASCE / AISC document is searched" in review.SYSTEM


def test_the_review_is_not_capped_by_default():
    """`--max-searches 8` was a cost control that read as a quality target. Unlimited is the default."""
    import inspect
    assert inspect.signature(review.run).parameters["max_searches"].default == 0
    assert "no cap" in _help_for("--max-searches")
    assert "Search as often as the review needs" in review.SYSTEM


def _help_for(flag):
    import argparse, contextlib, io
    from snl import cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.suppress(SystemExit):
        cli.main(["review", "--help"])
    return buf.getvalue()


def test_an_exact_hit_is_passed_on_whole(monkeypatch):
    """IS 2062 (Part 1):2025 Table 3 as the India corpus converted it: padded Markdown cells, the E 250 row 7,500
    characters in, the table 57,000 characters in all. The old 2,500-character cap on every hit cut the rows off
    and Collect would report them absent. An exact lookup is one provision: it goes through whole. Navigation
    snippets stay short."""
    import json, re
    fx = json.load(open(os.path.join(ROOT, "tests", "fixtures", "collect_tables_india.json"), encoding="utf-8"))
    table = fx["IS2062:Table 3"]
    row = next(l for l in table.split("\n") if re.match(r"\|\s*ii\)\s*\|\s*E 250\s*\|\s*A\s*\|", l))
    assert table.index(row) > 2500
    sent = []

    def fake_post(payload, timeout):
        sent.append(payload)
        return {"results": [{"text": table, "doc": "IS_2062_Part_1_2025", "section_id": "Table 3", "printed_label": "9"}]}, None

    monkeypatch.setattr(rag, "_post", fake_post)
    monkeypatch.setattr(rag, "url", lambda: "http://x/query")
    monkeypatch.setattr(rag, "status", lambda: {"known": True, "indexed_docs": ["IS_2062_Part_1_2025"]})
    res = rag.search("Table 3", "IS2062", qtype="exact_table", top_k=8, neighbors=1)
    assert res["ok"] and res["results"], res
    text = res["results"][0]["text"]
    assert row in text and "E 650" in text and "not shown" not in text
    assert sent[0].get("type") == "exact_table" and sent[0]["collection"] == "engineering_standards_IS2062"
    # a navigation snippet is capped and says so
    long_snippet = "x" * (rag.FTS_MAX_CHARS + 500)
    monkeypatch.setattr(rag, "_post", lambda payload, timeout: ({"results": [{"text": long_snippet, "doc": "IS_2062_Part_1_2025"}]}, None))
    res = rag.search("tensile strength yield stress", "IS2062", qtype="fts")
    t = res["results"][0]["text"]
    assert len(t) < len(long_snippet) and t.endswith("more characters not shown]")
    assert rag.EXACT_MAX_CHARS >= 57071                     # the whole IS 2062 Table 3 as the corpus returns it
