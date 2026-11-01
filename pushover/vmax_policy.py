"""vmax_policy.py -- what a public page headlines as the pushover strength (third wave, P10).

The pushover curves of the India runs are pushed far beyond any displacement the IS 1893 hazard asks of the
structure (to 10 % of the height, or a numerical stop), and many reach their peak base shear at 1.8-2.9 m of roof
displacement -- well beyond the deformation capacity of the links, braces and joints, which the analysis does not
limit. So the headline strength is the largest base shear on the curve UP TO the IS-MCE target displacement:

    Vmax(δt,MCE) = max V(u) for 0 <= u <= δt,MCE      (linear interpolation of the curve at δt)

The rest of the curve is still drawn and its peak is stated as information beyond the target, never as the headline.
If the curve ends (numerical stop) before δt,MCE the value is the peak of what was computed, a lower bound ("≥"),
and the page says that the target was not reached.

Te < T1 (the second P10 item): the NSP's bilinear fit gives an effective period Te = Ti sqrt(Ki / Ke). It is below the
elastic period T1 only when the fit's initial stiffness is not the elastic one (e.g. the secant at 0.3 Vmax falls on a
softened part of the curve): the target displacement then rests on an unrepresentative fit, and the pages say so.
"""
from __future__ import annotations

LEVEL = "IS-MCE"
KIP_TO_KN = 4.4482216152605
BASIS = ("Vmax is headlined only up to the IS-MCE target displacement δt: the largest base shear on the curve "
         "from zero to δt. The curve beyond δt is shown, but its peak is information only: it lies beyond the "
         "displacement the IS 1893 hazard asks of the structure, and the analysis does not limit the deformation "
         "capacity of the links, braces and joints that far.")
TE_TOL = 0.01                     # Te more than 1 % below T1 is flagged (rounding of the fit is not a finding)


def _target_mm(dd, level=LEVEL):
    n = ((dd or {}).get("nsp") or {}).get(level) or {}
    if n.get("target_disp_mm") is not None:
        return float(n["target_disp_mm"])
    if n.get("target_disp_in") is not None:
        return float(n["target_disp_in"]) * 25.4
    return None


def _curve(dd):
    u = (dd or {}).get("curve_u_mm")
    V = (dd or {}).get("curve_V_kN")
    if (not u or not V) and (dd or {}).get("curve_u_in") and (dd or {}).get("curve_V_kip"):
        u = [x * 25.4 for x in dd["curve_u_in"]]
        V = [x * KIP_TO_KN for x in dd["curve_V_kip"]]
    return list(u or []), list(V or [])


def full_lower_bound(dd) -> bool:
    """The whole curve's peak is a lower bound when it ended in a numerical stop (scripts/build_site_index.py rule)."""
    cap = (dd or {}).get("capacity") or {}
    tail = cap.get("tail_status") or ((dd or {}).get("tail") or {}).get("status")
    return (tail == "lower_bound") or str((dd or {}).get("stop_reason") or "").startswith("solver")


