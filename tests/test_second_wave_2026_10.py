"""2026-10 second wave (review E_NL item 15 leftovers, NL2 brief): the re-run record of a DDM re-run split into chunks,
the B-1.2 refresh of stored sweeps, and the presentation fixes (record pairs and analyses, the record-set disclosure,
phi_s x lambda_u as information, Vmax/W instead of Vmax/VB on sheds).

Pure tests run everywhere. Package tests use the published NL gold set (STELTIC_NL_GOLD, default
/home/claude/work/golds/nl_1004) and the PEB set (STELTIC_NL_PEB, default
/home/claude/work/golds/nl_peb/india_nl_gold_peb_2026-10-16), matched on the title part of the run id, and skip
without them."""
import copy
import glob
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# =============================================================================================== chunked re-run record
def test_rerun_record_keeps_every_chunk():
    from steltic_ddm.cli import _record_rerun
    first = dict(code="NL-30 / first-wave re-run", combos=["1.5DL+1.5LL"], date="2026-10-18T18:43:26")
    opts = dict(ddm_rerun=first)
    a = dict(code="NL-30 / re-run of named combinations", combos=["1.2DL+1.2LL+1.2W_X"], date="2026-10-23T16:00:00")
    b = dict(code="NL-30 / re-run of named combinations", combos=["1.2DL+1.2LL-1.2W_X"], date="2026-10-23T17:00:00")
    _record_rerun(opts, "ddm_rerun", a)
    _record_rerun(opts, "ddm_rerun", b)
    assert opts["ddm_rerun"] is b
    assert [r["combos"][0] for r in opts["ddm_rerun_history"]] == ["1.5DL+1.5LL", "1.2DL+1.2LL+1.2W_X", "1.2DL+1.2LL-1.2W_X"]
    _record_rerun(opts, "ddm_retry", dict(code="NL-30", combos=["x"]))
    assert opts["ddm_retry_history"] == [dict(code="NL-30", combos=["x"])]


def test_code_version_names_the_commit():
    from steltic_ddm.cli import code_version
    v = code_version()
    assert v is None or (len(v.split("+")[0]) >= 7 and all(c in "0123456789abcdef" for c in v.split("+")[0]))


# =============================================================================================== B-1.2 refresh (--b12-only)
def test_curve_prefix_match():
    from steltic_ddm.cli import curve_prefix_match
    stored = [(0.05, -2.1), (0.1, -4.2), (0.5, -21.0), (1.0, -42.0), (1.04, -47.4), (1.03, -49.0)]
    ok, n, dl, dd, bad = curve_prefix_match(stored[:4], stored)
    assert ok and n == 4 and dl == 0.0 and bad is None
    ok, n, dl, dd, bad = curve_prefix_match([(0.05, -2.1), (0.1, -4.2), (0.52, -21.0), (1.0, -42.0)], stored)
    assert not ok and bad == 2 and dl > 0.01
    assert not curve_prefix_match([(0.05, -2.1)], stored)[0]                      # one point proves nothing
    assert not curve_prefix_match(stored + [(1.0, -50.0)], stored)[0]             # longer than the stored curve


def test_sweep_stops_after_lambda_1_flag_exists():
    import inspect
    from steltic_ddm import solver
    assert "stop_after_lambda1" in inspect.signature(solver.sweep).parameters
    src = inspect.getsource(solver.sweep)
    assert "lambda1_captured" in src


def test_retry_has_b12_only_flag():
    import contextlib, io
    from steltic_ddm import cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        cli.main(["retry", "--help"])
    assert "--b12-only" in buf.getvalue()


# =============================================================================================== presentation (item 15)
NL_GOLD = os.environ.get("STELTIC_NL_GOLD", "/home/claude/work/golds/nl_1004")
NL_PEB = os.environ.get("STELTIC_NL_PEB", "/home/claude/work/golds/nl_peb/india_nl_gold_peb_2026-10-16")


def _gold(root, title):
    hits = sorted(p for p in glob.glob(os.path.join(root, "*" + title)) if os.path.isdir(p))
    if not hits:
        pytest.skip("NL gold run *%s not available under %s" % (title, root))
    return hits[0]


def _copy_run(src, dst, with_nl=True):
    import shutil
    keep = {"load_plan.json", "cfg.py", "ddm_results.json", "design", "report.html", "complete_gate.json"}
    os.makedirs(dst, exist_ok=True)
    for n in os.listdir(src):
        p = os.path.join(src, n)
        if n in ("nlrha", "pushover") and with_nl:
            shutil.copytree(p, os.path.join(dst, n), ignore=shutil.ignore_patterns("*.pkl", "*.gz", "*.csv"))
        elif n in keep:
            (shutil.copytree if os.path.isdir(p) else shutil.copy2)(p, os.path.join(dst, n))
    return dst


