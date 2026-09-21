"""india_combos.py -- IS 800:2007 Table 4 + IS 1893 (Part 1) load-combination generator (WP1.2).

expand_combinations(plan, cfg) returns the FULL list of combination dicts the demand envelope
runs, so an agent never hand-writes (and never forgets) a family.  Every entry is a plain dict
(JSON-serialisable) understood by india_loads.case_from_combination:

    {label, fD, fL, fLr, fS, fC, fE | fW, lateral_ref | rsa, direction, sign, torsion,
     torsion_mz{k: Mz per unit story force}, fEv, notional, tags[], family, cite,
     lateral_kind ('EQ'|'W'|None), service}

Families (clause text read from the licensed PDFs):
  * IS 800:2007 Table 4 (p.29), strength:  1.5DL+1.5LL;  1.2DL+1.2LL+-1.2(EL|WL);
    1.2DL+1.2LL+-0.6WL;  1.5DL+-1.5(EL|WL);  0.9DL+-1.5(EL|WL);  crane rows DL+LL+CL
    1.5/1.5/1.05 and DL+LL+CL+WL/EL 1.2/1.2/1.05/0.6 and 1.2/1.2/0.53/1.2 (LL leading /
    accompanying);  serviceability rows 1.0 / (1.0, 0.8, 0.8, 0.8) / (1.0, 1.0).
    Note: in Table 4 'CL' is one of the imposed loads (leading / accompanying columns); there
    is no separate crane column.
  * IS 1893 6.3.2.1: one horizontal direction at a time for orthogonal systems; 6.3.2.2:
    +-ELX +-0.3ELY for non-parallel systems (cfg['nonparallel'] or skew).
  * IS 1893 7.8.2: edi = 1.5 esi + 0.05 bi  or  esi - 0.05 bi (two torsion variants per EQ
    case).  The model already carries esi (forces act at the CM), so the ADDED moment is
    F x (0.5 esi + 0.05 bi) and F x (-0.05 bi) about the CM, with the sign of esi.
  * IS 1893 6.3.3.1 (as replaced by Amd 2) vertical shaking; 6.3.4.1 +-EL +-0.3ELZ and
    +-ELZ +-0.3EL; 6.3.4.4 deletes the component not considered (orthogonal systems ->
    one horizontal + vertical).  Av per 6.4.6 = (2/3)(Z/2)(2.5)/(R/I), applied as +-Av x the
    seismic-weight gravity (DL + Table 10 share of LL) -- the combination carries fEv = factor x
    (1.0 | 0.3) x Av.
  * IS 800 12.2.3: 1.2DL+0.5LL+-2.5EL and 0.9DL+-2.5EL for every Section 12 system, tagged
    col_only / conn_only (12.5.1.1, 12.7.3.1, 12.11.2.2, 12.11.3.4).
  * IS 800 4.3.6: notional horizontal loads 0.5 % of factored DL+LL at each level, both
    directions one at a time, with the gravity-only strength combinations, never with EL/WL.
"""
from __future__ import annotations

import math

IS800_T4 = "IS 800:2007 Table 4"
IS1893 = "IS 1893 (Part 1):2016 + Amd 1 (2017) + Amd 2 (2020)"


class CombinationError(ValueError):
    pass


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _zone(cfg, plan):
    try:
        from india_seismic_gates import zone_of
        return zone_of(dict(cfg or {}, load_plan=plan))
    except Exception:
        return None


def section12_system(cfg) -> bool:
    try:
        from india_seismic_gates import section12_system as _s12
        return _s12(cfg)
    except Exception:
        return True


def av_vertical(cfg, plan) -> dict:
    """IS 1893 6.4.6: Av = (2/3) x (Z/2) x 2.5 / (R/I) for buildings (Part 1)."""
    ss = (plan or {}).get("seismic_summary") or {}
    s = (cfg or {}).get("seis") or {}
    Z = _f(ss.get("Z", s.get("Z", (cfg or {}).get("Z"))))
    R = _f(ss.get("R", s.get("R", (cfg or {}).get("R"))))
    I = _f(ss.get("I", s.get("I", (cfg or {}).get("I"))))
    if None in (Z, R, I) or R <= 0:
        return {"found": False, "Av": None, "note": "Z, R and I needed for Av (6.4.6)"}
    Av = (2.0 / 3.0) * (Z / 2.0) * 2.5 / (R / I)
    return {"found": True, "Av": Av, "cite": IS1893 + " 6.4.6: Av = (2/3)(Z/2)(2.5)/(R/I)",
            "Z": Z, "R": R, "I": I}


