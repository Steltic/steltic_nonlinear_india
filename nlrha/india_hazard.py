"""India site hazard — IS 1893 Part 1:2016 zone / Z / ELASTIC spectrum for nonlinear analysis (not USGS).

Owner ruling D6: the nonlinear (NSP / NLRHA) target is the IS 1893 *elastic* spectrum
  DBE = (Z/2)·I·(Sa/g)      MCE = Z·I·(Sa/g)          (never divided by R)
Both levels are built and reported. The design coefficient Ah = (Z/2)(Sa/g)/(R/I) is kept only as a
labelled *reference* curve (it is the linear design-force coefficient, 6.4.2, not an NL demand).

NOTE (integration, WP1.14): `sa_over_g` delegates to the vendored shared `india_seismic.sa_over_g`
(snl/vendor_steltic_india, byte-identical to steltic_india; scripts/check_vendored.py guards drift --
do not fork india_seismic here).

Built only from LIVE RAG / indexed excerpts under engineering_rag_india
(stem IS_1893_Part_1_2016). Does NOT call USGS. USA site_hazard.build_site_hazard
remains available as ASCE scaffolding for regression; on this fork India jobs must
prefer build_india_site_hazard / cfg seismic fields.

Citations (verbatim anchors; re-retrieve LIVE before deliverable quotes):
  * Table 3 Seismic Zone Factor Z (Clause 6.4.2): II=0.10, III=0.16, IV=0.24, V=0.36
  * 6.4.2 Ah = (Z/2)·(Sa/g)/(R/I); Sa/g from soil-type expressions (Fig. 2 / 6.4.2)
  * 6.4.2.1 soil types I / II / III (rock-hard / medium-stiff / soft)
  * 7.7.4 Time History Method: ground motion preferably compatible with the design
    acceleration spectrum — NOT an ASCE 7 Ch.16 suite-acceptance code
  * 6.4.7 site-specific spectrum may be used if not less than 6.4.2

found:false: USGS MCE_R, NSHM disaggregation, conditional-mean spectrum as India authority.
"""
from __future__ import annotations

import math
import time
from typing import Any

from . import india_authority as IA

# Table 3 Seismic Zone Factor Z (Clause 6.4.2) — RAG exact_table 3
ZONE_FACTOR_Z = {
    "II": 0.10,
    "III": 0.16,
    "IV": 0.24,
    "V": 0.36,
}


# 6.4.2.1 / Table 4 soil types. Words are the IS 6.4.2.1 descriptors (rock or hard / medium or stiff / soft).
# ASCE site-class letters have NO cited IS mapping and are refused (NLREPO-14).
SOIL_ALIASES = {
    "i": "I", "1": "I", "rock": "I", "hard": "I", "rocky": "I", "type_i": "I", "rock_or_hard": "I",
    "ii": "II", "2": "II", "medium": "II", "stiff": "II", "type_ii": "II", "medium_or_stiff": "II",
    "iii": "III", "3": "III", "soft": "III", "type_iii": "III",
}

# D6: NL target level factors on Z·I·Sa/g (never R)
LEVEL_FACTOR = {"DBE": 0.5, "MCE": 1.0}
NL_LEVELS = ("DBE", "MCE")
LEVEL_LABEL = {
    "DBE": "IS 1893 elastic DBE (Z/2)·I·Sa/g (no R)",
    "MCE": "IS 1893 elastic MCE Z·I·Sa/g (no R)",
}

