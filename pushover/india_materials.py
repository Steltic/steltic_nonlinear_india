"""india_materials.py -- IS 2062 / IS 800 material and member-capacity helpers for the India NL models (WP4.5).

One source of steel strength for the pushover, the NLRHA and the DDM:
  * fy by grade and thickness band: IS 2062 (Part 1):2025 Table 3, ReH (MPa) for t <= 16 / >16-40 / >40-100 / >100 mm
    (values transcribed from the PDF, Table 3 rows i-xi);
  * expected-strength factor: an EOR input (nl_plan.material.expected_strength_factor), default 1.0 = nominal.
    IS 800 has no Ry; IS 18168:2023 Table 1 gives Ry for capacity design only (reported, not applied by default);
  * compression capacity: IS 800:2007 7.1.2 Pd = A·fcd, fcd = chi·fy/gamma_m0, buckling class from Table 10,
    imperfection factor alpha from Table 7, gamma_m0 = 1.10 (Table 5);
  * section capacities for the IS 800 Annex B-1.2 check (Sections 6, 7 (section), 8.2.1, 8.4, 9.3.1).

Section properties come from pushover.sections_db (IS 808 / IS 1161 rows, stored in inch units) and are converted
back to mm here. Nothing in this module is an acceptance criterion for nonlinear analysis (owner ruling D7).
"""
from __future__ import annotations
import math

MM_PER_IN = 25.4
E_MPA = 200000.0
GAMMA_M0 = 1.10          # IS 800 Table 5 (resistance governed by yielding)

# IS 2062 (Part 1):2025 Table 3 -- ReH, Min (MPa) by thickness/diameter: <=16, >16-40, >40-100, >100
IS2062_TABLE3_REH = {
    "E235": (235, 225, 215, 195),
    "E250": (250, 240, 230, 210),
    "E275": (275, 265, 255, 225),
    "E300": (300, 290, 280, 250),
    "E350": (350, 330, 320, 290),
    "E410": (410, 390, 380, 350),
    "E450": (450, 430, 420, 390),
    "E500": (500, 480, 470, 450),
    "E550": (550, 530, 520, None),
    "E600": (600, 580, 570, None),
    "E650": (650, 630, 620, None),
}
IS2062_CITE = "IS 2062 (Part 1):2025 Table 3 (ReH by thickness band)"

# IS 800:2007 Table 7 imperfection factor alpha
ALPHA = {"a": 0.21, "b": 0.34, "c": 0.49, "d": 0.76}

# IS 18168:2023 Table 1 material strength uncertainty factors (reference; capacity design only)
IS18168_RY = {"E250": 1.4, "E275": 1.4, "E300": 1.3, "E350": 1.2}

TUBE_TYPES = ("CHS", "RHS", "SHS", "HSS")


def normalize_grade(grade) -> str:
    g = str(grade or "E250").upper().replace(" ", "").replace("FE410", "E250")
    for q in ("BR", "B0", "A", "B", "C", "CU"):
        if g.endswith(q) and g[:-len(q)] in IS2062_TABLE3_REH:
            g = g[:-len(q)]
            break
    if g not in IS2062_TABLE3_REH:
        raise ValueError("steel grade %r not in IS 2062 Table 3 (E235..E650)" % grade)
    return g


def fy_is2062(grade="E250", t_mm: float = 10.0) -> tuple:
    """(fy MPa, band label) per IS 2062 Table 3 for thickness t (mm)."""
    g = normalize_grade(grade)
    row = IS2062_TABLE3_REH[g]
    t = float(t_mm)
    if t <= 16.0:
        i, band = 0, "t<=16"
    elif t <= 40.0:
        i, band = 1, "16<t<=40"
    elif t <= 100.0:
        i, band = 2, "40<t<=100"
    else:
        i, band = 3, "t>100"
    fy = row[i]
    if fy is None:
        raise ValueError("IS 2062 Table 3 gives no ReH for %s at t=%.1f mm (mutual agreement)" % (g, t))
    return float(fy), band


