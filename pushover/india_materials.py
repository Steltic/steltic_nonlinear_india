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

# IS 1161:2014 Table 2 (tubes for structural purposes): ReH / Rm min, MPa -- the values steltic_india sections.py uses
IS1161_TABLE2 = {"YST210": (210.0, 330.0), "YST240": (240.0, 410.0), "YST310": (310.0, 450.0), "YST355": (355.0, 490.0)}
IS1161_CITE = "IS 1161:2014 Table 2 (Tensile Properties of Steel Tubes for Structural Purposes)"
# which schedule roles belong to which member kind (steltic_india member_schedule.csv `role`)
ROLE_KIND = {"lateral_col": "col", "gravity_col": "col", "col": "col", "floor": "beam", "roof": "beam", "link": "beam",
             "beam": "beam", "collector": "beam", "brace": "brace"}


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
    from . import india_sections as ISEC
    bx = ISEC.get_mm(section)
    if bx is not None:                     # NL-4: HR built-up box -- exact plate values (mm), not via inches
        out = dict(label=bx["label"], type="BOX", box=True, tube=False)
        for k in ("A", "rx", "ry", "d", "bf", "tf", "tw", "Zx", "Zy", "Sx", "Sy", "Ix", "Iy", "J", "Aw"):
            out[k] = float(bx[k])
        out["source"] = bx["source"]
        return out
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


def _is1161_grade(grade) -> str | None:
    g = str(grade or "").upper().replace(" ", "")
    return g if g in IS1161_TABLE2 else None


def package_materials(root) -> dict:
    """NL-5: the steel the HR package designed with -- one source for the pushover, the NLRHA and the DDM.

    * design/calc_package.json `members[]`: per (role, section) the grade (`inputs.grade`) and the material record of the
      governing element (`governing_element_result.material`: fy / fu by IS 2062 Table 3 thickness band -- AUD-2 plate
      thickness for built-up boxes -- or IS 1161 Table 2 for tubes);
    * design/cfg_snapshot.json: steel_grade, brace_grade, brace_process, grade_by_section.
    Returns {'records': {(role, SECTION): rec}, 'snapshot': {...}, 'source': ...}; empty when the files are absent."""
    import json as _json, os as _os
    root = str(root)
    out = dict(records={}, snapshot={}, source=None)
    cp = _os.path.join(root, "design", "calc_package.json")
    if _os.path.exists(cp):
        try:
            pkgj = _json.load(open(cp, encoding="utf-8")) or {}
        except Exception:
            pkgj = {}
        for m in pkgj.get("members") or []:
            inp = m.get("inputs") or {}
            sec = str(inp.get("section") or m.get("section") or "").upper().replace(" ", "")
            role = str(inp.get("role") or "").lower()
            if not sec or not role:
                continue
            mat = ((m.get("governing_element_result") or {}).get("material") or {})
            out["records"][(role, sec)] = dict(role=role, section=sec, grade=inp.get("grade") or mat.get("grade"),
                                               fy_MPa=mat.get("fy_MPa"), fu_MPa=mat.get("fu_MPa"),
                                               t_mm=mat.get("t_mm"), band=mat.get("thickness_band_mm"),
                                               cite=mat.get("cite"), member_id=m.get("id"))
        out["source"] = "design/calc_package.json members[].governing_element_result.material"
    sn = _os.path.join(root, "design", "cfg_snapshot.json")
    if _os.path.exists(sn):
        try:
            snap = _json.load(open(sn, encoding="utf-8")) or {}
        except Exception:
            snap = {}
        out["snapshot"] = {k: snap.get(k) for k in ("steel_grade", "brace_grade", "brace_process", "grade_by_section")
                           if snap.get(k) is not None}
    return out


def _grade_or_none(g):
    try:
        return normalize_grade(g) if g else None
    except ValueError:
        return None


def material_plan(nl_plan: dict | None = None, package: dict | None = None) -> dict:
    """India material block: nl_plan.material (EOR inputs / overrides) over the HR package's steel (NL-5), with
    defaults and citations. `package` is package_materials(root)."""
    mp = dict(((nl_plan or {}).get("material") or {}))
    pk = package or {}
    snap = pk.get("snapshot") or {}
    f = mp.get("expected_strength_factor")
    gbs = {str(k).upper().replace(" ", ""): v for k, v in (snap.get("grade_by_section") or {}).items()}
    gbs.update({str(k).upper().replace(" ", ""): v for k, v in (mp.get("grade_by_section") or {}).items()})
    gbr = {}
    if snap.get("brace_grade"):
        gbr["brace"] = snap["brace_grade"]
    gbr.update({str(k).lower(): v for k, v in (mp.get("grade_by_role") or {}).items()})
    out = dict(
        default_grade=normalize_grade(mp.get("grade") or _grade_or_none(snap.get("steel_grade")) or "E250"),
        default_grade_basis=("nl_plan.material.grade (EOR)" if mp.get("grade") else
                             ("HR package cfg_snapshot.steel_grade" if snap.get("steel_grade") else "E250 (no grade in the package)")),
        grade_by_section=gbs, grade_by_role=gbr,
        eor_sections={str(k).upper().replace(" ", "") for k in (mp.get("grade_by_section") or {})},
        eor_roles={str(k).lower() for k in (mp.get("grade_by_role") or {})},
        eor_grade=bool(mp.get("grade")),
        package_records=dict(pk.get("records") or {}),
        package_source=pk.get("source"),
        brace_process=snap.get("brace_process"),
        expected_strength_factor=float(f) if f is not None else 1.0,
        expected_strength_basis=(mp.get("expected_strength_cite") or
                                 ("EOR input" if f is not None else "nominal (factor 1.0): IS 800 has no Ry; IS 18168 Table 1 Ry "
                                                                    "is for capacity design and is not applied by default")),
        hollow_forming=str(mp.get("hollow_forming") or "hot_rolled"),
        cite=IS2062_CITE,
    )
    return out


