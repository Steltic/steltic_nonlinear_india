"""2026-10 check fixes (independent review of the second-wave publish, findings 1-4, 6 and 14 for this repo; the NL
parts of finding 5): a pushover target the curve did not reach is said where the row is printed; a lower-bound Vmax
reads "≥"; the completeness gate has a plain-language reason (no ticket ids) on the four-analyses page and in the
site index; a pushover direction can be put "under review" from its stored results; no "EOR", ticket ids, JSON file
names or keys on a public NL page; margins rounded down the same way on every page.

Pure tests run everywhere. Package tests use the published NL gold set (STELTIC_NL_GOLD, default
/home/claude/work/golds/nl_1004), matched on the title part of the run id, and skip without it."""
import copy
import glob
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

NL_GOLD = os.environ.get("STELTIC_NL_GOLD", "/home/claude/work/golds/nl_1004")


def _gold(root, title):
    hits = sorted(p for p in glob.glob(os.path.join(root, "*" + title)) if os.path.isdir(p))
    if not hits:
        pytest.skip("NL gold run *%s not available under %s" % (title, root))
    return hits[0]


def _copy_run(src, dst):
    keep = {"load_plan.json", "cfg.py", "ddm_results.json", "design", "report.html", "complete_gate.json"}
    os.makedirs(dst, exist_ok=True)
    for n in os.listdir(src):
        p = os.path.join(src, n)
        if n in ("nlrha", "pushover"):
            shutil.copytree(p, os.path.join(dst, n), ignore=shutil.ignore_patterns("*.pkl", "*.gz", "*.csv"))
        elif n in keep:
            (shutil.copytree if os.path.isdir(p) else shutil.copy2)(p, os.path.join(dst, n))
    return dst


# =============================================================================================== public text (5, 6)
def test_scrub_removes_ticket_ids_eor_and_json_keys():
    from snl.public_text import scrub, scrub_html, has_internal_words, HINGE_NOTE_OLD, HINGE_NOTE
    t = ("Modelling disclosures (NL-21) ... free-vibration tail (NL-21); numerical stops (NL-24 / NL-36); "
         "information / EOR input; the engineer may set nl_plan.gm_selection.sf_bounds")
    s = scrub(t)
    assert "NL-" not in s and "EOR" not in s and "nl_plan" not in s
    assert "Modelling disclosures ..." in s and "design engineer's input" in s and "the design engineer may set them" in s
    assert scrub(s) == s and scrub(None) is None
    h = "<p>%s</p><img src='data:image/png;base64,AAAANL-21+/EOR'>" % HINGE_NOTE_OLD
    out = scrub_html(h)
    assert HINGE_NOTE in out and "hinge_params_used.json" not in out and "EOR input" not in out
    assert "base64,AAAANL-21+/EOR'" in out                                   # images untouched
    assert scrub_html(out) == out
    assert has_internal_words("see NL-31") and has_internal_words("EOR choice") and not has_internal_words(HINGE_NOTE)


def test_hinge_note_has_no_eor_and_no_file_name():
    from snl import grounding as G
    for st in (G.COLLECTED, G.GROUNDED, G.UNVERIFIED):
        b = G.block_html(st, {"clauses": {"IS 800 12": {"grounded": True, "citation": "p. 1"}}}, {"spec_values_collected": True})
        assert "EOR" not in b and "hinge_params_used.json" not in b and "design engineer's input" in b


# =============================================================================================== gate reason (3)
def _run(label, kind="seismic", status="LIMIT_POINT", lam_u=1.3, lam_end=1.3, **kw):
    r = dict(label=label, kind=kind, status=status, lambda_u=lam_u, lambda_end=lam_end, imp="+Y",
             phi=dict(cls="SEIS", phi_s=None), check=[None, "INFO"], hist=[[0.5, -1.0], [1.0, -2.0]])
    r.update(kw)
    return r