def section_props_mm(section: str) -> dict:
    """IS 808 / IS 1161 section properties in mm units (from the inch-converted tables)."""
    from . import sections_db as SDB
    p = SDB.props(section)
    s = MM_PER_IN
    out = dict(label=str(section).upper().replace(" ", ""), type=str(p.get("Type") or ""))
    out["A"] = float(p.get("A_si_mm2") or p["A"] * s * s)
    for k in ("rx", "ry", "d", "bf", "tf", "tw"):
        if isinstance(p.get(k), float):
            out[k] = p[k] * s
    for k in ("Zx", "Zy", "Sx", "Sy"):
        if isinstance(p.get(k), float):
            out[k] = p[k] * s ** 3
    for k in ("Ix", "Iy", "J"):
        if isinstance(p.get(k), float):
            out[k] = p[k] * s ** 4
    if isinstance(p.get("t_mm"), float):
        out["t"] = p["t_mm"]
    if isinstance(p.get("D_mm"), float):
        out["D"] = p["D_mm"]
    out["tube"] = is_tube(section, p)
    if out["tube"] and "t" not in out:
        out["t"] = out.get("tw") or out.get("tf")
    if out["tube"] and "D" not in out:
        out["D"] = out.get("d")
    return out


def is_tube(section: str, props: dict | None = None) -> bool:
    """Tube detection by table Type (CHS/RHS/SHS/HSS), not by the 'HSS' label prefix (WP4.14)."""
    if props is None:
        from . import sections_db as SDB
        try:
            props = SDB.props(section)
        except KeyError:
            props = {}
    t = str(props.get("Type") or "").upper()
    if t in TUBE_TYPES:
        return True
    lab = str(section).upper()
    return lab.startswith(TUBE_TYPES)


def governing_thickness_mm(sp: dict) -> float:
    if sp.get("tube"):
        return float(sp.get("t") or 0.0)
    return float(max(sp.get("tf") or 0.0, sp.get("tw") or 0.0))


def material_plan(nl_plan: dict | None = None) -> dict:
    """India material block from nl_plan.material (EOR inputs), with defaults and citations."""
    mp = dict(((nl_plan or {}).get("material") or {}))
    f = mp.get("expected_strength_factor")
    out = dict(
        default_grade=normalize_grade(mp.get("grade") or "E250"),
        grade_by_section={str(k).upper().replace(" ", ""): normalize_grade(v) for k, v in (mp.get("grade_by_section") or {}).items()},
        grade_by_role={str(k).lower(): normalize_grade(v) for k, v in (mp.get("grade_by_role") or {}).items()},
        expected_strength_factor=float(f) if f is not None else 1.0,
        expected_strength_basis=(mp.get("expected_strength_cite") or
                                 ("EOR input" if f is not None else "nominal (factor 1.0): IS 800 has no Ry; IS 18168 Table 1 Ry "
                                                                    "is for capacity design and is not applied by default")),
        hollow_forming=str(mp.get("hollow_forming") or "hot_rolled"),
        cite=IS2062_CITE,
    )
    return out


def fy_for_member(section: str, role: str | None = None, plan: dict | None = None) -> dict:
    """fy (nominal, MPa), expected fye = factor*fy, grade and band for one member section."""
    mp = plan or material_plan(None)
    key = str(section).upper().replace(" ", "")
    grade = mp["grade_by_section"].get(key) or (mp["grade_by_role"].get(str(role or "").lower()) if role else None) \
        or mp["default_grade"]
    sp = section_props_mm(section)
    t = governing_thickness_mm(sp)
    fy, band = fy_is2062(grade, t)
    fac = float(mp["expected_strength_factor"])
    return dict(section=key, grade=grade, t_mm=round(t, 2), band=band, fy_MPa=fy, factor=fac, fye_MPa=fy * fac,
                cite=IS2062_CITE, factor_basis=mp["expected_strength_basis"],
                ry_is18168_reference=IS18168_RY.get(grade))


def buckling_classes(sp: dict, hollow_forming: str = "hot_rolled") -> dict:
    """IS 800 Table 10 buckling class about z-z (major) and y-y (minor)."""
    if sp.get("tube"):
        c = "a" if str(hollow_forming).lower().startswith("hot") else "b"
        return {"zz": c, "yy": c, "basis": "Table 10 hollow section, %s" % hollow_forming}
    typ = str(sp.get("type") or "").upper()
    if typ in ("ISA", "MC", "LC", "JC", "SC", "MPC", "ISLC", "ISMC") or typ.endswith("C") and typ not in ("NPB", "WPB"):
        return {"zz": "c", "yy": "c", "basis": "Table 10 channel/angle"}
    h, b, tf = sp.get("d") or 0.0, sp.get("bf") or 1.0, sp.get("tf") or 0.0
    if h / b > 1.2:
        if tf <= 40.0:
            return {"zz": "a", "yy": "b", "basis": "Table 10 rolled I, h/bf>1.2, tf<=40"}
        return {"zz": "b", "yy": "c", "basis": "Table 10 rolled I, h/bf>1.2, 40<tf<=100"}
    if tf <= 100.0:
        return {"zz": "b", "yy": "c", "basis": "Table 10 rolled I, h/bf<=1.2, tf<=100"}
    return {"zz": "d", "yy": "d", "basis": "Table 10 rolled I, tf>100"}