CITE = {
    "zone_table": {
        "stem": IA.PRIMARY_STEM,
        "clause": "Table 3",
        "cite": "IS 1893 (Part 1):2016 Table 3 (Clause 6.4.2)",
        "found": True,
    },
    "ah_formula": {
        "stem": IA.PRIMARY_STEM,
        "clause": "6.4.2",
        "cite": "IS 1893 (Part 1):2016 6.4.2 — Ah = (Z/2)·(Sa/g)/(R/I)",
        "found": True,
        "excerpt": (
            "The design horizontal seismic coefficient Ah for a structure shall be determined by: "
            "Ah = (Z/2)·(Sa/g)/(R/I) where Z = seismic zone factor given in Table 3; "
            "I = importance factor …; R = response reduction factor …; "
            "(Sa/g) = design acceleration coefficient for different soil types …"
        ),
    },
    "spectrum": {
        "stem": IA.PRIMARY_STEM,
        "clause": "6.4.2",
        "cite": "IS 1893 (Part 1):2016 6.4.2 Sa/g expressions (response-spectrum form)",
        "found": True,
    },
    "time_history_compat": {
        "stem": IA.PRIMARY_STEM,
        "clause": "7.7.4",
        "cite": "IS 1893 (Part 1):2016 7.7.4 Time History Method",
        "found": True,
        "excerpt": (
            "Time history method shall be based on an appropriate ground motion "
            "(preferably compatible with the design acceleration spectrum in the desired "
            "range of natural periods) and shall be performed using accepted principles of "
            "earthquake structural dynamics."
        ),
    },
    "elastic_levels": {
        "stem": IA.PRIMARY_STEM,
        "clause": "6.4.2 / 3.28",
        "cite": "IS 1893 (Part 1):2016 6.4.2 Sa/g with Z (3.28 PGA 'considered by this standard'); "
                "DBE = (Z/2)·I·Sa/g, MCE = Z·I·Sa/g — owner ruling D6 (Z/2 = DBE convention of "
                "IS 1893:2002; IS 800:2007 4.1.1 'maximum credible earthquake'); R never applied",
        "found": True,
    },
    "site_specific": {
        "stem": IA.PRIMARY_STEM,
        "clause": "6.4.7",
        "cite": "IS 1893 (Part 1):2016 6.4.7 site-specific design acceleration spectrum",
        "found": True,
        "note": "May be used if effects are not less than the 6.4.2 spectrum.",
    },
}


def normalize_zone(zone: str | int | None) -> str:
    if zone is None:
        raise ValueError("seismic zone required (II|III|IV|V)")
    z = str(zone).strip().upper().replace("ZONE", "").replace(" ", "")
    if z in ("2", "II"):
        return "II"
    if z in ("3", "III"):
        return "III"
    if z in ("4", "IV"):
        return "IV"
    if z in ("5", "V"):
        return "V"
    if z in ZONE_FACTOR_Z:
        return z
    raise ValueError("unknown seismic zone %r — IS 1893 zones are II, III, IV, V" % zone)


def zone_factor(zone: str | int | None, Z_override: float | None = None) -> float:
    """Return Z from Table 3, or an explicit override (must be cited in nl_plan)."""
    if Z_override is not None:
        return float(Z_override)
    return ZONE_FACTOR_Z[normalize_zone(zone)]



def normalize_soil(soil: str | None) -> str:
    """IS 1893 6.4.2.1 soil type I | II | III. Raises when missing (no silent 'II') or ASCE letters."""
    if soil is None or str(soil).strip() == "":
        raise ValueError("IS 1893 soil type (I|II|III, 6.4.2.1) is required for the India hazard — "
                         "no default is assumed (NLREPO-14)")
    import re as _re
    raw = str(soil).strip()
    mo = _re.search(r"\btype\s*[-_ ]?\s*(III|II|I|3|2|1)\b", raw, _re.I)
    if mo:
        return {"1": "I", "2": "II", "3": "III"}.get(mo.group(1), mo.group(1).upper())
    key = raw.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
    if key.upper() in ("I", "II", "III"):
        return key.upper()
    if key in SOIL_ALIASES:
        return SOIL_ALIASES[key]
    if key in ("a", "b", "c", "d", "e", "f") or key.startswith("site_class"):
        raise ValueError("ASCE site class %r has no cited IS 1893 soil-type equivalent — the EOR must state "
                         "the IS 6.4.2.1 soil type (I/II/III)" % soil)
    for word, t in (("soft", "III"), ("medium", "II"), ("stiff", "II"), ("rock", "I"), ("hard", "I")):
        if word in key:
            return t
    raise ValueError("unknown soil type %r — use I|II|III (IS 1893 6.4.2.1)" % soil)

def sa_over_g(T: float, soil: str) -> float:
    """Design acceleration coefficient Sa/g (5 % damping), response-spectrum branch of IS 1893 6.4.2 --
    the SHARED steltic_india implementation (snl/vendor_steltic_india/india_seismic.py, WP1.14; RSA branch:
    1 + 15T below 0.1 s, plateau 2.5 to 0.40/0.55/0.67 s, 1.00/1.36/1.67 / T to 4 s, tails 0.25/0.34/0.42)."""
    from snl.vendor_steltic_india import shared
    return float(shared("india_seismic").sa_over_g(max(float(T), 0.0), normalize_soil(soil), "RSA"))