def _fy_from_grade(grade, sp) -> tuple:
    """(fy, fu or None, band, cite, grade label) for an IS 2062 grade by thickness, or an IS 1161 tube grade."""
    tg = _is1161_grade(grade)
    if tg:
        fy, fu = IS1161_TABLE2[tg]
        return fy, fu, None, IS1161_CITE, tg
    g = normalize_grade(grade)
    t = governing_thickness_mm(sp)
    fy, band = fy_is2062(g, t)
    return fy, None, band, IS2062_CITE, g


def fy_for_member(section: str, role: str | None = None, plan: dict | None = None) -> dict:
    """fy (nominal, MPa), expected fye = factor*fy, grade and band for one member.

    Resolution (NL-5): an EOR grade in nl_plan.material wins (by section, then role, then the plan grade); else the HR
    package's own record for (role, section) -- the fy the design used (IS 2062 Table 3 by thickness, IS 1161 Table 2
    for tubes); else the package grade for the section (cfg_snapshot grade_by_section / brace_grade / steel_grade) on
    the IS 2062 table. `role` may be a schedule role (lateral_col, floor, link, ...) or a kind (col / beam / brace):
    with a kind, the package records of that kind for the section are used when they agree, else the lowest fy is
    taken and flagged `ambiguous_role`."""
    mp = plan or material_plan(None)
    key = str(section).upper().replace(" ", "")
    r = str(role or "").lower()
    kind = ROLE_KIND.get(r, r)
    sp = section_props_mm(section)
    t = governing_thickness_mm(sp)
    fac = float(mp["expected_strength_factor"])
    source, flags, rec = None, [], None
    grade = None
    if key in mp.get("eor_sections", ()):
        grade, source = mp["grade_by_section"][key], "nl_plan.material.grade_by_section (EOR)"
    elif r and r in mp.get("eor_roles", ()):
        grade, source = mp["grade_by_role"][r], "nl_plan.material.grade_by_role (EOR)"
    elif mp.get("eor_grade"):
        grade, source = mp["default_grade"], "nl_plan.material.grade (EOR)"
    if grade is None:
        recs = mp.get("package_records") or {}
        rec = recs.get((r, key))
        if rec is None:
            cands = [v for (rr, ss), v in recs.items() if ss == key and ROLE_KIND.get(rr, rr) == kind and v.get("fy_MPa")]
            if not cands:
                cands = [v for (rr, ss), v in recs.items() if ss == key and v.get("fy_MPa")]
            if cands:
                rec = min(cands, key=lambda v: float(v["fy_MPa"]))
                if len({float(v["fy_MPa"]) for v in cands}) > 1:
                    flags.append("ambiguous_role: %s has fy %s by role; the lowest is used" %
                                 (key, sorted({(v["role"], v["fy_MPa"]) for v in cands})))
        if rec is not None and rec.get("fy_MPa"):
            fy = float(rec["fy_MPa"])
            g = rec.get("grade") or ""
            try:                                          # cross-check the package value on the IS 2062 / IS 1161 table
                fy_tab = _fy_from_grade(g, sp)[0]
            except Exception:
                fy_tab = None
            if fy_tab is not None and abs(fy_tab - fy) > 0.5:
                flags.append("package fy %.0f differs from the table value %.0f for %s at t=%.1f mm" % (fy, fy_tab, g, t))
            return dict(section=key, role=rec.get("role"), grade=g, t_mm=round(t, 2), band=rec.get("band"), fy_MPa=fy,
                        fu_MPa=rec.get("fu_MPa"), factor=fac, fye_MPa=fy * fac, cite=rec.get("cite") or IS2062_CITE,
                        source="HR package %s (%s)" % (mp.get("package_source") or "calc_package", rec.get("member_id")),
                        table_fy_MPa=fy_tab, factor_basis=mp["expected_strength_basis"], flags=flags,
                        ry_is18168_reference=IS18168_RY.get(_grade_or_none(g) or ""))
        grade = mp["grade_by_section"].get(key) or (mp["grade_by_role"].get(r) or mp["grade_by_role"].get(kind)) \
            or mp["default_grade"]
        source = ("HR package grade (cfg_snapshot) on the table" if (mp["grade_by_section"].get(key) or
                  mp["grade_by_role"].get(r) or mp["grade_by_role"].get(kind)) else mp.get("default_grade_basis", "default"))
    fy, fu, band, cite, glab = _fy_from_grade(grade, sp)
    return dict(section=key, role=r or None, grade=glab, t_mm=round(t, 2), band=band, fy_MPa=fy, fu_MPa=fu, factor=fac,
                fye_MPa=fy * fac, cite=cite, source=source, factor_basis=mp["expected_strength_basis"], flags=flags,
                ry_is18168_reference=IS18168_RY.get(glab))


def buckling_classes(sp: dict, hollow_forming: str = "hot_rolled") -> dict:
    """IS 800 Table 10 buckling class about z-z (major) and y-y (minor)."""
    if sp.get("box"):
        # Table 10 welded box: 'generally b'; thick welds and b/tf < 30: c -- the conservative row c for every built-up
        # box, as steltic_india india_is800 does (WP6-fix)
        return {"zz": "c", "yy": "c", "basis": "Table 10 welded box (row c, as the HR engine)"}
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
    if sp.get("box"):
        Av = sp.get("Aw") or 2.0 * (sp["d"] - 2 * sp["tf"]) * sp["tw"]      # two webs (8.4.1.1 welded plates, as HR)
    elif sp.get("tube"):
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
