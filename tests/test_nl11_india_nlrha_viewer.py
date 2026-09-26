"""NL-11: an India NLRHA writes nlrha/nlrha_viewer_3d.html -- levels DBE / MCE, braces by their axial state, fibre
members / links by their record-peak ratios, the 0.004 h line labelled as the linear check, the D7 sentence, mm units,
and no IO / LS / CP / ACCEPTABLE wording."""
import os
import shutil
import subprocess
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import india_nl_job  # noqa: E402

NODE = shutil.which("node") or ("/opt/node22/bin/node" if os.path.exists("/opt/node22/bin/node") else None)


def _results(pkg, f):
    from pushover.nonlinear_model import levels
    lv = levels(pkg)
    braces = [e["tag"] for e in pkg.model.elements if pkg.schedule.get(e["tag"], {}).get("member") == "brace"][:6]
    members = [e["tag"] for e in pkg.model.elements if pkg.schedule.get(e["tag"], {}).get("member") in ("col", "beam")][:20]
    nfr = 12
    frames = dict(t=[0.05 * i for i in range(nfr)],
                  story=[[[f * 0.01 * i * (k + 1), f * 0.008 * i * (k + 1), 1e-5 * i] for k in range(len(lv))] for i in range(nfr)],
                  brace_tags=braces, brace=[[(-0.3 if j % 2 else 0.2) * f * i / nfr for j in range(len(braces))] for i in range(nfr)],
                  ag=[[0.01 * i, -0.01 * i] for i in range(nfr)])
    spec = types.SimpleNamespace(dT=0.1, dc=0.08)
    return [dict(record="FF01", label="FEMA P-695 FF01", sf=1.2, x_comp=1, converged=True, reason="completed",
                 peak_story_drift=[[f * 0.003, f * 0.0025] for _ in lv], residual_drift=[1e-4 for _ in lv], t_window=(0.1, 0.4),
                 frames=frames, specs={t: spec for t in braces}, heights=[144.0] * len(lv),
                 member_peaks={"m": {t: [f * 0.9 * (1 + (t % 3) / 3), 0.004] for t in members}, "b": {}, "l": {}})]


def test_viewer_written_for_both_levels(tmp_path):
    from pushover import package_reader as PR
    from nlrha import viewer3d_india as V
    job = india_nl_job.make(outputs=False)
    pkg = PR.load(job)
    per = {}
    for lv, f in (("DBE", 1.0), ("MCE", 2.0)):
        summ = dict(n_records=1, n_converged=1, max_mean_drift=f * 0.003, max_peak_drift=f * 0.003,
                    story=[dict(story=i + 1, mean_X=f * 0.003, mean_Y=f * 0.0025) for i in range(5)],
                    base_shear=dict(mean_X_kN=f * 900, mean_Y_kN=f * 850, VB_design_X_kN=500, VB_design_Y_kN=480, elastic_kN=f * 1500, Sa_T1_g=f * 0.2))
        per[lv] = (dict(results=_results(pkg, f), gm=dict(target_label="IS 1893 elastic %s (no R)" % lv)), summ)
    out = os.path.join(job, "nlrha"); os.makedirs(out, exist_ok=True)
    p = V.write(out, pkg, per, dict(T1x=0.6, T1y=0.55), dict(damping=dict(xi=0.025)))
    html = open(p, encoding="utf-8").read()
    assert "nlrha_india" in html and "DBE" in html and "MCE" in html
    assert "provides no acceptance criteria for nonlinear analysis" in html
    data = html.split("const DATA")[1].split(";\n")[0]
    module = html.split("analysis-specific module")[1]
    for bad in ("ACCEPTABLE", "> IO", "Table 12.12-1", "16.4.1.1", "BSE-2N", "CP"):
        assert bad not in data and bad not in module, bad
    assert "7.11.1.1 is the LINEAR design check" in html
    if NODE:
        r = subprocess.run([NODE, os.path.join(ROOT, "tests", "js_viewer_smoke.js"), p], capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr


def test_finish_india_calls_the_viewer():
    src = open(os.path.join(ROOT, "nlrha", "cli.py"), encoding="utf-8").read()
    assert "viewer3d_india" in src.split("def _finish_india")[1].split("def _report_india")[0]