def chi(lam: float, cls: str) -> float:
    """IS 800 7.1.2.1 stress reduction factor chi for non-dimensional slenderness lam."""
    a = ALPHA[cls]
    phi = 0.5 * (1.0 + a * (lam - 0.2) + lam * lam)
    return min(1.0, 1.0 / (phi + math.sqrt(max(phi * phi - lam * lam, 0.0))))


def is800_Pd(section: str, L_mm: float, fy_MPa: float = 250.0, K: float = 1.0, gamma_m0: float = GAMMA_M0,
             hollow_forming: str = "hot_rolled") -> dict:
    """IS 800:2007 7.1.2 design compressive strength Pd (N) = A·chi·fy/gamma_m0, min over both axes."""
    sp = section_props_mm(section)
    cls = buckling_classes(sp, hollow_forming)
    best = None
    for ax, r in (("zz", sp.get("rx")), ("yy", sp.get("ry"))):
        if not r:
            continue
        KLr = K * float(L_mm) / r
        fcc = math.pi ** 2 * E_MPA / KLr ** 2
        lam = math.sqrt(fy_MPa / fcc)
        c = chi(lam, cls[ax])
        fcd = min(c * fy_MPa / gamma_m0, fy_MPa / gamma_m0)
        Pd = sp["A"] * fcd
        row = dict(axis=ax, cls=cls[ax], alpha=ALPHA[cls[ax]], KLr=KLr, lam=lam, chi=c, fcd=fcd, Pd_N=Pd)
        if best is None or Pd < best["Pd_N"]:
            best = row
    best.update(section=sp["label"], A_mm2=sp["A"], fy_MPa=fy_MPa, gamma_m0=gamma_m0, L_mm=float(L_mm), K=K,
                basis=cls["basis"], cite="IS 800:2007 7.1.2 / 7.1.2.1, Table 7, Table 10, gamma_m0 Table 5")
    return best


def brace_strengths(section: str, L_mm: float, fye_MPa: float, K: float = 1.0, hollow_forming: str = "hot_rolled") -> dict:
    """Brace model strengths (nominal, no partial factor): Pye = A·fye; Pcr = A·chi·fye (IS 800 7.1.2.1 curve)."""
    sp = section_props_mm(section)
    cls = buckling_classes(sp, hollow_forming)
    r = min(v for v in (sp.get("rx"), sp.get("ry")) if v)
    ax = "yy" if r == sp.get("ry") else "zz"
    KLr = K * float(L_mm) / r
    fcc = math.pi ** 2 * E_MPA / KLr ** 2
    lam = math.sqrt(fye_MPa / fcc)
    c = chi(lam, cls[ax])
    return dict(section=sp["label"], A_mm2=sp["A"], r_mm=r, KLr=KLr, lam=lam, cls=cls[ax], chi=c,
                Pye_N=sp["A"] * fye_MPa, Pcr_N=sp["A"] * c * fye_MPa, fye_MPa=fye_MPa,
                cite="IS 800:2007 7.1.2.1 curve (%s), no gamma_m0 (model strength)" % cls[ax])


