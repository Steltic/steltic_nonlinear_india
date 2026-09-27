"""`snl collect` (India) -- the IS specification values are read out of the IS corpus BEFORE the analyses run.

India has no foreign design basis and no NL acceptance criteria (D3 / D7): what the run takes from the
standards is IS 2062 fy / fu, IS 18168 Ry / Ru (reference), the IS 800 Section 12 joint-rotation capacity
(reference only), IS 1893 Z / I / Sa/g and damping. The hinge backbones are modelling assumptions and are
never collected. These tests pin the contract the hub's Run analyses gate depends on, and the machinery kept
from the US third cut: deterministic retrieval, rows decided from the building, a model that only
transcribes, quote / value checks, the transcript, the gate file.
"""
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snl import collect, rag                        # noqa: E402
from test_review import FakeRAG, _Server, _rag_env  # noqa: E402
import india_nl_job                                 # noqa: E402

STATEMENT = "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information."
ALL = ["material", "overstrength", "deformation_capacity", "spectrum", "damping"]


def _job(tmp_path=None):
    return india_nl_job.make(outputs=False)          # a fresh project: the IN_Ex1 package, nothing collected yet


def _events(buf):
    return [json.loads(l) for l in buf.getvalue().splitlines() if l.startswith("{")]


# ---------------------------------------------------------------- what the building needs
def test_gather_reads_the_building_and_nothing_else():
    f = collect.gather(_job())
    assert f["system"].startswith("SCBF") and f["grade"] == "E250" and "calc_package" in f["grade_basis"]
    assert f["zone"] == "IV" and f["Z"] == 0.24 and f["I"] == 1.0 and f["soil"] == "II"      # from seismic_calc / load_plan
    assert f["reference_rotation"]["refs"][0]["clause"] == "IS 800:2007 12.8.1"
    assert f["needed"] == ALL                                                                 # no hinge group is collected
    assert not set(f["needed"]) & set(collect.HINGE_GROUPS)


def test_the_groups_follow_the_building():
    f = collect.gather(_job())
    from pushover import india_materials as IM
    # a grade IS 18168 Table 1 does not list has no overstrength row to read; an unmapped system no IS 800 clause
    g = dict(f, grade="E410", reference_rotation=IM.reference_rotation("unknown"))
    assert [x for x in ALL if x not in ("overstrength", "deformation_capacity")] == ["material", "spectrum", "damping"]
    assert collect.plan_for("deformation_capacity", g) == []
    assert collect.plan_for("deformation_capacity", f) == [("IS800", "exact_section", "12.8.1", 0)]
    assert all(d.startswith("IS") for gid in ALL for d, _h, _q, _n in collect.plan_for(gid, f))   # IS documents only (D3)


