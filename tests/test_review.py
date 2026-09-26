"""The Review step against a fake OpenAI-compatible server and a fake standards server (stdlib only).

The fake model streams reasoning, one tool call (a standards search), then the review text; the test reads the
JSON event lines the step prints -- the same lines the Steltic hub relays -- and the files it writes.
"""
import io, json, os, shutil, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from snl import llm, rag, review  # noqa: E402
import india_nl_job  # noqa: E402

STATEMENT = "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information."


def _job():
    """A finished India job (IN_Ex1 package + synthetic outputs in the India package shapes)."""
    return india_nl_job.make()


class _Server:
    def __init__(self, handler):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


def _sse(w, obj):
    w.write(("data: " + json.dumps(obj) + "\n\n").encode("utf-8")); w.flush()


class FakeLLM(BaseHTTPRequestHandler):
    """Turn 1: reasoning + a tool call. Turn 2 (after the tool result): the review, with an inline <think> span."""
    calls = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        FakeLLM.calls.append(body)
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        w = self.wfile
        has_tool_result = any(m.get("role") == "tool" for m in body["messages"])
        if not has_tool_result:
            _sse(w, {"choices": [{"delta": {"reasoning": "The MCE mean drift is 0.92% of h; the linear limit "}}]})
            _sse(w, {"choices": [{"delta": {"reasoning_content": "is 0.004 h; look up 7.11.1.1."}}]})
            _sse(w, {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "search_engineering_standards", "arguments": '{"query": "storey drift'}}]}}]})
            _sse(w, {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ' 0.004 times the storey height", "document": "IS1893", "clause": "7.11.1.1"}'}}]}}]})
            _sse(w, {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 1200, "completion_tokens": 40}})
        else:
            tool_msg = next(m for m in body["messages"] if m.get("role") == "tool")
            assert "7.11.1.1" in tool_msg["content"] and "0.004 times" in tool_msg["content"], tool_msg["content"]
            _sse(w, {"choices": [{"delta": {"content": "<think>cite the passage</think>## 1. Summary\n\nIS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information. MCE mean drift 0.92% of h; 0.004 h is the linear limit "}}]})
            _sse(w, {"choices": [{"delta": {"content": "[IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 22].\n\n## 7. What to change, and why\n\nNothing is required.\n"}}]})
            _sse(w, {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1900, "completion_tokens": 60}})
        w.write(b"data: [DONE]\n\n"); w.flush()


IS1893, IS800, IS18168 = "IS_1893_Part_1_2016", "IS_800_2007", "IS_18168_2023"
COLL = {"engineering_standards_IS1893": IS1893, "engineering_standards_IS800": IS800, "engineering_standards_IS18168": IS18168,
        "engineering_standards_IS2062": "IS_2062_Part_1_2025"}


class FakeRAG(BaseHTTPRequestHandler):
    """The IS corpus bridge (engineering_rag_india rag_server) as the Review sees it: /healthz names the documents the
    corpus holds (`docs`), a query for one that is absent answers the server's own "not in the corpus" note, a query
    with no document searches everything that is present."""
    queries = []
    docs = [IS1893, IS800, IS18168]

    def log_message(self, *a):
        pass

    def do_GET(self):
        out = json.dumps({"ok": True, "spec_index": True, "indexed_docs": FakeRAG.docs}).encode("utf-8")
        self.send_response(200 if self.path.endswith("/healthz") else 404); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        FakeRAG.queries.append(body)
        coll = body.get("collection") or ""
        stem = COLL.get(coll, coll)
        hits, note = [], ""
        q = body.get("query") or ""
        if stem and stem not in FakeRAG.docs:
            note = "%s is not in the corpus on this PC -- install or update the IS corpus module and rebuild the index" % stem
        elif (body.get("clause") == "7.11.1.1" or "drift" in q) and (not stem or stem == IS1893) and IS1893 in FakeRAG.docs:
            hits = [{"text": "7.11.1.1 Storey drift in any storey shall not exceed 0.004 times the storey height, under the action of design base of shear VB.",
                     "doc": IS1893, "section_id": "7.11.1.1", "title": "Storey Drift", "printed_label": "22", "score": 12.5, "authoritative": True}]
        elif "joint rotation" in q and (not stem or stem == IS800) and not body.get("clause"):
            hits = [{"text": "12.8.1 ... should be shown to withstand inelastic deformation corresponding to a joint rotation of at least 0.04 radians without degradation ...",
                     "doc": IS800, "section_id": "12.8.1", "title": "Special Concentrically Braced Frames", "printed_label": "95", "score": 9.1, "authoritative": True}]
        elif "drift" in q and not stem and IS1893 not in FakeRAG.docs:
            hits = [{"text": "12.6 Storey Drift ... the storey drift ... IS 1893 (Part 1) ...", "doc": IS800, "section_id": "12.6", "title": "Storey Drift",
                     "printed_label": "94", "score": 4.0, "authoritative": True}]
        out = {"results": hits, "collection": coll, "count": len(hits), "matched": "exact_section" if hits else ""}
        if note:
            out["note"] = note
        out = json.dumps(out).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers()
        self.wfile.write(out)


