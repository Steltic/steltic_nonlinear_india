"""report_india.py -- India pushover supplement (informative, owner ruling D7): pushover_report.html + pushover_package.json.

Displays kN, mm, kN·m, MPa. No IO/LS/CP verdict, no BPON, no ASCE 7 / ASCE 41 limits, no Risk Category.
"""
from __future__ import annotations
import datetime, hashlib, html, json, os

from .postprocess import IS_NL_STATEMENT

KIP_TO_KN = 4.4482216152605
IN_TO_MM = 25.4


def stop_reason_mm(s):
    """The pushover stop message in mm for the India reports: the analysis runs in kip-in (Stage B) and
    nonlinear_model.pushover writes 'u=17.27 in' / 'roof u=1.84 in'. Every 'u=<x> in' becomes 'u = <25.4 x> mm'; other
    text is unchanged. None stays None."""
    import re
    if not s:
        return s
    return re.sub(r"u=(-?\d+(?:\.\d+)?) in\b", lambda m: "u = %.0f mm" % (float(m.group(1)) * IN_TO_MM), str(s))

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


def _elastic_block(results, stats):
    """NL-21 package block: the gravity members built elastic and their yield check per direction."""
    st = stats or {}
    if not st.get("elastic_members"):
        return dict(enabled=bool(st.get("gravity_elastic")), n_elastic=0, flagged_elastic=[])
    dirs = {d: r.get("elastic") for d, r in (results or {}).items() if r.get("elastic")}
    flagged = sorted({t for e in dirs.values() for t in (e.get("flagged_elastic") or [])})
    from .elastic_gravity import BASIS
    return dict(enabled=True, n_elastic=len(st["elastic_members"]), flagged_elastic=flagged, directions=dirs,
                max_ratio=max([e.get("max_ratio") or 0.0 for e in dirs.values()] or [0.0]), basis=BASIS)


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


SHED_MARK_START = "<!-- steltic:shed-base-shear-note -->"
SHED_MARK_END = "<!-- /steltic:shed-base-shear-note -->"


def shed_note_html(shed):
    """Second wave (review E_NL item 15): on a shed the strength coefficient Vmax/W is the headline, not Vmax/VB."""
    return ("%s<div class='note'><b>%s: Vmax/W is the headline here.</b> VB is the R-reduced IS 1893 design base shear, which "
            "is small for a light shed, so Vmax/VB is large and is not a measure of the structure's reserve; Vmax/W "
            "(W the IS 1893 seismic weight%s) is the strength coefficient.</div>%s" % (
                SHED_MARK_START, html.escape(shed.get("basis") or "Shed"),
                (", %s kN" % format(round(shed["W_kN"]), ",")) if shed.get("W_kN") else "", SHED_MARK_END))


def footer_words(verified, collected):
    """The provenance footer in words (was 'hinge_params verified=False; IS specification values collected=True')."""
    return "%s; %s" % ("the hinge parameters are verified" if str(verified) == "True" or verified is True else
                       "the hinge parameters are not verified against an IS table (none exists)",
                       "the IS specification values were collected from the IS corpus" if str(collected) == "True" or collected is True
                       else "the IS specification values were not collected")


REVIEW_MARK_START = "<!-- steltic:pushover-review -->"
REVIEW_MARK_END = "<!-- /steltic:pushover-review -->"
VMAX_MARK_START = "<!-- steltic:vmax-to-mce-target -->"
VMAX_MARK_END = "<!-- /steltic:vmax-to-mce-target -->"


def vmax_block_html(pkg) -> str:
    """Third wave, P10: the headline strength of each direction -- the peak UP TO the IS-MCE target displacement
    (pushover/vmax_policy.py) -- with the curve beyond the target as information and any Te < T1 flag. Marked, so a
    refresh replaces it in place."""
    from . import vmax_policy as VP
    rows, notes = [], []
    for d, dd in sorted(((pkg or {}).get("directions") or {}).items()):
        h = VP.vmax_to_target(dd)
        if h is None:
            continue
        rows.append("<tr><td>%s</td><td>%.1f%s</td><td>%s</td><td>%.1f</td><td>%s</td><td>%s</td></tr>" % (
            d, h["target_mm"], "" if h["target_reached"] else " (not reached: the curve ended before it)",
            VP.strength_text(h), h["u_mm"] or 0.0, VP.strength_text(h, ratio="VB") or "—", VP.strength_text(h, ratio="W") or "—"))
        bt = VP.beyond_text(d, h)
        if bt:
            notes.append(bt + ".")
        tn = VP.te_note(d, VP.te_flags(dd))
        if tn:
            notes.append(tn)
    if not rows:
        return ""
    return ("%s<p><b>Pushover strength (headline): Vmax up to the IS-MCE target displacement</b></p><table><tr><th>dir</th>"
            "<th>IS-MCE δt (mm)</th><th>Vmax up to δt</th><th>at roof u (mm)</th><th>Vmax/VB</th><th>Vmax/W</th></tr>%s</table>"
            "<div class='note'>%s%s</div>%s" % (VMAX_MARK_START, "".join(rows), html.escape(VP.BASIS),
                                                "".join("<br>" + html.escape(n) for n in notes), VMAX_MARK_END))


