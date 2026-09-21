"""India SI-native unit system (N-mm-sec) + legacy kip-in boundary helpers.

Wave 1 SI rewrite (2026-09-18): ENGINE_UNITS is **N-mm-sec**. Metric briefs normalize to
millimetres without kip-inch conversion for normal India jobs. OpenSees / steel_engine
geometry, section packs, E/G/g, and gravity masses use this system when activated.

Wave 2: report/design_pipeline/viewer SI labels + display scales. Legacy kip+inch
converters remain for USA archetypes and explicit units='kip-in'. Opt in with cfg['units']='kip-in' or
cfg['force_kip_in']=True.

load_plan RAG provenance strings stay in whatever units the standard cites (usually SI);
do not rewrite RAG text at the conversion boundary.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Active unit system (module default = SI for India repos)
# ---------------------------------------------------------------------------
UNIT_SYSTEM = "N-mm"  # "N-mm" | "kip-in"

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
        "India native OpenSees / design unit system is N-mm-sec. "
        "Call india_units.apply_si_geometry(cfg) [alias: apply_metric_geometry] for metric briefs; "
        "the USA twin's legacy unit system is never selected on an India job."
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
    "engine3d CFG['B*'] USA archetypes (inch geometry; unused by India briefs)",
    "aisc_shapes.csv / built-in W/_GEOM tables (inch) — dual-path fallback only",
    "static_model / design_post legacy kip-in branches (opt-in units='kip-in' only)",
    "Some report ASCE Table 12.x narrative strings still name USA clauses (IS path primary)",
    "CFS: SFIA designator twin + cfs_shapes.csv inch path (IS 811 preferred when label matches)",
    "CFS: AISI S400 Ω0 / expected-strength wall capacity — found:false under IS 801",
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
    """Set module + engine3d (if importable) to N-mm-sec."""
    global UNIT_SYSTEM
    UNIT_SYSTEM = "N-mm"
    try:
        import engine3d as eng
        eng.activate_si_units()
    except Exception:
        pass


def activate_kip_in() -> None:
    """Opt into legacy kip+inch for USA twin / explicit cfg."""
    global UNIT_SYSTEM
    UNIT_SYSTEM = "kip-in"
    try:
        import engine3d as eng
        eng.activate_kip_in_units()
    except Exception:
        pass


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
        if _india_declared(cfg):
            # WP1.12: an India job must declare its units -- never guessed from magnitudes
            raise UnitsError("India job without cfg['units'] (declare 'N-mm', 'mm' or 'm'); units are "
                             "never inferred from geometry magnitudes on steltic_india (WP1.12)")
        # Ambiguous / unset units (legacy USA archetypes only): infer from geometry magnitude
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


class UnitsError(ValueError):
    """Missing / ambiguous units on an India job."""


def _india_declared(cfg: dict) -> bool:
    j = str(cfg.get("jurisdiction") or cfg.get("code_jurisdiction") or cfg.get("code_region") or "").lower()
    lp = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    return j in ("india", "in", "bis", "is", "is_bis") or \
        str(lp.get("jurisdiction") or "").lower() in ("india", "in", "is", "is_bis", "bis")


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


def kn_per_m_to_kip_per_ft(value) -> float:
    """kN/m -> kip/ft (legacy USA display only; WP1.12 renamed from the misleading 'plf')."""
    return float(value) * KN_TO_KIP / (M_TO_IN / 12.0)


def mpa_to_ksi(value) -> float:
    return metric_stress_to_ksi(value, "MPa")


# ---------------------------------------------------------------------------
# Geometry / pressure application
# ---------------------------------------------------------------------------
_LENGTH_KEYS = (
    "story_heights", "storey_heights", "heights", "bay_x", "bay_y",
    "bay_spacing_x", "bay_spacing_y", "height", "width", "depth",
    "eave_height", "ridge_height", "xcoords", "ycoords",
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
    # India jurisdiction with UNSET units: refused (WP1.12) -- no guessing from magnitudes.
    if not metric and _india_declared(cfg):
        raise UnitsError("India job without cfg['units']: declare 'N-mm' (lengths mm), 'mm' or 'm' (WP1.12)")
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
        "factors": {                       # SI record only: no imperial factor in the package snapshot (WP6 residue grep)
            "m_to_mm": M_TO_MM,
            "kN_to_N": KN_TO_N,
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
    """India wave 1: SI-native (mm). Legacy kip-in when units/force_kip_in say so."""
    if wants_legacy_kip_in(cfg):
        return apply_metric_geometry_legacy_kip_in(cfg)
    return apply_si_geometry(cfg)


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
# Wave 2: report / CSV / viewer display helpers (engine stays N-mm or kip-in)
# ---------------------------------------------------------------------------
def display_scale(cfg: dict | None = None) -> dict:
    """Factors + labels to present engine quantities in engineer-facing units.

    SI engine stores force N, length mm, moment N·mm, stress MPa.
    Display defaults: kN, m (or mm for member lengths), kN·m, MPa.
    Legacy kip-in: kip, ft/in, kip-ft, ksi (identity /12 for moment-ft).
    """
    if is_si(cfg):
        return {
            "si": True,
            "force_div": 1000.0,          # N → kN
            "force_lbl": "kN",
            "force_raw_lbl": "N",
            "moment_div": 1.0e6,          # N·mm → kN·m
            "moment_lbl": "kN·m",
            "moment_raw_lbl": "N·mm",
            "length_div": 1000.0,         # mm → m (story / plan)
            "length_lbl": "m",
            "length_member_lbl": "mm",
            "length_member_div": 1.0,     # keep mm
            "stress_lbl": "MPa",
            "pressure_lbl": "kN/m²",
            "system": "N-mm-sec",
            "E_default": 200000.0,
            "Fy_default": 250.0,
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
    }


def fmt_force(v, cfg: dict | None = None, digits: int = 1) -> str:
    if v is None:
        return "—"
    sc = display_scale(cfg)
    return f"{float(v) / sc['force_div']:.{digits}f} {sc['force_lbl']}"


def fmt_moment(v, cfg: dict | None = None, digits: int = 1) -> str:
    """Engine moment (N·mm or kip-in) → display string."""
    if v is None:
        return "—"
    sc = display_scale(cfg)
    return f"{float(v) / sc['moment_div']:.{digits}f} {sc['moment_lbl']}"


def demand_field_names(cfg: dict | None = None) -> dict:
    """CSV / calc_package field names for the active unit system."""
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