def _ddm_job(tmp_path, runs, status):
    job = str(tmp_path / "job")
    os.makedirs(job, exist_ok=True)
    json.dump(dict(runs=runs, options=dict(dlam=0.05)), open(os.path.join(job, "ddm_results.json"), "w"))
    json.dump(dict(status=status, reasons=[], notes=[]), open(os.path.join(job, "complete_gate.json"), "w"))
    return job


def test_gate_reason_partial_names_the_stop_and_why_it_blocks(tmp_path):
    from snl.gate_reason import gate_reason, notes
    b12 = dict(ok=True, reached_lambda_1=True, groups=[dict(dc_max=0.8531)])
    stop = _run("1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z", status="SOLVER_FAILURE", lam_u=None, lam_end=1.3183,
                termination="runaway", runaway=dict(criterion="lambda -787.863 after 1.318 at step 53 of the stored curve"),
                retries=[dict(dlam=0.05, status="SOLVER_FAILURE"), dict(dlam=0.025, status="NO_LIMIT_POINT")], b12=b12)
    job = _ddm_job(tmp_path, [_run("1.5DL+1.5LL", kind="gravity"), stop], "partial")
    g = gate_reason(job)
    t = g["text"]
    assert g["label"] == "PARTIAL" and "NL-" not in t and "SOLVER_FAILURE" not in t
    assert "1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z" in t and "λ = 1.318" in t and "-787.9" in t
    assert "No capacity is reported" in t and "satisfied (largest ratio 0.854)" in t    # demand ratio rounded up
    assert "blocks COMPLETE" in t and "2 of the 3 sizes" in t and "Δλ 0.05, 0.025" in t
    n = notes(job)
    assert n and "NL-" not in " ".join(n) and "blocks COMPLETE" in n[0]


def test_gate_reason_solver_stops_says_why_it_does_not_block(tmp_path):
    from snl.gate_reason import gate_reason
    b12 = dict(ok=True, reached_lambda_1=True, groups=[dict(dc_max=0.863)])
    stop = _run("1.2DL+1.2LL-1.2EQ_Y[ea]+0.3EQ_Z", status="SOLVER_FAILURE", lam_u=None, lam_end=1.337749,
                termination="step_exhausted", b12=b12,
                retries=[dict(dlam=d, status="SOLVER_FAILURE") for d in (0.05, 0.025, 0.0125)])
    job = _ddm_job(tmp_path, [_run("1.5DL+1.5LL", kind="gravity"), stop], "complete_with_solver_stops")
    t = gate_reason(job)["text"]
    assert "λ = 1.337" in t and "stated, not blocking" in t and "all 3 load-step sizes" in t
    assert "information only" in t and "NL-" not in t


def test_gate_reason_shortfall_and_complete(tmp_path):
    from snl.gate_reason import gate_reason
    job = _ddm_job(tmp_path, [_run("1.5DL+1.5LL", kind="gravity")], "complete")
    assert gate_reason(job)["text"].startswith("All four analyses are complete")
    d = json.load(open(os.path.join(job, "ddm_results.json")))
    d["b12_check"] = dict(ok=False, combos=[dict(combo="1.5DL+1.5LL", groups=[dict(role="gravity_col", section="WPB300", dc_max=1.0651)])])
    json.dump(d, open(os.path.join(job, "ddm_results.json"), "w"))
    json.dump(dict(status="complete_with_capacity_shortfall"), open(os.path.join(job, "complete_gate.json"), "w"))
    t = gate_reason(job)["text"]
    assert "not satisfied" in t and "gravity col WPB300, ratio 1.066 under 1.5DL+1.5LL" in t