def normalize_level(level: str | None) -> str:
    lv = str(level or "DBE").strip().upper()
    if lv not in LEVEL_FACTOR:
        raise ValueError("NL hazard level %r — use DBE or MCE (IS 1893 elastic, D6)" % level)
    return lv


def elastic_sa(T: float, zone=None, I: float | None = None, soil: str | None = None,
               level: str = "DBE", Z: float | None = None) -> float:
    """IS 1893 elastic spectral acceleration (g) for NL analysis: f·Z·I·Sa/g, f = 0.5 DBE / 1.0 MCE. No R."""
    if I is None:
        raise ValueError("importance factor I (IS 1893 Table 8) is required")
    return LEVEL_FACTOR[normalize_level(level)] * zone_factor(zone, Z) * float(I) * sa_over_g(T, soil)


def elastic_spectrum(periods, zone=None, I: float | None = None, soil: str | None = None,
                     level: str = "DBE", Z: float | None = None) -> dict:
    """Elastic NL target over a period grid (5 % damped RSA shape of 6.4.2). spectrum_meta R is None by construction."""
    lv = normalize_level(level)
    ps = [float(t) for t in periods]
    sa = [elastic_sa(t, zone=zone, I=I, soil=soil, level=lv, Z=Z) for t in ps]
    return dict(periods=ps, sa_g=sa, sa_over_g=[sa_over_g(t, soil) for t in ps], level=lv,
                factor=LEVEL_FACTOR[lv], Z=zone_factor(zone, Z), I=float(I), soil=normalize_soil(soil),
                R=None, label=LEVEL_LABEL[lv], clause="IS 1893 6.4.2 (elastic, 5 %% damping) / 7.7.4",
                cite=CITE["elastic_levels"]["cite"])


def design_Ah(T: float, zone="III", I: float = 1.0, R: float = 5.0,
              soil: str = "II", Z: float | None = None) -> float:
    """Ah(T) = (Z/2)·(Sa/g)/(R/I) per 6.4.2 — linear DESIGN coefficient (reference only, never an NL target)."""
    Zv = zone_factor(zone, Z)
    sag = sa_over_g(T, soil)
    if R is None or float(R) == 0:
        raise ValueError("R (response reduction factor) must be > 0")
    return (Zv / 2.0) * sag / (float(R) / float(I))


def design_spectrum(periods, zone="III", I: float = 1.0, R: float = 5.0,
                    soil: str = "II", Z: float | None = None) -> dict:
    """Ah(T) over a period grid — REFERENCE curve for the linear design (6.4.2); not a scaling target."""
    ps = [float(t) for t in periods]
    return dict(periods=ps, sa_g=[design_Ah(t, zone=zone, I=I, R=R, soil=soil, Z=Z) for t in ps],
                sa_over_g=[sa_over_g(t, soil) for t in ps], zone=str(zone), Z=zone_factor(zone, Z),
                I=float(I), R=float(R), soil=normalize_soil(soil), clause="IS 1893 6.4.2 Ah (design coefficient)",
                role="reference_only", cite=CITE)


def default_period_grid(T_lower: float = 0.05, T_upper: float = 4.0, n: int = 80) -> list[float]:
    import numpy as np
    lo = max(0.01, float(T_lower))
    hi = max(lo * 1.01, float(T_upper))
    return [float(x) for x in np.geomspace(lo, hi, n)]


def _first(*vals):
    for v in vals:
        if v is not None and v != "":
            return v
    return None


