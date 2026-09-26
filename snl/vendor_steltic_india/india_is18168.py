"""IS 18168:2023 (Earthquake Resistant Design and Detailing of Steel Buildings) -- applicability and the
numbers that conflict with, or add to, IS 800:2007 Section 12 (decision D2; HR-INTEGRATE precedence rule).

Precedence rule (Foreword: "provisions of this standard shall govern when in conflict with those in Section 12
of IS 800 : 2007"): where both standards give a limit the STRICTER governs and the check record cites both;
where IS 18168 alone gives a provision it is cited alone.  IS 18168 is mandatory in Zones III-V (cl. 1.2) for
residential/educational/institutional, office/business and community/lifeline buildings and optional in Zone II.

Every number below was read from the licensed PDF (/home/claude/rv/pdfs/INDIA_STEEL/pdfs/IS_18168_2023.pdf,
`pdftotext -layout -f P -l P`; pdf page = printed page + 2):
  cl. 1.3  (pdf 3)  "In seismic zone V, all steel buildings shall be made of EBF systems; SCBFs shall not be used.
                     In seismic zones IV and V, SMRFs may be used in buildings of height less than 15 m."
  cl. 5.2 / Table 1 (pdf 7)  Ry: E250 1.4, E275 1.4, E300 1.3, E350 1.2 (B0 or C); Ru 1.2/1.2/1.1/1.1
  cl. 5.5  (pdf 7)  1.2 DL + gLL LL +- 1.0 ELm ; 0.9 DL +- 1.0 ELm ; ELm = Omega EL ; Omega = 2.5 SCBF/EBF, 3.0 SMRF;
                     gLL = 0.25 (LL <= 3.0 kN/m2) / 0.50 (LL > 3.0); for (a) columns of SMRF/SCBF/EBF, (b) beams of
                     SCBF/EBF, (c) braces of EBF, (d) all connections of the structural system
  cl. 7.2  (pdf 10) "The slenderness ratio of unbraced length of columns shall be less than 75."
  cl. 8.2  (pdf 11) sum Zpc fyc (1 - Pu/Pd) / sum 1.1 Ry Zpb fyb > 1.4 ; 8.2.1 not required at the roof level
  cl. 10.2 (pdf 14) "The effective slenderness ratio of braces shall be less than 160."
  cl. 10.4.1 (pdf 14) brace connection tension = lesser of max(1.1 Ry fy Ag, Ru fu An) and the system maximum
  cl. 11.3 (pdf 15) "The length of link e shall be less than 1.6 MpL/VpL"
  cl. 12.3.2.2 (pdf 21) capacity-protected elements: 1.1 Ry Sh x link design strength (Sh 1.25 I / 1.4 box)
  cl. 12.3.3.1 (pdf 21) "The link rotation angle shall not exceed 0.08 rad."
  cl. 12.3.4.5 (pdf 22) braces: 1.2 Ry x link design strength
  Table 2 (pdf 8) limiting width-to-thickness (5.3): outstanding flange b/tf and web d/tw, all as coeff x eps / sqrt(Ry),
                     eps = sqrt(250/fy): beam 9.0 / 44.5; column 9.0 / 72.7(1 - 1.04Ca) for Ca <= 0.118 and
                     24.9(2.68 - Ca) >= 44.4 for Ca > 0.118, Ca = Pu/(Py/gamma_m0); brace I 11.3 / 44.4, box 21.4 / 21.4;
                     link I 11.3 / 44.4, box 21.4 / 49.4   (WP6: applied to EBF links, braces, beams outside links, columns)
"""
from __future__ import annotations

DOC = "IS 18168:2023"
PDF = "/home/claude/rv/pdfs/INDIA_STEEL/pdfs/IS_18168_2023.pdf"

OMEGA = {"SCBF": 2.5, "EBF": 2.5, "SMRF": 3.0}                       # cl. 5.5 (pdf p. 7)
GAMMA_LL_5_5 = ((3.0, 0.25), (float("inf"), 0.50))                     # cl. 5.5
RY = {"E250": 1.4, "E275": 1.4, "E300": 1.3, "E350": 1.2}             # Table 1 (pdf p. 7), B0 or C
RU = {"E250": 1.2, "E275": 1.2, "E300": 1.1, "E350": 1.1}
COLUMN_KLR_LIMIT = 75.0                                                # cl. 7.2 (strict <)
BRACE_KLR_LIMIT = 160.0                                                # cl. 10.2 (strict <)
SCWB_MIN = 1.4                                                         # cl. 8.2 (strict >)
LINK_ROTATION_LIMIT = 0.08                                             # cl. 12.3.3.1
LINK_LENGTH_FACTOR = 1.6                                               # cl. 11.3
SH = {"I": 1.25, "box": 1.4}                                           # cl. 12.3.2.2
SMRF_HEIGHT_LIMIT_M_ZONES_IV_V = 15.0                                  # cl. 1.3 / 12.1.1
TABLE2 = {"beam": (9.0, 44.5), "brace": (11.3, 44.4), "brace_box": (21.4, 21.4),
          "link": (11.3, 44.4), "link_box": (21.4, 49.4), "column": (9.0, None)}   # Table 2 (pdf p. 8), x eps/sqrt(Ry)
