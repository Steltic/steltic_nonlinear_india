"""vmax_policy.py -- what a public page headlines from a pushover curve (third wave, P10; review M1, M2).

The India pushover curves are pushed far beyond any displacement the IS 1893 hazard asks of the structure (to 10 % of
the height, or a numerical stop); many peak at 1-3 m of roof displacement, beyond the deformation capacity of links,
braces and joints, which the analysis does not limit. So the headline is read on the curve from zero to the IS-MCE
target displacement δt only, and it says what kind of number it is (`kind`):

  peak       the curve has its maximum on [0, δt] before δt, or at δt with the curve falling after it: the largest base
             shear within the hazard's displacement, "Vmax up to the IS-MCE target" -- a peak, which may be a local
             one (peak_analysed states a higher peak beyond δt);
  at_target  the maximum on [0, δt] is at δt and the curve is still rising there: the headline is the BASE SHEAR AT
             δt, a demand governed by stiffness, NOT a strength (and not "≥ strength": nothing about the strength
             beyond δt is claimed); its ratios are V(δt)/VB and V(δt)/W, never Vmax/VB;
  ended      the curve ended (numerical stop) before δt: the headline is the peak of the computed curve; "≥" only if the
             curve was still rising at its end (the strength is then at least that value), else it is a peak.

Separately, always: the peak of the analysed curve (`peak_analysed`: the largest base shear over the whole computed
curve, with its roof displacement) -- information; when it lies beyond δt it is beyond what the hazard asks.

Te (review M2): the NSP effective period Te = Ti sqrt(Ki / Ke) (ASCE 41-17 Eq. 7-27, Ki the elastic lateral stiffness).
With Ki the elastic stiffness, Te >= T1. Flagged: Te < T1 (Ki was not the elastic stiffness: a package computed
before the M2 fix) and Te > TE_HIGH x T1 (Ke far below Ki: the curve softens early, δt rests on a strongly non-linear
fit) -- both shown as computed.
"""
from __future__ import annotations

LEVEL = "IS-MCE"
KIP_TO_KN = 4.4482216152605
BASIS = ("The headline is read on the pushover curve up to the IS-MCE target displacement δt only. Where the curve "
         "reaches its peak before δt, the headline is that strength (Vmax up to the IS-MCE target). Where the curve is "
         "still rising at δt, the headline is the base shear at δt: a demand at the target, not the strength, which lies "
         "beyond δt. Where the curve ended before δt, the headline is the peak of what was computed (≥ when it was still "
         "rising). The peak of the whole analysed curve is stated separately as information: beyond δt it lies beyond "
         "the displacement the IS 1893 hazard asks of the structure, and the analysis does not limit the deformation "
         "capacity of the links, braces and joints that far.")
TE_TOL = 0.01                     # Te more than 1 % below T1 is flagged (rounding of the fit is not a finding)
TE_HIGH = 1.5                     # Te above 1.5 T1 (Ke below 0.44 Ki) is flagged: a review threshold, not a code value
REL = 1e-6

LABELS = {"peak": "Vmax up to the IS-MCE target",
          "at_target": "Base shear at the IS-MCE target δt",
          "ended": "Peak of the computed curve (it ended before the IS-MCE target δt)"}
QUALIFIER = {"peak": "the largest base shear up to δt, a peak reached before δt (a higher one may follow beyond δt)",
             "at_target": "the curve is still rising at δt; the strength lies beyond δt and is not claimed",
             "ended": "the curve ended in a numerical stop before δt"}


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
    """The curve ended in a numerical stop (scripts/build_site_index.py rule)."""
    cap = (dd or {}).get("capacity") or {}
    tail = cap.get("tail_status") or ((dd or {}).get("tail") or {}).get("status")
    return (tail == "lower_bound") or str((dd or {}).get("stop_reason") or "").startswith("solver")


def _bases(dd, level):
    cap = (dd or {}).get("capacity") or {}
    VB = float(cap["V_design_kip"]) * KIP_TO_KN if cap.get("V_design_kip") else None
    n = ((dd or {}).get("nsp") or {}).get(level) or {}
    W = float(n["W_kip"]) * KIP_TO_KN if n.get("W_kip") else None
    full = cap.get("Vmax_kN")
    if VB is None and full and cap.get("Vmax_over_VB"):            # VB not stored: from the stored ratio
        VB = float(full) / float(cap["Vmax_over_VB"])
    if W is None and full and cap.get("Vmax_over_W"):
        W = float(full) / float(cap["Vmax_over_W"])
    return VB, W