LOWER_BOUND_WORDS = "a lower bound: the curve ended in a numerical stop before it lost strength, so the peak is not established"


def _lower_bound(dd):
    cap = (dd or {}).get("capacity") or {}
    tail = cap.get("tail_status") or ((dd or {}).get("tail") or {}).get("status")
    return tail == "lower_bound" or str((dd or {}).get("stop_reason") or "").startswith("solver")


def _direction_segment(h, d):
    """(start, end) of direction d's section-3 block: its '<p><b>d</b>' line up to the end of its response table."""
    i = h.find("<p><b>%s</b>" % d)
    if i < 0:
        return None
    j = h.find("</table>", i)
    return (i, j + len("</table>")) if j > 0 else None


def _check_fixes(h, pkg, review):
    """2026-10 check fixes on the report text (findings 1, 2, 4, 5, 6): '≥' on a lower-bound Vmax, the IS target a
    curve did not reach, 'under review' (pushover/review.py), '—' for a steel without a thickness band, no ticket ids,
    no 'EOR'. Every value comes from the stored package; idempotent."""
    import re
    from snl.public_text import scrub_html
    dirs = (pkg or {}).get("directions") or {}
    for d, dd in dirs.items():
        if _lower_bound(dd):                                # finding 2
            seg = _direction_segment(h, d)
            if seg:
                a, b = seg
                line_end = h.find("</p>", a)
                line = h[a:line_end]
                if "Vmax = " in line:
                    new = line.replace("Vmax = ", "Vmax ≥ ", 1)
                    new = re.sub(r"(Vmax/(?:VB|W)) = ", r"\1 ≥ ", new)
                    new = new.replace("; curve end", " — %s; curve end" % LOWER_BOUND_WORDS, 1)
                    h = h[:a] + new + h[line_end:]
        for lv, n in (dd.get("nsp") or {}).items():         # finding 1
            if n.get("reached_target") is not False:
                continue
            r = (dd.get("response") or {}).get(lv) or {}
            end = r.get("roof_disp_mm")
            if end is None and (dd.get("capacity") or {}).get("u_end_in") is not None:
                end = float(dd["capacity"]["u_end_in"]) * IN_TO_MM
            h = re.sub(r"(<tr><td>%s</td><td>%s</td>(?:<td>[^<]*</td>){8})<td>NO</td>" % (re.escape(d), re.escape(lv)),
                       lambda m: m.group(1) + "<td>NO — the curve ended at %.0f mm</td>" % (end or 0), h)
            seg = _direction_segment(h, d)
            if seg:
                a, b = seg
                part = h[a:b].replace("<tr><td>%s</td>" % lv, "<tr><td>%s (curve end: the %.1f mm target was not "
                                      "reached; values at the curve end)</td>" % (lv, n.get("target_disp_mm") or 0), 1)
                h = h[:a] + part + h[b:]
            h = h.replace("<h3>%s %s — member groups" % (d, lv),
                          "<h3>%s %s at the curve end (%.0f mm; target not reached) — member groups" % (d, lv, end or 0), 1)
    # third wave, P10: the strength up to the IS-MCE target is the headline; the whole-curve peak is information
    if VMAX_MARK_START in h and VMAX_MARK_END in h:
        h = h[:h.index(VMAX_MARK_START)] + h[h.index(VMAX_MARK_END) + len(VMAX_MARK_END):]
    vb_html = vmax_block_html(pkg)
    if vb_html:
        h = h.replace("<h2>3 Response at δt (interpolated)</h2>", "<h2>3 Response at δt (interpolated)</h2>" + vb_html, 1)
        for d in dirs:
            h = h.replace("<p><b>%s</b>: Vmax " % d, "<p><b>%s</b>: whole-curve peak (information) Vmax " % d, 1)
    # finding 4: the review note at the top, 'UNDER REVIEW' on the direction's line; removed when the record goes
    if REVIEW_MARK_START in h and REVIEW_MARK_END in h:
        h = h[:h.index(REVIEW_MARK_START)] + h[h.index(REVIEW_MARK_END) + len(REVIEW_MARK_END):]
    h = re.sub(r" <span class='rv'>\(UNDER REVIEW[^<]*\)</span>", "", h)
    if review:
        from .review import note_text_of
        block = "%s%s%s" % (REVIEW_MARK_START, "".join(
            "<div class='stmt' style='border-left-color:#b3261e;background:#fdecea'>%s</div>" % html.escape(
                note_text_of(e)) for d, e in sorted(review.items())), REVIEW_MARK_END)
        h = h.replace("<h2>1 Capacity curves</h2>", block + "<h2>1 Capacity curves</h2>", 1)
        for d in review:
            h = h.replace("<p><b>%s</b>:" % d, "<p><b>%s</b> <span class='rv'>(UNDER REVIEW, see the note at the top)</span>:" % d, 1)
    h = re.sub(r" -- hinge_params verified=(True|False|None); IS specification values collected=(True|False)\.",
               lambda m: " -- %s." % footer_words(m.group(1), m.group(2)), h)
    # finding 5: no 'None' in the steel table (YSt 310 tubes have no IS 2062 thickness band)
    i = h.find("<h2>4 Steel by section</h2>")
    if i >= 0:
        j = h.find("</table>", i)
        if j > 0:
            h = h[:i] + h[i:j].replace("<td>None</td>", "<td>—</td>") + h[j:]
    return scrub_html(h)                                    # findings 3 and 6: no ticket ids, no 'EOR'


