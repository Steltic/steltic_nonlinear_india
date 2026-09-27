"""A finished India NL job for the Review / Revise / Collect tests (stdlib only).

The design package is the IN_Ex1 fixture (steltic_india IS 800 / IS 1893 SCBF, Delhi zone IV); the analysis
outputs are SYNTHETIC -- small, hand-written, in the exact shapes steltic_nonlinear_india writes them
(nlrha/report_india.py index + per-level packages, pushover/report_india.py, snl/compare.build_india,
steltic_ddm India results). They exercise the readers; they are not an analysis result of IN_Ex1.
"""
import json, os, shutil, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "tests", "fixtures", "IN_Ex1_pkg")
STATEMENT = ("IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; "
             "results are for information.")
REF = {"value": 0.04, "system": "SCBF / SBF CONCENTRIC BRACES",
       "refs": [{"value": 0.04, "what": "joint rotation", "clause": "IS 800:2007 12.8.1",
                 "quote": "joint rotation of at least 0.04 radians without degradation"}]}


def _w(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w", encoding="utf-8"), indent=1)


def _level(lv, f):
    story = [{"story": i + 1, "h_mm": 3600.0, "mean_X": f * (0.0030 + 0.0004 * i), "mean_Y": f * (0.0028 + 0.0003 * i),
              "max_X": f * (0.0045 + 0.0005 * i), "max_Y": f * (0.0041 + 0.0004 * i)} for i in range(5)]
    per = [{"record": "FF%02d" % k, "label": "FEMA P-695 FF%02d" % k, "sf": 1.1 + 0.1 * k, "converged": True, "reason": None,
            "max_drift_X": f * 0.0060, "max_drift_Y": f * 0.0055, "storey_drift": None, "peak_roof_mm": [f * 60.0, f * 55.0],
            "residual_max": f * 0.0004, "base_shear_kN": [f * 2100.0, f * 1950.0], "retry": k == 3} for k in range(1, 8)]
    return {"jurisdiction": "india", "level": lv, "target_label": "IS 1893 elastic %s" % lv, "statement": STATEMENT,
            "acceptance_basis": None, "verdict": None, "n_records": 7, "n_converged": 7, "converged_all": True,
            "per_record": per, "story": story,
            "base_shear": {"mean_X_kN": f * 2100.0, "mean_Y_kN": f * 1950.0, "max_kN": f * 2300.0, "VB_design_kN": 984.72,
                           "elastic_kN": f * 3692.7, "Sa_T1_g": f * 0.25, "T1_s": 0.62, "mean_over_VB": f * 2.133, "mean_over_elastic": 0.569},
            "ductility": {"X": {"uy_mm": 40.0, "mu_mean": f * 1.5, "mu_max": f * 1.9}},
            "member_groups": [{"kind": "beam", "section": "NPB400X180X57.38", "level": 2, "n": 4, "strain_ratio_mean": f * 0.8,
                               "strain_ratio_max": f * 1.1, "chord_rot_mean_rad": f * 0.004, "chord_rot_max_rad": f * 0.006,
                               "ratio_to_reference": f * 0.15},
                              {"kind": "col", "section": "WPB300X300X100.85", "level": 1, "n": 6, "strain_ratio_mean": f * 0.5,
                               "strain_ratio_max": f * 0.7, "chord_rot_mean_rad": f * 0.002, "chord_rot_max_rad": f * 0.003,
                               "ratio_to_reference": f * 0.075}],
            "brace_groups": [{"section": "CHS168.3X6.3", "level": 1, "n": 4, "mu_tension_mean": f * 1.2, "mu_tension_max": f * 1.8,
                              "mu_compression_mean": f * 1.4, "mu_compression_max": f * 2.2, "n_buckled_max": 2}],
            "reference_rotation": REF,
            "force_controlled_columns": [{"ele": 11, "section": "WPB300X300X100.85", "z_mm": 0.0, "P_mean_kN": f * 900.0,
                                          "P_max_kN": f * 1100.0, "Pd_kN": 2600.0, "ratio_max": f * 0.42, "cite": "IS 800:2007 7.1.2"}],
            "non_vacuous": {"ok": True, "sfrs_kinds": ["beam", "brace", "col"], "missing_kinds": [], "n_member_rows": 2, "n_brace_rows": 1},
            "max_mean_drift": f * 0.0046, "max_peak_drift": f * 0.0061}


def make(name="IN_Ex1_SCBF", outputs=True):
    """-> the job folder: the IN_Ex1 package, plus (outputs=True) a finished run's outputs."""
    job = os.path.join(tempfile.mkdtemp(), name)
    shutil.copytree(PKG, job)
    if not outputs:
        return job
    nl = os.path.join(job, "nlrha")
    levels = {}
    for lv, f in (("DBE", 1.0), ("MCE", 2.0)):
        summ = _level(lv, f)
        _w(os.path.join(nl, lv, "nlrha_package.json"), {"building": name, "jurisdiction": "india", "level": lv, "statement": STATEMENT,
                                                         "acceptance_basis": None, "verdict": None, "plasticity": "fibre",
                                                         "materials": [{"section": "NPB400X180X57.38", "grade": "E250", "fy_MPa": 250.0, "factor": 1.0}],
                                                         "response_summary": summ})
        levels[lv] = {"package": os.path.join(lv, "nlrha_package.json"), "target_label": summ["target_label"], "n_records": 7,
                      "n_converged": 7, "max_mean_drift": summ["max_mean_drift"], "max_peak_drift": summ["max_peak_drift"],
                      "base_shear": summ["base_shear"], "ductility": summ["ductility"], "non_vacuous": summ["non_vacuous"],
                      "scale_factors": [p["sf"] for p in summ["per_record"]]}
    _w(os.path.join(nl, "nlrha_package.json"), {"building": name, "jurisdiction": "india", "statement": STATEMENT, "acceptance_basis": None,
                                                "verdict": None, "levels": levels, "modal": {"T1x": 0.62, "T1y": 0.58},
                                                "numerics": {"damping": {"model": "rayleigh", "zeta": 0.025}, "plasticity": "fibre"},
                                                "hazard": {"Z": 0.24, "I": 1.0, "soil": "II", "levels": ["DBE", "MCE"], "R_in_target": False},
                                                "plasticity": "fibre"})
    _w(os.path.join(job, "pushover", "pushover_package.json"), {
        "building": name, "jurisdiction": "india", "statement": STATEMENT, "acceptance_basis": None, "verdict": None,
        "basis": {"zone": "IV", "Z": 0.24, "soil": "II", "I": 1.0, "R_design": 4.5, "W_kN": 14770.8, "VB_kN": 984.72, "system": "SCBF"},
        "params_verified": False, "brace_backbone_note": "post-buckling backbone shape from literature placeholders",
        "plasticity": "fibre", "reference_rotation": REF,
        "directions": {d: {"T1": 0.62, "mode": 1, "meff_frac": 0.81, "stop_reason": "max_drift", "tail": {"status": "max_drift"},
                           "capacity": {"Vmax_kN": 3900.0, "Vmax_over_VB": 3.96, "uy_fit_in": 1.57},
                           "nsp": {"IS-DBE": {"Te": 0.64, "Sa": 0.255, "C0": 1.3, "C1": 1.0, "C2": 1.0, "target_disp_mm": 42.0, "reached_target": True},
                                   "IS-MCE": {"Te": 0.64, "Sa": 0.51, "C0": 1.3, "C1": 1.0, "C2": 1.0, "target_disp_mm": 84.0, "reached_target": True}},
                           "response": {"IS-DBE": {"V_over_VB": 2.4, "max_story_drift": 0.0049}}} for d in ("X", "Y")}})
    _w(os.path.join(job, "ddm_results.json"), {"job": job, "runs": [
        {"label": "1.5DL+1.5LL", "status": "LIMIT_POINT", "lambda_u": 2.41, "lambda_end": 2.41},
        {"label": "1.2DL+1.2LL+1.2EL_X", "status": "LIMIT_POINT", "lambda_u": 1.37, "lambda_end": 1.37}],
        "b12_check": {"ok": True}, "gravity_gate": {"ok": True, "summary": "sum of reactions within 1 %"}, "options": {"india": True}})
    _w(os.path.join(job, "snl_summary.json"), {"jurisdiction": "india", "statement": STATEMENT, "verdict": None,
                                               "design": {"Z": 0.24, "I": 1.0, "R": 4.5, "VB_kN": 984.72, "W_kN": 14770.8},
                                               "nlrha": levels, "pushover": {"X": {"T1": 0.62, "Vmax_kN": 3900.0}}, "ddm": {"b12_ok": True}})
    _w(os.path.join(job, "snl_run.json"), {"started": "2026-09-26T10:00:00", "finished": "2026-09-26T11:10:00",
                                           "steps": {"pushover": {"returncode": 0, "seconds": 600}, "nlrha": {"returncode": 0, "seconds": 3000},
                                                     "ddm": {"returncode": 0, "seconds": 600}}})
    _w(os.path.join(job, "complete_gate.json"), {"status": "COMPLETE", "disclosures": [
        {"id": "india_nsp_acceptance_tables", "found": False, "note": "no IS NSP / hinge acceptance tables"},
        {"id": "asce_16_1_2_drift_relief_analogue", "found": False, "note": "feedback drift loop ineligible"}]})
    hp = json.load(open(os.path.join(ROOT, "pushover", "hinge_params.json"), encoding="utf-8"))
    _w(os.path.join(job, "pushover", "hinge_params_used.json"), hp)
    open(os.path.join(job, "pushover", "pushover_report.html"), "w", encoding="utf-8").write(
        "<html><body><h1>Pushover (IS, informative)</h1><div class=\"banner\">UNVERIFIED MODELLING PARAMETERS — hinge_params.json has verified=false. Backbone and acceptance placeholders.</div><p>curve</p></body></html>")
    return job