def inputs_from_cfg(cfg: dict | None) -> dict:
    """Pull India hazard inputs from cfg / nl_plan / seis block. Missing values stay None (no defaults)."""
    cfg = cfg or {}
    plan = cfg.get("nl_plan") if isinstance(cfg.get("nl_plan"), dict) else {}
    seis = cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}
    hazard = cfg.get("india_hazard") if isinstance(cfg.get("india_hazard"), dict) else {}
    src = {**seis, **hazard, **(plan.get("hazard") or {})}
    zone = _first(src.get("zone"), src.get("seismic_zone"), cfg.get("seismic_zone"), cfg.get("zone"))
    Z = _first(src.get("Z"), src.get("zone_factor"), cfg.get("Z"))
    soil = _first(src.get("soil"), src.get("soil_type"), cfg.get("soil_type"), cfg.get("soil"))
    I = _first(src.get("I"), src.get("importance"), src.get("importance_factor"), cfg.get("importance_factor"), cfg.get("I"))
    R = _first(src.get("R"), src.get("response_reduction"), cfg.get("R"))
    return dict(zone=zone, Z=(float(Z) if Z is not None else None), soil=soil,
                I=(float(I) if I is not None else None), R=(float(R) if R is not None else None), raw=src)


def inputs_from_package(root) -> dict:
    """Structured India inputs from the HR package.

    Sources, first found wins (NL-4): design/calc_package.json (`seismic_calc`: engine W per floor, Z, I, R, zone;
    `seismic_analysis.scale`: V-bar_B per direction = max(engine, agent), the base shear the members were designed
    for), seismic_calc.json (older packages), load_plan.json `seismic_summary` (zone, soil, per-direction R_x / R_y,
    Ta_x / Ta_y, VB_x / VB_y, W_by_floor).

    Returns zone, Z, soil, I, R, R_x, R_y, Ta_x, Ta_y, Ta, W_kN, W_by_floor_kN, VB_kN, VB_x_kN, VB_y_kN, h_m (None
    where absent), `sources`, and `W_check` (engine W vs the agent's seismic_summary W).
    """
    import json as _json
    import os as _os
    root = str(root)
    out = dict(zone=None, Z=None, soil=None, I=None, R=None, R_x=None, R_y=None, Ta_x=None, Ta_y=None, Ta=None,
               W_kN=None, W_by_floor_kN=None, VB_kN=None, VB_x_kN=None, VB_y_kN=None, h_m=None, system=None,
               sources={}, W_check=None)

    def _load(rel):
        pth = _os.path.join(root, rel)
        if not _os.path.exists(pth):
            return {}
        try:
            return _json.load(open(pth, encoding="utf-8")) or {}
        except Exception:
            return {}
    ss = (_load("load_plan.json") or {}).get("seismic_summary") or {}
    sc = _load("seismic_calc.json")
    cp = _load(_os.path.join("design", "calc_package.json"))
    csc = cp.get("seismic_calc") if isinstance(cp.get("seismic_calc"), dict) else {}
    scale = ((cp.get("seismic_analysis") or {}).get("scale") or {}) if isinstance(cp.get("seismic_analysis"), dict) else {}

    def put(key, val, src):
        if val is not None and val != "" and out.get(key) is None:
            out[key] = val
            out["sources"][key] = src
    put("zone", csc.get("zone"), "calc_package.seismic_calc.zone"); put("zone", ss.get("zone"), "load_plan.seismic_summary.zone")
    put("Z", csc.get("Z"), "calc_package.seismic_calc.Z"); put("Z", sc.get("Z"), "seismic_calc.Z")
    put("Z", ss.get("Z"), "load_plan.seismic_summary.Z")
    put("soil", ss.get("soil") or sc.get("soil"), "load_plan.seismic_summary.soil")
    put("I", csc.get("I"), "calc_package.seismic_calc.I"); put("I", sc.get("I"), "seismic_calc.I")
    put("I", ss.get("I"), "load_plan.seismic_summary.I")
    put("R", sc.get("R"), "seismic_calc.R"); put("R", ss.get("R"), "load_plan.seismic_summary.R")
    put("R", csc.get("R"), "calc_package.seismic_calc.R")
    put("R_x", ss.get("R_x"), "load_plan.seismic_summary.R_x"); put("R_y", ss.get("R_y"), "load_plan.seismic_summary.R_y")
    put("Ta_x", sc.get("Ta_x_s") or ss.get("Ta_x_s"), "seismic_summary.Ta_x_s")
    put("Ta_y", sc.get("Ta_y_s") or ss.get("Ta_y_s"), "seismic_summary.Ta_y_s")
    put("Ta", sc.get("Ta_s") or ss.get("Ta_s"), "seismic_summary.Ta_s")
    put("system", csc.get("system") or ss.get("system"), "calc_package.seismic_calc.system")
    wf_engine = csc.get("W_by_floor_engine_kN") if isinstance(csc.get("W_by_floor_engine_kN"), list) else None
    wf_sc = sc.get("W_kN") if isinstance(sc.get("W_kN"), list) else None
    wf_ss = ss.get("W_by_floor_kN") if isinstance(ss.get("W_by_floor_kN"), list) else None
    # mass = W (D6) must be the HR ENGINE's IS 1893 7.3 / 7.4 W -- the one its modal mass uses (it includes nodal
    # masses, crane bridge + crab, envelope cladding, partitions per R1); the agent's table is the fallback
    put("W_by_floor_kN", wf_engine, "calc_package.seismic_calc.W_by_floor_engine_kN (HR engine W)")
    put("W_by_floor_kN", wf_sc, "seismic_calc.W_kN (per floor)")
    put("W_by_floor_kN", wf_ss, "load_plan.seismic_summary.W_by_floor_kN")
    if out["W_by_floor_kN"]:
        put("W_kN", float(sum(out["W_by_floor_kN"])), "sum(%s)" % out["sources"]["W_by_floor_kN"].split(" (")[0])
    if isinstance(ss.get("W_kN"), (int, float)):
        put("W_kN", float(ss["W_kN"]), "load_plan.seismic_summary.W_kN")
    if wf_engine and wf_ss and len(wf_engine) == len(wf_ss):
        We, Wa = float(sum(wf_engine)), float(sum(wf_ss))
        out["W_check"] = dict(W_engine_kN=We, W_agent_kN=Wa, rel_diff=(We - Wa) / Wa if Wa else None,
                              used="engine", note="mass = W uses the HR engine W (calc_package.seismic_calc)")
    # design base shear per direction: V-bar_B from the RSA scaling record (max(engine, agent) per direction)
    for d in ("x", "y"):
        rec = scale.get(d.upper()) or {}
        put("VB_%s_kN" % d, rec.get("VBbar_kN") or rec.get("VB_scaled_kN"), "calc_package.seismic_analysis.scale.%s.VBbar_kN" % d.upper())
        put("VB_%s_kN" % d, ss.get("VB_%s_kN" % d), "load_plan.seismic_summary.VB_%s_kN" % d)
    put("VB_kN", sc.get("VB_kN"), "seismic_calc.VB_kN")
    if out["VB_x_kN"] is not None or out["VB_y_kN"] is not None:
        put("VB_kN", max(v for v in (out["VB_x_kN"], out["VB_y_kN"]) if v is not None), "max(VB_x, VB_y)")
    put("VB_kN", ss.get("VB_kN"), "load_plan.seismic_summary.VB_kN")
    for d in ("x", "y"):
        put("R_%s" % d, out["R"], "R (no per-direction value in the package)")
    put("h_m", ss.get("hi_m"), "load_plan.seismic_summary.hi_m")
    if out["zone"] is None and out["Z"] is not None:
        inv = {v: k for k, v in ZONE_FACTOR_Z.items()}
        out["zone"] = inv.get(round(float(out["Z"]), 2))
        if out["zone"]:
            out["sources"]["zone"] = "Table 3 inverse of Z"
    return out


