"""report_india.py -- India NLRHA report + package (owner ruling D7: informative results, IS documents only).

Per level: <out>/<LEVEL>/nlrha_report.html, nlrha_package.json. Index: <out>/nlrha_package.json + nlrha_report.html.
Display units kN, mm, MPa. No ACCEPTABLE/NOT ACCEPTABLE, no ASCE 7 Ch.16 / ASCE 41 limits, no Risk Category.
"""
from __future__ import annotations
import datetime, html, json, os

from .response_summary import IS_NL_STATEMENT
from .report import CSS, _png, fig_scaling

GM_BASIS_INDIA = dict(
    record_library="FEMA P-695 far-field set (22 pairs; PEER NGA) — record library (information)",
    selection_scaling=("selection/scaling rules per EOR; IS 1893 7.7.4 requires motions 'preferably compatible with the "
                       "design acceleration spectrum in the desired range of natural periods'. This tool fits the suite mean "
                       "RotD100 to >= 0.9 x the IS elastic target over [T_lower, T_upper] (EOR-adoptable convention, not IS law)."),
    tectonic_consistency="EOR to confirm (non-Indian crustal records); Indian/regional sets (e.g. PESMOS) can be supplied with --records-set",
    target="IS 1893 elastic spectrum (DBE = (Z/2)·I·Sa/g, MCE = Z·I·Sa/g), 5 % damping, no R (D6)",
)


def _f(v, d=2):
    return "—" if v is None else "%.*f" % (d, v)


def fig_drift_is(summ):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(summ["story"])
    fig, axs = plt.subplots(1, 2, figsize=(8.4, 4.2), sharey=True)
    for d, ax in enumerate(axs):
        for p in summ["per_record"]:
            if p["converged"] and p["storey_drift"]:
                ax.plot([100 * v[d] for v in p["storey_drift"]], range(1, n + 1), color="#9db3cc", lw=0.8)
        ax.plot([100 * (s["mean_X"] if d == 0 else s["mean_Y"]) for s in summ["story"]], range(1, n + 1), color="#1a3d7c",
                lw=2.2, marker="o", label="suite mean")
        ax.set_xlabel("peak storey drift (%%) — %s" % ("X" if d == 0 else "Y")); ax.grid(alpha=.3); ax.legend(fontsize=8)
    axs[0].set_ylabel("storey")
    fig.suptitle("%s — storey drift per record (grey) and suite mean (information)" % summ["level"], fontsize=10)
    return _png(fig)


def _provenance(prm, where):
    """The component-parameter provenance block (snl.grounding), marked so `snl revise` can replace it in place."""
    if prm is None:
        return ""
    try:
        from snl import grounding as G
        st, ev = G.state(prm, where)
        return G.block_html(st, ev, prm)
    except Exception:                                   # never lose a report over a provenance note
        return ""


def elastic_block(results) -> dict:
    """NL-21: the gravity members built elastic -- their first-yield ratio, max over the records of the level."""
    from pushover import elastic_gravity as EG
    peaks, meta = {}, {}
    for r in results or []:
        EG.envelope(peaks, r.get("elastic_peaks") or {})
        meta.update(r.get("elastic_meta") or {})
    if not peaks:
        st = ((results or [{}])[0].get("stats") or {}) if results else {}
        return dict(enabled=bool(st.get("gravity_elastic")), n_elastic=0, flagged_elastic=[])
    out = EG.summary(peaks, meta={int(k): v for k, v in meta.items()})
    out.update(enabled=True, statistic="max over the records of the level")
    return out