def test_record_set_library_facts_come_from_the_index():
    from nlrha import record_set as RS
    lib = RS.library_facts()
    idx = json.load(open(os.path.join(RS.LIBRARY_DIR, "index.json")))
    assert lib["name"] == idx["set"] and lib["source"] == idx["source"]
    assert lib["n_pairs"] == len(idx["records"]) == 22 and lib["n_components"] == 44
    assert lib["M"] == (min(r["M"] for r in idx["records"]), max(r["M"] for r in idx["records"]))
    assert lib["n_events"] == len({r["earthquake"] for r in idx["records"]})
    assert lib["p695"] and lib["n_pulse"] == 0
    # nothing Indian or Himalayan in the shipped library (the disclosure says so; this keeps it true)
    words = " ".join("%s %s" % (r["earthquake"], r["station"]) for r in idx["records"]).lower()
    for w in ("india", "himalaya", "nepal", "gorkha", "bhuj", "uttarkashi", "chamoli", "sikkim", "koyna", "latur", "assam"):
        assert w not in words


def _levels(dbe_ids, mce_ids, k=2.0, conv=11):
    def lv(ids, f):
        return dict(ground_motions=dict(selected=[dict(id=i, sf=0.1 * (n + 1) * f, earthquake="E%d" % i, year=1990)
                                                  for n, i in enumerate(ids)],
                                        T_lower=0.06, T_upper=0.65, common_multiplier=1.14, min_ratio_in_range=0.9,
                                        sets=[dict(set="FEMA P-695 (ATC-63) Far-Field record set, 22 pairs / 44 components")]),
                    response_summary=dict(n_records=len(ids), n_converged=conv))
    return {"DBE": lv(dbe_ids, 1.0), "MCE": lv(mce_ids, k)}


def test_analyses_text_says_pairs_levels_and_analyses():
    from nlrha import record_set as RS
    s = RS.suite_facts(_levels(list(range(11)), list(range(11))))
    assert RS.analyses_text(s) == ("11 record pairs (two horizontal components each), run at DBE and at MCE: "
                                   "22 analyses, 22 converged")
    assert s["same_pairs"] is True and s["mce_over_dbe_sf"] == 2.0
    s2 = RS.suite_facts(_levels(list(range(11)), list(range(1, 12)), conv=10))
    assert s2["same_pairs"] is False and s2["mce_over_dbe_sf"] is None
    assert RS.analyses_text(s2).endswith("22 analyses, 20 converged")


def test_disclosure_names_set_source_scaling_and_what_it_lacks():
    from nlrha import record_set as RS
    lines = RS.disclosure(_levels(list(range(11)), list(range(11))))
    txt = " ".join(lines)
    lib = RS.library_facts()
    assert lib["name"] in txt and lib["source"] in txt
    assert "no Indian or Himalayan records" in txt and "near-field and long-duration effects" in txt
    assert "0.9 × the target" in txt and "IS 1893 (Part 1):2016 elastic spectrum" in txt and "no R" in txt
    assert "preferably compatible with the design acceleration spectrum in the desired range of natural periods" in txt
    assert "22 analyses" in txt and "× 2.00" in txt
    assert "no scale-factor bounds were set" in txt
    # a user-supplied set is not described as the P-695 set
    lv = _levels(list(range(11)), list(range(11)))
    for p in lv.values():
        p["ground_motions"]["sets"] = [dict(set="PESMOS user folder")]
    txt2 = " ".join(RS.disclosure(lv))
    assert "PESMOS user folder" in txt2 and "Indian or Himalayan" not in txt2


def test_7_7_4_quote_matches_the_corpus():
    corpus = "/home/claude/work/corpus/engineering_rag_india/documents/standards/IS_1893_Part_1_2016/markdown/pages_recovered/page_025.md"
    if not os.path.exists(corpus):
        pytest.skip("India corpus not available")
    from nlrha import record_set as RS
    t = open(corpus, encoding="utf-8").read()
    q = "an appropriate ground motion (preferably compatible with the design acceleration spectrum in the desired range of natural periods)"
    assert q in t
    assert q in " ".join(RS.disclosure(_levels(list(range(11)), list(range(11)))))


