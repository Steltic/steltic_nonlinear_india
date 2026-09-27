"""NL-19: `snl run` on an India HR package passes no ASCE site class and runs the NLRHA with fibre plasticity (the USA
default imk was passed and silently ignored by the India CLI); a fresh HR package is recognised as India from
load_plan.json before any NL output exists."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from snl import cli, compare  # noqa: E402


def _job(tmp_path, juris):
    j = tmp_path / ("job_" + juris)
    j.mkdir()
    (j / "load_plan.json").write_text(json.dumps({"jurisdiction": juris}))
    return str(j)


def _cmds(monkeypatch, job):
    seen = []
    monkeypatch.setattr(cli, "_run", lambda cmd, log, env=None, cwd=None: (seen.append(cmd), dict(returncode=0, seconds=0))[1])
    monkeypatch.setattr(compare, "build", lambda job: "x.html")
    monkeypatch.setattr(cli, "_hub", lambda job: None)
    cli.main(["run", job, "--only", "pushover", "nlrha", "--no-criteria"])
    return seen


def test_fresh_hr_package_is_india(tmp_path):
    assert compare._is_india_job(_job(tmp_path, "india"))
    assert not compare._is_india_job(_job(tmp_path, "usa"))


def test_india_run_passes_fibre_and_no_site_class(tmp_path, monkeypatch):
    seen = _cmds(monkeypatch, _job(tmp_path, "india"))
    po, nl = seen
    assert "--site-class" not in po and "--site-class" not in nl
    assert nl[nl.index("--plasticity") + 1] == "fibre" and nl[nl.index("--member-nseg") + 1] == "4"


def test_usa_run_keeps_its_defaults(tmp_path, monkeypatch):
    seen = _cmds(monkeypatch, _job(tmp_path, "usa"))
    po, nl = seen
    assert "--site-class" in nl and nl[nl.index("--plasticity") + 1] == "imk"