def write_level(outdir, pkg, gm, results, summ, modal, numerics, elapsed_s, prm=None):
    os.makedirs(outdir, exist_ok=True)
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    stats = (results[0].get("stats") if results else {}) or {}
    pj = dict(building=pkg.name, jurisdiction="india", generated=ts, level=summ["level"], statement=IS_NL_STATEMENT,
              acceptance_basis=None, verdict=None, target_label=gm.get("target_label"), gm_basis=gm.get("gm_basis"),
              ground_motions={k: v for k, v in gm.items() if k not in ("periods",)},
              modal=modal, numerics=numerics, plasticity=stats.get("plasticity"),
              fibre_eles=len(stats.get("fibre_eles") or []), fibre_secs=stats.get("fibre_secs"),
              materials=stats.get("material_india"), mass_gate=(pkg.calc or {}).get("_is_mass_gate"),
              response_summary=summ, elapsed_s=elapsed_s,
              gravity_source=(numerics or {}).get("gravity_source"), links=stats.get("links") or 0,
              spec_values_collected=bool((prm or {}).get("spec_values_collected")),
              params_verified=(prm or {}).get("verified"),
              elastic_members=elastic_block(results), record_trim=(numerics or {}).get("record_trim"))
    json.dump(pj, open(os.path.join(outdir, "nlrha_package.json"), "w", encoding="utf-8"), indent=1, default=str)
    H = ["<!doctype html><meta charset='utf-8'><style>%s .stmt{background:#fff4d6;border-left:5px solid #b8860b;padding:9px 13px;"
         "margin:12px 0;font-weight:bold}</style><title>NLRHA %s</title>" % (CSS, summ["level"]),
         "<h1>Nonlinear response-history analysis — %s (information)</h1>" % html.escape(summ["level"]),
         "<div class='sub'>%s · IS 1893 (Part 1):2016 + Amd 1–2 7.7.4 · IS 800:2007 · generated %s · %.0f s</div>" % (
             html.escape(pkg.name), ts, elapsed_s),
         "<div class='stmt'>%s</div>" % IS_NL_STATEMENT,
         _provenance(prm, os.path.dirname(os.path.abspath(outdir))),
         "<div class='note'>Target: %s. %s</div>" % (html.escape(str(gm.get("target_label"))),
                                                    html.escape(GM_BASIS_INDIA["selection_scaling"])),
         "<h2>1 Ground motions</h2><figure><img src='%s'></figure>" % fig_scaling(gm),
         "<table><tr><th>#</th><th>record</th><th>scale factor</th><th>converged</th><th>max drift X</th><th>max drift Y</th>"
         "<th>V<sub>X</sub> (kN)</th><th>V<sub>Y</sub> (kN)</th><th>roof X/Y (mm)</th></tr>"]
    for i, p in enumerate(summ["per_record"], 1):
        H.append("<tr><td>%d</td><td>%s</td><td>%.3f</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            i, html.escape(p["label"][:48]), p["sf"], "yes" if p["converged"] else "NO — " + html.escape(str(p["reason"])),
            _f(100 * p["max_drift_X"] if p["max_drift_X"] is not None else None, 3) + " %",
            _f(100 * p["max_drift_Y"] if p["max_drift_Y"] is not None else None, 3) + " %",
            _f(p["base_shear_kN"][0], 0), _f(p["base_shear_kN"][1], 0),
            "%s / %s" % (_f(p["peak_roof_mm"][0], 1), _f(p["peak_roof_mm"][1], 1))))
    H.append("</table><p>Scale-factor bounds: %s%s</p>" % (gm.get("sf_bounds"), (" — " + "; ".join(gm.get("sf_warnings") or [])) if gm.get("sf_warnings") else ""))
    H.append("<h2>2 Storey drifts</h2><figure><img src='%s'></figure><table><tr><th>storey</th><th>h (mm)</th><th>mean X</th>"
             "<th>mean Y</th><th>max X</th><th>max Y</th></tr>" % fig_drift_is(summ))
    for s in summ["story"]:
        H.append("<tr><td>%d</td><td>%.0f</td><td>%s %%</td><td>%s %%</td><td>%s %%</td><td>%s %%</td></tr>" % (
            s["story"], s["h_mm"], _f(100 * s["mean_X"], 3), _f(100 * s["mean_Y"], 3), _f(100 * s["max_X"], 3), _f(100 * s["max_Y"], 3)))
    H.append("</table><p class='note'>For comparison only: IS 1893 7.11.1.1 limits the storey drift of the LINEAR analysis under "
             "the design base shear VB to 0.004 h; it is not a nonlinear acceptance criterion.</p>")
    bs = summ["base_shear"]
    H.append("<h2>3 Base shear</h2><table><tr><th>quantity</th><th>value</th></tr>"
             "<tr><td>suite mean peak V<sub>X</sub> / V<sub>Y</sub> (kN)</td><td>%s / %s</td></tr>"
             "<tr><td>design VB (IS 1893 7.6)</td><td>%s kN — mean/VB = %s</td></tr>"
             "<tr><td>elastic Sa(T1)·W at %s (T1 = %s s, Sa = %s g)</td><td>%s kN — mean/elastic = %s</td></tr></table>" % (
                 _f(bs["mean_X_kN"], 0), _f(bs["mean_Y_kN"], 0), _f(bs["VB_design_kN"], 0), _f(bs.get("mean_over_VB"), 2),
                 summ["level"], _f(bs["T1_s"], 3), _f(bs["Sa_T1_g"], 3), _f(bs["elastic_kN"], 0), _f(bs.get("mean_over_elastic"), 2)))
    if summ.get("ductility"):
        H.append("<p>Displacement ductility demand (peak roof / pushover yield roof displacement): %s</p>" % "; ".join(
            "%s μ mean %.2f, max %.2f (u<sub>y</sub> %.1f mm)" % (d, v["mu_mean"], v["mu_max"], v["uy_mm"]) for d, v in summ["ductility"].items()))
    ref = summ["reference_rotation"]
    H.append("<h2>4 Member deformations (fibre strain, chord rotation)</h2>")
    H.append("<p class='note'>Reference joint-rotation capacity (IS 800 §12, not an acceptance limit): %s</p>" % (
        "; ".join("%.2f rad — %s “%s”" % (x["value"], x["clause"], html.escape(x["quote"])) for x in ref.get("refs", [])) or "n/a"))
    H.append("<table><tr><th>kind</th><th>section</th><th>storey</th><th>n</th><th>ε/εy mean</th><th>ε/εy max</th>"
             "<th>chord rot mean (rad)</th><th>max (rad)</th><th>max ÷ reference</th></tr>")
    for g in summ["member_groups"]:
        H.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%.2f</td><td>%.2f</td><td>%.5f</td><td>%.5f</td><td>%s</td></tr>" % (
            g["kind"], g["section"], g["level"], g["n"], g["strain_ratio_mean"], g["strain_ratio_max"],
            g["chord_rot_mean_rad"], g["chord_rot_max_rad"], _f(g["ratio_to_reference"], 3)))
    H.append("</table>")
    if summ["brace_groups"]:
        H.append("<table><tr><th>brace</th><th>storey</th><th>n</th><th>μ tension mean/max</th><th>δ/δy compression mean/max</th><th>buckled (max)</th></tr>")
        for g in summ["brace_groups"]:
            H.append("<tr><td>%s</td><td>%s</td><td>%d</td><td>%.2f / %.2f</td><td>%.2f / %.2f</td><td>%d</td></tr>" % (
                g["section"], g["level"], g["n"], g["mu_tension_mean"], g["mu_tension_max"], g["mu_compression_mean"],
                g["mu_compression_max"], g["n_buckled_max"]))
        H.append("</table>")
    nv = summ["non_vacuous"]
    em = pj.get("elastic_members") or {}
    tr = pj.get("record_trim") or {}
    H.append("<h2>Modelling disclosures (NL-21)</h2><ul>")
    if em.get("n_elastic"):
        H.append("<li>%s. %d members elastic; largest first-yield ratio %.2f (%s); above 1.0: %s.</li>" % (
            html.escape(em.get("basis") or ""), em["n_elastic"], em.get("max_ratio") or 0.0, em.get("statistic"),
            html.escape(", ".join(str(t) for t in em.get("flagged_elastic") or []) or "none")))
    if tr:
        H.append("<li>Records: %s; free vibration %s s.</li>" % (html.escape(str(tr.get("basis") or tr.get("method"))), tr.get("free_vib_s")))
    H.append("</ul>")
    H.append("<p>Non-vacuous check: %s (rows %d members, %d braces; missing kinds %s)</p>" % (
        "yes" if nv["ok"] else "NO", nv["n_member_rows"], nv["n_brace_rows"], nv["missing_kinds"] or "none"))
    if summ["force_controlled_columns"]:
        H.append("<h2>5 Column axial force vs IS 800 7.1.2 Pd (information)</h2><table><tr><th>section</th><th>z (mm)</th>"
                 "<th>P mean (kN)</th><th>P max (kN)</th><th>Pd (kN)</th><th>max/Pd</th></tr>")
        for r in summ["force_controlled_columns"]:
            H.append("<tr><td>%s</td><td>%.0f</td><td>%.0f</td><td>%.0f</td><td>%.0f</td><td>%.3f</td></tr>" % (
                r["section"], r["z_mm"], r["P_mean_kN"], r["P_max_kN"], r["Pd_kN"], r["ratio_max"]))
        H.append("</table>")
    H.append("<h2>6 Model</h2><p>Plasticity %s; damping %s; accidental torsion %s; mass = IS seismic weight (gate %s); "
             "modes to 90 %% mass: T90 = %s s; spurious modes %s.</p>" % (
                 pj["plasticity"], html.escape(json.dumps(numerics.get("damping"))), html.escape(json.dumps(numerics.get("torsion"))),
                 "ok" if (pj["mass_gate"] or {}).get("ok") else "n/a", _f((modal or {}).get("T90"), 3),
                 (modal or {}).get("spurious_modes")))
    path = os.path.join(outdir, "nlrha_report.html")
    open(path, "w", encoding="utf-8").write("\n".join(H))
    return path