def vmax_to_target(dd, VB_kN=None, W_kN=None, level=LEVEL) -> dict | None:
    """The headline of one direction (module docstring). VB_kN defaults to the direction's design base shear recorded in
    the capacity block (V_design_kip), W_kN to the IS seismic weight from the NSP block."""
    u, V = _curve(dd)
    t = _target_mm(dd, level)
    if not u or t is None:
        return None
    VB0, W0 = _bases(dd, level)
    VB_kN = VB_kN if VB_kN is not None else VB0
    W_kN = W_kN if W_kN is not None else W0
    tol = REL * max(t, 1.0)
    best, u_best, v_t, after = None, None, None, None
    reached = False
    for i, (ui, vi) in enumerate(zip(u, V)):
        if ui <= t + tol:
            if best is None or vi > best:
                best, u_best = vi, ui
            if ui >= t - tol:                                   # a curve point at the target
                reached, v_t = True, vi
                after = V[i + 1] if i + 1 < len(V) else None
                break
            continue
        if i > 0 and u[i - 1] < t:                              # interpolate the curve at the target
            f = (t - u[i - 1]) / (ui - u[i - 1])
            v_t = V[i - 1] + f * (vi - V[i - 1])
            if best is None or v_t > best:
                best, u_best = v_t, t
            after = vi
        reached = True
        break
    if best is None:
        return None
    if (((dd or {}).get("nsp") or {}).get(level) or {}).get("reached_target") is False:
        reached = False                                         # the NSP says the curve ended before the target
    if not reached:
        kind = "ended"
        last = max(i for i, x in enumerate(u) if x <= t + tol)
        lower_bound = u_best >= u[last] - tol                   # its maximum is its last point: still rising at the end
    elif u_best >= t - tol and (after is None or after >= best * (1.0 - REL)):
        kind, lower_bound = "at_target", False                  # still rising at δt
    else:
        kind, lower_bound = "peak", False
    i_pk = max(range(len(V)), key=lambda i: V[i])
    peak = dict(V_kN=float(V[i_pk]), u_mm=float(u[i_pk]), numerical_stop=full_lower_bound(dd),
                at_curve_end=(i_pk == len(V) - 1),
                V_over_VB=(float(V[i_pk]) / VB_kN) if VB_kN else None, V_over_W=(float(V[i_pk]) / W_kN) if W_kN else None)
    strength = kind != "at_target"
    return dict(level=level, target_mm=t, target_reached=reached, kind=kind, label=LABELS[kind], qualifier=QUALIFIER[kind],
                is_strength=strength, at_target=(kind == "at_target"), lower_bound=lower_bound,
                V_kN=float(best), u_mm=float(u_best), V_at_target_kN=(float(v_t) if v_t is not None else None),
                V_over_VB=(best / VB_kN) if VB_kN else None, V_over_W=(best / W_kN) if W_kN else None,
                peak_analysed=peak, basis=BASIS)


def ratio_label(h, base="VB") -> str:
    """'Vmax/VB' for a strength, 'V(δt)/VB' for the base shear at the target."""
    return ("V(δt)/%s" % base) if (h or {}).get("at_target") else ("Vmax/%s" % base)


def te_flags(dd) -> list:
    """[(level, Te, T1, kind)] where the NSP effective period is below T1 ('below') or above TE_HIGH x T1 ('far_above')."""
    T1 = (dd or {}).get("T1")
    out = []
    if not T1:
        return out
    for lv, n in sorted(((dd or {}).get("nsp") or {}).items()):
        Te = n.get("Te")
        if Te is None:
            continue
        if float(Te) < float(T1) * (1.0 - TE_TOL):
            out.append((lv, float(Te), float(T1), "below"))
        elif float(Te) > float(T1) * TE_HIGH:
            out.append((lv, float(Te), float(T1), "far_above"))
    return out


def te_note(direction, flags) -> str | None:
    """One or two sentences for a public page, or None."""
    if not flags:
        return None
    out = []
    lo = [f for f in flags if f[3] == "below"]
    hi = [f for f in flags if f[3] == "far_above"]
    if lo:
        out.append("Pushover %s: %s, below the elastic period T1 = %.3f s. The effective period cannot be shorter than the "
                   "elastic one; the bilinear fit took its initial stiffness from a softened part of the curve, so the "
                   "target displacement from it is uncertain (shown as computed)."
                   % (direction, " and ".join("%s Te = %.3f s" % (f[0], f[1]) for f in lo), lo[0][2]))
    if hi:
        out.append("Pushover %s: %s, more than %.1f times the elastic period T1 = %.3f s. The curve softens early, so the "
                   "effective stiffness of the bilinear fit is far below the elastic one and the target displacement is "
                   "sensitive to the fit (shown as computed)."
                   % (direction, " and ".join("%s Te = %.3f s" % (f[0], f[1]) for f in hi), TE_HIGH, hi[0][2]))
    return " ".join(out)


def strength_text(h, unit="kN", ratio=None) -> str | None:
    """The headline value: '9,223 kN', '≥ 9,223 kN' (the curve ended before δt while still rising), or the ratio."""
    ge = "≥ " if h.get("lower_bound") else ""
    if ratio == "VB":
        return ("%s%.1f" % (ge, h["V_over_VB"])) if h.get("V_over_VB") is not None else None
    if ratio == "W":
        return ("%s%.2f" % (ge, h["V_over_W"])) if h.get("V_over_W") is not None else None
    return "%s%s %s" % (ge, "{:,.0f}".format(h["V_kN"]), unit)


def headline_text(direction, h) -> str:
    """'Y: Base shear at the IS-MCE target δt = 11,333 kN at 93 mm (δt = 93 mm) — the curve is still rising at δt; ...'."""
    return "%s: %s = %s at %s mm (δt = %.0f mm) — %s" % (
        direction, h["label"], strength_text(h), "{:,.0f}".format(h["u_mm"]), h["target_mm"], h["qualifier"])


def peak_text(direction, h) -> str | None:
    """Information sentence on the peak of the analysed curve, when it is not the headline point; or None."""
    p = (h or {}).get("peak_analysed")
    if not p or (abs(p["u_mm"] - h["u_mm"]) <= REL * max(h["u_mm"], 1.0) and abs(p["V_kN"] - h["V_kN"]) <= REL * max(h["V_kN"], 1.0)):
        return None
    where = "beyond" if p["u_mm"] > h["target_mm"] else "within"
    tail = ""
    if p.get("numerical_stop") and p.get("at_curve_end"):
        tail = " (the curve ended in a numerical stop while still rising, so the strength is at least this)"
    return ("%s: the peak of the analysed curve is %s kN at %s mm of roof displacement, %s the IS-MCE target (%.0f mm)%s — "
            "information, not the headline" % (direction, "{:,.0f}".format(p["V_kN"]), "{:,.0f}".format(p["u_mm"]), where,
                                              h["target_mm"], tail))