def vertical_required(cfg, plan) -> tuple:
    """IS 1893 6.3.3.1 as replaced by Amd 2 (b)(1)-(7)."""
    cfg = cfg or {}
    why = []
    z = _zone(cfg, plan)
    if z in ("IV", "V"):
        why.append("Zone %s (6.3.3.1(b)(1))" % z)
    if cfg.get("irregular") or cfg.get("_irregular") or (plan or {}).get("irregular"):
        why.append("vertical or plan irregularity (b)(2)")
    soil = str(((plan or {}).get("seismic_summary") or {}).get("soil") or (cfg.get("seis") or {}).get("soil") or "")
    if "soft" in soil.lower() or soil.strip().upper() in ("III", "TYPE III"):
        why.append("soft soil (b)(3)")
    if cfg.get("long_span"):
        why.append("long spans (b)(4)")
    if cfg.get("overhang") or cfg.get("large_overhang"):
        why.append("large overhangs (b)(5)")
    if cfg.get("prestressed"):
        why.append("prestressed members (b)(6)/(7)")
    if cfg.get("vertical_eq") is True and not why:
        why.append("declared by the EOR")
    return bool(why), why


def _levels(sf):
    return sorted(int(k) for k in (sf or {}).keys())


def _story_vec(plan, ref):
    sf = ((plan or {}).get("story_forces") or {}).get(ref)
    if sf is None:
        return None
    out = {}
    for k, v in dict(sf).items():
        if isinstance(v, dict):
            out[int(k)] = (float(v.get("fx", 0)), float(v.get("fy", 0)), float(v.get("mz", 0)))
        else:
            seq = list(v) + [0, 0, 0]
            out[int(k)] = (float(seq[0]), float(seq[1]), float(seq[2]))
    return out


def plan_extents(cfg) -> dict:
    """Per-level plan dimensions bx (X) and by (Y) in engine length units, from the framed grid."""
    out = {}
    try:
        import engine3d as E
        NF = len(cfg["heights"])
        for k in range(1, NF + 1):
            pts = E.grid(cfg, k)
            xs = [E._xy_in(cfg, i, j)[0] for i, j in pts]
            ys = [E._xy_in(cfg, i, j)[1] for i, j in pts]
            out[k] = (max(xs) - min(xs), max(ys) - min(ys))
    except Exception:
        NX, NY = cfg.get("NX"), cfg.get("NY")
        SX, SY = cfg.get("SX"), cfg.get("SY")
        for k in range(1, len(cfg.get("heights") or []) + 1):
            out[k] = ((NX or 0) * (SX or 0), (NY or 0) * (SY or 0))
    return out


def torsion_moments(plan, cfg, direction, eccentricity=None) -> dict:
    """Per-unit (unfactored story force) added moments for the two 7.8.2 variants.

    eccentricity = {"X": {k: esi_y}, "Y": {k: esi_x}} in engine length units (esi = CM - CR,
    measured perpendicular to the force).  Returns {"a": {k: Mz}, "b": {k: Mz}, "esi": {...},
    "b_i": {...}}."""
    ref = "EQ_" + direction
    vec = _story_vec(plan, ref)
    if not vec:
        return {}
    ext = plan_extents(cfg)
    ecc = ((eccentricity or {}).get(direction) or {}) if eccentricity else {}
    a, b, es, bb = {}, {}, {}, {}
    for k, (fx, fy, _mz) in vec.items():
        F = fx if direction == "X" else fy
        bi = ext.get(k, (0.0, 0.0))[1 if direction == "X" else 0]   # plan dimension perpendicular to force
        esi = float(ecc.get(k, ecc.get(str(k), 0.0)) or 0.0)
        s = 1.0 if esi >= 0 else -1.0
        d_a = 0.5 * esi + 0.05 * bi * s          # 1.5 esi + 0.05 bi, minus the esi already in the model
        d_b = -0.05 * bi * s                      # esi - 0.05 bi
        # force along X applied at y offset d -> Mz = -Fx d ; force along Y at x offset d -> Mz = +Fy d
        sgn = -1.0 if direction == "X" else 1.0
        a[k] = sgn * F * d_a
        b[k] = sgn * F * d_b
        es[k] = esi
        bb[k] = bi
    return {"a": a, "b": b, "esi": es, "b_i": bb}