def write_index(out, pkg, level_summaries: dict, modal, numerics, hazard):
    """Top-level nlrha_package.json / nlrha_report.html summarising both levels."""
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    idx = dict(building=pkg.name, jurisdiction="india", generated=ts, statement=IS_NL_STATEMENT, acceptance_basis=None,
               verdict=None, levels={}, modal=modal, numerics=numerics, gm_basis=GM_BASIS_INDIA,
               hazard=dict(Z=hazard["site"]["Z"], I=hazard["site"]["importance_I"], soil=hazard["site"]["soil_type"],
                           levels=hazard["design"]["levels"], R_in_target=False) if hazard else None,
               plasticity=numerics.get("plasticity"))
    for lv, (summ, path) in level_summaries.items():
        idx["levels"][lv] = dict(package=os.path.relpath(path, out), target_label=summ["target_label"],
                                 n_records=summ["n_records"], n_converged=summ["n_converged"],
                                 max_mean_drift=summ["max_mean_drift"], max_peak_drift=summ["max_peak_drift"],
                                 base_shear=summ["base_shear"], ductility=summ["ductility"], non_vacuous=summ["non_vacuous"],
                                 scale_factors=[p["sf"] for p in summ["per_record"]])
    json.dump(idx, open(os.path.join(out, "nlrha_package.json"), "w", encoding="utf-8"), indent=1, default=str)
    H = ["<!doctype html><meta charset='utf-8'><style>%s</style><title>NLRHA (IS, information)</title>" % CSS,
         "<h1>Nonlinear response-history analysis — IS 1893 7.7.4 (information)</h1>",
         "<div class='note'><b>%s</b></div>" % IS_NL_STATEMENT,
         "<table><tr><th>level</th><th>target</th><th>records (converged)</th><th>scale factors</th><th>max mean drift</th>"
         "<th>max peak drift</th><th>mean V / VB</th><th>report</th></tr>"]
    for lv, d in idx["levels"].items():
        sf = d["scale_factors"]
        H.append("<tr><td>%s</td><td>%s</td><td>%d (%d)</td><td>%.3f–%.3f</td><td>%s %%</td><td>%s %%</td><td>%s</td>"
                 "<td><a href='%s/nlrha_report.html'>%s</a></td></tr>" % (
                     lv, html.escape(d["target_label"]), d["n_records"], d["n_converged"], min(sf), max(sf),
                     _f(100 * d["max_mean_drift"] if d["max_mean_drift"] is not None else None, 3),
                     _f(100 * d["max_peak_drift"] if d["max_peak_drift"] is not None else None, 3),
                     _f(d["base_shear"].get("mean_over_VB"), 2), lv, lv))
    H.append("</table>")
    open(os.path.join(out, "nlrha_report.html"), "w", encoding="utf-8").write("\n".join(H))
    return os.path.join(out, "nlrha_package.json")