# ---------------------------------------------------------------- the step, offline
def test_collect_writes_the_gate_file_the_engines_accept():
    job = _job()
    TableRAG.queries.clear()
    R = _Server(TableRAG)
    try:
        _rag_env(R)
        os.environ["STELTIC_LLM_MODEL"] = "MOCK"; os.environ.pop("STELTIC_LLM_BASE_URL", None)
        buf = io.StringIO()
        r = collect.run(job, emit=collect.Emitter(buf))
        assert r["ok"] and r["verified"] and r["missing"] == []
        assert os.path.basename(r["path"]) == collect.OUT_NAME
        d = json.load(open(r["path"], encoding="utf-8"))
        assert d["spec_values_collected"] is True and d["verified"] is False       # backbones: modelling assumptions
        for g in ALL:
            src = d["india_spec"][g]["source"]
            assert src.startswith("MOCK") and ("Table" in src or "cl." in src) and "p." in src, (g, src)
        for hg in collect.HINGE_GROUPS:
            assert "modelling assumption" in d[hg]["india_status"] and "not an acceptance criterion" in d[hg]["india_status"]
        assert d["material"]["Fy_ksi"] == pytest.approx(250 * 0.1450377, abs=1e-3) and d["material"]["Ry_expected"] == 1.0
        assert d["india_spec"]["deformation_capacity"]["rotation_rad"] == 0.04 and "REFERENCE ONLY" in d["india_spec"]["deformation_capacity"]["use"]
        assert STATEMENT in d["_README"]
        # the untouched groups keep the repository values
        tpl = json.load(open(os.path.join(ROOT, "pushover", "hinge_params.json"), encoding="utf-8"))
        assert d["nsp"] == tpl["nsp"] and d["numerics"] == tpl["numerics"] and d["beam_flexure"]["a_over_thetay"] == tpl["beam_flexure"]["a_over_thetay"]
        # the engines load it
        from pushover import hinge_models as HM
        prm = HM.load_params(r["path"])
        assert prm["material"]["Fy_ksi"] < 50.0
        # the IS corpus was asked, as exact lookups, and nothing else
        assert {q["collection"] for q in TableRAG.queries} <= {"engineering_standards_IS2062", "engineering_standards_IS18168",
                                                              "engineering_standards_IS800", "engineering_standards_IS1893", ""}
        assert all(q.get("type") in ("exact_table", "exact_section") for q in TableRAG.queries if q.get("collection"))
        # and the paper trail exists for the design-criteria document
        assert os.path.exists(os.path.join(job, collect.EVIDENCE_NAME)) and os.path.exists(os.path.join(job, "retrieval_log.md"))
        ev = json.load(open(os.path.join(job, collect.EVIDENCE_NAME), encoding="utf-8"))
        assert ev["spec_values_collected"] and ev["needed"] == ALL and len(ev["searches"]) == 7
        types = [e["type"] for e in _events(buf)]
        assert "tool" in types and "tool_result" in types and types[-1] == "milestone"
    finally:
        R.close(); os.environ.pop("RAG_API_URL", None); os.environ.pop("STELTIC_LLM_MODEL", None); rag._status_cache = None


def test_no_standards_server_collects_nothing_and_says_so():
    job = _job()
    os.environ.pop("RAG_API_URL", None); os.environ["STELTIC_LLM_MODEL"] = "MOCK"; rag._status_cache = None
    try:
        buf = io.StringIO()
        r = collect.run(job, emit=collect.Emitter(buf))
        assert not r["ok"] and r["missing"] == ALL
        assert not os.path.exists(os.path.join(job, collect.OUT_NAME))            # the gate stays closed
        assert any(e["type"] == "error" and "RAG_API_URL" in e["text"] and "IS corpus module" in e["text"] for e in _events(buf))
    finally:
        os.environ.pop("STELTIC_LLM_MODEL", None)


def test_a_group_that_cannot_be_read_keeps_the_gate_closed(monkeypatch):
    """A system IS 800 Section 12 does not name has no clause to read, yet the group is asked for: missing."""
    job = _job()
    real = collect.gather
    monkeypatch.setattr(collect, "gather", lambda j: dict(real(j), reference_rotation={"refs": []}))
    R = _Server(TableRAG)
    try:
        _rag_env(R)
        os.environ["STELTIC_LLM_MODEL"] = "MOCK"; os.environ.pop("STELTIC_LLM_BASE_URL", None)
        r = collect.run(job, emit=collect.Emitter(io.StringIO()))
        assert not r["ok"] and r["missing"] == ["deformation_capacity"]
        assert os.path.basename(r["path"]) == collect.PARTIAL_NAME
        assert not os.path.exists(os.path.join(job, collect.OUT_NAME))
        d = json.load(open(r["path"], encoding="utf-8"))
        assert d["spec_values_collected"] is False and "deformation_capacity: MISSING" in d["source"]
    finally:
        R.close(); os.environ.pop("RAG_API_URL", None); os.environ.pop("STELTIC_LLM_MODEL", None); rag._status_cache = None


# ---------------------------------------------------------------- validation: what a model may not hand back
FACTS = collect.gather(_job())
GOOD = {
    "material": {"fu_MPa": 410.0, "fy_t16_MPa": 250.0, "fy_t40_MPa": 240.0, "fy_t100_MPa": 230.0, "fy_tgt100_MPa": 210.0,
                 "source": "IS 2062 (Part 1):2025 Table 3, p. 9"},
    "overstrength": {"Ry": 1.4, "Ru": 1.2, "source": "IS 18168:2023 Table 1, p. 7"},
    "deformation_capacity": {"rotation_rad": 0.04, "source": "IS 800:2007 cl. 12.8.1, p. 94"},
    "spectrum": {"Z": 0.24, "Sa_plateau": 2.5, "Tc_s": 0.55, "Sa_c": 1.36, "Sa_floor": 0.34, "I_row_i": 1.5, "I_row_ii": 1.2,
                 "I_row_iii": 1.0, "source": "IS 1893 (Part 1):2016 Table 3; cl. 6.4.2; Table 8, p. 11-21"},
    "damping": {"damping_percent": 5, "source": "IS 1893 (Part 1):2016 cl. 7.2.4, p. 21"},
}