def _fmt(x):
    s = ("%.2f" % abs(x)).rstrip("0").rstrip(".")
    return s


def _lat_label(f, kind, d, extra=""):
    tok = {"EQ": "EQ", "W": "W"}[kind]
    return "%s%s%s_%s%s" % ("+" if f >= 0 else "-", _fmt(f), tok, d, extra)


def _grav_label(fD, fL, fLr=0.0, fS=0.0, fC=0.0):
    parts = ["%sDL" % _fmt(fD)]
    if fL:
        parts.append("%sLL" % _fmt(fL))
    if fLr and not fL:
        parts.append("%sLLr" % _fmt(fLr))
    if fS:
        parts.append("%sSL" % _fmt(fS))
    if fC:
        parts.append("%sCL" % _fmt(fC))
    return "+".join(parts)


def _rsa_required(cfg, plan):
    an = [str(a).upper() for a in ((cfg or {}).get("analyses") or [])]
    if any(a in ("RSA", "RS", "MRSA") for a in an):
        return True
    try:
        from india_seismic_gates import esm_permitted
        ok, _ = esm_permitted(dict(cfg or {}, load_plan=plan), None)
        return not ok
    except Exception:
        return True


def member_wind_patterns(plan) -> list:
    """load_plan['member_wind'] -> list of patterns (india_wind_tables.lowrise_member_wind output, or a
    list of pattern dicts).  Each pattern needs name + pressures in kN/m2 (+ = towards the surface)."""
    mw = (plan or {}).get("member_wind")
    if not mw:
        return []
    pats = mw.get("patterns") if isinstance(mw, dict) else mw
    out = []
    for p in pats or []:
        if not isinstance(p, dict) or not p.get("name"):
            raise CombinationError("member_wind pattern without a name: %r" % (p,))
        if p.get("roof_windward_kNm2") is None and p.get("wall_windward_kNm2") is None:
            raise CombinationError("member_wind pattern %s has no pressures" % p["name"])
        q = dict(p)
        axis = str(q.get("wind_axis") or "").upper()
        if axis not in ("X", "Y"):
            raise CombinationError("member_wind pattern %s: wind_axis 'X' or 'Y' (direction of the wind) is "
                                   "required" % q["name"])
        q["wind_axis"] = axis
        out.append(q)
    return out