def _env(llm_url, rag_url, model="fake-model"):
    env = dict(os.environ)
    env.update({"STELTIC_LLM_BASE_URL": llm_url, "STELTIC_LLM_API_KEY": "sk-test", "STELTIC_LLM_MODEL": model, "RAG_API_URL": rag_url})
    return env


def test_gather_reads_the_run_without_inventing():
    ev = review.gather(_job())
    assert ev["job"] == "IN_Ex1_SCBF" and ev["files"]["snl_summary.json"] and ev["files"]["nlrha/nlrha_package.json"]
    assert ev["statement"] == STATEMENT and ev["nlrha"]["verdict"] is None and ev["summary"]["verdict"] is None
    assert set(ev["nlrha"]["levels"]) == {"DBE", "MCE"}
    mce = ev["nlrha"]["levels"]["MCE"]
    assert len(mce["records"]) == 7 and mce["story"][0]["mean_X_pct"] == 0.6 and mce["max_mean_drift_pct"] == 0.92
    assert mce["reference_rotation"]["refs"][0]["clause"] == "IS 800:2007 12.8.1"          # IS 800 Section 12, reference only
    assert set(ev["pushover"]["directions"]) == {"X", "Y"} and ev["pushover"]["directions"]["X"]["capacity"]["Vmax_over_VB"] == 3.96
    assert ev["pushover"]["params_verified"] is False
    assert ev["ddm"]["b12_check"]["ok"] and any(r["label"] == "1.2DL+1.2LL+1.2EL_X" for r in ev["ddm"]["runs"])
    assert ev["design"]["seismic"]["Z"] == 0.24 and ev["design"]["seismic"]["zone"] == "IV" and ev["design"]["worst_members"][0]["DC"] <= 1.0
    assert ev["complete_gate"]["disclosures"][0]["found"] is False
    assert len(json.dumps(ev, default=str)) < 120_000          # bounded: the model's context, not the run folder
    # no US design basis in what the model is handed (D3), and no verdict to repeat (D7)
    txt = json.dumps(ev, default=str)
    assert "ACCEPTABLE" not in txt and "risk_category" not in txt