# =============================================================================================== pushover review (4)
def _package(drop=True, reached_mce=True):
    """A synthetic two-direction pushover package: Y has a one-step loss of half its base shear and links far beyond
    the chevron kinematics; X is regular."""
    def curve(k, n, drop_at=None):
        u = [0.0] + [5.0 * i for i in range(1, n)]
        V = [0.0] + [k * x for x in u[1:]]
        if drop_at:
            V = [v if i < drop_at else (0.5 * V[drop_at - 1] + 10.0 * (u[i] - u[drop_at])) for i, v in enumerate(V)]
        return u, V

    def links(g, drift):
        return dict(member_groups=[], brace_groups=[], link_groups=[dict(section="L", level=1, n=2, gamma_max_rad=g)])

    ux, Vx = curve(100.0, 30)
    uy, Vy = curve(40.0, 400, drop_at=8 if drop else None)
    cens = dict(members_yielded=0, braces_buckled=0, braces_yielded_tension=0, links_yielded=2)

    def d_(u, V, T1, g, drift, lb, reached):
        return dict(T1=T1, stop_reason="solver non-convergence at roof u=3.0 in" if lb else "descending branch captured",
                    tail=dict(status="lower_bound" if lb else "captured"),
                    curve_u_mm=u, curve_V_kN=V,
                    capacity=dict(Vmax_kN=max(V), Vmax_over_VB=max(V) / 1000.0, Vmax_over_W=max(V) / 20000.0, u_end_in=u[-1] / 25.4,
                                  tail_status="lower_bound" if lb else "captured",
                                  stop_reason="solver non-convergence" if lb else "descending branch captured"),
                    nsp={"IS-DBE": dict(target_disp_mm=60.0, target_over_H=60.0 / 40000.0, reached_target=True, Te=T1, Ki=1.0, Ke=1.0, Sa=0.5),
                         "IS-MCE": dict(target_disp_mm=120.0, target_over_H=120.0 / 40000.0, reached_target=reached, Te=T1, Ki=1.0, Ke=1.0, Sa=1.0)},
                    response={"IS-DBE": dict(roof_disp_mm=60.0, V_over_VB=1.0, max_story_drift=drift, members=links(g, drift), census=cens),
                              "IS-MCE": dict(roof_disp_mm=120.0 if reached else u[-1], V_over_VB=1.2, max_story_drift=2 * drift,
                                             members=links(g * 1.1, 2 * drift), census=cens)})
    return dict(directions=dict(X=d_(ux, Vx, 0.6, 0.012, 0.0023, False, True),
                                Y=d_(uy, Vy, 0.9, 0.42, 0.0061, True, reached_mce)))


def test_review_evidence_and_text():
    from pushover import review as RV
    pkg = _package()
    ev = RV.evidence(pkg, "Y", l_over_e=8500 / 900)
    assert ev["drop"] and abs(ev["drop"]["fraction"] - 0.5) < 0.05
    f = RV.findings(ev, RV.evidence(pkg, "X", l_over_e=8500 / 900))
    t = " ".join(f)
    assert "in one step, a loss of 5" in t and "only links have" in t
    assert "0.42 rad at 0.61 % storey drift" in t and "L / e = 9.4" in t and "in line with that" in t
    assert "not compatible with the frame's drift" in t
    s = RV.summary_sentence("Y", ev)
    assert s.startswith("Pushover Y under review") and "not to be relied on" in s


def _job_with_package(tmp_path, pkg, report=None):
    job = str(tmp_path / "job")
    os.makedirs(os.path.join(job, "pushover"), exist_ok=True)
    json.dump(pkg, open(os.path.join(job, "pushover", "pushover_package.json"), "w"))
    if report is not None:
        open(os.path.join(job, "pushover", "pushover_report.html"), "w", encoding="utf-8").write(report)
    return job


