"""NL-9 (and NL-8): `snl collect` reads every grade the design uses (IS 2062 grades, IS 1161 tube grades) and every IS 800 /
IS 18168 rotation reference of a combined system. NL-9: a SCRIPTED transcriber -- an answers file written from
collect_request.json by an agent or a person -- goes through the same quote / value checks as a model."""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snl import collect, rag                                   # noqa: E402
import test_collect as TC                                      # noqa: E402


def _scripted(tmp_answers, monkeypatch):
    job = TC._job()
    TC.TableRAG.queries.clear()
    R = TC._Server(TC.TableRAG)
    old = dict(os.environ)
    os.environ["RAG_API_URL"] = R.url + "/query"; rag._status_cache = None
    real = collect.gather
    monkeypatch.setattr(collect, "gather", lambda j: dict(real(j), needed=list(TC.NO_MATERIAL)))
    return job, R, old


def test_prepare_writes_the_request_and_collects_nothing(monkeypatch):
    job, R, old = _scripted(None, monkeypatch)
    try:
        r = collect.run(job, emit=collect.Emitter(io.StringIO()), prepare=True)
        assert r["prepared"] and not r["ok"] and not os.path.exists(os.path.join(job, collect.OUT_NAME))
        req = json.load(open(r["prepared"], encoding="utf-8"))
        assert set(req["groups"]) == set(TC.NO_MATERIAL) and req["groups"]["damping"]["passages"]
        assert "7.2.4" in req["groups"]["damping"]["table_and_row"]
        assert set(req["answers_template"]["answers"]["spectrum"]) >= {"Z", "Sa_c", "I_row_ii"}
        assert os.path.exists(os.path.join(job, "collect_request.md"))
    finally:
        R.close(); os.environ.clear(); os.environ.update(old); rag._status_cache = None


def test_scripted_answers_pass_the_same_checks(monkeypatch, tmp_path):
    job, R, old = _scripted(None, monkeypatch)
    try:
        good = {"transcriber": "test agent", "answers": {"overstrength": TC.GOOD_OVERSTRENGTH, "deformation_capacity": TC.GOOD_DEFORMATION,
                                                         "spectrum": TC.GOOD_SPECTRUM, "damping": TC.GOOD_DAMPING}}
        p = tmp_path / "answers.json"; p.write_text(json.dumps(good))
        r = collect.run(job, emit=collect.Emitter(io.StringIO()), answers=str(p))
        assert r["ok"], r
        d = json.load(open(r["path"], encoding="utf-8"))
        assert d["india_spec"]["overstrength"]["Ry"] == 1.4 and any("SCRIPTED" in x and "test agent" in x for x in d["_README"])
        ev = json.load(open(os.path.join(job, collect.EVIDENCE_NAME), encoding="utf-8"))
        assert ev["model"] == "SCRIPTED" and len(ev["transcriber"]["answers_sha256"]) == 64
        # a remembered number (Ry 1.1, the AISC A992 value) is not in the IS 18168 cell: rejected, no retry, gate closed
        bad = json.loads(json.dumps(good)); bad["answers"]["overstrength"]["Ry"]["value"] = 1.1
        p.write_text(json.dumps(bad))
        os.remove(os.path.join(job, collect.OUT_NAME))
        r = collect.run(job, emit=collect.Emitter(io.StringIO()), answers=str(p))
        assert not r["ok"] and r["missing"] == ["overstrength"] and r["path"].endswith(collect.PARTIAL_NAME)
        # a quote that is not in the passages is rejected too
        bad = json.loads(json.dumps(good)); bad["answers"]["damping"]["damping_percent"]["quote"] = "damping 5 percent (from memory)"
        p.write_text(json.dumps(bad))
        r = collect.run(job, emit=collect.Emitter(io.StringIO()), answers=str(p))
        assert not r["ok"] and "damping" in r["missing"]
    finally:
        R.close(); os.environ.clear(); os.environ.update(old); rag._status_cache = None