def _bad(**over):
    d = json.loads(json.dumps(GOOD))
    for path, v in over.items():
        keys = path.split("."); cur = d
        for k in keys[:-1]:
            cur = cur[k]
        if v is None:
            cur.pop(keys[-1], None)
        else:
            cur[keys[-1]] = v
    return d


def test_validation_passes_the_is_values():
    ok, probs = collect.validate(GOOD, ALL, FACTS)
    assert ok, probs


@pytest.mark.parametrize("over, group, why", [
    ({"material.source": "from memory"}, "material", "source"),                        # no table id, no page
    ({"material.fy_t16_MPa": 260.0}, "material", "differs from pushover/india_materials.py"),
    ({"material.fy_t40_MPa": 255.0}, "material", "ReH must not rise"),
    ({"material.fu_MPa": 240.0}, "material", "fu <= fy"),
    ({"overstrength.Ry": 0.9}, "overstrength", "Ry outside"),
    ({"overstrength.Ry": 1.3}, "overstrength", "differs from pushover/india_materials.py IS18168_RY"),
    ({"deformation_capacity.rotation_rad": 0.2}, "deformation_capacity", "outside"),
    ({"deformation_capacity.rotation_rad": 0.02}, "deformation_capacity", "reference_rotation"),     # the OCBF value for an SCBF
    ({"spectrum.Z": 0.2}, "spectrum", "Table 3 values"),
    ({"spectrum.Z": 0.16}, "spectrum", "ZONE_FACTOR_Z[IV]"),                                          # zone III's Z for a zone IV site
    ({"spectrum.Sa_c": 1.67}, "spectrum", "c / Tc"),
    ({"spectrum.I_row_ii": None}, "spectrum", "Table 8"),
    ({"damping.damping_percent": 0}, "damping", "damping_percent"),
    ({"material": None}, "material", "group missing"),
])
def test_validation_refuses_what_it_should(over, group, why):
    ok, probs = collect.validate(_bad(**over), ALL, FACTS)
    assert not ok and any(why in p for p in probs[group]), probs


def test_the_json_the_model_returns_may_be_fenced_or_wrapped():
    assert collect._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert collect._parse_json('Here it is:\n{"a": {"b": 2}} thanks') == {"a": {"b": 2}}
    assert collect._parse_json("no json here") is None


# ---------------------------------------------------------------- the run picks the collected file up
def test_snl_run_uses_the_collected_file_by_default(monkeypatch, capsys):
    from snl import cli
    job = _job()
    open(os.path.join(job, collect.OUT_NAME), "w").write(json.dumps({"verified": False, "spec_values_collected": True}))
    seen = {}
    monkeypatch.setattr(cli, "_run", lambda cmd, log, env=None, cwd=None: (seen.setdefault("cmds", []).append(cmd), dict(returncode=0, seconds=0, log=log))[1])
    monkeypatch.setattr(cli, "_unpack", lambda p, out: job)
    import types
    a = types.SimpleNamespace(package=job, out=None, steltic_engine=None, only=["pushover"], skip=[], params=None,
                              site_class="D", tail=None, post_cap_ratio=None, parallel=1, dt=0.01, integrator="hht",
                              n_records=11, target=None, level=None, records_set=None, pulse_fraction=None, sf_bounds=None,
                              plasticity=None, member_nseg=None, no_block=True, no_criteria=True, risk_category=None,
                              project=None, engineer=None, reviewer=None, site_hazard=None)
    try:
        cli.cmd_run(a)
    except Exception:
        pass                                                        # later steps of cmd_run are not under test
    out = capsys.readouterr().out
    assert "component parameters: " + os.path.join(job, collect.OUT_NAME) in out and "(collected from the corpus)" in out
    if seen.get("cmds"):
        assert "--params" in seen["cmds"][0] and seen["cmds"][0][seen["cmds"][0].index("--params") + 1] == os.path.join(job, collect.OUT_NAME)