def test_review_streams_events_grounds_a_clause_and_writes_the_files():
    FakeLLM.calls.clear(); FakeRAG.queries.clear()
    L, R = _Server(FakeLLM), _Server(FakeRAG)
    job = _job()
    try:
        for k, v in _env(L.url, R.url).items():
            os.environ[k] = v
        buf = io.StringIO()
        r = review.run(job, focus="is the MCE drift a concern?", emit=review.Emitter(buf), max_searches=4)
        assert r["ok"] and len(r["searches"]) == 1
        lines = buf.getvalue().splitlines()
        events = [json.loads(l) for l in lines if l.startswith("{")]
        types = [e["type"] for e in events]
        assert types[:2] == ["status", "milestone"]
        assert "reasoning" in types and "token" in types and "tool" in types and "tool_result" in types and "usage" in types
        # reasoning arrives from the separate delta field AND from the inline <think> span; neither lands in the review
        reasoning = "".join(e["text"] for e in events if e["type"] == "reasoning")
        assert "look up 7.11.1.1" in reasoning and "cite the passage" in reasoning
        tokens = "".join(e["text"] for e in events if e["type"] == "token")
        assert "<think>" not in tokens and "## 1. Summary" in tokens
        tool = next(e for e in events if e["type"] == "tool")
        assert tool["name"] == "search_engineering_standards" and "7.11.1.1" in tool["title"] and tool["step"] == 1
        assert next(e for e in events if e["type"] == "tool_result")["summary"].startswith("1 passage")
        assert FakeRAG.queries[0]["collection"] == "engineering_standards_IS1893" and FakeRAG.queries[0]["clause"] == "7.11.1.1"
        corpus = next(e for e in events if e["type"] == "milestone" and e["text"].startswith("standards corpus"))
        assert "IS 1893 (Part 1):2016 (IS_1893_Part_1_2016)" in corpus["text"] and "ABSENT: IS 1893" not in corpus["text"]
        assert "DOCUMENTS IN THE CORPUS -- present: IS 1893 (Part 1):2016 (IS_1893_Part_1_2016)" in FakeLLM.calls[0]["messages"][0]["content"]
        assert "How to search" in FakeLLM.calls[0]["messages"][0]["content"]
        usage = [e for e in events if e["type"] == "usage"]
        assert usage[-1]["cum_in"] == 3100 and usage[-1]["cum_out"] == 100
        # the evidence went to the model, with the focus
        user = FakeLLM.calls[0]["messages"][1]["content"]
        assert "EVIDENCE" in user and '"max_mean_drift_pct": 0.92' in user and "is the MCE drift a concern?" in user
        assert FakeLLM.calls[0]["tools"][0]["function"]["name"] == "search_engineering_standards"
        sysmsg = FakeLLM.calls[0]["messages"][0]["content"]
        assert STATEMENT in sysmsg and "no foreign design basis" in sysmsg
        docs = FakeLLM.calls[0]["tools"][0]["function"]["parameters"]["properties"]["document"]["enum"]
        assert "IS1893" in docs and "IS800" in docs and "IS18168" in docs and not any(d.startswith(("ASCE", "A3")) for d in docs)
        # every plain line is a log line, every event line is exactly one JSON object
        for l in lines:
            if l.startswith("{"):
                json.loads(l)
        md = open(os.path.join(job, "review.md"), encoding="utf-8").read()
        assert "[IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 22]" in md and "<think>" not in md
        h = open(os.path.join(job, "review.html"), encoding="utf-8").read()
        assert "<h2>1. Summary</h2>" in h and "fake-model" in h and "1 standards searches" in h and STATEMENT in h
        tr = json.load(open(os.path.join(job, "review_transcript.json"), encoding="utf-8"))
        assert tr["searches"][0]["passages"][0].startswith("7.11.1.1 Storey drift") and tr["evidence"]["job"] == "IN_Ex1_SCBF"
    finally:
        L.close(); R.close()
        for k in ("STELTIC_LLM_BASE_URL", "STELTIC_LLM_API_KEY", "STELTIC_LLM_MODEL", "RAG_API_URL"):
            os.environ.pop(k, None)


def test_mock_model_writes_the_review_offline_and_still_searches():
    FakeRAG.queries.clear()
    R = _Server(FakeRAG)
    job = _job()
    try:
        os.environ.update({"STELTIC_LLM_MODEL": "MOCK", "RAG_API_URL": R.url})
        os.environ.pop("STELTIC_LLM_BASE_URL", None)
        buf = io.StringIO()
        r = review.run(job, emit=review.Emitter(buf))
        # three searches: 7.11.1.1 hits as asked; 7.7.4 climbs the whole ladder (4 rungs) and misses; the IS 800 clause
        # misses with its clause filter and is answered with the filter dropped
        assert r["ok"] and len(r["searches"]) == 3 and len(FakeRAG.queries) == 7
        assert [s["via"].split(" (")[0] for s in r["searches"]] == ["as-asked", "exhausted", "no-filter"] and all(s["counted"] for s in r["searches"])
        md = r["review_md"]
        assert "model MOCK" in md and STATEMENT in md and "0.920%" in md and "0.004 h" in md
        assert "ACCEPTABLE" not in md and "PASS" not in md.upper().replace("PASSAGE", "")   # no verdict (D7)
        assert "[IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 22]" in md          # found in the corpus
        assert "cl. 7.7.4] (UNVERIFIED)" in md                             # the fake corpus has no passage for it
        assert "[IS 800:2007 cl. 12.8.1, p. 95]" in md and "reference only" in md
        assert {q["collection"] for q in FakeRAG.queries} == {"engineering_standards_IS1893", "engineering_standards_IS800", ""}
        assert os.path.exists(os.path.join(job, "review.html"))
        events = [json.loads(l) for l in buf.getvalue().splitlines() if l.startswith("{")]
        assert [e["type"] for e in events if e["type"] == "tool"] == ["tool"] * 3
    finally:
        R.close()
        for k in ("STELTIC_LLM_MODEL", "RAG_API_URL"):
            os.environ.pop(k, None)


def _rag_env(R):
    os.environ["RAG_API_URL"] = R.url + "/query"
    rag._status_cache = None


