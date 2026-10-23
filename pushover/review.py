"""review.py -- pushover directions put "under review" from their stored results (2026-10 check fixes, finding 4).

A pushover direction is put under review by a person, not by a rule: `scripts/pushover_review.py` reads the stored
pushover package (and, when asked, the NLRHA packages), computes the evidence below and writes
<job>/pushover/pushover_review.json. Every number in the record is computed from the stored results; nothing is
re-analysed. The four-analyses sheet, the pushover report (on `snl report`) and the site index read the record and say
"under review" wherever that direction's results are printed.

Evidence (`evidence(pkg, d, ...)`):
  * the largest one-step loss of base shear before Vmax (a sudden loss in a pushover of a ductile frame needs an
    explanation: a brace buckling, a fracture -- or a modelling fault);
  * where Vmax is reached (roof displacement, and as a share of the height) and how far that is beyond the IS-MCE target;
  * the bilinear fit: Te = T1 sqrt(Ki / Ke) with Ki the secant at 0.3 Vmax (pushover.postprocess.initial_stiffness); a
    Ki below the initial slope (Te below T1) means the fit took Ki on the curve after a loss of strength;
  * the EBF link rotations at the IS-DBE / IS-MCE targets against the storey drift. A mid-span (chevron) link of length
    e in a bay of length L rotates about L / e times the storey drift (rigid-plastic kinematics); a link rotation many
    times that is not compatible with the frame's deformation. The other push direction of the same model is the
    comparison.

Record format (pushover_review.json):
  {"date": "...", "basis": "...", "directions": {"Y": {"status": "under_review", "summary": "...",
   "findings": ["...", ...], "nlrha": "..." | null, "evidence": {...}}}}
"""
from __future__ import annotations

import datetime
import json
import os

UNDER_REVIEW = "under_review"
RECORD = "pushover_review.json"
LABEL = "under review"