CITE_TABLE2 = (DOC + " Table 2 (pdf p. 8; 5.3): outstanding flange b/tf and web d/tw limits = coefficient x eps/sqrt(Ry), "
               "eps = sqrt(250/fy); beam 9.0/44.5, column 9.0/[72.7(1-1.04Ca) | 24.9(2.68-Ca) >= 44.4], brace 11.3/44.4, "
               "link 11.3/44.4 (I-sections)")

CITE_1_3 = (DOC + " 1.3 (pdf p. 3): 'In seismic zone V, all steel buildings shall be made of EBF systems; SCBFs "
            "shall not be used. In seismic zones IV and V, SMRFs may be used in buildings of height less than 15 m.'")
CITE_1_2 = DOC + " 1.2 (pdf p. 3): mandatory in Zones III, IV, V; 'optional for ... seismic zone II'"
CITE_5_5 = (DOC + " 5.5 (pdf p. 7): 1.2DL + gLL LL +- Omega EL; 0.9DL +- Omega EL; Omega = 2.5 SCBF/EBF, 3.0 SMRF")
CITE_7_2 = DOC + " 7.2 (pdf p. 10): 'slenderness ratio of unbraced length of columns shall be less than 75'"
CITE_8_2 = DOC + " 8.2 (pdf p. 11): sum Zpc fyc (1 - Pu/Pd) / sum 1.1 Ry Zpb fyb > 1.4; 8.2.1 not at roof"
CITE_10_2 = DOC + " 10.2 (pdf p. 14): 'effective slenderness ratio of braces shall be less than 160'"
CITE_TABLE1 = DOC + " Table 1 (pdf p. 7): Ry E250/E275 1.4, E300 1.3, E350 1.2 (B0 or C)"
PRECEDENCE = ("IS 18168:2023 Foreword: governs over IS 800:2007 Section 12 where in conflict -> the stricter limit "
              "governs and both are cited (HR-INTEGRATE rule)")

_SYS = {"SMF": "SMRF", "SMRF": "SMRF", "SCBF": "SCBF", "EBF": "EBF"}


def components(system):
    """IS 18168 systems named in a (possibly mixed, '+'-joined) system string: 'SMF+SCBF' -> ['SMRF', 'SCBF']
    (WP6-fix: a transverse SMRF with longitudinal SCBF bays is covered by both sets of rules)."""
    out = []
    for part in str(system or "").upper().replace("-", "").replace("_", "").replace(" ", "").split("+"):
        c = _SYS.get(part)
        if c and c not in out:
            out.append(c)
    return out


def normalize_system(system):
    comps = components(system)
    return comps[0] if comps else None


def _zone(z):
    if z is None:
        return None
    s = str(z).upper().replace("ZONE", "").strip()
    if s in ("II", "III", "IV", "V"):
        return s
    try:
        return {0.10: "II", 0.16: "III", 0.24: "IV", 0.36: "V"}.get(round(float(s), 2))
    except ValueError:
        return None


import re as _re

# cl. 1.2 (a)-(c) occupancy list (ruling R8): residential / educational / institutional; office and business;
# community, utility and lifeline buildings required for disaster management.  Word-boundary keyword match on the
# job's occupancy record (cfg['occupancy'] = {use | uses} as for IS 1893 Table 8, or a list of such records).
OCCUPANCY_1_2_KEYWORDS = (
    "residential", "residence", "residences", "apartment", "apartments", "housing", "house", "flats", "hostel",
    "dormitory", "hotel", "educational", "education", "school", "college", "university", "institutional",
    "institution", "hospital", "clinic", "nursing home", "healthcare", "office", "offices", "business", "bank",
    "commercial", "community", "utility", "lifeline", "disaster", "emergency", "fire station", "police",
    "telephone exchange", "power station", "water supply", "food storage")