def test_corpus_status_names_what_is_present_and_absent():
    FakeRAG.docs = [IS1893, IS800, IS18168, "IS_2062_P1_2025", "IS_1161_2014"]
    R = _Server(FakeRAG)
    try:
        _rag_env(R)
        st = rag.status(force=True)
        assert st["ok"] and st["known"] and st["spec_index"] is True
        cm = rag.corpus_map(st)
        assert cm["present"] == {"IS1893": IS1893, "IS800": IS800, "IS18168": IS18168, "IS2062": "IS_2062_P1_2025"}   # a stem variant still counts
        assert cm["absent"] == ["IS808", "IS875_P1", "IS875_P2"] and cm["other"] == ["IS_1161_2014"]
        line = rag.describe_corpus(cm)
        assert "IS 2062 (Part 1):2025 (IS_2062_P1_2025)" in line and "ABSENT: IS 808:2021 (stem IS_808_2021)" in line and "IS_1161_2014" in line
        assert "engineering_rag_india" in line
        assert rag.resolve("engineering_standards_IS18168") == "IS18168" and rag.resolve("is-800") == "IS800" and rag.resolve("IS875_P1") == "IS875_P1"
        assert rag.resolve("IS_1893_Part_1_2016") == "IS1893" and rag.resolve("nope") is None
        assert rag.resolve("ASCE7") is None and rag.resolve("A342") is None                   # no foreign design basis (D3)
    finally:
        R.close(); FakeRAG.docs = [IS1893, IS800, IS18168]; os.environ.pop("RAG_API_URL", None); rag._status_cache = None


def test_a_document_the_corpus_lacks_is_a_gap_not_a_miss_and_costs_no_budget():
    FakeRAG.docs = [IS800, IS18168]                                # a PC whose IS corpus has no IS 1893
    FakeRAG.queries.clear()
    R = _Server(FakeRAG)
    try:
        _rag_env(R)
        res = rag.search("storey drift 0.004 times the storey height", "IS1893", clause="7.11.1.1")
        assert res["ok"] and res["counted"] is False and res["missing_document"] == "IS1893"
        assert "CORPUS GAP" in res["note"] and "stem IS_1893_Part_1_2016" in res["note"] and "Present: IS800 (IS_800_2007), IS18168 (IS_18168_2023)" in res["note"]
        assert "Do not search IS1893 again" in res["note"]
        # one wide search across the documents that ARE here, never the absent document itself
        assert [q["collection"] for q in FakeRAG.queries] == [""] and res["via"] == "any-document"
        assert res["results"][0]["source"] == IS800 and "from IS_800_2007" in res["note"]
        txt = rag.render(res)
        assert txt.startswith("(answered by: any-document)") and "CORPUS GAP" in txt
        # the review: the model is told, and the budget is not spent on the gap
        FakeRAG.queries.clear()
        job = _job()
        os.environ["STELTIC_LLM_MODEL"] = "MOCK"
        buf = io.StringIO()
        r = review.run(job, emit=review.Emitter(buf), max_searches=1)
        gaps = [s for s in r["searches"] if s["missing_document"] == "IS1893"]
        assert r["ok"] and len(r["searches"]) == 3 and len(gaps) == 2 and all(s["counted"] is False for s in gaps)
        assert all("budget" not in (s["note"] or "") for s in r["searches"])   # two uncounted calls + one counted, budget of one
        events = [json.loads(l) for l in buf.getvalue().splitlines() if l.startswith("{")]
        corpus = next(e for e in events if e["type"] == "milestone" and e["text"].startswith("standards corpus"))
        assert "ABSENT: IS 1893 (Part 1):2016 (stem IS_1893_Part_1_2016)" in corpus["text"] and "present: IS 800:2007 (IS_800_2007)" in corpus["text"]
        assert any("absent on this PC" in l and l.startswith("standards corpus: IS 1893") for l in buf.getvalue().splitlines() if not l.startswith("{"))
        results = [e for e in events if e["type"] == "tool_result"]
        assert sum("IS1893 is not in the corpus (not counted)" in e["summary"] for e in results) == 2
        assert "[IS 1893 (Part 1):2016 cl. 7.11.1.1] (UNVERIFIED)" in r["review_md"]    # IS 800 text is not passed off as IS 1893
    finally:
        R.close(); FakeRAG.docs = [IS1893, IS800, IS18168]
        for k in ("RAG_API_URL", "STELTIC_LLM_MODEL"):
            os.environ.pop(k, None)
        rag._status_cache = None