def vb_direction_kN(ind: dict, direction: str):
    """Design base shear for a push / response direction ('X' | 'Y'): V-bar_B of that direction, else VB."""
    d = str(direction or "").lower()[:1]
    v = (ind or {}).get("VB_%s_kN" % d) if d in ("x", "y") else None
    return v if v is not None else (ind or {}).get("VB_kN")


def build_india_site_hazard(
    zone: str | int | None = None,
    soil: str | None = None,
    I: float | None = None,
    R: float | None = None,
    Z: float | None = None,
    T1x: float | None = None,
    T1y: float | None = None,
    T_lower: float | None = None,
    T_upper: float | None = None,
    periods: list[float] | None = None,
    cfg: dict | None = None,
    site_specific_spectrum: dict | None = None,
    levels=NL_LEVELS,
) -> dict:
    """site_hazard.json for India NL jobs (no USGS).

    Targets (D6): `is1893_elastic_DBE` = (Z/2)·I·Sa/g and `is1893_elastic_MCE` = Z·I·Sa/g — R never enters.
    `is1893_design_Ah_reference` (Ah, R-reduced) is written only as a labelled reference when R is known.
    Explicit arguments win; cfg fills what is None. Soil, I and T1 are REQUIRED (no silent defaults).
    """
    if cfg:
        pulled = inputs_from_cfg(cfg)
        zone = zone if zone is not None else pulled["zone"]
        Z = Z if Z is not None else pulled["Z"]
        soil = soil if soil is not None else pulled["soil"]
        I = I if I is not None else pulled["I"]
        R = R if R is not None else pulled["R"]

    if zone is None and Z is None:
        raise ValueError(
            "India hazard needs seismic zone (II–V) or Z — set cfg['seismic_zone'] / "
            "cfg['india_hazard'] or pass zone=/Z=. USGS path is USA scaffolding only."
        )
    if soil is None:
        raise ValueError("India hazard: IS 1893 soil type missing (6.4.2.1) — read seismic_summary.soil or pass --soil-type")
    if I is None:
        raise ValueError("India hazard: importance factor I missing (IS 1893 Table 8) — read seismic_calc.I or pass --importance")
    if T1x is None and T1y is None:
        raise ValueError("India hazard: building period missing — pass T1 (Ta from seismic_calc.json or the NL modal); "
                         "no 1.0 s default is assumed")

    zone_label = normalize_zone(zone) if zone is not None else "custom_Z"
    Zv = zone_factor(zone, Z)
    soil_n = normalize_soil(soil)
    I = float(I)
    T1x = float(T1x if T1x is not None else T1y)
    T1y = float(T1y if T1y is not None else T1x)
    Tmax, Tmin = max(T1x, T1y), min(T1x, T1y)
    T_lower = T_lower if T_lower is not None else 0.2 * Tmin
    T_upper = T_upper if T_upper is not None else 2.0 * Tmax
    ps = list(periods) if periods else default_period_grid(max(0.02, 0.5 * T_lower), max(1.5 * T_upper, 4.0))

    targets = {}
    floor_notes = []
    for lv in levels:
        lv = normalize_level(lv)
        el = elastic_spectrum(ps, zone=zone, I=I, soil=soil_n, level=lv, Z=Zv)
        sa = el["sa_g"]
        meta = dict(source="IS_1893_6.4.2_elastic", level=lv, factor=LEVEL_FACTOR[lv], Z=Zv, I=I, soil=soil_n, R=None)
        ssp = site_specific_spectrum if (site_specific_spectrum and
                                        normalize_level(site_specific_spectrum.get("level", "DBE")) == lv) else None
        if ssp:
            # 6.4.7: site-specific effects shall not be less than the 6.4.2 spectrum -> floor per period
            import numpy as _np
            s_site = _np.interp(ps, ssp["periods"], ssp["sa_g"])
            ratio = [float(a / b) if b > 0 else float("inf") for a, b in zip(s_site, sa)]
            sa = [float(max(a, b)) for a, b in zip(s_site, sa)]
            meta.update(source="site_specific_floored_6.4.7", min_site_to_code_ratio=min(ratio),
                        floored=bool(min(ratio) < 1.0))
            floor_notes.append("%s: site-specific spectrum floored to 6.4.2 (min ratio %.3f)" % (lv, min(ratio)))
        targets["is1893_elastic_%s" % lv] = dict(
            periods=ps, sa=sa, level=lv, clause=LEVEL_LABEL[lv] + "; 7.7.4 compatibility",
            cite=CITE["elastic_levels"]["cite"], spectrum_meta=meta, role="nl_target",
        )
    if R is not None:
        ah = design_spectrum(ps, zone=zone if zone is not None else "III", I=I, R=float(R), soil=soil_n, Z=Zv)
        targets["is1893_design_Ah_reference"] = dict(
            periods=ps, sa=ah["sa_g"], clause="IS 1893 6.4.2 Ah = (Z/2)(Sa/g)/(R/I) — linear design coefficient",
            cite=CITE["ah_formula"]["cite"], spectrum_meta=dict(source="IS_1893_6.4.2_Ah", R=float(R), I=I),
            role="reference_only_not_an_NL_target",
        )

    return dict(
        schema=2,
        jurisdiction="india",
        india_authoritative=True,
        authority="IS_1893_Part_1_2016",
        edition="IS 1893 (Part 1):2016 + Amd 1 (2017) + Amd 2 (2020)",
        generated=time.strftime("%Y-%m-%dT%H:%M:%S"),
        site=dict(
            seismic_zone=zone_label,
            Z=Zv,
            soil_type=soil_n,
            importance_I=I,
            response_reduction_R=(float(R) if R is not None else None),
            note="IS 1893 zone/soil. R is used only for the Ah reference curve, never for the NL target.",
        ),
        periods_of_building=dict(T1x=T1x, T1y=T1y, T_lower=T_lower, T_upper=T_upper),
        design=dict(
            Z=Zv, zone=zone_label, soil=soil_n, I=I, R_reference_only=(float(R) if R is not None else None),
            levels=[normalize_level(x) for x in levels],
            level_basis=CITE["elastic_levels"]["cite"],
            spectrum_meta=dict(source="IS_1893_6.4.2_elastic", R=None),
            sds=None, sd1=None, sms=None, sm1=None, ss=None, s1=None, tl=None, sdc=None,
        ),
        deagg={},
        targets=targets,
        site_specific_floor=floor_notes or None,
        envelope=None,
        near_fault=dict(near_fault=False, sources=[], found=False,
                        note="No near-fault screen in IS 1893 (found:false)."),
        sigma_model=None,
        sources=[CITE["zone_table"]["cite"], CITE["elastic_levels"]["cite"], CITE["spectrum"]["cite"],
                 CITE["time_history_compat"]["cite"]],
        asce_usgs_scaffolding=dict(
            found=False,
            note=next((g["note"] for g in IA.ASCE_GAPS if g["id"] == "asce_mcer_usgs"),
                      "USGS MCE_R / NSHM is not India authority"),
        ),
        _INDIA_README=[
            "Built from IS 1893 zone/Z/soil/I — not USGS.",
            "NL targets: targets.is1893_elastic_DBE / is1893_elastic_MCE (elastic, no R, owner ruling D6).",
            "targets.is1893_design_Ah_reference is the R-reduced design coefficient — reference only.",
        ],
    )