# ---------------------------------------------------------------- transcription, against the real converted IS cells
from http.server import BaseHTTPRequestHandler   # noqa: E402
from test_review import _sse, _env               # noqa: E402

FX = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "collect_tables_india.json"), encoding="utf-8"))
SERVED = {("engineering_standards_IS2062", "Table 3"): ("IS2062:Table 3", "IS_2062_Part_1_2025", "Table 3", "9"),
          ("engineering_standards_IS18168", "Table 1"): ("IS18168:Table 1", "IS_18168_2023", "Table 1", "7"),
          ("engineering_standards_IS800", "12.8.1"): ("IS800:12.8.1", "IS_800_2007", "12.8.1", "94"),
          ("engineering_standards_IS1893", "Table 3"): ("IS1893:Table 3", "IS_1893_Part_1_2016", "Table 3", "12"),
          ("engineering_standards_IS1893", "6.4.2"): ("IS1893:6.4.2", "IS_1893_Part_1_2016", "6.4.2", "11"),
          ("engineering_standards_IS1893", "Table 8"): ("IS1893:Table 8", "IS_1893_Part_1_2016", "Table 8", "21"),
          ("engineering_standards_IS1893", "7.2.4"): ("IS1893:7.2.4", "IS_1893_Part_1_2016", "7.2.4", "21")}


def _line(key, pat):
    import re
    return next(l for l in FX[key].split("\n") if re.search(pat, l)).strip()


class TableRAG(BaseHTTPRequestHandler):
    """The IS corpus bridge answering exact lookups with the cells exactly as its converter left them."""
    queries = []
    docs = ["IS_2062_Part_1_2025", "IS_18168_2023", "IS_800_2007", "IS_1893_Part_1_2016"]

    def log_message(self, *a):
        pass

    def do_GET(self):
        out = json.dumps({"ok": True, "spec_index": True, "indexed_docs": TableRAG.docs}).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        TableRAG.queries.append(body)
        q = (body.get("query") or "").strip() or (body.get("clause") or "").strip()
        hit = SERVED.get((body.get("collection") or "", q))
        hits = []
        if hit and body.get("type") in ("exact_table", "exact_section", "id"):
            key, doc, sec, page = hit
            hits.append({"text": FX[key], "doc": doc, "section_id": sec, "title": sec, "printed_label": page, "score": 20, "authoritative": True})
        out = json.dumps({"results": hits, "collection": body.get("collection", ""), "count": len(hits), "matched": body.get("type") if hits else ""}).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


class ScriptedLLM(BaseHTTPRequestHandler):
    """Answers each call with the next item of `script` (a dict -> JSON reply). Records every request."""
    calls = []
    script = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        ScriptedLLM.calls.append(body)
        ans = ScriptedLLM.script.pop(0) if ScriptedLLM.script else {}
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        w = self.wfile
        _sse(w, {"choices": [{"delta": {"reasoning": "copying the cells"}}]})
        _sse(w, {"choices": [{"delta": {"content": json.dumps(ans)}}]})
        _sse(w, {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 500, "completion_tokens": 80}})
        w.write(b"data: [DONE]\n\n"); w.flush()


def _q(v, quote):
    return {"value": v, "quote": quote}


E250_ROW = _line("IS18168:Table 1", r"E250 \(B0 or C\)")
GOOD_OVERSTRENGTH = {"Ry": _q(1.4, E250_ROW), "Ru": _q(1.2, E250_ROW)}
GOOD_DEFORMATION = {"rotation_rad": _q(0.04, "corresponding to a joint rotation of at least 0.04 radians")}
GOOD_SPECTRUM = {"Z": _q(0.24, _line("IS1893:Table 3", r"^\| Z \|")),
                 "Sa_plateau": _q(2.5, "| Medium stiff soil sites (Type II) | 2.5 | 0.10 s < T < 0.55 s |"),
                 "Tc_s": _q(0.55, "| Medium stiff soil sites (Type II) | 2.5 | 0.10 s < T < 0.55 s |"),
                 "Sa_c": _q(1.36, "| Medium stiff soil sites (Type II) | 1.36/T | 0.55 s < T < 4.00 s |"),
                 "Sa_floor": _q(0.34, "| Medium stiff soil sites (Type II) | 0.34 | T > 4.00 s |"),
                 "I_row_i": _q(1.5, _line("IS1893:Table 8", r"^\| i\) \|")),
                 "I_row_ii": _q(1.2, _line("IS1893:Table 8", r"^\| ii\) \|")),
                 "I_row_iii": _q(1.0, _line("IS1893:Table 8", r"^\| iii\) \|"))}