def _j(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                                  # noqa: BLE001
        return None


def record_path(job):
    return os.path.join(job, "pushover", RECORD)


def load(job):
    """The review record of a job ({} when there is none)."""
    return _j(record_path(job)) or {}


def directions_under_review(job):
    """{direction: entry} for the directions whose status is under review."""
    return {d: e for d, e in ((load(job).get("directions") or {}).items())
            if isinstance(e, dict) and e.get("status") == UNDER_REVIEW}


def summary(job, d):
    e = directions_under_review(job).get(d)
    return (e or {}).get("summary")


# ------------------------------------------------------------------------------------------------ evidence
def _fmt(v, n=0):
    return format(round(float(v), n), ",.%df" % n)


def link_rotation(resp):
    """(largest link rotation in rad, max storey drift) at one target, from the stored response; (None, drift) when the
    package has no link groups."""
    lg = ((resp or {}).get("members") or {}).get("link_groups") or []
    g = max((x.get("gamma_max_rad") or 0.0 for x in lg), default=None)
    return g, (resp or {}).get("max_story_drift")


def evidence(pkg, d, l_over_e=None):
    """Facts of one push direction, from the stored package only."""
    dd = (pkg.get("directions") or {})[d]
    u = [float(x) for x in dd.get("curve_u_mm") or []]
    V = [float(x) for x in dd.get("curve_V_kN") or []]
    out = dict(direction=d, T1=dd.get("T1"))
    if not u or not V:
        return out
    vmax = max(V)
    im = V.index(vmax)
    drop = None
    for i in range(1, im + 1):
        if V[i - 1] > 0 and (drop is None or (V[i - 1] - V[i]) / V[i - 1] > drop["fraction"]):
            drop = dict(step=i, u_from_mm=u[i - 1], u_to_mm=u[i], V_from_kN=V[i - 1], V_to_kN=V[i],
                        fraction=(V[i - 1] - V[i]) / V[i - 1])
    if drop and drop["fraction"] <= 0:
        drop = None
    nsp = dd.get("nsp") or {}
    H = None
    for n in nsp.values():
        if n.get("target_over_H") and n.get("target_disp_mm"):
            H = n["target_disp_mm"] / n["target_over_H"]
            break
    i0 = next((i for i in range(1, len(u)) if u[i] > 0), None)
    out.update(Vmax_kN=vmax, u_at_Vmax_mm=u[im], u_end_mm=u[-1], H_mm=H, drop=drop,
               initial_slope_kN_mm=(V[i0] / u[i0]) if i0 else None,
               stop=(dd.get("capacity") or {}).get("stop_reason") or dd.get("stop_reason"),
               lower_bound=((dd.get("capacity") or {}).get("tail_status") == "lower_bound"))
    lv = {}
    for name, n in nsp.items():
        r = (dd.get("response") or {}).get(name) or {}
        g, dr = link_rotation(r)
        lv[name] = dict(target_mm=n.get("target_disp_mm"), reached=n.get("reached_target"), Te=n.get("Te"),
                        Ki_over_Ke=(n["Ki"] / n["Ke"]) if n.get("Ki") and n.get("Ke") else None,
                        roof_mm=r.get("roof_disp_mm"), V_over_VB=r.get("V_over_VB"), drift=dr, link_rot=g,
                        link_rot_kinematic=(l_over_e * dr) if (l_over_e and dr) else None,
                        census=r.get("census"))
    out["levels"] = lv
    out["l_over_e"] = l_over_e
    return out


def nlrha_link_evidence(job):
    """Largest link rotation and the largest peak storey drift per NLRHA level (stored packages)."""
    out = {}
    for lvl in ("DBE", "MCE"):
        p = _j(os.path.join(job, "nlrha", lvl, "nlrha_package.json")) or {}
        rs = p.get("response_summary") or {}
        lg = rs.get("link_groups") or []
        if lg:
            out[lvl] = dict(link_rot=max(x.get("gamma_max_rad") or 0.0 for x in lg), peak_drift=rs.get("max_peak_drift"))
    return out


def findings(ev, other=None, nl=None):
    """Plain sentences for the record, from `evidence` of the direction (and of the other direction, for comparison)."""
    d = ev["direction"]
    out = []
    dr = ev.get("drop")
    lv = ev.get("levels") or {}
    dbe = lv.get("IS-DBE") or {}
    if dr and dr["fraction"] >= 0.10:
        c = dbe.get("census") or {}
        tail = ""
        if c and dbe.get("roof_mm") and dbe["roof_mm"] >= dr["u_to_mm"]:
            only_links = (not c.get("braces_buckled") and not c.get("members_yielded")
                          and not c.get("braces_yielded_tension") and c.get("links_yielded"))
            tail = (" At the next reported point (the IS-DBE target, %s mm) %s brace has buckled and %s beam or column "
                    "fibre has yielded%s." % (
                        _fmt(dbe["roof_mm"], 1), "no" if not c.get("braces_buckled") else str(c["braces_buckled"]),
                        "no" if not c.get("members_yielded") else str(c["members_yielded"]),
                        "; only links have" if only_links else ""))
        out.append("Between %s and %s mm of roof displacement the base shear falls from %s kN to %s kN in one step, a "
                   "loss of %.0f %%.%s" % (_fmt(dr["u_from_mm"], 1), _fmt(dr["u_to_mm"], 1), _fmt(dr["V_from_kN"]),
                                           _fmt(dr["V_to_kN"]), 100 * dr["fraction"], tail))
    rot = [(name, x) for name, x in lv.items() if x.get("link_rot") is not None and x.get("drift")]
    if rot:
        parts = ["%s %.2f rad at %.2f %% storey drift" % (name, x["link_rot"], 100 * x["drift"]) for name, x in rot]
        s = ("The largest EBF link rotation at the targets is %s, about %.0f times the 0.08 rad link rotation angle of IS "
             "18168 12.3.3.1 (a reference here, not an acceptance limit)." % (
                 "; ".join(parts), max(x["link_rot"] for _, x in rot) / 0.08))
        if ev.get("l_over_e"):
            k = [x for _, x in rot if x.get("link_rot_kinematic")]
            if k:
                s += (" A mid-span link of length e in a bay of length L rotates about L / e times the storey drift "
                      "(here L / e = %.1f), so about %s rad at these drifts." % (
                          ev["l_over_e"], " / ".join("%.3f" % x["link_rot_kinematic"] for x in k)))
        if other:
            o_rot = [(name, x) for name, x in (other.get("levels") or {}).items() if x.get("link_rot") is not None and x.get("drift")]
            if o_rot:
                name, x = o_rot[0]
                lim = (ev["l_over_e"] * x["drift"] * 1.5) if ev.get("l_over_e") else None
                s += (" In the %s direction the same model gives %.3f rad at %.2f %% drift (%s)%s." % (
                    other["direction"], x["link_rot"], 100 * x["drift"], name,
                    ", in line with that" if (lim is not None and x["link_rot"] <= lim) else ""))
        s += " The link rotations in this direction are therefore not compatible with the frame's drift."
        out.append(s)
    H = ev.get("H_mm")
    if ev.get("Vmax_kN") and ev.get("u_at_Vmax_mm") is not None:
        s = "Vmax (%s kN) is reached at a roof displacement of %s mm%s" % (
            _fmt(ev["Vmax_kN"]), _fmt(ev["u_at_Vmax_mm"]), (" (%.1f %% of the %.1f m height)" % (100 * ev["u_at_Vmax_mm"] / H, H / 1000)) if H else "")
        if dr and dr["fraction"] >= 0.10 and ev["u_at_Vmax_mm"] > dr["u_to_mm"]:
            s += ", after the loss of strength above, and is %.1f times the %s kN reached before it" % (
                ev["Vmax_kN"] / dr["V_from_kN"], _fmt(dr["V_from_kN"]))
        s += "; the curve ends at %s mm in a numerical stop%s." % (
            _fmt(ev["u_end_mm"]), "" if not ev.get("lower_bound") else ", so Vmax is a lower bound")
        out.append(s)
    fit = [(name, x) for name, x in lv.items() if x.get("Te") and ev.get("T1") and x["Te"] < 0.95 * ev["T1"]]
    if fit and ev.get("initial_slope_kN_mm"):
        ki = (lv[fit[0][0]].get("Ki_over_Ke") or 0)
        out.append("The bilinear fit takes its initial stiffness as the secant at 0.3 Vmax, which here lies on the curve "
                   "after the loss of strength: Te is %s, below T1 = %.3f s (Ki / Ke = %.2f). The targets (%s) and the "
                   "responses at them come from that fit." % (
                       ", ".join("%.3f s at %s" % (x["Te"], name) for name, x in fit), ev["T1"], ki,
                       ", ".join("%s mm at %s" % (_fmt(x["target_mm"], 1), name) for name, x in lv.items() if x.get("target_mm"))))
    unreached = [(name, x) for name, x in lv.items() if x.get("reached") is False]
    for name, x in unreached:
        out.append("The %s target (%s mm) is not reached: the curve ends at %s mm." % (
            name, _fmt(x["target_mm"], 1), _fmt(ev["u_end_mm"], 1)))
    return out


def nlrha_sentence(nl):
    if not nl:
        return None
    return ("The NLRHA uses the same link model, and its link rotations show the same pattern (%s), so its link results "
            "are part of the same review; its drifts and base shears are shown as computed." % "; ".join(
                "%s up to %.2f rad at a peak storey drift of %.2f %%" % (lvl, x["link_rot"], 100 * (x.get("peak_drift") or 0))
                for lvl, x in nl.items()))


def summary_sentence(d, ev):
    dr = ev.get("drop")
    bits = []
    if dr and dr["fraction"] >= 0.10:
        bits.append("a one-step loss of %.0f %% of the base shear at %s mm" % (100 * dr["fraction"], _fmt(dr["u_to_mm"])))
    if any((x.get("link_rot") or 0) > 0.08 for x in (ev.get("levels") or {}).values()):
        bits.append("EBF link rotations not compatible with the storey drift")
    if ev.get("H_mm") and ev.get("u_at_Vmax_mm") and ev["u_at_Vmax_mm"] > 0.05 * ev["H_mm"]:
        bits.append("a peak at %s mm of roof displacement" % _fmt(ev["u_at_Vmax_mm"]))
    return ("Pushover %s under review: the curve is not physically credible as it stands (%s); its Vmax, target "
            "displacements and responses are not to be relied on until the cause is found." % (d, "; ".join(bits) or "see the findings"))


def make_record(job, directions, l_over_e=None, with_nlrha=False, date=None):
    """The review record for `directions` of one job, every number from the stored packages."""
    pkg = _j(os.path.join(job, "pushover", "pushover_package.json")) or {}
    if not pkg.get("directions"):
        raise ValueError("no stored pushover package in %s" % job)
    nl = nlrha_link_evidence(job) if with_nlrha else {}
    rec = dict(date=date or datetime.date.today().isoformat(),
               basis="read from the stored pushover%s packages; no analysis was re-run" % (" and NLRHA" if nl else ""),
               directions={})
    for d in directions:
        ev = evidence(pkg, d, l_over_e)
        others = [x for x in pkg["directions"] if x != d]
        oev = evidence(pkg, others[0], l_over_e) if others else None
        rec["directions"][d] = dict(status=UNDER_REVIEW, summary=summary_sentence(d, ev), findings=findings(ev, oev, nl),
                                    nlrha=nlrha_sentence(nl), evidence=ev)
    return rec


def write_record(job, rec):
    p = record_path(job)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1, default=str)
    return p


def note_text_of(e):
    """One paragraph for a page from a record entry: the summary, the findings and the NLRHA sentence."""
    return " ".join([e.get("summary") or ""] + list(e.get("findings") or []) + ([e["nlrha"]] if e.get("nlrha") else [])).strip()


def note_text(job, d):
    e = directions_under_review(job).get(d)
    return note_text_of(e) if e else None