def section_capacity(section: str, fy_MPa: float, gamma_m0: float = GAMMA_M0) -> dict:
    """IS 800 section capacities for Annex B-1.2 (instability / LTB / amplification excluded by B-1.2):
    Nd = A·fy/gamma_m0 (6.2 / 7 section), Mdz = Zpz·fy/gamma_m0 (8.2.1.2, plastic/compact, beta_b = 1),
    Mdy = Zpy·fy/gamma_m0, Vd = Av·fy/(sqrt(3)·gamma_m0) (8.4.1)."""
    sp = section_props_mm(section)
    A = sp["A"]
    Zpz = sp.get("Zx") or 0.0
    Zpy = sp.get("Zy") or 0.0
    if sp.get("tube"):
        Av = 2.0 * A / math.pi if str(sp.get("type")).upper() == "CHS" else A * 0.5
    else:
        Av = (sp.get("d") or 0.0) * (sp.get("tw") or 0.0)
    return dict(section=sp["label"], A=A, Nd_N=A * fy_MPa / gamma_m0, Mdz_Nmm=Zpz * fy_MPa / gamma_m0,
                Mdy_Nmm=Zpy * fy_MPa / gamma_m0, Vd_N=Av * fy_MPa / (math.sqrt(3.0) * gamma_m0), fy_MPa=fy_MPa,
                gamma_m0=gamma_m0,
                cite="IS 800:2007 Annex B-1.2 -> 6.2 (Tdg), 7 (section A·fy/gamma_m0), 8.2.1.2 (Zp·fy/gamma_m0), "
                     "8.4 (Av·fy/(sqrt3·gamma_m0)), 9.3.1.1 (linear interaction)")


def b12_interaction(N_N: float, Mz_Nmm: float, My_Nmm: float, V_N: float, cap: dict) -> dict:
    """IS 800 9.3.1.1 conservative linear interaction N/Nd + Mz/Mdz + My/Mdy <= 1 and shear V/Vd (B-1.2)."""
    terms = dict(N=abs(N_N) / cap["Nd_N"] if cap["Nd_N"] else 0.0,
                 Mz=abs(Mz_Nmm) / cap["Mdz_Nmm"] if cap["Mdz_Nmm"] else 0.0,
                 My=abs(My_Nmm) / cap["Mdy_Nmm"] if cap["Mdy_Nmm"] else 0.0)
    dc = terms["N"] + terms["Mz"] + terms["My"]
    dv = abs(V_N) / cap["Vd_N"] if cap["Vd_N"] else 0.0
    return dict(dc=dc, dc_shear=dv, terms=terms, ok=bool(dc <= 1.0 and dv <= 1.0),
                clause="IS 800:2007 Annex B-1.2 / 9.3.1.1 / 8.4")


# ------------------------------------------------------------------ IS 800 §12 / IS 18168 reference deformation capacities
def reference_rotation(system: str | None) -> dict:
    """IS 800 §12 joint-rotation capacity for the SFRS (a REFERENCE value, not an acceptance limit — D7)."""
    s = str(system or "").upper()
    rows = []
    if "EBF" in s or "ECCENTRIC" in s:
        rows.append(dict(value=0.08, what="link rotation angle", clause="IS 18168:2023 12.3.3.1",
                         quote="The link rotation angle shall not exceed 0.08 rad."))
        return dict(value=None, system=s, refs=rows,
                    note="IS 800 12.9: EBF 'in accordance with specialist literature'; IS 18168 link value shown")
    if "SMF" in s or "SMRF" in s or "SPECIAL MOMENT" in s:
        rows.append(dict(value=0.04, what="joint rotation", clause="IS 800:2007 12.11.1",
                         quote="withstand inelastic deformation corresponding to a joint rotation of 0.04 radians"))
        rows.append(dict(value=0.04, what="storey drift angle (connections)", clause="IS 18168:2023 12.1.3.2",
                         quote="connections accommodate storey drift angle 0.04 rad"))
        return dict(value=0.04, system=s, refs=rows)
    if "SCBF" in s or "SPECIAL CONC" in s or "SBF" in s:
        rows.append(dict(value=0.04, what="joint rotation", clause="IS 800:2007 12.8.1",
                         quote="joint rotation of at least 0.04 radians without degradation"))
        return dict(value=0.04, system=s, refs=rows)
    if "OCBF" in s or "OBF" in s or "ORDINARY CONC" in s:
        rows.append(dict(value=0.02, what="joint rotation", clause="IS 800:2007 12.7.1",
                         quote="joint rotation of at least 0.02 radians without degradation"))
        return dict(value=0.02, system=s, refs=rows)
    if "OMF" in s or "OMRF" in s or "ORDINARY MOMENT" in s or "PORTAL" in s:
        rows.append(dict(value=0.02, what="joint rotation", clause="IS 800:2007 12.10.1",
                         quote="joint rotation of 0.02 radians without degradation in strength"))
        return dict(value=0.02, system=s, refs=rows)
    return dict(value=None, system=s, refs=[], note="system not mapped to an IS 800 §12 frame type")