GOOD_DAMPING = {"damping_percent": _q(5, "The value of damping shall be taken as 5 percent of critical damping")}
NO_MATERIAL = ["overstrength", "deformation_capacity", "spectrum", "damping"]


def _live(script, needed=NO_MATERIAL, monkeypatch=None):
    job = _job()
    TableRAG.queries.clear(); ScriptedLLM.calls.clear(); ScriptedLLM.script = list(script)
    R = _Server(TableRAG); L = _Server(ScriptedLLM)
    old = dict(os.environ)
    os.environ.update(_env(L.url, R.url + "/query")); rag._status_cache = None
    if monkeypatch is not None:
        real = collect.gather
        monkeypatch.setattr(collect, "gather", lambda j: dict(real(j), needed=list(needed)))
    return job, R, L, old


def _done(R, L, old):
    R.close(); L.close(); os.environ.clear(); os.environ.update(old); rag._status_cache = None


def test_the_model_only_transcribes_and_every_value_is_backed_by_a_cell(monkeypatch):
    """The real converted cells of IS 18168 Table 1, IS 800 12.8.1, IS 1893 Table 3 / 6.4.2 / Table 8 / 7.2.4 and a
    model that copies them: the IS values in, no searching by the model, reasoning low. (IS 2062 Table 3: see
    test_every_is_group_is_transcribed_from_its_whole_table.)"""
    job, R, L, old = _live([GOOD_OVERSTRENGTH, GOOD_DEFORMATION, GOOD_SPECTRUM, GOOD_DAMPING], monkeypatch=monkeypatch)
    try:
        buf = io.StringIO()
        r = collect.run(job, emit=collect.Emitter(buf))
        assert r["ok"] and r["missing"] == [], r
        d = json.load(open(r["path"], encoding="utf-8"))
        s = d["india_spec"]
        assert s["overstrength"]["Ry"] == 1.4 and s["overstrength"]["Ru"] == 1.2
        assert s["deformation_capacity"]["rotation_rad"] == 0.04 and s["deformation_capacity"]["clause"] == "12.8.1"
        assert s["spectrum"]["Z"] == 0.24 and s["spectrum"]["Sa_c"] == 1.36 and s["spectrum"]["I_row_ii"] == 1.2
        assert s["damping"]["damping_percent"] == 5 and s["damping"]["damping_ratio"] == 0.05
        for g in NO_MATERIAL:
            assert ("Table" in s[g]["source"] or "cl." in s[g]["source"]) and "p." in s[g]["source"], s[g]["source"]   # built from the passages
            assert s[g]["quotes"], "the cell every value was read from travels with it"
        assert s["deformation_capacity"]["source"] == "IS 800:2007 cl. 12.8.1, p. 94"
        assert all("tools" not in c for c in ScriptedLLM.calls), "the model has no search tool to wander with"
        assert len(ScriptedLLM.calls) == 4, "one call per group"
        assert all(c.get("reasoning", {}).get("effort", "low") == "low" for c in ScriptedLLM.calls if "reasoning" in c)
        assert all(q.get("type") in ("exact_table", "exact_section") for q in TableRAG.queries)
        tr = [json.loads(l) for l in open(os.path.join(job, collect.TRANSCRIPT_NAME), encoding="utf-8")]
        assert any(t["type"] == "answer" and "copying the cells" in t["reasoning"] for t in tr)
    finally:
        _done(R, L, old)