def refresh_report(pushover_dir, shed=None):
    """Report-only refresh of a stored India pushover report: stop messages in mm ('u=17.27 in' -> 'u = 439 mm', the
    first-wave fix, which reached only re-run pushovers) and, on a shed, the note above section 3 and Vmax/W before
    Vmax/VB in each direction's line; 2026-10 check fixes (`_check_fixes`): '≥' on a lower-bound Vmax, the target a curve
    did not reach, 'under review', no 'None', no ticket ids, no 'EOR'. Idempotent; returns True when the file changed."""
    import re
    p = os.path.join(pushover_dir, "pushover_report.html")
    if not os.path.exists(p):
        return False
    h0 = h = open(p, encoding="utf-8").read()
    h = re.sub(r"(; stop: )([^<]*)(</p>)", lambda m: m.group(1) + stop_reason_mm(m.group(2)) + m.group(3), h)
    if shed and shed.get("shed"):
        note = shed_note_html(shed)
        if SHED_MARK_START in h and SHED_MARK_END in h:
            h = h[:h.index(SHED_MARK_START)] + note + h[h.index(SHED_MARK_END) + len(SHED_MARK_END):]
        else:
            h = h.replace("<h2>3 Response at δt (interpolated)</h2>", "<h2>3 Response at δt (interpolated)</h2>" + note, 1)
        h = re.sub(r"\(Vmax/VB = ([^,()]+), Vmax/W = ([^()]+?)\)",
                   lambda m: "(Vmax/W = %s; Vmax/VB = %s, VB R-reduced, see the note above)" % (m.group(2), m.group(1)), h)
    try:
        pkg = json.load(open(os.path.join(pushover_dir, "pushover_package.json"), encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        pkg = {}
    from .review import directions_under_review
    h = _check_fixes(h, pkg, directions_under_review(os.path.dirname(os.path.abspath(pushover_dir))))
    if h != h0:
        open(p, "w", encoding="utf-8").write(h)
        return True
    return False


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
        elastic_members=_elastic_block(results, stats),
        params_verified=prm.get("verified"), params_state=_state(prm, out), spec_values_collected=bool(prm.get("spec_values_collected")),
        brace_backbone_note=("post-buckling brace backbone shape: modelling assumption (literature-based; IS 800 / "
                             "IS 18168 give no brace hysteresis) -- information, design engineer's input"),
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
    try:                                                     # second wave: on a shed Vmax/W, not Vmax/VB, comes first
        from snl.shed import shed_basis
        shed = shed_basis(str(pkg.root))
    except Exception:                                        # noqa: BLE001
        shed = dict(shed=False)
    if shed.get("shed"):
        h.append(shed_note_html(shed))
    for d, r in results.items():
        cap = r["capacity"]
        ratios = (("Vmax/W = %s; Vmax/VB = %s, VB R-reduced, see the note above" if shed.get("shed") else "Vmax/VB = %s, Vmax/W = %s")
                  % ((_f(cap["Vmax_over_W"], 3), _f(cap["Vmax_over_VB"], 2)) if shed.get("shed") else
                     (_f(cap["Vmax_over_VB"], 2), _f(cap["Vmax_over_W"], 3))))
        h.append("<p><b>%s</b>: Vmax = %s kN (%s); curve end %s mm, μ(end) = %s; stop: %s</p>" % (
            d, _f(cap["Vmax_kN"], 0), ratios, _f(cap["u_end_in"] * IN_TO_MM, 0),
            _f(cap["mu_end"], 2), html.escape(str(stop_reason_mm(cap["stop_reason"])))))
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
    em = pkgj.get("elastic_members") or {}
    if em.get("n_elastic"):
        h.append("<h2>Gravity members modelled elastic (disclosure)</h2><p class='note'>%s. %d members elastic; largest "
                 "first-yield ratio up to the IS-MCE target %.2f; members above 1.0: %s.</p>"
                 % (html.escape(em.get("basis") or ""), em["n_elastic"], em.get("max_ratio") or 0.0,
                    html.escape(", ".join(str(t) for t in em.get("flagged_elastic") or []) or "none")))
    h.append("<p class='note'>Analysis %.0f s. Hinge / brace backbone shapes are modelling assumptions (literature-based; "
             "IS 800, IS 1893 and IS 18168 tabulate none) -- %s.</p>" % (seconds, footer_words(prm.get("verified"), prm.get("spec_values_collected"))))
    hp = os.path.join(out, "pushover_report.html")
    open(hp, "w", encoding="utf-8").write("\n".join(h))
    try:                                                     # 2026-10 check fixes: the same text as a refreshed report
        refresh_report(out)
    except Exception:                                        # noqa: BLE001 -- never lose a report over its wording
        pass
    return hp