OCCUPANCY_OUTSIDE_1_2_KEYWORDS = (
    "warehouse", "warehouses", "industrial", "factory", "storage", "shed", "workshop", "godown", "manufacturing",
    "plant", "hangar", "mill")
CITE_1_2_OCC = (DOC + " 1.2 (pdf p. 3): 'shall be adopted in the design of the following types of steel buildings "
                "located in seismic zones III, IV or V ...: a) Residential, educational and institutional buildings; "
                "b) Office and business buildings; and c) Community, utility and lifeline buildings required for "
                "disaster management activities' (ruling R8)")


def _has_word(text, kw):
    """Word-boundary match that ignores negated occurrences ('non-residential', 'no food storage'; RR-BUG-1, the
    same negation rule as the IS 1893 Table 8 importance factor)."""
    from india_seismic import _negated
    t = _re.sub(r"\s+", " ", _re.sub(r"[_/()\-]+", " ", text))
    return any(not _negated(t, m.start()) for m in _re.finditer(r"\b%s\b" % _re.escape(kw), t))


def occupancy_in_scope(occupancy) -> dict:
    """cl. 1.2 occupancy test (ruling R8): {in_scope True | False | None, matched, basis}.  True when any use is in
    the 1.2 list; False only when every recognised use is outside it (warehouse / industrial / storage ...);
    None when the occupancy is not declared or not recognised (callers then apply IS 18168 - conservative)."""
    recs = occupancy if isinstance(occupancy, (list, tuple)) else [occupancy]
    uses = []
    for o in recs:
        if isinstance(o, dict):
            uses += [str(u) for u in ([o.get("use")] + list(o.get("uses") or [])) if u]
            if o.get("educational") or o.get("hospital"):
                uses.append("educational" if o.get("educational") else "hospital")
        elif o:
            uses.append(str(o))
    text = " ; ".join(uses).lower()
    if not text.strip():
        return {"in_scope": None, "matched": [], "basis": "occupancy not declared", "cite": CITE_1_2_OCC}
    hit = [k for k in OCCUPANCY_1_2_KEYWORDS if _has_word(text, k)]
    if hit:
        return {"in_scope": True, "matched": hit, "basis": "occupancy %r in the 1.2 list" % text, "cite": CITE_1_2_OCC}
    out = [k for k in OCCUPANCY_OUTSIDE_1_2_KEYWORDS if _has_word(text, k)]
    if out:
        return {"in_scope": False, "matched": out, "basis": "occupancy %r not in the 1.2 list" % text,
                "cite": CITE_1_2_OCC}
    return {"in_scope": None, "matched": [], "basis": "occupancy %r not recognised against the 1.2 list" % text,
            "cite": CITE_1_2_OCC}


def applies(system, zone, *, opt_in=False, occupancy=None, override=None) -> dict:
    """{applies, mandatory, system, zone, cite, occupancy_basis}.  Ruling R8: mandatory in Zones III-V for
    SMRF/SCBF/EBF (1.3) when the occupancy is in the 1.2 list; an occupancy outside the list (warehouse, industrial
    ...) makes it optional; an undeclared / unrecognised occupancy is treated as in scope (conservative).
    override = cfg['apply_is18168']: True applies it in any zone (Zone II opt-in, or an optional occupancy);
    False is honoured except where 1.2 makes it mandatory (listed occupancy in Zones III-V: ignored with a note).
    opt_in (legacy) is the same as override True.  Other systems (OMRF/OCBF/...) are outside its scope (1.3)."""
    sysn = normalize_system(system)
    z = _zone(zone)
    if sysn is None:
        return {"applies": False, "mandatory": False, "system": sysn, "zone": z,
                "reason": "system not covered by IS 18168 (1.3: SMRF, SCBF, EBF only)", "cite": CITE_1_2}
    if opt_in and override is None:
        override = True
    occ = occupancy_in_scope(occupancy)
    seismic = z in ("III", "IV", "V")
    mandatory = seismic and occ["in_scope"] is not False
    out = {"mandatory": mandatory, "system": sysn, "zone": z, "cite": CITE_1_2 + "; " + CITE_1_2_OCC,
           "occupancy_in_scope": occ["in_scope"], "occupancy_basis": occ["basis"], "override": override}
    if seismic and occ["in_scope"] is None:
        out["note"] = "%s: IS 18168 applied in Zone %s (conservative; declare cfg['occupancy'] or " \
                      "cfg['apply_is18168'])" % (occ["basis"], z)
    if override is True:
        out["applies"] = True
        if not mandatory:
            out["note"] = "applied by cfg['apply_is18168'] = True (%s)" % ("Zone II opt-in" if z == "II" else occ["basis"])
    elif override is False:
        if mandatory and occ["in_scope"] is True:
            out["applies"] = True
            out["note"] = ("cfg['apply_is18168'] = False ignored: 1.2 makes IS 18168 mandatory for %s in Zone %s"
                           % (", ".join(occ["matched"]), z))
        else:
            out["applies"] = False
            out["note"] = "not applied: cfg['apply_is18168'] = False (EOR override; %s)" % occ["basis"]
    else:
        out["applies"] = bool(mandatory)
        if seismic and not mandatory:
            out["note"] = "optional: %s (1.2); set cfg['apply_is18168'] = True to apply it" % occ["basis"]
    return out