def expand_combinations(plan, cfg, *, eccentricity=None, method=None) -> list:
    """Generate every required IS 800 Table 4 / IS 1893 / IS 800 12.2.3 combination."""
    plan = plan or {}
    cfg = cfg or {}
    sf = plan.get("story_forces") or {}
    has_eq = bool(sf.get("EQ_X") or sf.get("EQ_Y")) and not cfg.get("no_seismic")
    has_w = bool(sf.get("W_X") or sf.get("W_Y"))
    snow = _f(cfg.get("snow"), 0.0) or 0.0
    crane = cfg.get("crane") or cfg.get("cranes")
    rsa = (method or "").upper() == "RSA" if method else _rsa_required(cfg, plan)
    nonpar = bool(cfg.get("nonparallel") or cfg.get("skew"))
    s12 = section12_system(cfg) if has_eq else False
    # IS 18168:2023 5.5 overstrength combinations (decision D2; stricter-governs precedence): mandatory in
    # Zones III-V for SMRF/SCBF/EBF.  Omega 2.5 (SCBF/EBF) equals the IS 800 12.2.3 factor -> those rows carry
    # both cites; Omega 3.0 (SMRF) is stricter -> extra rows.  cl. 5.5 (a)-(d): columns; beams of SCBF/EBF;
    # braces of EBF; all connections -> tags sfrs_beam / sfrs_brace mark who else must be checked.
    is18168 = {"applies": False}
    if s12:
        try:
            import india_is18168 as I18
            is18168 = I18.applies(cfg.get("system"), _zone(cfg, plan), opt_in=bool(cfg.get("apply_is18168")))
            if is18168["applies"]:
                is18168["Omega"] = I18.omega(cfg.get("system"))["Omega"]
                is18168["members"] = I18.overstrength_members(cfg.get("system"))
                is18168["cite"] = I18.CITE_5_5
        except Exception:
            is18168 = {"applies": False}
    vreq, vwhy = vertical_required(cfg, plan) if has_eq else (False, [])
    av = av_vertical(cfg, plan) if vreq else {"found": False, "Av": None}
    if vreq and not av.get("found"):
        raise CombinationError("vertical earthquake required (%s) but Av cannot be computed: %s"
                               % ("; ".join(vwhy), av.get("note")))
    Av = av.get("Av") or 0.0
    tors = {d: torsion_moments(plan, cfg, d, eccentricity) for d in ("X", "Y")} if has_eq else {}
    combos = []

    def add(label, fD, fL, fLr=0.0, family="", cite=IS800_T4, **kw):
        c = {"label": label, "fD": fD, "fL": fL, "fLr": fLr, "family": family, "cite": cite}
        c.update(kw)
        c.setdefault("tags", [])
        combos.append(c)
        return c

    # ---- gravity (strength), + IS 800 4.3.6 notional loads (never with EL/WL) ----
    g = add(_grav_label(1.5, 1.5, 1.5), 1.5, 1.5, 1.5, family="T4 DL+LL", cite=IS800_T4 + " DL+LL")
    if snow:
        add(_grav_label(1.5, 1.5, 0, 1.5), 1.5, 1.5, 0.0, fS=1.5, family="T4 DL+LL(snow)", cite=IS800_T4 + " DL+LL (snow)")
        # IS 875 (Part 4):2021 4.3: severe imbalance (zero snow on one half of the roof) -- cfg['snow_partial'] =
        # {'axis': 'X'|'Y' (direction across the ridge / the half-split)} adds the two half-loaded rows (WP6-fix)
        spx = cfg.get("snow_partial")
        if spx:
            ax_ = str((spx.get("axis") if isinstance(spx, dict) else spx) or "X").upper()
            for side in ("lo", "hi"):
                add(_grav_label(1.5, 1.5, 0, 1.5) + "[SL:%s-%s]" % (ax_, side), 1.5, 1.5, 0.0, fS=1.5,
                    family="T4 DL+LL(snow) + IS 875-4 4.3 partial", snow_pattern=[ax_, side],
                    cite=IS800_T4 + " DL+LL (snow); IS 875 (Part 4):2021 4.3 partial loading (zero snow on one half)")
    if cfg.get("notional_loads", True):
        for d in ("X", "Y"):
            for s in (1, -1):
                add(g["label"] + "%sN_%s" % ("+" if s > 0 else "-", d), 1.5, 1.5, 1.5,
                    family="T4 DL+LL + 4.3.6 notional", cite="IS 800:2007 4.3.6 (0.5 % factored gravity)",
                    notional={"dir": d, "sign": s, "ratio": 0.005})
    # ---- crane rows (LL leading / crane leading) ----
    if crane:
        from india_loads import CRANE_PATTERNS, CRANE_CITE
        for (fD_, fL_, fC_, fam_) in ((1.5, 1.5, 1.05, "T4 DL+LL+CL (LL leading)"),
                                      (1.5, 1.05, 1.5, "T4 DL+LL+CL (CL leading)")):
            for pat in CRANE_PATTERNS:
                add(_grav_label(fD_, fL_, fL_, 0, fC_) + "[CL:%s%s]" % pat, fD_, fL_, fL_, fC=fC_, family=fam_,
                    cite=IS800_T4 + " DL+LL+CL; " + CRANE_CITE, crane=True, crane_pattern=list(pat))
    # ---- lateral families ----
    kinds = (["EQ"] if has_eq else []) + (["W"] if has_w else [])
    for kind in kinds:
        for d in ("X", "Y"):
            ref = ("EQ_" if kind == "EQ" else "W_") + d
            if not sf.get(ref):
                continue
            key = "fE" if kind == "EQ" else "fW"
            rows = [(1.2, 1.2, 1.2, "T4 DL+LL+%s" % ("EL" if kind == "EQ" else "WL")),
                    (1.5, 0.0, 1.5, "T4 DL+%s" % ("EL" if kind == "EQ" else "WL")),
                    (0.9, 0.0, 1.5, "T4 0.9DL+%s" % ("EL" if kind == "EQ" else "WL"))]
            if kind == "W":
                rows.insert(1, (1.2, 1.2, 0.6, "T4 DL+LL+0.6WL"))
            if kind == "EQ" and s12:
                rows += [(1.2, 0.5, 2.5, "IS 800 12.2.3(a)"), (0.9, 0.0, 2.5, "IS 800 12.2.3(b)")]
                if is18168.get("applies") and (is18168.get("Omega") or 0) > 2.5:
                    om = is18168["Omega"]          # SMRF 3.0: stricter than 12.2.3, both families kept
                    rows += [(1.2, 0.5, om, "IS 18168 5.5(1)"), (0.9, 0.0, om, "IS 18168 5.5(2)")]
            if crane:
                rows += [(1.2, 1.2, 0.6, "T4 DL+LL+CL+0.6%s" % ("EL" if kind == "EQ" else "WL")),
                         (1.2, 1.2, 1.2, "T4 DL+LL+0.53CL+1.2%s" % ("EL" if kind == "EQ" else "WL"))]
            for (fD, fL, fl, fam) in rows:
                is1223 = fam.startswith("IS 800 12.2.3") or fam.startswith("IS 18168 5.5")
                is5_5 = fam.startswith("IS 18168 5.5") or (fam.startswith("IS 800 12.2.3") and is18168.get("applies")
                                                          and abs((is18168.get("Omega") or 0) - fl) < 1e-9)
                fC = 0.0
                if fam.startswith("T4 DL+LL+CL+0.6"):
                    fC = 1.05
                elif fam.startswith("T4 DL+LL+0.53CL"):
                    fC = 0.53
                if kind == "EQ" and fl == 0.6 and not crane:
                    continue
                fLr = fL          # Table 4 'LL' = every imposed load (floor + roof); 7.3.2 is about mass only
                for s in (1, -1):
                    f = s * fl
                    tvars = (["a", "b"] if (kind == "EQ" and tors.get(d)) else [None])
                    zvars = ([None] if not (kind == "EQ" and vreq) else [0.3, -0.3])
                    for tv in tvars:
                        for zv in zvars:
                            extra = ""
                            if tv:
                                extra += "[e%s]" % tv
                            if zv is not None:
                                extra += "%s0.3EQ_Z" % ("+" if zv > 0 else "-")
                            tags = []
                            cite_fam = IS800_T4
                            if is1223:
                                tags = ["col_only", "conn_only"]
                                if fam.startswith("IS 800 12.2.3"):
                                    tags.append("is800_12_2_3")
                                    cite_fam = "IS 800:2007 12.2.3"
                                else:
                                    cite_fam = "IS 18168:2023 5.5"
                                if is5_5:
                                    tags.append("is18168_5_5")
                                    mem = is18168.get("members") or {}
                                    if mem.get("beam"):
                                        tags.append("sfrs_beam")
                                    if mem.get("brace"):
                                        tags.append("sfrs_brace")
                                    if fam.startswith("IS 800 12.2.3"):
                                        cite_fam += " (= IS 18168:2023 5.5, Omega %.1f)" % is18168["Omega"]
                                extra += "[col]"
                            lab = _grav_label(fD, fL, fLr, 0, fC) + _lat_label(f, kind, d, extra)
                            cpats = [("L", None), ("R", None)] if fC else [None]
                            for cp in cpats:
                                c = add(lab + ("[CL:%s]" % cp[0] if cp else ""), fD, fL, fLr, family=fam, cite=cite_fam
                                        + (" + " + IS1893 + " 6.3" if kind == "EQ" else " + IS 875 (Part 3):2015"),
                                        lateral_kind=kind, direction=d, sign=s, tags=tags, fC=fC)
                                if cp:
                                    c["crane"] = True
                                    c["crane_pattern"] = list(cp)
                                c[key] = f
                                if kind == "EQ" and rsa:
                                    c["rsa"] = d
                                else:
                                    c["lateral_ref"] = ref
                                if tv:
                                    c["torsion"] = tv
                                    c["torsion_mz"] = {str(k): v for k, v in tors[d][tv].items()}
                                if zv is not None:
                                    c["fEv"] = fl * zv * Av
                                    c["vertical"] = {"Av": Av, "coef": zv}
                                if kind == "EQ" and nonpar:
                                    o = "Y" if d == "X" else "X"
                                    c.setdefault("terms", []).append({"ref": "EQ_" + o, "f": 0.3 * f, "rsa": o if rsa else None})
                                    c["label"] += "%s0.3EQ_%s" % ("+" if f >= 0 else "-", o)
            # vertical-dominant combos +-ELZ +-0.3EL (6.3.4.1(c)) for the Table 4 EQ rows
            if kind == "EQ" and vreq:
                for (fD, fL, fl, fam) in [(1.2, 1.2, 1.2, "T4 DL+LL+EL (ELZ leading)"),
                                          (1.5, 0.0, 1.5, "T4 DL+EL (ELZ leading)"),
                                          (0.9, 0.0, 1.5, "T4 0.9DL+EL (ELZ leading)")]:
                    for sz in (1, -1):
                        for s in (1, -1):
                            f = s * 0.3 * fl
                            lab = _grav_label(fD, fL) + "%s%sEQ_Z" % ("+" if sz > 0 else "-", _fmt(fl)) + \
                                _lat_label(f, "EQ", d)
                            c = add(lab, fD, fL, 0.0, family=fam, cite=IS1893 + " 6.3.4.1(c)",
                                    lateral_kind="EQ", direction=d, sign=s, tags=[])
                            c["fE"] = f
                            c["fEv"] = sz * fl * Av
                            c["vertical"] = {"Av": Av, "coef": sz}
                            if rsa:
                                c["rsa"] = d
                            else:
                                c["lateral_ref"] = ref
    # ---- member-level wind (low-rise / portal: IS 875-3 7.3.1 (Cpe - Cpi) pd patterns) ----
    for pat in member_wind_patterns(plan):
        for (fD, fL, fl, fam) in ((1.5, 0.0, 1.5, "T4 DL+WL (member wind)"),
                                  (0.9, 0.0, 1.5, "T4 0.9DL+WL (member wind, uplift)"),
                                  (1.2, 1.2, 1.2, "T4 DL+LL+WL (member wind)"),
                                  (1.2, 1.2, 0.6, "T4 DL+LL+0.6WL (member wind)")):
            c = add(_grav_label(fD, fL, fL) + "+%s%s" % (_fmt(fl), pat["name"]), fD, fL, fL, family=fam,
                    cite=IS800_T4 + " + IS 875 (Part 3):2015 7.3.1, Table 5, Table 6",
                    lateral_kind="W", direction=pat.get("wind_axis"), sign=1, tags=["member_wind"])
            c["fWM"] = fl
            c["member_wind"] = {k: pat.get(k) for k in ("name", "direction", "wind_axis", "roof_windward_kNm2",
                                                        "roof_leeward_kNm2", "wall_windward_kNm2",
                                                        "wall_leeward_kNm2", "Cpi")}
    # ---- serviceability (Table 4 cols 7-10): tagged, excluded from the strength envelope ----
    add("SLS:1.0DL+1.0LL", 1.0, 1.0, 1.0, family="T4 SLS DL+LL", cite=IS800_T4 + " serviceability", service=True,
        tags=["service"])
    for kind in (["W"] if has_w else []) + (["EQ"] if has_eq else []):
        for d in ("X", "Y"):
            ref = ("EQ_" if kind == "EQ" else "W_") + d
            if not sf.get(ref):
                continue
            key = "fE" if kind == "EQ" else "fW"
            for (fD, fL, fl) in ((1.0, 0.8, 0.8), (1.0, 0.0, 1.0)):
                c = add("SLS:" + _grav_label(fD, fL) + _lat_label(fl, kind, d), fD, fL, 0.0,
                        family="T4 SLS", cite=IS800_T4 + " serviceability", service=True, tags=["service"],
                        lateral_kind=kind, direction=d, sign=1)
                c[key] = fl
                c["lateral_ref"] = ref
    # meta record for the report / gates
    for c in combos:
        c.setdefault("lateral_kind", None)
    _META.clear()
    _META.update({"rsa": rsa, "vertical": {"required": vreq, "why": vwhy, **av}, "section12": s12, "is18168": is18168,
                  "nonparallel": nonpar, "torsion": {d: {k: v for k, v in (tors.get(d) or {}).items()
                                                         if k in ("esi", "b_i")} for d in ("X", "Y")},
                  "n": len(combos)})
    return combos