def test_a_miss_climbs_the_ladder_before_it_is_a_miss():
    FakeRAG.queries.clear()
    R = _Server(FakeRAG)
    try:
        _rag_env(R)
        # rung 1 (clause 9.9.9 on IS 800) misses; rung 2 without the filter finds the joint-rotation passage
        res = rag.search("joint rotation", "IS800", clause="9.9.9")
        assert res["results"] and res["counted"] and res["via"].startswith("no-filter")
        assert [(q["collection"], q.get("clause", "")) for q in FakeRAG.queries] == [("engineering_standards_IS800", "9.9.9"), ("engineering_standards_IS800", "")]
        assert rag.render(res).startswith("(answered by: no-filter")
        # asked of the wrong document: rung 5 answers from the one that holds it, and says so
        FakeRAG.queries.clear()
        res = rag.search("joint rotation", "IS18168")
        assert res["results"] and res["via"] == "any-document" and "answered by IS_800_2007, NOT by IS18168" in res["note"]
        assert [q["collection"] for q in FakeRAG.queries] == ["engineering_standards_IS18168", ""]
        # nothing anywhere: the ladder is reported, the model is told what to do
        FakeRAG.queries.clear()
        res = rag.search("gremlins", "IS800", clause="1.2.3")
        assert res["results"] == [] and res["via"] == "exhausted" and "NOT FOUND after 4 attempts" in res["note"]
        assert [a["how"] for a in res["attempts"]] == ["as-asked", "no-filter", "exact-id 1.2.3", "any-document"]
        assert rag.render(res).startswith("NO PASSAGES. (tried: exhausted)")
    finally:
        R.close(); os.environ.pop("RAG_API_URL", None); rag._status_cache = None


def test_no_standards_server_is_said_not_hidden():
    job = _job()
    os.environ.update({"STELTIC_LLM_MODEL": "MOCK"}); os.environ.pop("RAG_API_URL", None)
    try:
        buf = io.StringIO()
        r = review.run(job, emit=review.Emitter(buf))
        assert r["ok"] and r["searches"] == []
        events = [json.loads(l) for l in buf.getvalue().splitlines() if l.startswith("{")]
        assert "no standards server" in events[1]["text"]
        assert r["review_md"].count("(UNVERIFIED)") >= 3
        res = rag.search("anything", "IS1893")
        assert res["ok"] is False and "RAG_API_URL is empty" in res["note"] and rag.render(res).startswith("NO PASSAGES")
        assert rag.search("x", "NOT-A-DOC")["ok"] is False
        assert rag.search("x", "ASCE7")["ok"] is False                     # no foreign design basis on this fork (D3)
    finally:
        os.environ.pop("STELTIC_LLM_MODEL", None)


def test_search_budget_is_enforced_and_told_to_the_model():
    FakeRAG.queries.clear()
    R = _Server(FakeRAG)
    job = _job()
    try:
        os.environ.update({"STELTIC_LLM_MODEL": "MOCK", "RAG_API_URL": R.url})
        r = review.run(job, emit=review.Emitter(io.StringIO()), max_searches=1)
        assert r["ok"] and len(r["searches"]) == 3 and len(FakeRAG.queries) == 1
        assert "budget" in (r["searches"][1]["note"] or "")
    finally:
        R.close()
        for k in ("STELTIC_LLM_MODEL", "RAG_API_URL"):
            os.environ.pop(k, None)


def test_an_empty_job_is_refused_with_a_reason():
    tmp = tempfile.mkdtemp()
    os.environ.update({"STELTIC_LLM_MODEL": "MOCK"})
    try:
        buf = io.StringIO()
        r = review.run(tmp, emit=review.Emitter(buf))
        assert not r["ok"]
        events = [json.loads(l) for l in buf.getvalue().splitlines() if l.startswith("{")]
        assert events[-1]["type"] == "error" and "run the analyses first" in events[-1]["text"]
    finally:
        os.environ.pop("STELTIC_LLM_MODEL", None)


def test_cli_entry_point_runs_the_review():
    job = _job()
    env = dict(os.environ); env.update({"STELTIC_LLM_MODEL": "MOCK"}); env.pop("RAG_API_URL", None)
    p = subprocess.run([sys.executable, "-m", "snl", "review", job, "--focus", "cost", "--no-standards"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stdout + p.stderr
    lines = p.stdout.splitlines()
    assert any(l.startswith('{"type": "milestone"') for l in lines) and any(l.startswith(">> review:") for l in lines)
    assert os.path.exists(os.path.join(job, "review.md")) and "Focus asked:** cost" in open(os.path.join(job, "review.md")).read()


def test_llm_client_splits_inline_think_spans_across_deltas():
    sp = llm._ThinkSplitter()
    out = sp.feed("hello <thi"); out += sp.feed("nk>secret</think> world")
    assert out == [("token", "hello "), ("reasoning", "secret"), ("token", " world")]
    assert sp.flush() is None
    c = llm.connection()
    assert c["mock"] is True                     # nothing set -> offline path, never a socket