def vmax_to_target(dd, VB_kN=None, W_kN=None, level=LEVEL) -> dict | None:
    """The headline pushover strength of one direction (module docstring). VB_kN defaults to the direction's design
    base shear recorded in the capacity block (V_design_kip), W_kN to the IS seismic weight from the NSP block."""
    u, V = _curve(dd)
    t = _target_mm(dd, level)
    if not u or t is None:
        return None
    best, u_best = None, None
    reached = False
    for i, (ui, vi) in enumerate(zip(u, V)):
        if ui <= t + 1e-9:
            if best is None or vi > best:
                best, u_best = vi, ui
            if ui >= t - 1e-9:
                reached = True
                break
            continue
        if i > 0 and u[i - 1] < t:                      # interpolate the curve at the target
            f = (t - u[i - 1]) / (ui - u[i - 1])
            vt = V[i - 1] + f * (vi - V[i - 1])
            if best is None or vt > best:
                best, u_best = vt, t
        reached = True
        break
    if best is None:
        return None
    if (((dd or {}).get("nsp") or {}).get(level) or {}).get("reached_target") is False:
        reached = False                                        # the NSP says the curve ended before the target
    cap = (dd or {}).get("capacity") or {}
    if VB_kN is None and cap.get("V_design_kip"):
        VB_kN = float(cap["V_design_kip"]) * KIP_TO_KN
    if W_kN is None:
        n = ((dd or {}).get("nsp") or {}).get(level) or {}
        if n.get("W_kip"):
            W_kN = float(n["W_kip"]) * KIP_TO_KN
    full = cap.get("Vmax_kN")
    if VB_kN is None and full and cap.get("Vmax_over_VB"):          # VB not stored: from the stored ratio
        VB_kN = float(full) / float(cap["Vmax_over_VB"])
    if W_kN is None and full and cap.get("Vmax_over_W"):
        W_kN = float(full) / float(cap["Vmax_over_W"])
    u_full = (float(cap["u_at_Vmax_in"]) * 25.4) if cap.get("u_at_Vmax_in") is not None else None
    if full is None or u_full is None:                         # not in the capacity block: from the curve
        i_pk = max(range(len(V)), key=lambda i: V[i])
        full = V[i_pk] if full is None else full
        u_full = u[i_pk] if u_full is None else u_full
    beyond = None
    if full is not None and u_full is not None and u_full > t and float(full) > best * (1.0 + 1e-6):
        beyond = dict(Vmax_kN=float(full), u_mm=u_full, lower_bound=full_lower_bound(dd),
                      Vmax_over_VB=(float(full) / VB_kN) if VB_kN else None,
                      Vmax_over_W=(float(full) / W_kN) if W_kN else None)
    return dict(level=level, target_mm=t, target_reached=reached, Vmax_kN=best, u_mm=u_best,
                Vmax_over_VB=(best / VB_kN) if VB_kN else None, Vmax_over_W=(best / W_kN) if W_kN else None,
                lower_bound=not reached, beyond=beyond, basis=BASIS)


def te_flags(dd) -> list:
    """[(level, Te, T1)] where the NSP effective period is below the elastic period T1 (module docstring)."""
    T1 = (dd or {}).get("T1")
    out = []
    if not T1:
        return out
    for lv, n in sorted(((dd or {}).get("nsp") or {}).items()):
        Te = n.get("Te")
        if Te is not None and float(Te) < float(T1) * (1.0 - TE_TOL):
            out.append((lv, float(Te), float(T1)))
    return out


def te_note(direction, flags) -> str | None:
    """One sentence for a public page, or None."""
    if not flags:
        return None
    lv = " and ".join("%s Te = %.3f s" % (f[0], f[1]) for f in flags)
    return ("Pushover %s: %s, below the elastic period T1 = %.3f s. The effective period cannot be shorter than the "
            "elastic one; the bilinear fit took its initial stiffness from a softened part of the curve, so the target "
            "displacement from it is uncertain (shown as computed)." % (direction, lv, flags[0][2]))


def strength_text(h, unit="kN", ratio=None) -> str:
    """'9,223 kN' / '≥ 9,223 kN' (lower bound: the curve ended before the IS-MCE target)."""
    ge = "≥ " if h.get("lower_bound") else ""
    if ratio == "VB":
        return ("%s%.1f" % (ge, h["Vmax_over_VB"])) if h.get("Vmax_over_VB") is not None else None
    if ratio == "W":
        return ("%s%.2f" % (ge, h["Vmax_over_W"])) if h.get("Vmax_over_W") is not None else None
    return "%s%s %s" % (ge, "{:,.0f}".format(h["Vmax_kN"]), unit)


def beyond_text(direction, h) -> str | None:
    """Information sentence on the curve beyond the IS-MCE target, or None."""
    b = (h or {}).get("beyond")
    if not b:
        return None
    return ("%s: beyond the IS-MCE target (%.0f mm) the curve continues to %s%s kN at %s mm of roof displacement%s — "
            "information, not the pushover strength" % (
                direction, h["target_mm"], "≥ " if b.get("lower_bound") else "", "{:,.0f}".format(b["Vmax_kN"]),
                "{:,.0f}".format(b["u_mm"]), " (the curve ended in a numerical stop)" if b.get("lower_bound") else ""))
