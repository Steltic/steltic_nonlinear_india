"""India site hazard — IS 1893 Part 1:2016 zone / Z / design spectrum (not USGS).

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

# 6.4.2.1 / Table 4 soil classification aliases → I | II | III
SOIL_ALIASES = {
    "i": "I", "1": "I", "rock": "I", "hard": "I", "rocky": "I", "type_i": "I",
    "ii": "II", "2": "II", "medium": "II", "stiff": "II", "type_ii": "II",
    "iii": "III", "3": "III", "soft": "III", "type_iii": "III",
    # ASCE site-class letters sometimes appear in briefs — map conservatively, cite gap
    "a": "I", "b": "I", "c": "II", "d": "II", "e": "III",
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
    if soil is None:
        return "II"
    key = str(soil).strip().lower().replace(" ", "_").replace("-", "_")
    if key in ("i", "ii", "iii"):
        return key.upper()
    if key.upper() in ("I", "II", "III"):
        return key.upper()
    if key in SOIL_ALIASES:
        return SOIL_ALIASES[key]
    raise ValueError("unknown soil type %r — use I|II|III (IS 1893 6.4.2.1)" % soil)


def sa_over_g(T: float, soil: str = "II") -> float:
    """Design acceleration coefficient Sa/g (5% damping), response-spectrum form of 6.4.2.

    Piecewise expressions transcribed from IS_1893_Part_1_2016.search.md §6.4.2
    (Fig. 2(b) response-spectrum method). Re-verify LIVE before sealing.
    """
    s = normalize_soil(soil)
    T = max(float(T), 0.0)
    if s == "I":  # rocky / hard
        if T < 0.10:
            return 1.0 + 15.0 * T
        if T <= 0.40:
            return 2.5
        if T <= 4.00:
            return 1.0 / T
        return 0.25
    if s == "II":  # medium / stiff
        if T < 0.10:
            return 1.0 + 15.0 * T
        if T <= 0.55:
            return 2.5
        if T <= 4.00:
            return 1.36 / T
        return 0.34
    # III soft
    if T < 0.10:
        return 1.0 + 15.0 * T
    if T <= 0.67:
        return 2.5
    if T <= 4.00:
        return 1.67 / T
    return 0.42


def design_Ah(T: float, zone="III", I: float = 1.0, R: float = 5.0,
              soil: str = "II", Z: float | None = None) -> float:
    """Ah(T) = (Z/2)·(Sa/g)/(R/I) per 6.4.2."""
    Zv = zone_factor(zone, Z)
    sag = sa_over_g(T, soil)
    if R is None or float(R) == 0:
        raise ValueError("R (response reduction factor) must be > 0")
    return (Zv / 2.0) * sag / (float(R) / float(I))


def design_spectrum(periods, zone="III", I: float = 1.0, R: float = 5.0,
                    soil: str = "II", Z: float | None = None) -> dict:
    """Absolute design spectral acceleration Sa = Ah(T) (in g) over a period grid."""
    ps = [float(t) for t in periods]
    ah = [design_Ah(t, zone=zone, I=I, R=R, soil=soil, Z=Z) for t in ps]
    sag = [sa_over_g(t, soil) for t in ps]
    return dict(
        periods=ps,
        sa_g=ah,  # Ah in units of g — scaling target for 7.7.4 compatibility
        sa_over_g=sag,
        zone=normalize_zone(zone) if Z is None else str(zone),
        Z=zone_factor(zone, Z),
        I=float(I),
        R=float(R),
        soil=normalize_soil(soil),
        clause="IS 1893 6.4.2 / 7.7.4",
        cite=CITE,
    )


def default_period_grid(T_lower: float = 0.05, T_upper: float = 4.0, n: int = 80) -> list[float]:
    import numpy as np
    lo = max(0.01, float(T_lower))
    hi = max(lo * 1.01, float(T_upper))
    return [float(x) for x in np.geomspace(lo, hi, n)]


def inputs_from_cfg(cfg: dict | None) -> dict:
    """Pull India hazard inputs from cfg / nl_plan / seis block (steltic_india style)."""
    cfg = cfg or {}
    plan = cfg.get("nl_plan") if isinstance(cfg.get("nl_plan"), dict) else {}
    seis = cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}
    hazard = cfg.get("india_hazard") if isinstance(cfg.get("india_hazard"), dict) else {}
    src = {**seis, **hazard, **(plan.get("hazard") or {})}

    zone = src.get("zone") or src.get("seismic_zone") or cfg.get("seismic_zone") or cfg.get("zone")
    Z = src.get("Z") or src.get("zone_factor")
    soil = src.get("soil") or src.get("soil_type") or src.get("site_class") or cfg.get("soil_type")
    I = src.get("I") or src.get("importance") or cfg.get("importance_factor") or 1.0
    R = src.get("R") or src.get("response_reduction") or cfg.get("R") or 5.0
    return dict(zone=zone, Z=Z, soil=soil, I=float(I), R=float(R), raw=src)


def build_india_site_hazard(
    zone: str | int | None = None,
    soil: str = "II",
    I: float = 1.0,
    R: float = 5.0,
    Z: float | None = None,
    T1x: float | None = None,
    T1y: float | None = None,
    T_lower: float | None = None,
    T_upper: float | None = None,
    periods: list[float] | None = None,
    cfg: dict | None = None,
    site_specific_spectrum: dict | None = None,
) -> dict:
    """Write-shaped site_hazard.json for India jobs (no USGS).

    Target for record scaling: design Sa = Ah(T) in g (7.7.4 compatibility with 6.4.2).
    Conditional spectrum / MCE_R / near-fault USGS screens are omitted (found:false as India authority).
    """
    if cfg:
        pulled = inputs_from_cfg(cfg)
        zone = zone or pulled["zone"]
        if Z is None:
            Z = pulled["Z"]
        soil = soil or pulled["soil"] or "II"
        I = I if I is not None else pulled["I"]
        R = R if R is not None else pulled["R"]

    if zone is None and Z is None:
        raise ValueError(
            "India hazard needs seismic zone (II–V) or Z — set cfg['seismic_zone'] / "
            "cfg['india_hazard'] or pass zone=/Z=. USGS path is USA scaffolding only."
        )

    zone_label = normalize_zone(zone) if zone is not None else "custom_Z"
    Zv = zone_factor(zone, Z)
    soil_n = normalize_soil(soil)

    if T1x is None and T1y is None:
        T1x = T1y = 1.0
    elif T1x is None:
        T1x = T1y
    elif T1y is None:
        T1y = T1x
    Tmax, Tmin = max(T1x, T1y), min(T1x, T1y)
    T_lower = T_lower if T_lower is not None else 0.2 * Tmin
    T_upper = T_upper if T_upper is not None else max(2.0 * Tmax, 4.0)

    if site_specific_spectrum:
        # 6.4.7 path — caller supplies periods/sa already floored vs 6.4.2
        ps = list(site_specific_spectrum["periods"])
        sa = list(site_specific_spectrum["sa_g"])
        spec_meta = dict(source="site_specific", clause="6.4.7", note=CITE["site_specific"]["note"])
    else:
        ps = list(periods) if periods else default_period_grid(max(0.05, 0.5 * T_lower), max(T_upper, 4.0))
        spec = design_spectrum(ps, zone=zone or "III", I=I, R=R, soil=soil_n, Z=Zv)
        sa = spec["sa_g"]
        spec_meta = dict(source="IS_1893_6.4.2", soil=soil_n, Z=Zv, I=I, R=R)

    return dict(
        schema=1,
        jurisdiction="india",
        india_authoritative=True,
        authority="IS_1893_Part_1_2016",
        generated=time.strftime("%Y-%m-%dT%H:%M:%S"),
        site=dict(
            seismic_zone=zone_label,
            Z=Zv,
            soil_type=soil_n,
            importance_I=float(I),
            response_reduction_R=float(R),
            note="IS 1893 zone/soil — not ASCE site class / Risk Category",
        ),
        periods_of_building=dict(T1x=T1x, T1y=T1y, T_lower=T_lower, T_upper=T_upper),
        design=dict(
            Z=Zv,
            zone=zone_label,
            soil=soil_n,
            I=float(I),
            R=float(R),
            spectrum_meta=spec_meta,
            # placeholders so USA report printers do not crash if pointed here
            sds=None, sd1=None, sms=None, sm1=None, ss=None, s1=None, tl=None, sdc=None,
        ),
        deagg={},
        targets=dict(
            is1893_design=dict(
                periods=ps,
                sa=sa,
                clause="IS 1893 6.4.2 Ah(T) [g]; time-history compatibility per 7.7.4",
                cite=CITE["ah_formula"]["cite"],
            ),
            # Keep key name absent for mcer — target_from_hazard india path uses is1893
        ),
        envelope=None,
        near_fault=dict(
            near_fault=False,
            sources=[],
            note="USGS near-fault screen not applicable; India path has no analogue in corpus (found:false).",
            found=False,
        ),
        sigma_model=None,
        sources=[
            CITE["zone_table"]["cite"],
            CITE["ah_formula"]["cite"],
            CITE["spectrum"]["cite"],
            CITE["time_history_compat"]["cite"],
        ],
        asce_usgs_scaffolding=dict(
            found=False,
            note=next(
                (g["note"] for g in IA.ASCE_GAPS if g["id"] == "asce_mcer_usgs"),
                "USGS MCE_R / NSHM is not India authority",
            ),
        ),
        _INDIA_README=[
            "This site_hazard.json was built from IS 1893 zone/Z/soil — not USGS.",
            "Scale records for compatibility with targets.is1893_design (Ah in g) per 7.7.4.",
            "Do NOT treat ASCE Ch.16 suite acceptance numerics as India law.",
        ],
    )


def target_from_india_hazard(hz: dict, kind: str = "is1893"):
    """Return (periods, sa, label) for India design spectrum."""
    import numpy as np
    kind = (kind or "is1893").lower()
    if kind in ("is1893", "design", "code", "ah"):
        t = (hz.get("targets") or {}).get("is1893_design") or {}
        if not t.get("periods"):
            raise ValueError("india site_hazard missing targets.is1893_design")
        label = "IS 1893 design Ah(T) [%s]" % (t.get("clause") or "6.4.2 / 7.7.4")
        return np.array(t["periods"]), np.array(t["sa"]), label
    raise ValueError("india hazard target kind %r — use is1893|design|code|ah" % kind)


def resolve_hazard_path(cfg_or_job=None, prefer_india: bool | None = None) -> str:
    """'india' | 'usgs_scaffolding' — default india on this fork when zone/inputs present or prefer_india."""
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
    # Fork default: India authority docs say stop assuming USGS — but keep USGS callable
    # when lat/lon explicitly supplied without India inputs (regression / dual path).
    return "india_if_inputs_else_usgs"
