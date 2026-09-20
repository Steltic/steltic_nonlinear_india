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


def normalize_system(system):
    s = str(system or "").upper().replace("-", "").replace("_", "").replace(" ", "")
    return _SYS.get(s)


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


def applies(system, zone, *, opt_in=False) -> dict:
    """{applies, mandatory, system, zone, cite}.  Mandatory in Zones III-V for SMRF/SCBF/EBF (1.2/1.3); in Zone II
    only when the job opts in (cfg['apply_is18168']).  Other systems (OMRF/OCBF/...) are outside its scope (1.3)."""
    sysn = normalize_system(system)
    z = _zone(zone)
    if sysn is None:
        return {"applies": False, "mandatory": False, "system": sysn, "zone": z,
                "reason": "system not covered by IS 18168 (1.3: SMRF, SCBF, EBF only)", "cite": CITE_1_2}
    mandatory = z in ("III", "IV", "V")
    return {"applies": bool(mandatory or (opt_in and z == "II")), "mandatory": mandatory, "system": sysn,
            "zone": z, "cite": CITE_1_2}


def gamma_LL(LL_kNm2) -> float:
    """cl. 5.5: 0.25 for imposed load class <= 3.0 kN/m2, 0.50 above."""
    v = float(LL_kNm2 or 0.0)
    for lim, g in GAMMA_LL_5_5:
        if v <= lim:
            return g
    return 0.50


def omega(system) -> dict:
    sysn = normalize_system(system)
    if sysn is None:
        return {"found": False, "Omega": None, "clause": DOC + " 1.3 / 5.5", "cite": CITE_5_5,
                "reason": "no Omega for systems outside IS 18168 (1.3)"}
    return {"found": True, "Omega": OMEGA[sysn], "system": sysn, "clause": DOC + " 5.5", "cite": CITE_5_5}


def overstrength_rows(system, LL_kNm2) -> list:
    """(fD, fL, fLat, family) rows of cl. 5.5 eq. (1) and (2)."""
    om = omega(system)
    if not om["found"]:
        return []
    g = gamma_LL(LL_kNm2)
    return [(1.2, g, om["Omega"], "IS 18168 5.5(1)"), (0.9, 0.0, om["Omega"], "IS 18168 5.5(2)")]


def overstrength_members(system) -> dict:
    """Who must be designed for the 5.5 combinations (cl. 5.5 a-d)."""
    sysn = normalize_system(system)
    return {"column": sysn in ("SMRF", "SCBF", "EBF"), "beam": sysn in ("SCBF", "EBF"), "brace": sysn == "EBF",
            "connection": sysn is not None}


def system_gate(system, zone, height_m=None) -> dict:
    """cl. 1.3: Zone V -> EBF only (SCBF not permitted); SMRF in Zones IV/V only when h < 15 m.
    Returns a {value, limit, ok, clause, cite} record; ok=None when the height is needed and missing."""
    sysn = normalize_system(system)
    z = _zone(zone)
    rec = {"id": "is18168_1_3_system", "clause": DOC + " 1.3 / 12.1.1", "cite": CITE_1_3, "value": sysn, "zone": z,
           "limit": "Zone V: EBF only; SMRF in Zones IV/V: h < 15 m", "dc": None, "source": "steel_engine/india_is18168.py"}
    if sysn is None or z is None:
        rec.update(ok=None, reason="system/zone not resolved")
        return rec
    if z == "V" and sysn == "SCBF":
        rec.update(ok=False, reason="SCBF not permitted in Zone V (1.3): use EBF (or SMRF < 15 m)")
        return rec
    if z in ("IV", "V") and sysn == "SMRF":
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
