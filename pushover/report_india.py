"""report_india.py -- India pushover supplement (informative, owner ruling D7): pushover_report.html + pushover_package.json.

Displays kN, mm, kN·m, MPa. No IO/LS/CP verdict, no BPON, no ASCE 7 / ASCE 41 limits, no Risk Category.
"""
from __future__ import annotations
import datetime, hashlib, html, json, os

from .postprocess import IS_NL_STATEMENT

KIP_TO_KN = 4.4482216152605
IN_TO_MM = 25.4

CSS = """
body{font-family:Georgia,serif;max-width:1080px;margin:28px auto;padding:0 18px;color:#1b1b1b;line-height:1.45}
h1{font-size:25px;margin-bottom:2px} h2{font-size:18px;border-bottom:2px solid #333;padding-bottom:3px;margin-top:30px}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:8px 0 14px} th,td{border:1px solid #bbb;padding:3px 6px;text-align:right}
th{background:#eee} td:first-child,th:first-child{text-align:left}
.stmt{background:#fff4d6;border-left:5px solid #b8860b;padding:9px 13px;margin:12px 0;font-weight:bold}
.note{background:#f6f6f6;border-left:4px solid #999;padding:8px 12px;font-size:13px;margin:10px 0}
img{max-width:100%}
"""


def _f(v, d=2):
    return "—" if v is None else ("%.*f" % (d, v))


def _png_curve(runs, results, basis):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import base64, io
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    for d, run in runs.items():
        ax.plot([u * IN_TO_MM for u in run["rec"]["u"]], [v * KIP_TO_KN for v in run["rec"]["V"]], lw=1.8, label="push %s" % d)
        for lv, n in results[d]["nsp"].items():
            ax.axvline(n["target_disp_in"] * IN_TO_MM, ls="--", lw=0.9, color="#b3261e" if "MCE" in lv else "#1a3d7c")
    # NL-17: the design base shear of each push direction (V-bar_B of that direction, IS 1893 7.7.3 scaled; NL-6)
    from nlrha.india_hazard import vb_direction_kN
    ind = getattr(basis, "india", None) or {}
    drawn = set()
    for d in runs:
        vb = vb_direction_kN(ind, d) if ind else None
        if vb is None and basis.V_design_kip:
            vb = basis.V_design_kip * KIP_TO_KN
        if vb and round(vb, 1) not in drawn:
            drawn.add(round(vb, 1))
            ax.axhline(vb, color="#555", lw=1, ls=":" if d == "X" else "-.", label="design V̄B %s (IS 1893 7.7.3)" % d)
    ax.set_xlabel("roof displacement (mm)"); ax.set_ylabel("base shear (kN)"); ax.grid(alpha=.3); ax.legend(fontsize=8)
    ax.set_title("Capacity curves; dashed = delta_t at IS-DBE (blue) / IS-MCE (red)", fontsize=10)
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=120, bbox_inches="tight"); plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode("ascii")


def gravity_source(gtable) -> str:
    """'hr_engine' when the NL gravity is the HR engine's seismic-weight state (NL-14 table rows carry HR_EV_kN),
    else 'idealised' (level W_i as equal nodal loads -- the fallback when the HR engine is not importable)."""
    rows = list(gtable or [])
    return "hr_engine" if rows and all(r.get("HR_EV_kN") is not None for r in rows) else "idealised"