REPORT = ("<h1>Pushover</h1><div class='note' data-provenance=\"collected\">%s</div><h2>1 Capacity curves</h2><img src='x'>"
          "<h2>2 Target displacements</h2><table>"
          "<tr><td>Y</td><td>IS-DBE</td><td>0.9</td><td>0.9</td><td>0.5</td><td>1.4</td><td>1.0</td><td>1.0</td><td>60.0</td><td>0.0015</td><td>yes</td></tr>"
          "<tr><td>Y</td><td>IS-MCE</td><td>0.9</td><td>0.9</td><td>1.0</td><td>1.4</td><td>1.0</td><td>1.0</td><td>120.0</td><td>0.0030</td><td>NO</td></tr>"
          "</table><h2>3 Response at δt (interpolated)</h2>"
          "<p><b>X</b>: Vmax = 14500 kN (Vmax/VB = 14.50, Vmax/W = 0.725); curve end 145 mm, μ(end) = 2.00; stop: none</p>"
          "<table><tr><td>IS-DBE</td><td>60.0</td></tr><tr><td>IS-MCE</td><td>120.0</td></tr></table>"
          "<p><b>Y</b>: Vmax = 8000 kN (Vmax/VB = 8.00, Vmax/W = 0.400); curve end 1995 mm, μ(end) = 2.00; stop: solver</p>"
          "<table><tr><td>IS-DBE</td><td>60.0</td></tr><tr><td>IS-MCE</td><td>40.0</td></tr></table>"
          "<h3>Y IS-MCE — member groups (fibre strain / chord rotation)</h3>"
          "<h2>4 Steel by section</h2><table><tr><td>CHS114.3X3.6</td><td>roof</td><td>YSt 310</td><td>3.6</td><td>None</td></tr></table>"
          "<h2>Modelling disclosures (NL-21)</h2>")


def test_pushover_refresh_lower_bound_target_review_none(tmp_path):
    from snl.public_text import HINGE_NOTE_OLD
    from pushover import review as RV
    from pushover.report_india import refresh_report
    pkg = _package(reached_mce=False)
    job = _job_with_package(tmp_path, pkg, REPORT % HINGE_NOTE_OLD)
    po = os.path.join(job, "pushover")
    assert refresh_report(po)
    h = open(os.path.join(po, "pushover_report.html"), encoding="utf-8").read()
    # third wave (P10): the old line is the whole-curve peak (information); the headline is the table above it
    assert "<p><b>X</b>: whole-curve peak (information) Vmax = 14500 kN (Vmax/VB = 14.50" in h   # captured, no "≥"
    assert "Pushover strength (headline): Vmax up to the IS-MCE target displacement" in h
    assert "Vmax ≥ 8000 kN (Vmax/VB ≥ 8.00, Vmax/W ≥ 0.400) — a lower bound" in h
    assert "<td>NO — the curve ended at" in h and "IS-MCE (curve end: the 120.0 mm target was not reached" in h
    assert "Y IS-MCE at the curve end" in h
    assert "<td>None</td>" not in h and "EOR" not in h and "NL-21" not in h and "hinge_params_used.json" not in h
    assert "UNDER REVIEW" not in h
    RV.write_record(job, RV.make_record(job, ["Y"], l_over_e=9.44))
    assert refresh_report(po)
    h2 = open(os.path.join(po, "pushover_report.html"), encoding="utf-8").read()
    assert h2.count("Pushover Y under review") == 1 and "<b>Y</b> <span class='rv'>(UNDER REVIEW" in h2
    assert not refresh_report(po)                                             # idempotent
    os.remove(RV.record_path(job))
    assert refresh_report(po)                                                 # the record removed: the note goes
    h3 = open(os.path.join(po, "pushover_report.html"), encoding="utf-8").read()
    assert "UNDER REVIEW" not in h3 and "under review" not in h3 and h3 == h


def test_index_pushover_fields(tmp_path):
    import build_site_index as B
    from pushover import review as RV
    job = _job_with_package(tmp_path, _package(reached_mce=False))
    p = B.pushover_results(job)
    # third wave (P10): up to the IS-MCE target (120 mm) 12.0; the whole-curve 14,500 kN is information beyond it
    assert p["vmax_vb_text_x"] == "12.0" and not p["vmax_lower_bound_x"] and "14,500 kN" in p["vmax_beyond_text_x"]
    assert p["vmax_vb_text_y"].startswith("≥ ") and p["vmax_lower_bound_y"] and "lower bound" in p["vmax_lower_bound_note"]
    assert p["mce_target_reached_y"] is False and "not reached" in p["mce_target_text_y"]
    assert not p["under_review_y"]
    RV.write_record(job, RV.make_record(job, ["Y"]))
    p = B.pushover_results(job)
    assert p["under_review_y"] and p["vmax_vb_text_y"] == "under review" and p["review_y"].startswith("Pushover Y under review")
    res = dict(pushover=p, nlrha={}, ddm={})
    assert "under review" in B.meta_line(res) and B.flag_line(res).startswith("Pushover Y under review")