_META = {}


def last_expansion_meta() -> dict:
    return dict(_META)


def validate_combinations(combos, cfg, plan=None) -> list:
    """(sev, msg) findings: required families missing from an explicit or generated list."""
    out = []
    cfg = cfg or {}
    combos = [c for c in (combos or []) if isinstance(c, dict)]
    sf = (plan or cfg.get("load_plan") or {}).get("story_forces") or {}
    has_eq = any(c.get("fE") is not None for c in combos) or bool(sf.get("EQ_X") or sf.get("EQ_Y"))
    has_w = any(c.get("fW") is not None for c in combos) or bool(sf.get("W_X") or sf.get("W_Y"))
    fam = lambda fD, fL, fl, key: [c for c in combos if abs(float(c.get("fD", 0)) - fD) < 1e-9
                                  and abs(float(c.get("fL", 0)) - fL) < 1e-9 and c.get(key) is not None
                                  and abs(abs(float(c.get(key))) - fl) < 1e-9]
    if not any(abs(float(c.get("fD", 0)) - 1.5) < 1e-9 and abs(float(c.get("fL", 0)) - 1.5) < 1e-9
               and not (c.get("fE") or c.get("fW")) for c in combos):
        out.append(("ERROR", "IS 800 Table 4 1.5DL+1.5LL combination missing"))
    for kind, key, present in (("EQ", "fE", has_eq), ("W", "fW", has_w)):
        if not present or (kind == "EQ" and cfg.get("no_seismic")):
            continue
        def _dir(c):
            if c.get("direction"):
                return c["direction"]
            r = str(c.get("lateral_ref") or c.get("rsa") or "")
            if r[-1:] in ("X", "Y"):
                return r[-1:]
            try:
                from india_loads import label_lateral_terms
                t = label_lateral_terms(c.get("label"))
                return t[0][2] if t else None
            except Exception:
                return None
        dirs_present = {_dir(c) for c in combos if c.get(key) is not None}
        for (fD, fL, fl) in ((1.2, 1.2, 1.2), (1.5, 0.0, 1.5), (0.9, 0.0, 1.5)):
            rows = fam(fD, fL, fl, key)
            for d in ("X", "Y"):
                if not sf.get(("EQ_" if kind == "EQ" else "W_") + d) and d not in dirs_present:
                    continue
                sg = {1 if float(c[key]) > 0 else -1 for c in rows if _dir(c) == d}
                if sg != {1, -1}:
                    out.append(("ERROR", "IS 800 Table 4 %sDL+%sLL+-%s%s_%s: both signs required (have %s)"
                                % (fD, fL, fl, kind, d, sorted(sg) or "none")))
        if kind == "EQ":
            if not any(c.get("torsion") or c.get("torsion_mz") for c in combos if c.get("fE") is not None):
                out.append(("ERROR", "IS 1893 7.8.2 design-eccentricity (torsion) cases missing"))
            if section12_system(cfg) and not fam(1.2, 0.5, 2.5, "fE") and not fam(0.9, 0.0, 2.5, "fE"):
                out.append(("ERROR", "IS 800 12.2.3 combinations (1.2DL+0.5LL+-2.5EL, 0.9DL+-2.5EL) missing "
                                     "for a Section 12 system"))
            try:
                import india_is18168 as I18
                a = I18.applies(cfg.get("system"), _zone(cfg, plan), opt_in=bool(cfg.get("apply_is18168")))
                om = I18.omega(cfg.get("system"))["Omega"] if a["applies"] else None
                if om and not fam(1.2, 0.5, om, "fE") and not fam(0.9, 0.0, om, "fE"):
                    out.append(("ERROR", "IS 18168:2023 5.5 overstrength combinations (Omega = %.1f for %s) missing "
                                         "(mandatory in Zone %s)" % (om, a["system"], a["zone"])))
            except Exception:
                pass
            vreq, why = vertical_required(cfg, plan)
            if vreq and not any(c.get("fEv") for c in combos):
                out.append(("ERROR", "IS 1893 6.3.3.1 (Amd 2) vertical earthquake required (%s) but no ELZ "
                                     "term in any combination" % "; ".join(why)))
    if cfg.get("crane") or cfg.get("cranes"):
        if not any(c.get("fC") for c in combos):
            out.append(("ERROR", "crane present but no IS 800 Table 4 DL+LL+CL rows"))
    return out


def combos_to_report_rows(combos) -> list:
    """Rows for report Ch.4 generated from the actual list."""
    rows = []
    for c in combos:
        f = c.get("fE", c.get("fW"))
        rows.append({"label": c["label"], "family": c.get("family"), "fD": c["fD"], "fL": c["fL"],
                     "fLr": c.get("fLr", 0.0), "flat": f, "kind": c.get("lateral_kind"),
                     "direction": c.get("direction"), "torsion": c.get("torsion"), "fEv": c.get("fEv"),
                     "tags": c.get("tags") or [], "cite": c.get("cite"), "rsa": c.get("rsa")})
    return rows