def _sha(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return None


def _state(prm, out):
    try:
        from snl import grounding as G
        return G.state(prm, out)[0]
    except Exception:
        return None


def _provenance(prm, out):
    """The component-parameter provenance block (snl.grounding), marked so `snl revise` can replace it in place."""
    try:
        from snl import grounding as G
        st, ev = G.state(prm, out)
        return G.block_html(st, ev, prm)
    except Exception:                                   # never lose a report over a provenance note
        return ""


def write(out, pkg, prm, runs, results, gtable, stats, seconds, modal_info=None):
    b = pkg.basis
    ind = b.india or {}
    ref = results[next(iter(results))].get("ref_rot") if results else None
    pkgj = dict(
        building=pkg.name, jurisdiction="india", generated=datetime.datetime.now().isoformat(timespec="seconds"),
        statement=IS_NL_STATEMENT, acceptance_basis=None, verdict=None,
        display_units="kN, mm, kN·m, MPa (analysis kip-in Stage B)",
        basis=dict(zone=ind.get("zone"), Z=ind.get("Z"), soil=ind.get("soil"), I=ind.get("I"), R_design=ind.get("R"),
                   W_kN=ind.get("W_kN"), VB_kN=ind.get("VB_kN"), VB_x_kN=ind.get("VB_x_kN"), VB_y_kN=ind.get("VB_y_kN"),
                   R_x=ind.get("R_x"), R_y=ind.get("R_y"), Ta_s=ind.get("Ta"), W_kip=b.W_kip,
                   V_design_kip=b.V_design_kip, system=b.system, sources=b.sources),
        hazard=dict(levels={"IS-DBE": "(Z/2)·I·Sa/g", "IS-MCE": "Z·I·Sa/g"}, R_in_target=False,
                    note="Sa(Te) from nlrha.india_hazard.elastic_sa (same function as the NLRHA target, D6)"),
        mass_gate=(pkg.calc or {}).get("_is_mass_gate"),
        materials=stats.get("material_india") if stats else None,
        plasticity=(stats or {}).get("plasticity"), numerics=dict(plasticity=(stats or {}).get("plasticity"),
                                                                  member_nseg=(stats or {}).get("member_nseg")),
        fibre_eles=len((stats or {}).get("fibre_eles") or []), fibre_secs=(stats or {}).get("fibre_secs"),
        restrained_dofs=(stats or {}).get("restrained_zero_stiffness_dofs"),
        gravity=gtable, gravity_source=gravity_source(gtable), reference_rotation=ref, modal=modal_info,
        links=(stats or {}).get("links") or 0,
        params_verified=prm.get("verified"), params_state=_state(prm, out), spec_values_collected=bool(prm.get("spec_values_collected")),
        brace_backbone_note=("post-buckling brace backbone shape: modelling assumption (literature-based; IS 800 / "
                             "IS 18168 give no brace hysteresis) -- information, EOR input"),
        directions={},
    )
    for d, run in runs.items():
        r = results[d]
        pkgj["directions"][d] = dict(
            T1=run["pattern"]["T1"], mode=run["pattern"]["mode"], meff_frac=run["pattern"]["meff_frac"],
            stop_reason=run["stop_reason"], tail=run["tail"], dU_fine_in=run.get("dU_fine"),
            curve_u_in=[float(x) for x in run["rec"]["u"]], curve_V_kip=[float(x) for x in run["rec"]["V"]],
            curve_u_mm=[float(x) * IN_TO_MM for x in run["rec"]["u"]], curve_V_kN=[float(x) * KIP_TO_KN for x in run["rec"]["V"]],
            nsp={lv: dict(n, target_disp_mm=n["target_disp_in"] * IN_TO_MM) for lv, n in r["nsp"].items()},
            capacity=r["capacity"], response=r["resp"])
    os.makedirs(out, exist_ok=True)
    jp = os.path.join(out, "pushover_package.json")
    json.dump(pkgj, open(jp, "w", encoding="utf-8"), indent=1, default=str)

    h = ["<!doctype html><meta charset='utf-8'><title>Pushover (IS, informative)</title><style>%s</style>" % CSS,
         "<h1>Nonlinear static (pushover) analysis — information</h1>",
         "<p>%s · IS 1893 (Part 1):2016 + Amd 1–2 · IS 800:2007 · IS 2062 · generated %s</p>" % (html.escape(pkg.name), pkgj["generated"]),
         "<div class='stmt'>%s</div>" % IS_NL_STATEMENT,
         _provenance(prm, out),
         "<div class='note'>Target displacement δ<sub>t</sub>: coefficient method (C0·C1·C2·Sa·Te²/4π²·g, ASCE 41 form — "
         "no IS procedure exists) with Sa(Te) from the IS 1893 <b>elastic</b> spectrum: IS-DBE = (Z/2)·I·Sa/g, "
         "IS-MCE = Z·I·Sa/g (R not applied). Z = %s, I = %s, soil %s. Mass and gravity = IS seismic weight W = %s kN "
         "(gate %s). Steel: IS 2062 fy by thickness band, expected-strength factor %s.</div>" % (
             ind.get("Z"), ind.get("I"), html.escape(str(ind.get("soil"))), _f(ind.get("W_kN"), 1),
             "ok" if (pkgj["mass_gate"] or {}).get("ok") else "n/a",
             (pkgj["materials"] or [{}])[0].get("factor", 1.0) if pkgj["materials"] else "1.0")]
    h.append("<h2>1 Capacity curves</h2><img src='%s'>" % _png_curve(runs, results, b))
    h.append("<h2>2 Target displacements</h2><table><tr><th>dir</th><th>level</th><th>T1 (s)</th><th>Te (s)</th><th>Sa (g)</th>"
             "<th>C0</th><th>C1</th><th>C2</th><th>δt (mm)</th><th>δt/H</th><th>reached</th></tr>")
    for d, r in results.items():
        for lv, n in r["nsp"].items():
            h.append("<tr><td>%s</td><td>%s</td><td>%.3f</td><td>%.3f</td><td>%.3f</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%.1f</td><td>%.4f</td><td>%s</td></tr>"
                     % (d, lv, runs[d]["pattern"]["T1"], n["Te"], n["Sa"], n["C0"], n["C1"], n["C2"], n["target_disp_in"] * IN_TO_MM,
                        n["target_over_H"], "yes" if n["reached_target"] else "NO"))
    h.append("</table>")
    h.append("<h2>3 Response at δt (interpolated)</h2>")
    for d, r in results.items():
        cap = r["capacity"]
        h.append("<p><b>%s</b>: Vmax = %s kN (Vmax/VB = %s, Vmax/W = %s); curve end %s mm, μ(end) = %s; stop: %s</p>" % (
            d, _f(cap["Vmax_kN"], 0), _f(cap["Vmax_over_VB"], 2), _f(cap["Vmax_over_W"], 3), _f(cap["u_end_in"] * IN_TO_MM, 0),
            _f(cap["mu_end"], 2), html.escape(str(cap["stop_reason"]))))
        h.append("<table><tr><th>level</th><th>roof (mm)</th><th>V (kN)</th><th>V/VB</th><th>max storey drift</th>"
                 "<th>member groups yielded</th><th>brace groups yielded (T)</th><th>braces buckled</th><th>max chord rot (rad)</th><th>IS 800 §12 ref (rad)</th></tr>")
        for lv, a in r["resp"].items():
            mg = (a.get("members") or {}).get("member_groups") or []
            mx = max((g["chord_rot_max_rad"] for g in mg), default=None)
            c = a.get("census") or {}
            h.append("<tr><td>%s</td><td>%.1f</td><td>%.0f</td><td>%s</td><td>%.4f</td><td>%s/%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                lv, a["roof_disp_mm"], a["base_shear_kN"], _f(a["V_over_VB"], 2), a["max_story_drift"],
                c.get("members_yielded", "—"), c.get("member_groups", "—"), c.get("braces_yielded_tension", "—"),
                c.get("braces_buckled", "—"), _f(mx, 5), _f((ref or {}).get("value"), 2)))
        h.append("</table>")
    lvn = [lv for lv in next(iter(results.values()))["resp"]] if results else []
    for d, r in results.items():
        for lv in lvn:
            a = r["resp"][lv]
            mg = (a.get("members") or {}).get("member_groups") or []
            if not mg:
                continue
            h.append("<h3>%s %s — member groups (fibre strain / chord rotation)</h3><table><tr><th>kind</th><th>section</th><th>storey</th><th>n</th>"
                     "<th>ε/εy max</th><th>chord rot max (rad)</th><th>÷ reference</th></tr>" % (d, lv))
            for g in mg:
                h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%d</td><td>%.2f</td><td>%.5f</td><td>%s</td></tr>" % (
                    g["kind"], g["section"], g["level"], g["n"], g["strain_ratio_max"], g["chord_rot_max_rad"], _f(g["ratio_to_reference"], 3)))
            h.append("</table>")
            bg = (a.get("members") or {}).get("brace_groups") or []
            if bg:
                h.append("<table><tr><th>brace section</th><th>storey</th><th>n</th><th>μ tension</th><th>δ/δy compression</th><th>buckled</th></tr>")
                for g in bg:
                    h.append("<tr><td>%s</td><td>%s</td><td>%d</td><td>%.2f</td><td>%.2f</td><td>%d</td></tr>" % (
                        g["section"], g["level"], g["n"], g["mu_tension_max"], g["mu_compression_max"], g["n_buckled_max"]))
                h.append("</table>")
    if ref:
        h.append("<div class='note'>Reference deformation capacity (not an acceptance limit): %s</div>" % "; ".join(
            "%s %.2f rad — %s: “%s”" % (x["what"], x["value"], x["clause"], html.escape(x["quote"])) for x in ref.get("refs", [])))
    if pkgj["materials"]:
        h.append("<h2>4 Steel by section</h2><table><tr><th>section</th><th>role</th><th>grade</th><th>t (mm)</th><th>band</th><th>fy (MPa)</th><th>factor</th></tr>")
        for m in pkgj["materials"]:
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%.0f</td><td>%.2f</td></tr>" % (
                m["section"], m.get("role"), m["grade"], m["t_mm"], m["band"], m["fy_MPa"], m["factor"]))
        h.append("</table>")
    h.append("<p class='note'>Analysis %.0f s. Hinge / brace backbone shapes are modelling assumptions (literature-based; "
             "IS 800, IS 1893 and IS 18168 tabulate none) -- hinge_params verified=%s; IS specification values collected=%s.</p>"
             % (seconds, prm.get("verified"), bool(prm.get("spec_values_collected"))))
    hp = os.path.join(out, "pushover_report.html")
    open(hp, "w", encoding="utf-8").write("\n".join(h))
    return hp