def test_shed_rule():
    from snl.shed import shed_basis
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        json.dump(dict(seismic_summary=dict(W_by_floor_kN=[956.1], W_kN=956.1)), open(os.path.join(d, "load_plan.json"), "w"))
        b = shed_basis(d)
        assert b["shed"] and b["floors"] == 1 and b["basis"].startswith("Single-storey") and b["W_kN"] == 956.1
        json.dump(dict(seismic_summary=dict(W_by_floor_kN=[3011.5, 458.9])), open(os.path.join(d, "load_plan.json"), "w"))
        open(os.path.join(d, "cfg.py"), "w").write('cfg = dict(building_type="industrial", occupancy={"use": "warehouse"})\n')
        assert shed_basis(d)["shed"] and "industrial" in shed_basis(d)["basis"]
        open(os.path.join(d, "cfg.py"), "w").write('cfg = dict(occupancy={"use": "office"})\n')
        assert not shed_basis(d)["shed"]


def test_meta_line_has_no_vmax_vb_on_a_shed():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import build_site_index as B
    res = dict(pushover=dict(shed=True, vmax_vb_x=91.6, vmax_vb_y=128.1, vmax_w_x=3.664, vmax_w_y=5.125),
               nlrha=dict(drift_dbe_pct=0.13, drift_mce_pct=0.26, levels=dict(DBE=dict(pairs=11), MCE=dict(pairs=11)),
                          n_records=22, n_converged=22),
               ddm=dict(gravity_lambda=2.163, gravity_lambda_text="2.163", gravity_status="plastic plateau"))
    m = B.meta_line(res)
    assert "Vmax/VB" not in m and "Vmax/W 3.66 / 5.12" in m
    assert "11 record pairs at DBE and MCE: 22/22 analyses converged" in m
    res["pushover"]["shed"] = False
    assert "Vmax/VB 91.6 / 128.1 (Vmax/W 3.66 / 5.12)" in B.meta_line(res)


def test_phi_s_note_says_not_an_is800_factor():
    from steltic_ddm import phi_s
    ph = phi_s.choose("gravity", 5.0, "beam", material="HR", risk_category=None)
    t = phi_s.india_note(ph, 1.174, 0.939)
    assert "not an IS 800 factor" in t and "SSRC 2013 Table 10" in t and "information only" in t
    assert "does not mean the design fails" in t and "B-1.2" in t and "lambda_u = 1.174" in t
    assert "does not mean" not in phi_s.india_note(ph, 1.6, 1.3)
    assert phi_s.india_note(dict(phi_s=None)) is None


def test_peb_four_analyses_page(tmp_path):
    """Ex1 PEB (a shed): the header reads load_plan (not 'VB — kN, W 0.0, R None'), pushover and NLRHA rows show V/W, the
    record pairs / analyses / record set rows and notes are there, and snl report refreshes the stored NLRHA and pushover
    reports (record set; Vmax/W first; mm) idempotently."""
    src = _gold(NL_PEB, "_PEB_factory_shed_tapered_Bengaluru")
    job = _copy_run(src, str(tmp_path / "IN_Ex1"))
    from snl import compare, cli
    compare.build(job)
    h = open(os.path.join(job, "four_analyses.html"), encoding="utf-8").read()
    assert "design VB 29.9 / 39.8 kN (X / Y), W 956 kN, R 4 / 3 (X / Y)" in h
    assert "VB — kN" not in h and "R None" not in h and "W 0.0 kN" not in h
    assert "V/VB" not in h.split("<h2>Notes</h2>")[0]                     # no V/VB in the table of a shed
    assert "V/W = " in h and "Vmax/W = 1.972 / 1.847" in h
    assert "11 record pairs (two horizontal components each), 11 converged" in h
    assert "run at DBE and at MCE: 22 analyses, 22 converged" in h
    assert "no Indian or Himalayan records" in h and "sp3risk.com" in h
    assert "not an IS 800 factor" in h
    cli._refresh_india_reports(job)
    n0 = open(os.path.join(job, "nlrha", "nlrha_report.html"), encoding="utf-8").read()
    assert "record pairs (converged)" in n0 and "Ground-motion record set" in n0 and "suite-mean peak V / W" in n0
    d0 = open(os.path.join(job, "nlrha", "DBE", "nlrha_report.html"), encoding="utf-8").read()
    assert "no Indian or Himalayan records" in d0 and "Scale-factor bounds: None" not in d0
    v0 = open(os.path.join(job, "nlrha", "nlrha_viewer_3d.html"), encoding="utf-8").read()
    assert "22 analyses, 22 converged" in v0 and " 22 records " not in v0.replace("\\u00b7", " ")
    p0 = open(os.path.join(job, "pushover", "pushover_report.html"), encoding="utf-8").read()
    assert "(Vmax/W = 1.972; Vmax/VB = 63.12" in p0 and " in (" not in p0.split("stop:")[1][:120]
    cli._refresh_india_reports(job)                                           # idempotent
    assert open(os.path.join(job, "nlrha", "nlrha_report.html"), encoding="utf-8").read() == n0
    assert open(os.path.join(job, "pushover", "pushover_report.html"), encoding="utf-8").read() == p0
    assert open(os.path.join(job, "nlrha", "nlrha_viewer_3d.html"), encoding="utf-8").read() == v0


