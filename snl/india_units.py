"""India SI boundary helpers for steltic_nonlinear_india (NL fork).

HR/CFS India are SI-native N-mm-sec. NL Stages A–B (this wave):
  - Stage A: report/viewer labels via display_scale (SI display from kip-in engine OK)
  - Stage B: N-mm HR packages convert once at ingest (_nl_unit_bridge) → analysis stays kip-in
OpenSees/pushover/NLRHA/DDM analysis remains kip-in until Stages C–D.

Legacy kip+inch converters remain for USA archetypes. Opt in with cfg['units']='kip-in' or
cfg['force_kip_in']=True. Prefer cfg['units']='N-mm' for SI display / SI package handoff.

load_plan RAG provenance strings stay in whatever units the standard cites (usually SI);
do not rewrite RAG text at the conversion boundary.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Active unit system (module default = SI for India repos)
# ---------------------------------------------------------------------------
UNIT_SYSTEM = "kip-in"  # NL default; HR/CFS use N-mm
# OpenSees analysis unit system until Stage D flip (display may still be SI via display_scale)
ANALYSIS_UNITS = "kip-in"  # "kip-in" | "N-mm"

ENGINE_UNITS = {
    "force": "N",
    "length": "mm",
    "moment": "N-mm",  # reports often show kN·m (= N-mm / 1e6)
    "stress": "MPa",  # = N/mm²
    "pressure_area": "kN/m² (gravity / cladding briefs)",
    "mass": "tonne (= N·s²/mm)",
    "time": "s",
    "g_mm_s2": 9810.0,
    "E_steel_MPa": 200000.0,
    "G_steel_MPa": 76923.07692307692,  # E/2.6
    "note": (
        "NL wave: boundary helpers only. HR/CFS engines are N-mm-sec; NL OpenSees remains "
        "kip-in until NL SI rewrite. apply_si_geometry normalizes briefs to mm for stubs; "
        "call activate_kip_in() before pushover/NLRHA until NL engine flips."
    ),
}

LEGACY_KIP_IN_UNITS = {
    "force": "kip",
    "length": "in",
    "moment": "kip-in",
    "stress": "ksi",
    "pressure_area": "psf",
    "g_in_s2": 386.4,
    "E_steel_ksi": 29000.0,
    "G_steel_ksi": 11200.0,
}

# Remaining kip islands after wave 1 (honest inventory — not yet SI-native)
KIP_ISLANDS = [
    "NL OpenSees / pushover / NLRHA / DDM analysis still kip-in (Stages A–B done; C–D pending — docs/SI_NL_MIGRATION_PLAN.md)",
    "hinge params / ASCE 41 scaffolding in ksi",
    "fibre sections E=29000 ksi / areas in² (Stage C twin pending)",
    "steltic_ddm portal_adapter _seis_V_kip / wind H kip / beamUniform kip/in",
    "record scaling & hazard USGS path imperial-tolerant; India zone path exists",
    "Many NL report HTML strings still hardcode kip (viewer unit_labels Stage A; full report sweep Stage C/D)",
]

# Exact conversion factors
MM_PER_IN = 25.4
IN_PER_M = 39.37007874015748
M_TO_IN = IN_PER_M  # legacy alias
M_TO_MM = 1000.0
MM_TO_IN = 1.0 / MM_PER_IN
KN_TO_KIP = 1.0 / 4.4482216152605
KIP_TO_N = 4448.2216152605
KN_TO_N = 1000.0
MPA_TO_KSI = 1.0 / 6.894757293168361
KSI_TO_MPA = 6.894757293168361
KNM_TO_KIPIN = KN_TO_KIP * M_TO_IN
KNM_TO_KIPFT = KN_TO_KIP * (M_TO_IN / 12.0)
KN_PER_M2_TO_PSF = (1.0 / 4.4482216152605) / ((39.37007874015748 / 12.0) ** 2) * 1000.0  # ≈20.8854
PSF_TO_KN_PER_M2 = 1.0 / KN_PER_M2_TO_PSF


def activate_si() -> None:
    """Mark module SI; NL OpenSees engine not flipped this wave (no engine3d)."""
    global UNIT_SYSTEM
    UNIT_SYSTEM = "N-mm"


def activate_kip_in() -> None:
    """NL analysis path remains kip-in until NL SI rewrite."""
    global UNIT_SYSTEM
    UNIT_SYSTEM = "kip-in"


def active_unit_system() -> str:
    return UNIT_SYSTEM


def is_si(cfg: dict | None = None) -> bool:
    """True when cfg (or module default) is SI-native N-mm."""
    if cfg is not None:
        if cfg.get("force_kip_in"):
            return False
        u = str(cfg.get("units") or "").lower().strip()
        if u in ("kip-in", "kip+inch", "kip_in", "imperial", "usa", "in"):
            return False
        if u in ("n-mm", "n-mm-s", "n-mm-sec", "si", "metric", "mm", "m",
                 "india_metric", "india_si"):
            return True
        if cfg.get("metric") or cfg.get("si_native"):
            return True
        # Ambiguous / unset units: infer from geometry magnitude
        probe = cfg.get("heights") or cfg.get("story_heights") or cfg.get("SX")
        h0 = None
        if isinstance(probe, (list, tuple)) and probe:
            h0 = probe[0]
        elif isinstance(probe, (int, float)):
            h0 = probe
        if h0 is not None:
            # mm storeys are thousands; inch storeys are ~100–200; metre briefs <30
            if float(h0) >= 500:
                return True   # already mm
            if float(h0) < 30:
                return True   # metres (will be converted)
            return False      # looks like inches
        return UNIT_SYSTEM == "N-mm"
    return UNIT_SYSTEM == "N-mm"


def wants_legacy_kip_in(cfg: dict) -> bool:
    if cfg.get("force_kip_in"):
        return True
    u = str(cfg.get("units") or "").lower().strip()
    return u in ("kip-in", "kip+inch", "kip_in", "imperial", "usa", "in")


# ---------------------------------------------------------------------------
# Scalar converters (both directions)
# ---------------------------------------------------------------------------
def length_to_mm(value, unit: str = "m") -> float:
    u = (unit or "m").lower().strip()
    if u in ("mm",):
        return float(value)
    if u in ("cm",):
        return float(value) * 10.0
    if u in ("m", "metre", "meter", "metres", "meters"):
        return float(value) * M_TO_MM
    if u in ("in", "inch", "inches"):
        return float(value) * MM_PER_IN
    if u in ("ft", "feet"):
        return float(value) * 12.0 * MM_PER_IN
    raise ValueError(f"unsupported length unit {unit!r}")


def metric_length_to_in(value, unit: str = "m") -> float:
    """Legacy: metric → inches (kip-in path)."""
    u = (unit or "m").lower().strip()
    if u in ("in", "inch", "inches"):
        return float(value)
    if u == "mm":
        return float(value) * MM_TO_IN
    if u == "cm":
        return float(value) * MM_TO_IN * 10.0
    if u == "m":
        return float(value) * M_TO_IN
    if u in ("ft", "feet"):
        return float(value) * 12.0
    raise ValueError(f"unsupported length unit {unit!r}")


def metric_force_to_kip(value, unit: str = "kN") -> float:
    u = (unit or "kN").lower().strip()
    if u == "kip":
        return float(value)
    if u in ("kn", "kilonewton"):
        return float(value) * KN_TO_KIP
    if u in ("n", "newton"):
        return float(value) * KN_TO_KIP / 1000.0
    if u == "kgf":
        return float(value) * 9.80665 * KN_TO_KIP / 1000.0
    raise ValueError(f"unsupported force unit {unit!r}")


def force_to_N(value, unit: str = "kN") -> float:
    u = (unit or "kN").lower().strip()
    if u in ("n", "newton"):
        return float(value)
    if u in ("kn", "kilonewton"):
        return float(value) * KN_TO_N
    if u == "kip":
        return float(value) * KIP_TO_N
    raise ValueError(f"unsupported force unit {unit!r}")


def metric_pressure_to_psf(value, unit: str = "kN/m2") -> float:
    u = (unit or "kN/m2").lower().replace("²", "2").replace(" ", "")
    if u in ("psf",):
        return float(value)
    if u in ("ksi",):
        return float(value) * 144000.0
    if u in ("mpa",):
        return float(value) * MPA_TO_KSI * 144000.0
    if u in ("kn/m2", "kn/m^2", "kpa"):
        return float(value) * KN_PER_M2_TO_PSF
    raise ValueError(f"unsupported pressure unit {unit!r}")


def metric_stress_to_ksi(value, unit: str = "MPa") -> float:
    u = (unit or "MPa").lower().strip()
    if u == "ksi":
        return float(value)
    if u == "mpa":
        return float(value) * MPA_TO_KSI
    if u == "pa":
        return float(value) * MPA_TO_KSI / 1e6
    raise ValueError(f"unsupported stress unit {unit!r}")


def kn_per_m_to_plf(value) -> float:
    """kN/m → kip/ft (legacy)."""
    return float(value) * KN_TO_KIP / (M_TO_IN / 12.0)


def mpa_to_ksi(value) -> float:
    return metric_stress_to_ksi(value, "MPa")


# ---------------------------------------------------------------------------
# Geometry / pressure application
# ---------------------------------------------------------------------------
_LENGTH_KEYS = (
    "story_heights", "storey_heights", "heights", "bay_x", "bay_y",
    "bay_spacing_x", "bay_spacing_y", "height", "width", "depth",
    "eave_height", "ridge_height",
)


def _alias_engine_keys(cfg: dict) -> None:
    if not cfg.get("heights"):
        for src in ("story_heights", "storey_heights"):
            if cfg.get(src) is not None:
                v = cfg[src]
                cfg["heights"] = list(v) if isinstance(v, (list, tuple)) else v
                break
    if cfg.get("SX") is None:
        for src in ("bay_x", "bay_spacing_x"):
            if cfg.get(src) is not None:
                cfg["SX"] = cfg[src]
                break
    if cfg.get("SY") is None:
        for src in ("bay_y", "bay_spacing_y"):
            if cfg.get(src) is not None:
                cfg["SY"] = cfg[src]
                break


def apply_si_geometry(cfg: dict) -> dict:
    """Normalize metric brief geometry to **mm**; set units='N-mm'; activate SI engine.

    Recognises cfg['units'] in {metric, SI, m, mm, india_metric, india_si, N-mm, …}
    or cfg['metric']=True / cfg['si_native']=True.

    Leaves load_plan RAG strings untouched. Idempotent via cfg['_units_converted'].
    """
    if wants_legacy_kip_in(cfg):
        return apply_metric_geometry_legacy_kip_in(cfg)

    units = str(cfg.get("units") or "").lower()
    metric = bool(cfg.get("metric") or cfg.get("si_native")) or units in (
        "metric", "si", "m", "mm", "india_metric", "india_si", "n-mm", "n-mm-s",
        "n-mm-sec",
    )
    # India jurisdiction with UNSET units: only treat as SI if geometry looks like metres
    # (storey height < 30). Inch archetypes (heights~156, SX~360) must not be ×1000'd.
    if not metric and str(cfg.get("jurisdiction") or "").lower() in ("india", "in", "bis"):
        probe = cfg.get("heights") or cfg.get("story_heights") or cfg.get("storey_heights")
        h0 = None
        if isinstance(probe, (list, tuple)) and probe:
            h0 = probe[0]
        elif isinstance(probe, (int, float)):
            h0 = probe
        if h0 is not None and float(h0) < 30.0:
            metric = True
        elif units in ("n-mm", "si", "metric"):
            metric = True
    if not metric:
        return cfg
    if cfg.get("_units_converted") and str(cfg.get("units")) == "N-mm":
        activate_si()
        return cfg

    length_unit = "mm" if units == "mm" else "m"
    # If already N-mm with heights in mm-ish (>100), skip re-scale
    if units in ("n-mm", "n-mm-s", "n-mm-sec") and cfg.get("heights"):
        h0 = cfg["heights"][0] if isinstance(cfg["heights"], (list, tuple)) else cfg["heights"]
        if isinstance(h0, (int, float)) and h0 > 100:
            _alias_engine_keys(cfg)
            cfg["_units_converted"] = {
                "from": "mm", "to": "mm", "engine": ENGINE_UNITS,
                "note": "already N-mm",
            }
            cfg["units"] = "N-mm"
            activate_si()
            return cfg

    def conv_list(key):
        if key not in cfg or cfg[key] is None:
            return
        val = cfg[key]
        if isinstance(val, (list, tuple)):
            cfg[key] = [length_to_mm(v, length_unit) for v in val]
        else:
            cfg[key] = length_to_mm(val, length_unit)

    for k in _LENGTH_KEYS:
        conv_list(k)

    geom = cfg.get("geometry")
    if isinstance(geom, dict) and not geom.get("_units_converted"):
        for k in list(geom.keys()):
            if isinstance(geom[k], (int, float)):
                try:
                    geom[k] = length_to_mm(geom[k], length_unit)
                except Exception:
                    pass
            elif isinstance(geom[k], (list, tuple)) and geom[k] and isinstance(geom[k][0], (int, float)):
                geom[k] = [length_to_mm(v, length_unit) for v in geom[k]]
        geom["_units_converted"] = True

    _alias_engine_keys(cfg)

    cfg["_units_converted"] = {
        "from": length_unit,
        "to": "mm",
        "engine": ENGINE_UNITS,
        "factors": {
            "m_to_mm": M_TO_MM,
            "mm_per_in": MM_PER_IN,
            "kN_to_N": KN_TO_N,
            "MPa_to_ksi_legacy": MPA_TO_KSI,
        },
    }
    cfg["units"] = "N-mm"
    cfg["si_native"] = True
    activate_si()
    return cfg


def apply_metric_geometry_legacy_kip_in(cfg: dict) -> dict:
    """Legacy metric → inches for explicit kip-in jobs (wave 1 opt-in)."""
    units = str(cfg.get("units") or "").lower()
    # If caller set kip-in but geometry still in metres, convert m→in
    length_unit = "mm" if units == "mm" else "m"
    # Detect: if heights look like metres (< 30), treat as m
    if cfg.get("_units_converted") and cfg["_units_converted"].get("to") == "in":
        activate_kip_in()
        return cfg

    # For force_kip_in with metric geometry keys still present
    metric_geom = bool(cfg.get("metric")) or any(
        k in cfg for k in ("story_heights", "storey_heights", "bay_x", "bay_y")
    )
    if not metric_geom and units in ("kip-in", "kip+inch", "imperial"):
        activate_kip_in()
        cfg["units"] = "kip-in"
        return cfg

    if units in ("kip-in", "kip+inch", "imperial", "usa"):
        # heights may already be inches
        h = cfg.get("heights") or cfg.get("story_heights")
        if h is not None:
            h0 = h[0] if isinstance(h, (list, tuple)) else h
            if isinstance(h0, (int, float)) and h0 > 50:
                _alias_engine_keys(cfg)
                cfg["units"] = "kip-in"
                activate_kip_in()
                return cfg

    def conv_list(key):
        if key not in cfg or cfg[key] is None:
            return
        val = cfg[key]
        if isinstance(val, (list, tuple)):
            cfg[key] = [metric_length_to_in(v, length_unit) for v in val]
        else:
            cfg[key] = metric_length_to_in(val, length_unit)

    for k in _LENGTH_KEYS:
        conv_list(k)

    geom = cfg.get("geometry")
    if isinstance(geom, dict) and not geom.get("_units_converted"):
        for k in list(geom.keys()):
            if isinstance(geom[k], (int, float)):
                try:
                    geom[k] = metric_length_to_in(geom[k], length_unit)
                except Exception:
                    pass
            elif isinstance(geom[k], (list, tuple)) and geom[k] and isinstance(geom[k][0], (int, float)):
                geom[k] = [metric_length_to_in(v, length_unit) for v in geom[k]]
        geom["_units_converted"] = True

    _alias_engine_keys(cfg)
    cfg["_units_converted"] = {
        "from": length_unit,
        "to": "in",
        "engine": LEGACY_KIP_IN_UNITS,
        "factors": {"m_to_in": M_TO_IN, "kN_to_kip": KN_TO_KIP, "MPa_to_ksi": MPA_TO_KSI},
        "legacy": True,
    }
    cfg["units"] = "kip-in"
    activate_kip_in()
    return cfg


def apply_metric_geometry(cfg: dict) -> dict:
    """NL boundary: metric briefs → kip-in (NL OpenSees still kip-in this wave).

    For mm package stubs shared with HR/CFS, call apply_si_geometry() or set
    cfg['si_native']=True / units='N-mm'.
    """
    if cfg.get("si_native") or str(cfg.get("units") or "").lower() in (
        "n-mm", "n-mm-s", "n-mm-sec", "india_si",
    ):
        return apply_si_geometry(cfg)
    return apply_metric_geometry_legacy_kip_in(cfg)


def apply_metric_pressures(cfg: dict) -> dict:
    """Pressures: SI path keeps kN/m²; legacy converts kN/m² → psf."""
    if wants_legacy_kip_in(cfg) or not is_si(cfg):
        units = str(cfg.get("units") or "").lower()
        metric = bool(cfg.get("metric")) or units in ("metric", "si", "m", "mm", "india_metric")
        if not metric or cfg.get("_pressures_converted"):
            return cfg
        for k in ("D_floor", "D_roof", "L_floor", "Lr", "S", "clad", "q_wind", "pz", "pd"):
            if k in cfg and cfg[k] is not None and isinstance(cfg[k], (int, float)):
                cfg[k] = metric_pressure_to_psf(cfg[k], "kN/m2")
        cfg["_pressures_converted"] = {"to": "psf", "legacy": True}
        return cfg

    # SI: pressures stay kN/m² — just mark provenance
    if cfg.get("_pressures_converted"):
        return cfg
    cfg["_pressures_converted"] = {"to": "kN/m2", "engine": "N-mm"}
    return cfg


def apply_si_pressures(cfg: dict) -> dict:
    """Alias — SI keeps kN/m²."""
    return apply_metric_pressures(cfg)


def report_unit_labels(cfg: dict | None = None) -> dict:
    """Labels for reports / smoke banners."""
    if is_si(cfg):
        return {
            "force": "N",
            "force_display": "kN",
            "length": "mm",
            "length_display": "m",
            "moment": "N-mm",
            "moment_display": "kN·m",
            "stress": "MPa",
            "pressure": "kN/m²",
            "system": "N-mm-sec",
        }
    return {
        "force": "kip",
        "force_display": "kip",
        "length": "in",
        "length_display": "ft",
        "moment": "kip-in",
        "moment_display": "kip-ft",
        "stress": "ksi",
        "pressure": "psf",
        "system": "kip-in",
    }


def conversion_cheatsheet() -> str:
    return (
        "India SI-native (wave 1): geometry in mm, force N, stress MPa, OpenSees N-mm-sec "
        "(E=2e5 MPa, g=9810 mm/s², mass in tonne). "
        "Briefs in m → apply_si_geometry (×1000). Pressures stay kN/m². "
        "Legacy kip-in: units='kip-in' / force_kip_in=True. "
        f"KIP_ISLANDS ({len(KIP_ISLANDS)}): " + "; ".join(KIP_ISLANDS[:3]) + "…"
    )



# ---------------------------------------------------------------------------
# Stage A — dual display (engine may still be kip-in)
# ---------------------------------------------------------------------------
def analysis_unit_system(cfg: dict | None = None) -> str:
    """OpenSees/pushover/NLRHA analysis units (kip-in until Stage D)."""
    if cfg is not None and cfg.get("_nl_analysis_units"):
        return str(cfg["_nl_analysis_units"])
    return ANALYSIS_UNITS


def display_scale(cfg: dict | None = None) -> dict:
    """Factors + labels to present *analysis-engine* quantities in engineer-facing units.

    NL Stages A–B: analysis remains kip-in. When SI display is requested
    (`units='N-mm'` / `si_native` / `is_si`), convert kip→kN, in→m, kip-in→kN·m.
    After Stage D (ANALYSIS_UNITS='N-mm'), matches HR (÷1000 / ÷1e6).
    Legacy kip-in display: identity /12 for kip-ft.
    """
    analysis = analysis_unit_system(cfg)
    want_si = is_si(cfg) if cfg is not None else (UNIT_SYSTEM == "N-mm")

    if want_si and analysis == "N-mm":
        return {
            "si": True,
            "force_div": 1000.0,          # N → kN
            "force_lbl": "kN",
            "force_raw_lbl": "N",
            "moment_div": 1.0e6,          # N·mm → kN·m
            "moment_lbl": "kN·m",
            "moment_raw_lbl": "N·mm",
            "length_div": 1000.0,         # mm → m
            "length_lbl": "m",
            "length_member_lbl": "mm",
            "length_member_div": 1.0,
            "stress_lbl": "MPa",
            "pressure_lbl": "kN/m²",
            "system": "N-mm-sec",
            "E_default": 200000.0,
            "Fy_default": 250.0,
            "analysis": "N-mm",
        }
    if want_si and analysis == "kip-in":
        # Stage A–B: kip-in engine numbers → SI display labels
        return {
            "si": True,
            "force_div": KN_TO_KIP,       # kip / KN_TO_KIP = kN
            "force_lbl": "kN",
            "force_raw_lbl": "kip",
            "moment_div": KNM_TO_KIPIN,   # kip-in / KNM_TO_KIPIN = kN·m
            "moment_lbl": "kN·m",
            "moment_raw_lbl": "kip-in",
            "length_div": M_TO_IN,        # in / M_TO_IN = m
            "length_lbl": "m",
            "length_member_lbl": "mm",
            "length_member_div": MM_TO_IN,  # in → mm (÷ MM_TO_IN == ×25.4)
            "stress_lbl": "MPa",
            "pressure_lbl": "kN/m²",
            "system": "N-mm-sec (display; analysis kip-in)",
            "E_default": 200000.0,
            "Fy_default": 250.0,
            "analysis": "kip-in",
            "bridged_display": True,
        }
    return {
        "si": False,
        "force_div": 1.0,
        "force_lbl": "kip",
        "force_raw_lbl": "kip",
        "moment_div": 12.0,               # kip-in → kip-ft
        "moment_lbl": "kip-ft",
        "moment_raw_lbl": "kip-in",
        "length_div": 12.0,               # in → ft
        "length_lbl": "ft",
        "length_member_lbl": "in",
        "length_member_div": 1.0,
        "stress_lbl": "ksi",
        "pressure_lbl": "psf",
        "system": "kip-in",
        "E_default": 29000.0,
        "Fy_default": 50.0,
        "analysis": analysis,
    }


def fmt_force(v, cfg: dict | None = None, digits: int = 1) -> str:
    if v is None:
        return "—"
    sc = display_scale(cfg)
    return f"{float(v) / sc['force_div']:.{digits}f} {sc['force_lbl']}"


def fmt_moment(v, cfg: dict | None = None, digits: int = 1) -> str:
    """Engine moment (kip-in Stages A–B, or N·mm after Stage D) → display string."""
    if v is None:
        return "—"
    sc = display_scale(cfg)
    return f"{float(v) / sc['moment_div']:.{digits}f} {sc['moment_lbl']}"


def fmt_length(v, cfg: dict | None = None, digits: int = 2, member: bool = False) -> str:
    if v is None:
        return "—"
    sc = display_scale(cfg)
    if member:
        return f"{float(v) / sc['length_member_div']:.{digits}f} {sc['length_member_lbl']}"
    return f"{float(v) / sc['length_div']:.{digits}f} {sc['length_lbl']}"


def demand_field_names(cfg: dict | None = None) -> dict:
    """CSV / calc_package field names for the *package* unit system (HR export)."""
    if is_si(cfg):
        return {
            "length": "length_mm",
            "P_comp": "P_comp_N",
            "P_tens": "P_tens_N",
            "Mz": "Mz_Nmm",
            "My": "My_Nmm",
            "V": "V_N",
            "Mx_display": "Mx_kNm",
            "My_display": "My_kNm",
            "M_conn": "M_kNm",
            "P_conn": "P_N",
            "V_conn": "V_N",
            "axial": "axial_N",
            "Fpx": "Fpx_N_by_level",
            "Fpx_max": "Fpx_max_N",
            "P_basis": "P_basis_N",
            "conn_col": "demand_N_or_kNm",
            "Lb": "Lb_mm",
        }
    return {
        "length": "length_in",
        "P_comp": "P_comp_kip",
        "P_tens": "P_tens_kip",
        "Mz": "Mz_kipin",
        "My": "My_kipin",
        "V": "V_kip",
        "Mx_display": "Mx_kipft",
        "My_display": "My_kipft",
        "M_conn": "M_kipft",
        "P_conn": "P_kip",
        "V_conn": "V_kip",
        "axial": "axial_kip",
        "Fpx": "Fpx_kip_by_level",
        "Fpx_max": "Fpx_max_kip",
        "P_basis": "P_basis_kip",
        "conn_col": "demand_kip_or_kipft",
        "Lb": "Lb_in",
    }


# ---------------------------------------------------------------------------
# Stage B — package boundary: N-mm HR package → kip-in analysis once
# ---------------------------------------------------------------------------
def detect_package_si_signals(
    schedule_fieldnames: list | None = None,
    sample_E: float | None = None,
    max_node_coord: float | None = None,
    cfg_units: str | None = None,
) -> dict:
    """Heuristic signals that an HR package is N-mm (not kip-in)."""
    names = {str(n).strip() for n in (schedule_fieldnames or [])}
    si_cols = bool(names & {"length_mm", "P_comp_N", "P_tens_N", "Mx_kNm", "My_kNm", "V_N", "Mz_Nmm"})
    kip_cols = bool(names & {"length_in", "P_comp_kip", "Mx_kipft", "V_kip"})
    e_si = sample_E is not None and 1.0e5 < float(sample_E) < 3.0e5
    e_kip = sample_E is not None and 2.0e4 < float(sample_E) < 3.5e4
    # mm plan: multi-metre bays → coords often > 5000; inch plans rarely exceed ~3000 for mid-rise
    coord_si = max_node_coord is not None and float(max_node_coord) >= 5000.0
    u = (cfg_units or "").lower().strip()
    cfg_si = u in ("n-mm", "n-mm-s", "n-mm-sec", "si", "metric", "mm", "india_si", "india_metric")
    return {
        "si_schedule_cols": si_cols,
        "kip_schedule_cols": kip_cols,
        "E_looks_MPa": e_si,
        "E_looks_ksi": e_kip,
        "coords_look_mm": coord_si,
        "cfg_units_si": cfg_si,
        "likely_si": bool(si_cols or (e_si and not e_kip) or (coord_si and cfg_si) or (cfg_si and not kip_cols and e_si)),
    }


def schedule_row_to_kip_in(row: dict) -> dict:
    """Normalize one member_schedule row to kip-in field names used by NL analysis."""
    out = {
        "member": (row.get("member") or "").strip(),
        "section": (row.get("section") or "").strip(),
        "governing_combo": row.get("governing_combo", "") or "",
    }
    # length
    if row.get("length_in") not in (None, ""):
        out["length_in"] = float(row["length_in"])
    elif row.get("length_mm") not in (None, ""):
        out["length_in"] = float(row["length_mm"]) * MM_TO_IN
    else:
        out["length_in"] = 0.0
    # axial
    if row.get("P_comp_kip") not in (None, ""):
        out["P_comp_kip"] = float(row["P_comp_kip"])
    elif row.get("P_comp_N") not in (None, ""):
        out["P_comp_kip"] = float(row["P_comp_N"]) / KIP_TO_N
    elif row.get("P_comp_kN") not in (None, ""):
        out["P_comp_kip"] = float(row["P_comp_kN"]) * KN_TO_KIP
    else:
        out["P_comp_kip"] = 0.0
    # moment display (kip-ft in schedule)
    if row.get("Mx_kipft") not in (None, ""):
        out["Mx_kipft"] = float(row["Mx_kipft"])
    elif row.get("Mx_kNm") not in (None, ""):
        out["Mx_kipft"] = float(row["Mx_kNm"]) * KNM_TO_KIPFT
    elif row.get("Mz_Nmm") not in (None, ""):
        out["Mx_kipft"] = (float(row["Mz_Nmm"]) / 1.0e6) * KNM_TO_KIPFT
    else:
        out["Mx_kipft"] = 0.0
    return out


def convert_elastic_section_mm_to_in(A, E, G, J, Iy, Iz) -> tuple:
    """Convert elasticBeamColumn section props from N-mm (MPa, mm^n) → kip-in (ksi, in^n)."""
    mm2 = MM_PER_IN ** 2
    mm4 = MM_PER_IN ** 4
    return (
        float(A) / mm2,
        float(E) * MPA_TO_KSI,
        float(G) * MPA_TO_KSI,
        float(J) / mm4,
        float(Iy) / mm4,
        float(Iz) / mm4,
    )


def mass_tonne_to_kip_sec2_in(m: float) -> float:
    """OpenSees mass: tonne (N·s²/mm) → kip·s²/in."""
    return float(m) * MM_PER_IN / KIP_TO_N


def build_nl_unit_bridge(source: str = "N-mm", detail: dict | None = None) -> dict:
    """Provenance block stored on calc['_nl_unit_bridge'] / cfg['_nl_unit_bridge']."""
    return {
        "from": source,
        "to": "kip-in",
        "analysis": "kip-in",
        "stage": "B",
        "factors": {
            "mm_per_in": MM_PER_IN,
            "kip_to_N": KIP_TO_N,
            "MPa_to_ksi": MPA_TO_KSI,
            "kNm_to_kipft": KNM_TO_KIPFT,
        },
        "detail": detail or {},
        "note": (
            "HR N-mm package converted once at NL ingest; OpenSees/pushover/NLRHA stay kip-in "
            "until Stage D. Display may still use SI labels via display_scale."
        ),
    }