def target_from_india_hazard(hz: dict, kind: str = "is1893", level: str = "DBE"):
    """(periods, sa, label) of the ELASTIC India NL target at `level` (DBE | MCE). Refuses any R-reduced target."""
    import numpy as np
    kind = (kind or "is1893").lower()
    if kind not in ("is1893", "elastic", "dbe", "mce"):
        raise ValueError("india hazard target kind %r — use is1893 (elastic DBE/MCE)" % kind)
    if kind in ("dbe", "mce"):
        level = kind
    lv = normalize_level(level)
    t = (hz.get("targets") or {}).get("is1893_elastic_%s" % lv) or {}
    if not t.get("periods"):
        raise ValueError("india site_hazard missing targets.is1893_elastic_%s — rebuild with `nlrha hazard` "
                         "(old R-reduced is1893_design targets are refused, D6)" % lv)
    meta = t.get("spectrum_meta") or {}
    if meta.get("R") not in (None, 1, 1.0):
        raise ValueError("NL target carries R=%r — the IS NL target must be elastic (D6)" % meta.get("R"))
    return np.array(t["periods"]), np.array(t["sa"]), LEVEL_LABEL[lv]


def elastic_sa_from_hazard(hz_or_site: dict, T: float, level: str = "DBE") -> float:
    """Sa(T) (g) at `level` from a site_hazard dict (or its `site` block) — used by the NSP (same function)."""
    site = hz_or_site.get("site", hz_or_site)
    return elastic_sa(T, Z=site["Z"], I=site["importance_I"], soil=site["soil_type"], level=level)


def resolve_hazard_path(cfg_or_job=None, prefer_india: bool | None = None) -> str:
    """'india' | 'usgs_scaffolding' | 'india_if_inputs_else_usgs'."""
    if prefer_india is True:
        return "india"
    if prefer_india is False:
        return "usgs_scaffolding"
    cfg = cfg_or_job if isinstance(cfg_or_job, dict) else {}
    try:
        pulled = inputs_from_cfg(cfg)
        if pulled.get("zone") or pulled.get("Z") is not None:
            return "india"
    except Exception:
        pass
    if str(cfg.get("jurisdiction", "")).lower() in ("india", "is", "is_bis", "bis"):
        return "india"
    return "india_if_inputs_else_usgs"