def test_multistorey_four_analyses_keeps_vmax_vb(tmp_path):
    src = _gold(NL_GOLD, "_EBF_8levels_Lplan_Pune")
    job = _copy_run(src, str(tmp_path / "IN_Ex15"))
    from snl import compare
    compare.build(job)
    h = open(os.path.join(job, "four_analyses.html"), encoding="utf-8").read()
    assert "V/VB = " in h and "Vmax/VB = " in h and "lower bound" in h            # Ex15 X and Y ended in solver stops
    assert "below 1.0 only through φs (λu 1.173" in h and "does not mean the design fails" in h   # phi_s x lambda_u 0.939


def test_ddm_report_notes_phi_s_and_partial_imposed_basis():
    from steltic_ddm import phi_s, report_ddm as RD
    ph = phi_s.choose("gravity", 5.0, "beam", material="HR", risk_category=None)
    pw = phi_s.choose("wind", 5.0, "beam", material="HR", risk_category=None)
    red = dict(imposed_reduction=dict(fL=1.5, n_columns=99))
    runs = [dict(combo=("1.5DL+1.5LL",), res=dict(lambda_u=1.174), check=(0.939, "INFO"), phi=ph,
                 b12=dict(ok=True, groups=[dict(dc_max=0.9)], **red)),
            dict(combo=("1.2DL+1.2LL+1.2W_X",), res=dict(lambda_u=1.46), check=(1.24, "INFO"), phi=pw,
                 b12=dict(ok=True, groups=[dict(dc_max=0.7)])),
            dict(combo=("1.2DL+1.2LL+1.2EQ_X[ea]",), res=dict(lambda_u=1.5), check=(None, "INFO"), phi=dict(phi_s=None),
                 b12=dict(ok=True, groups=[dict(dc_max=0.7)]))]
    h = RD._phi_s_notes_html(runs)
    assert "is not an IS 800 factor" in h and "HR-G" in h and "HR-W" in h and h.count("does not mean the design fails") == 1
    o = dict(imposed_load_reduction=dict(applied=True))
    t = RD._imposed_basis_by_combo(runs, o)
    assert "1.2DL+1.2LL+1.2W_X" in t and "1.5DL+1.5LL" not in t and "EQ" not in t
    runs[1]["b12"].update(red)
    assert RD._imposed_basis_by_combo(runs, o) == ""
    assert RD._imposed_basis_by_combo(runs, dict(imposed_load_reduction=dict(applied=False))) == ""


def test_stored_basis_text_is_cleaned_for_the_report():
    from steltic_ddm.report_ddm import _stored_text
    old = ("IS 800:2007 4.3.6: notional horizontal force 0.5 %% of factored gravity load -> equivalent out-of-plumb "
           "psi = 1/200 (equivalence, EOR to confirm)")
    t = _stored_text(old)
    assert "0.5 % of" in t and "%%" not in t and "design engineer to confirm" in t and "EOR" not in t


def test_gate_reads_stored_runaways_through_the_guard(tmp_path):
    """IN_Ex18 as published (2026-10-04 set): 1.2DL+1.2LL-1.2W_X stored as a DUCTILITY_CAP after a lambda -732 step. The
    gate now reads it through the NL-36 guard, as the report and the site index do: a runaway reason, never 'complete'."""
    src = _gold(NL_GOLD, "_SMF_podium_11levels_Kochi")
    d = json.load(open(os.path.join(src, "ddm_results.json")))
    if not any(r["label"] == "1.2DL+1.2LL-1.2W_X" and r.get("status") == "DUCTILITY_CAP" for r in d["runs"]):
        pytest.skip("gold no longer holds the stored runaway")
    job = _copy_run(src, str(tmp_path / "IN_Ex18"))
    from nlrha import india_authority as IA
    st = IA.design_status(job_dir=job, evidence={"from_artifact": True})
    rs = " ".join(st["artefact_gate"]["reasons"])
    assert "1.2DL+1.2LL-1.2W_X" in rs and "runaway" in rs and st["status"] != "complete"
