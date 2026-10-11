"""NL-32: the India pushover writes pushover/pushover_viewer_3d.html (the Pushover tab of the Steltic viewer bundle).

* full: from the run records (capacity curve, storey displacements, MemberRecorder samples per step), saved as
  pushover/viewer_data.json.gz so `snl report` rebuilds it without a re-run;
* lite: from pushover_package.json alone (jobs run before NL-32) -- the curve and the IS-DBE / IS-MCE snapshots,
  coloured per member group;
* IS 1893 D7 wording, the 0.004 h line labelled as the linear check, mm / kN, no IO / LS / CP / ACCEPTABLE."""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import india_nl_job  # noqa: E402

NODE = shutil.which("node") or ("/opt/node22/bin/node" if os.path.exists("/opt/node22/bin/node") else None)


def _check_html(p):
    html = open(p, encoding="utf-8").read()
    assert "pushover_india" in html and "IS-DBE" in html and "IS-MCE" in html
    assert "provides no acceptance criteria for nonlinear analysis" in html
    assert "7.11.1.1 is the LINEAR design check" in html
    data = html.split("const DATA")[1].split(";\n")[0]
    module = html.split("analysis-specific module")[1]
    for bad in ("ACCEPTABLE", "> IO", "BSE-1N", "BSE-2N", "P-695"):
        assert bad not in data and bad not in module, bad
    if NODE:
        r = subprocess.run([NODE, os.path.join(ROOT, "tests", "js_viewer_smoke.js"), p], capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout.startswith("OK"), r.stdout + r.stderr
    return json.loads(data.lstrip(" =").strip())


def _groups(pkg, f):
    from pushover.nonlinear_model import member_kind, levels
    zs = [z for _, z, _, _ in levels(pkg)]
    lv = lambda z: min(range(len(zs)), key=lambda i: abs(zs[i] - z)) + 1
    mg, bg = {}, {}
    for e in pkg.model.elements:
        row = pkg.schedule.get(e["tag"], {}); sec = row.get("section"); k = member_kind(pkg, e)
        z = max(pkg.model.nodes[e["n1"]][2], pkg.model.nodes[e["n2"]][2])
        if not sec:
            continue
        if k == "brace":
            bg.setdefault((sec, lv(z)), 0); bg[(sec, lv(z))] += 1
        elif k in ("col", "beam"):
            mg.setdefault((k, sec, lv(z)), 0); mg[(k, sec, lv(z))] += 1
    members = [dict(kind=k, section=s, level=l, n=n, strain_ratio_max=f * (1.2 if l == 1 else 0.4), yielded=bool(f > 1 and l == 1),
                    chord_rot_max_rad=0.003 * f) for (k, s, l), n in mg.items()]
    braces = [dict(section=s, level=l, n=n, n_buckled_max=(n if f > 1 and l == 1 else (1 if l == 1 else 0)),
                   mu_tension_max=0.5 * f, mu_compression_max=1.1 * f, yielded_tension=False) for (s, l), n in bg.items()]
    return dict(member_groups=members, brace_groups=braces, link_groups=[])


def _package(pkg):
    from pushover.nonlinear_model import levels
    n_lv = len(levels(pkg))
    u = [2.0 * i for i in range(60)]; V = [min(40.0 * x, 3000.0) for x in u]
    dirs = {}
    for d in ("X", "Y"):
        resp = {}
        for lvn, f in (("IS-DBE", 1.0), ("IS-MCE", 2.0)):
            resp[lvn] = dict(roof_disp_mm=30.0 * f, base_shear_kN=1200.0 * f, V_over_VB=2.0 * f, VB_design_kN=600.0,
                             story_drifts=[dict(story=i + 1, drift_ratio=0.002 * f / (i + 1)) for i in range(n_lv)],
                             max_story_drift=0.002 * f, census=dict(braces_buckled=int(3 * f)), members=_groups(pkg, f))
        dirs[d] = dict(T1=0.6, stop_reason="max_drift", curve_u_mm=u, curve_V_kN=V,
                       capacity=dict(Vmax_kN=3000.0, u_at_Vmax_in=3.0, Vmax_over_VB=5.0, V_design_kip=600.0 / 4.4482216152605),
                       nsp={"IS-DBE": dict(Te=0.6, Sa=0.3), "IS-MCE": dict(Te=0.6, Sa=0.6)}, response=resp)
    return dict(jurisdiction="india", directions=dirs)


def test_lite_viewer_from_package():
    from pushover import viewer3d_india as V
    job = india_nl_job.make(outputs=False)
    out = os.path.join(job, "pushover"); os.makedirs(out, exist_ok=True)
    from pushover import package_reader as PR
    pkg = PR.load(job)
    json.dump(_package(pkg), open(os.path.join(out, "pushover_package.json"), "w"))
    p = V.ensure(job)
    assert p and p.endswith(os.path.join("pushover", "pushover_viewer_3d.html"))
    d = _check_html(p)["pushover_india"]
    assert d["mode"] == "lite" and set(d["dirs"]) == {"X", "Y"}
    X = d["dirs"]["X"]
    assert X["frames"]["label"] == ["unloaded", "IS-DBE target", "IS-MCE target"]
    assert X["targets"]["IS-MCE"]["frame"] == 2 and X["VB_kN"] == 600.0
    # deformed shape from the saved drifts: roof = sum(drift_i h_i), monotonic up the building
    st = X["frames"]["story"][2]
    assert all(b >= a for a, b in zip(st, st[1:])) and st[-1] > 0
    # every brace / column / beam element maps to a group; level-1 braces are all buckled at MCE, partly at DBE
    states = {d["group_label"][g]: s["state"] for g, s in ((int(k), v) for k, v in X["frames"]["groups"][2].items())}
    assert any("brace" in k and k.endswith("L1") and v == "buckled" for k, v in states.items())
    states1 = {d["group_label"][int(g)]: s["state"] for g, s in X["frames"]["groups"][1].items()}
    assert any("brace" in k and k.endswith("L1") and v == "partial" for k, v in states1.items())
    assert "Lite viewer" in d["lite_note"]
    # bundle hub refreshed, and ensure() does not rebuild an up-to-date viewer
    assert os.path.exists(os.path.join(job, "steltic_viewer_bundle.html"))
    t = os.path.getmtime(p); time.sleep(0.05)
    assert V.ensure(job) == p and os.path.getmtime(p) == t


def _run(pkg):
    """Synthetic India run records in the shapes _run_india holds (kip-in)."""
    from pushover.nonlinear_model import levels
    n_lv = len(levels(pkg))
    members = [e["tag"] for e in pkg.model.elements if pkg.schedule.get(e["tag"], {}).get("member") in ("col", "beam")][:12]
    braces = [e["tag"] for e in pkg.model.elements if pkg.schedule.get(e["tag"], {}).get("member") == "brace"][:6]
    n = 450
    runs, results = {}, {}
    for d in ("X", "Y"):
        u = [0.02 * i for i in range(n)]; Vk = [min(500.0 * x, 900.0) - (0 if x < 6 else 30 * (x - 6)) for x in u]
        samples = [dict(m={t: (0.004 * i, 1e-5 * i) for t in members}, b={t: (0.01 * i * (1 if j % 2 else -1), bool(j % 2 == 0 and i > 300))
                                                                           for j, t in enumerate(braces)}, l={}) for i in range(n)]
        runs[d] = dict(pattern=dict(T1=0.7), stop_reason="max_drift",
                       rec=dict(u=u, V=Vk, story_u=[[x * (k + 1) / n_lv for k in range(n_lv)] for x in u], members=samples,
                                elastic=[{999: 0.002 * i} for i in range(n)]))
        results[d] = dict(nsp={"IS-DBE": dict(Te=0.7, Sa=0.3, target_disp_in=1.0), "IS-MCE": dict(Te=0.7, Sa=0.6, target_disp_in=2.5)},
                          capacity=dict(Vmax_kN=900.0 * 4.448, u_at_Vmax_in=1.8, Vmax_over_VB=6.0, V_design_kip=150.0),
                          resp={"IS-DBE": dict(step_bracket=[50, 51], weight=0.3, V_over_VB=2.0, max_story_drift=0.002),
                                "IS-MCE": dict(step_bracket=[124, 125], weight=0.9, V_over_VB=4.0, max_story_drift=0.005)},
                          meta=dict(members={t: {} for t in members}, braces={t: {} for t in braces}, links={}))
    return runs, results, {t: (0.08, 0.1) for t in braces}


def test_full_viewer_from_run_and_rebuild(tmp_path):
    from pushover import viewer3d_india as V
    from pushover import package_reader as PR
    job = india_nl_job.make(outputs=False)
    pkg = PR.load(job)
    out = os.path.join(job, "pushover"); os.makedirs(out, exist_ok=True)
    runs, results, bd = _run(pkg)
    p = V.write_from_run(out, pkg, runs, results, bd)
    assert os.path.exists(os.path.join(out, "viewer_data.json.gz"))
    d = _check_html(p)["pushover_india"]
    assert d["mode"] == "full" and len(d["brace_tags"]) == len(d["brace_spec"]) and d["brace_spec"][0] == [2.032, 2.54]
    X = d["dirs"]["X"]
    ci = X["frames"]["ci"]
    assert len(ci) <= V.MAX_FRAMES and ci[0] == 0 and ci[-1] == 449 and X["n_steps"] == 450
    assert ci[X["targets"]["IS-DBE"]["frame"]] == 50 and ci[X["targets"]["IS-MCE"]["frame"]] == 125      # bracket by weight
    assert ci[X["vmax_frame"]] == max(range(450), key=lambda i: runs["X"]["rec"]["V"][i])
    assert X["curve"]["u"][1] == round(0.02 * 25.4, 2) and abs(X["VB_kN"] - 150.0 * 4.4482216152605) < 0.1
    assert d["elastic_tags"] == [999] and len(X["frames"]["eg"]) == len(ci)
    assert any(X["frames"]["b_bk"][-1])                                                               # buckled late in the push
    # snl report path: the saved data rebuilds the same (full) viewer without the run
    os.remove(p)
    json.dump(dict(jurisdiction="india", directions={}), open(os.path.join(out, "pushover_package.json"), "w"))
    q = V.ensure(job)
    assert q == p and _check_html(q)["pushover_india"]["mode"] == "full"


def test_ensure_skips_us_and_missing_packages(tmp_path):
    from pushover import viewer3d_india as V
    assert V.ensure(str(tmp_path)) is None
    os.makedirs(tmp_path / "pushover")
    json.dump(dict(jurisdiction="usa", directions={}), open(tmp_path / "pushover" / "pushover_package.json", "w"))
    assert V.ensure(str(tmp_path)) is None


def test_india_run_and_snl_hub_call_the_viewer():
    src = open(os.path.join(ROOT, "pushover", "cli.py"), encoding="utf-8").read()
    body = src.split("def _run_india")[1].split("def main")[0]
    assert "viewer3d_india" in body and "write_from_run" in body
    hub = open(os.path.join(ROOT, "snl", "cli.py"), encoding="utf-8").read().split("def _hub")[1].split("def cmd_report")[0]
    assert "V3I.ensure(job)" in hub