def test_a_remembered_number_is_rejected_and_the_retry_names_it(monkeypatch):
    """A model that 'remembers' Ry = 1.1 (the AISC A992 value) against the IS 18168 E250 row: no cell holds it,
    so it is rejected, and the retry tells the model exactly which field and why."""
    bad = dict(GOOD_OVERSTRENGTH, Ry=_q(1.1, E250_ROW))
    job, R, L, old = _live([bad, GOOD_OVERSTRENGTH, GOOD_DEFORMATION, GOOD_SPECTRUM, GOOD_DAMPING], monkeypatch=monkeypatch)
    try:
        r = collect.run(job, emit=collect.Emitter(io.StringIO()))
        assert r["ok"]
        assert len(ScriptedLLM.calls) == 5, "overstrength (rejected), overstrength again, deformation, spectrum, damping"
        retry = ScriptedLLM.calls[1]["messages"][-1]["content"]
        assert "NOT ACCEPTED" in retry and "Ry: the number 11 is not in the quote" in retry
        d = json.load(open(r["path"], encoding="utf-8"))
        assert d["india_spec"]["overstrength"]["Ry"] == 1.4
    finally:
        _done(R, L, old)


def test_a_quote_that_is_not_in_the_passage_is_rejected(monkeypatch):
    invented = dict(GOOD_SPECTRUM, Z=_q(0.24, "Zone IV Z = 0.24"))
    job, R, L, old = _live([GOOD_OVERSTRENGTH, GOOD_DEFORMATION, invented, invented, invented, GOOD_DAMPING], monkeypatch=monkeypatch)
    try:
        r = collect.run(job, emit=collect.Emitter(io.StringIO()))
        assert not r["ok"] and r["missing"] == ["spectrum"]
        assert os.path.basename(r["path"]) == collect.PARTIAL_NAME and not os.path.exists(os.path.join(job, collect.OUT_NAME))
        ev = json.load(open(os.path.join(job, collect.EVIDENCE_NAME), encoding="utf-8"))
        assert any("Z: the quote does not occur in the passages" in p for p in ev["problems"]["spectrum"])
        assert len(ScriptedLLM.calls) == 6, "three attempts for the spectrum, then it is missing -- no loop"
    finally:
        _done(R, L, old)


def test_the_trace_survives_a_run_that_dies(monkeypatch):
    job, R, L, old = _live([GOOD_OVERSTRENGTH], monkeypatch=monkeypatch)
    try:
        L.close()                                                          # the provider goes away mid-run
        r = collect.run(job, emit=collect.Emitter(io.StringIO()))
        assert not r["ok"]
        tr = [json.loads(l) for l in open(os.path.join(job, collect.TRANSCRIPT_NAME), encoding="utf-8")]
        assert tr and tr[0]["type"] == "prefetch" and any(t["type"] == "prompt" for t in tr)
    finally:
        R.close(); os.environ.clear(); os.environ.update(old); rag._status_cache = None


def test_the_same_search_a_fourth_time_is_refused_without_a_round_trip(monkeypatch):
    """Three strikes: the guard is kept from the US step even though the India prefetch never repeats itself."""
    job = _job()
    FakeRAG.queries.clear()
    R = _Server(FakeRAG)
    try:
        _rag_env(R)
        os.environ["STELTIC_LLM_MODEL"] = "MOCK"
        real_prefetch = collect.prefetch

        def greedy(facts, search):
            for _ in range(4):
                search({"document": "IS1893", "type": "exact_section", "query": "7.2.4"}, raw=True)
            return real_prefetch(facts, search)
        monkeypatch.setattr(collect, "prefetch", greedy)
        r = collect.run(job, emit=collect.Emitter(io.StringIO()))
        vias = [s["via"] for s in r["searches"] if (s["args"] or {}).get("query") == "7.2.4"]
        assert len(vias) == 5 and "refused" not in vias[:3] and vias[3:] == ["refused", "refused"]   # the prefetch's own is the 5th
        assert "ABSENT" in r["searches"][3]["note"]
        posts = sum(1 for q in FakeRAG.queries if "7.2.4" in (q.get("query") or ""))
        assert posts and posts % 3 == 0, "only the first three went on the wire (each climbs the same ladder)"
    finally:
        R.close(); os.environ.pop("RAG_API_URL", None); os.environ.pop("STELTIC_LLM_MODEL", None); rag._status_cache = None