# =============================================================================================== DDM report (3, 5, 14)
def test_ddm_report_rounding_and_plain_text():
    import inspect
    from steltic_ddm import report_ddm as RD
    assert RD._lam(dict(lambda_u=1.04199, status="LIMIT_POINT")) == "1.041 [LIMIT_POINT]"
    assert "1.337" in RD._lam(dict(lambda_u=None, status="SOLVER_FAILURE", termination="step_exhausted", lambda_end=1.337749))
    src = inspect.getsource(RD.build_india) + inspect.getsource(RD._solver_failure_html) + inspect.getsource(RD._imposed_basis_by_combo)
    assert "(NL-" not in src and "NL %s" not in src and "second wave, NL" not in src
    t = RD.restraint_summary_text("PEB restraints (NL-33, cfg['flange_braces'] as peb_build / D-T1): rafters 141 lateral")
    assert "NL-" not in t and "cfg[" not in t and "Steltic design ruling D-T1, lateral-torsional buckling" in t
    t = RD.restraint_summary_text("Rolled-section restraints (NL-38, from the HR cfg, brief spacing for girt): columns at Ky x L")
    assert t.startswith("Rolled-section restraints (from the HR design input; girt spacing from the project brief)")
    s = RD.restraint_sources_text({"fly": "cfg['LLT_hog_mm']['roof'] (the design's bottom-flange LTB length, fly-brace spacing)",
                                   "purlin": "cfg['secondary_members'] 'roof purlin (IS 808 channel MC)' spacing_mm",
                                   "girt": "brief (cfg declares none): 'Wall girts at 2.375 m'"})
    assert "cfg" not in s and "fly braces: the design's bottom-flange LTB length" in s and "girts: the project brief" in s


def test_peb_restraint_summary_for_new_runs_is_plain():
    import inspect
    from steltic_ddm import peb_restraints as PR
    src = inspect.getsource(PR.summary) if hasattr(PR, "summary") else inspect.getsource(PR)
    assert "(NL-33, cfg['flange_braces']" not in src and "(NL-38, from the HR cfg" not in src


# =============================================================================================== whole pages (gold)
def test_four_analyses_and_index_on_an_ebf_run(tmp_path):
    """Ex15 EBF (2026-10-04 gold): the gate box, '≥' on both lower-bound directions, rounding down, no ticket ids or
    sha256 line; with a review record on Y, 'UNDER REVIEW' on the Y rows and the note; the index fields."""
    src = _gold(NL_GOLD, "_EBF_8levels_Lplan_Pune")
    job = _copy_run(src, str(tmp_path / "IN_Ex15"))
    from snl import compare
    from pushover import review as RV
    import build_site_index as B
    RV.write_record(job, RV.make_record(job, ["Y"], l_over_e=10.0, with_nlrha=True))
    compare.build(job)
    h = open(os.path.join(job, "four_analyses.html"), encoding="utf-8").read()
    assert "Completeness gate: " in h and "Inputs (sha256)" not in h and "NL-" not in h and "EOR" not in h
    # third wave (P10): Vmax up to the IS-MCE target -- both targets were reached, so no lower bound any more
    assert "Pushover strength Vmax up to the IS-MCE target (X / Y)" in h and "Vmax/VB = 3.0 / 2.0" in h
    assert "≥ marks a lower bound" not in h and "the curve continues to" in h
    assert "UNDER REVIEW (see the note below)" in h and "Pushover Y under review" in h
    assert "sweeps that stopped numerically" in h
    summ = json.load(open(os.path.join(job, "snl_summary.json")))
    assert summ.get("gate_reason", {}).get("label") and summ.get("pushover_review", {}).get("Y")
    gate = json.load(open(os.path.join(job, "complete_gate.json")))
    assert gate.get("reason_text") and all("NL-" not in n for n in gate.get("notes") or [])
    e = B.run_entry(job, None, "IN_Ex15_EBF_8levels_Lplan_Pune")
    r = e["results"]
    assert r["gate_reason_text"] and r["gate_label"] and r["pushover"]["under_review_y"]
    assert "NL-" not in json.dumps(e, ensure_ascii=False) and "EOR" not in json.dumps(e, ensure_ascii=False)
    assert "under review" in e["meta"]