def applies_for_cfg(system, zone, cfg) -> dict:
    """applies() with the job's occupancy record and the cfg['apply_is18168'] override (ruling R8)."""
    cfg = cfg or {}
    return applies(system, zone, occupancy=cfg.get("occupancy"), override=cfg.get("apply_is18168"))


def gamma_LL(LL_kNm2) -> float:
    """cl. 5.5: 0.25 for imposed load class <= 3.0 kN/m2, 0.50 above."""
    v = float(LL_kNm2 or 0.0)
    for lim, g in GAMMA_LL_5_5:
        if v <= lim:
            return g
    return 0.50


def omega(system) -> dict:
    comps = components(system)
    sysn = comps[0] if comps else None
    if sysn is None:
        return {"found": False, "Omega": None, "clause": DOC + " 1.3 / 5.5", "cite": CITE_5_5,
                "reason": "no Omega for systems outside IS 18168 (1.3)"}
    om = max(OMEGA[c] for c in comps)                    # mixed system: the larger Omega governs every member (stricter)
    return {"found": True, "Omega": om, "system": sysn, "components": comps, "clause": DOC + " 5.5", "cite": CITE_5_5}


def overstrength_rows(system, LL_kNm2) -> list:
    """(fD, fL, fLat, family) rows of cl. 5.5 eq. (1) and (2)."""
    om = omega(system)
    if not om["found"]:
        return []
    g = gamma_LL(LL_kNm2)
    return [(1.2, g, om["Omega"], "IS 18168 5.5(1)"), (0.9, 0.0, om["Omega"], "IS 18168 5.5(2)")]


def overstrength_members(system) -> dict:
    """Who must be designed for the 5.5 combinations (cl. 5.5 a-d); mixed systems: the union of the components."""
    comps = components(system)
    return {"column": any(c in ("SMRF", "SCBF", "EBF") for c in comps), "beam": any(c in ("SCBF", "EBF") for c in comps),
            "brace": "EBF" in comps, "connection": bool(comps)}


def system_gate(system, zone, height_m=None) -> dict:
    """cl. 1.3: Zone V -> EBF only (SCBF not permitted); SMRF in Zones IV/V only when h < 15 m.
    Returns a {value, limit, ok, clause, cite} record; ok=None when the height is needed and missing."""
    comps = components(system)
    sysn = comps[0] if comps else None
    z = _zone(zone)
    rec = {"id": "is18168_1_3_system", "clause": DOC + " 1.3 / 12.1.1", "cite": CITE_1_3, "value": "+".join(comps) or sysn,
           "zone": z, "limit": "Zone V: EBF only; SMRF in Zones IV/V: h < 15 m", "dc": None, "source": "steel_engine/india_is18168.py"}
    if sysn is None or z is None:
        rec.update(ok=None, reason="system/zone not resolved")
        return rec
    if z == "V" and "SCBF" in comps:
        rec.update(ok=False, reason="SCBF not permitted in Zone V (1.3): use EBF (or SMRF < 15 m)")
        return rec
    if z in ("IV", "V") and "SMRF" in comps:
        if height_m is None:
            rec.update(ok=None, reason="building height needed for the 15 m limit (1.3 / 12.1.1)")
            return rec
        ok = float(height_m) < SMRF_HEIGHT_LIMIT_M_ZONES_IV_V
        rec.update(ok=ok, height_m=float(height_m), dc=float(height_m) / SMRF_HEIGHT_LIMIT_M_ZONES_IV_V,
                   reason=None if ok else "SMRF in Zone %s only for buildings of height less than 15 m (1.3)" % z)
        return rec
    rec.update(ok=True)
    return rec


def ry_for_grade(grade_key, quality=None):
    """Table 1 Ry for IS 2062 E250-E350 (B0 or C).  BR/A qualities are not listed -> None (5.2(b) route needs the
    elongation/CVN evidence, then Ry = 1.4 per 5.2.1)."""
    if quality is not None and str(quality).upper() not in ("B0", "C"):
        return None
    return RY.get(str(grade_key or "").upper())