def test_rows_are_decided_from_the_building_not_by_the_model():
    from pushover import india_materials as IM
    f = collect.gather(_job())
    assert "grade E250" in collect.row_for("material", f)[1]
    assert "'E250 (B0 or C)'" in collect.row_for("overstrength", f)[1]
    assert "12.8.1" in collect.row_for("deformation_capacity", f)[1] and "REFERENCE ONLY" in collect.row_for("deformation_capacity", f)[1]
    assert "zone IV" in collect.row_for("spectrum", f)[1] and "soil type II" in collect.row_for("spectrum", f)[1]
    smf = dict(f, reference_rotation=IM.reference_rotation("SMF"))
    assert collect.plan_for("deformation_capacity", smf) == [("IS800", "exact_section", "12.11.1", 0)]
    ebf = dict(f, reference_rotation=IM.reference_rotation("EBF"))
    assert collect.plan_for("deformation_capacity", ebf) == [("IS18168", "exact_section", "12.3.3.1", 0)]
    soft = dict(f, soil="III")
    assert any("Soft soil sites (Type III)" in w for _f, w, _k in collect.fields_for("spectrum", soft))


# ---------------------------------------------------------------- exact lookups passed whole (3629a4b)
E250_A_ROW = _line("IS2062:Table 3", r"^\|\s*ii\)\s*\|\s*E 250\s*\|\s*A\s*\|")
GOOD_MATERIAL = {"fu_MPa": _q(410, E250_A_ROW), "fy_t16_MPa": _q(250, E250_A_ROW), "fy_t40_MPa": _q(240, E250_A_ROW),
                 "fy_t100_MPa": _q(230, E250_A_ROW), "fy_tgt100_MPa": _q(210, E250_A_ROW)}


def test_every_is_group_is_transcribed_from_its_whole_table(monkeypatch):
    """IS 2062 Table 3's E 250 row sits 7,500 characters into the passage; exact lookups now arrive whole, so the
    material group is read like every other, and the gate file is written from five transcribed IS groups."""
    job, R, L, old = _live([GOOD_MATERIAL, GOOD_OVERSTRENGTH, GOOD_DEFORMATION, GOOD_SPECTRUM, GOOD_DAMPING], needed=ALL, monkeypatch=monkeypatch)
    try:
        r = collect.run(job, emit=collect.Emitter(io.StringIO()))
        assert r["ok"] and r["verified"] and os.path.basename(r["path"]) == collect.OUT_NAME, r
        d = json.load(open(r["path"], encoding="utf-8"))
        m = d["india_spec"]["material"]
        assert (m["fu_MPa"], m["fy_t16_MPa"], m["fy_t40_MPa"], m["fy_t100_MPa"], m["fy_tgt100_MPa"]) == (410, 250, 240, 230, 210)
        assert m["source"] == "IS 2062 (Part 1):2025 Table 3, p. 9" and m["quotes"]["fu_MPa"] == E250_A_ROW
        assert d["material"]["Fy_ksi"] == pytest.approx(36.259, abs=1e-3) and d["spec_values_collected"] and d["verified"] is False
        prompt = ScriptedLLM.calls[0]["messages"][-1]["content"]
        assert E250_A_ROW in prompt and "E 650" in prompt, "the whole table was handed over"
    finally:
        _done(R, L, old)


def test_a_row_the_model_reports_absent_is_asked_for_once_more_and_then_let_go(monkeypatch):
    """A model reading a passage cut short says the row is not there. Absent is asked once more, with the size
    of what was handed over (the row of a long table sits far below its header), then believed."""
    absent = {f: {"value": None, "quote": None, "why": "the E 250 row is not in the passage"} for f in GOOD_MATERIAL}
    job, R, L, old = _live([absent, absent, GOOD_OVERSTRENGTH, GOOD_DEFORMATION, GOOD_SPECTRUM, GOOD_DAMPING], needed=ALL, monkeypatch=monkeypatch)
    try:
        r = collect.run(job, emit=collect.Emitter(io.StringIO()))
        assert not r["ok"] and r["missing"] == ["material"]
        assert len(ScriptedLLM.calls) == 6, "material absent, material once more, then the other four -- not a third material call"
        second = ScriptedLLM.calls[1]["messages"][-1]["content"]
        assert "read to the end before answering that a cell is absent" in second and "IS 2062 Table 3" in second
        ev = json.load(open(os.path.join(job, collect.EVIDENCE_NAME), encoding="utf-8"))
        assert any(p.startswith("fu_MPa: not read -- the E 250 row is not in the passage") for p in ev["problems"]["material"])
    finally:
        _done(R, L, old)