# =============================================================================================== NLRHA / pushover words (5)
def test_nlrha_model_paragraph_in_words():
    import html
    from nlrha.report_india import damping_text, torsion_text, refresh_model_paragraph
    d = {"xi": 0.025, "cap": 0.05, "basis": "Rayleigh 2.5 % at T1 and 0.2 T1 (hinge_params damping.xi_default (modelling assumption)); rest",
         "warning": None, "source": "hinge_params damping.xi_default (modelling assumption)",
         "reference": {"value": 0.05, "clause": "IS 1893 (Part 1):2016 7.2.4", "role": "reference (Ah); not the model's viscous damping"}}
    t = {"mode": "pos", "sx": 1, "sy": 1, "e_ratio": 0.05, "clause": "IS 1893 7.8.2 (0.05 b), default on for India"}
    assert damping_text(d).startswith("ξ = 2.5 % (cap 5 %); Rayleigh 2.5 % at T1 and 0.2 T1 (modelling assumption)")
    assert "hinge_params" not in damping_text(d) and torsion_text(t).startswith("eccentricity 0.05 b, + in X and + in Y")
    assert torsion_text(dict(mode="off")) == "off"
    h = "<p>Plasticity fibre; damping %s; accidental torsion %s; mass = IS seismic weight (gate ok); spurious modes [].</p>" % (
        html.escape(json.dumps(d)), html.escape(json.dumps(t)))
    out = refresh_model_paragraph(h)
    assert "{" not in out and "&quot;" not in out and "spurious modes none." in out and "ξ = 2.5 %" in out
    assert refresh_model_paragraph(out) == out


def test_pushover_footer_and_shed_basis_words():
    from pushover.report_india import footer_words
    assert footer_words("False", "True") == ("the hinge parameters are not verified against an IS table (none exists); "
                                             "the IS specification values were collected from the IS corpus")
    from snl import shed
    import inspect
    assert "HR cfg %s" not in inspect.getsource(shed.shed_basis)


def test_pushover_viewer_annotations(tmp_path):
    from pushover import viewer3d_india as V3I, review as RV
    job = _job_with_package(tmp_path, _package(reached_mce=False))
    data = dict(dirs={"X": dict(stop="solver non-convergence at roof u=3.0 in"), "Y": dict(stop="x")})
    V3I.annotate(os.path.join(job, "pushover"), data)
    assert data["dirs"]["Y"]["lower_bound"] and not data["dirs"]["X"]["lower_bound"]
    assert data["dirs"]["Y"]["targets_not_reached"] == ["IS-MCE"] and data["dirs"]["Y"]["review"] is None
    assert data["dirs"]["X"]["stop"] == "solver non-convergence at roof u = 76 mm"
    RV.write_record(job, RV.make_record(job, ["Y"]))
    V3I.annotate(os.path.join(job, "pushover"), data)
    assert data["dirs"]["Y"]["review"].startswith("Pushover Y under review")
    assert "d.lower_bound?'≥ '" in V3I.MODULE_JS and "UNDER REVIEW" in V3I.MODULE_JS and "NL-21" not in V3I.LITE_NOTE