def stricter(is800_limit, is18168_limit, *, kind="max"):
    """Precedence helper: the governing limit of two 'value <= limit' (kind='max') or 'value >= limit'
    (kind='min') requirements."""
    if is800_limit is None:
        return is18168_limit
    if is18168_limit is None:
        return is800_limit
    return min(is800_limit, is18168_limit) if kind == "max" else max(is800_limit, is18168_limit)


TABLE2_SECTION_TYPES = ("I", "box")
BOX_ROW_BASIS = ("IS 18168:2023 Table 2 gives closed-box rows only for braces (iii) and links (iv); no explicit row for a "
                 "box %s -> the closed-box brace row (iii) 21.4/21.4 eps/sqrt(Ry) is applied as the conservative "
                 "analogue (flagged; EOR to confirm)")


def table2_limits(component, fy_MPa, Ry, Ca=None, box=False):
    """Table 2 (5.3) limiting outstanding-flange b/tf and web d/tw for an I-section (or closed box) of the lateral
    load resisting system: component in beam | column | brace | link; Ca = Pu/(Py/gamma_m0) for columns.
    Box braces / links use their closed-box rows; a box column or beam (no explicit row) uses the closed-box
    brace row (iii) and the record carries that basis (H05)."""
    eps = (250.0 / float(fy_MPa)) ** 0.5
    f = eps / float(Ry) ** 0.5
    basis = None
    if box and component in ("brace", "link"):
        key = component + "_box"
    elif box:
        key, basis = "brace_box", BOX_ROW_BASIS % component
    else:
        key = component
    cf, cw = TABLE2[key]
    if component == "column" and not box:
        ca = float(Ca or 0.0)
        cw = 72.7 * (1 - 1.04 * ca) if ca <= 0.118 else max(24.9 * (2.68 - ca), 44.4)
    out = {"flange_b_over_tf": cf * f, "web_d_over_tw": cw * f, "eps": eps, "Ry": Ry, "Ca": Ca,
           "clause": DOC + " Table 2 / 5.3", "cite": CITE_TABLE2, "row": key}
    if box:
        out["cite"] = CITE_TABLE2 + "; closed box: flange width = flange width minus the web thicknesses"
    if basis:
        out["basis"] = basis
    return out


def table2_check(component, props, fy_MPa, Ry, Ca=None, member=None):
    """{id, member, value, limit, dc, ok, clause, cite} per Table 2: rolled / built-up I-section b = bf/2 outstand,
    d = clear web depth (d - 2 tf); closed box (H05) b = B - 2 tw between the webs, d = D - 2 tf between the flanges.
    Section types without a Table 2 row (CHS, angle, channel, ...) return ok None with the reason."""
    p = props
    st = p.get("section_type")
    if st not in TABLE2_SECTION_TYPES:
        return {"id": "is18168_table2_%s" % component, "member": member, "value": None, "limit": None, "dc": None,
                "ok": None, "found": False, "clause": DOC + " Table 2 / 5.3", "cite": CITE_TABLE2,
                "reason": "no Table 2 row for section type %r" % st, "source": "steel_engine/india_is18168.py"}
    box = st == "box"
    lim = table2_limits(component, fy_MPa, Ry, Ca=Ca, box=box)
    bf, tf, tw, d = float(p["bf"]), float(p["tf"]), float(p["tw"]), float(p["d"])
    rf = ((bf - 2.0 * tw) / tf) if box else ((bf / 2.0) / tf)
    rw = (d - 2.0 * tf) / tw
    dcf, dcw = rf / lim["flange_b_over_tf"], rw / lim["web_d_over_tw"]
    dc = max(dcf, dcw)
    out = {"id": "is18168_table2_%s" % component, "member": member, "value": {"b/tf": round(rf, 2), "d/tw": round(rw, 2)},
           "limit": {"b/tf": round(lim["flange_b_over_tf"], 2), "d/tw": round(lim["web_d_over_tw"], 2)},
           "dc": dc, "ok": dc <= 1.0, "clause": lim["clause"], "cite": lim["cite"], "eps": lim["eps"], "Ry": Ry,
           "Ca": Ca, "section_type": st, "table2_row": lim["row"], "source": "steel_engine/india_is18168.py"}
    if box:
        out["flange_basis"] = "b = B - 2 tw (flange width minus the web thicknesses); d = D - 2 tf"
    if lim.get("basis"):
        out["basis"] = lim["basis"]
    return out
