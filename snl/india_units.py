"""Metric/SI boundary helpers for steltic_nonlinear_india (NL fork).

Same conversion factors as steltic_india.steel_engine.india_units — keep in sync.
Full N-mm OpenSees/engine rewrite is deferred; convert metric briefs at the cfg
boundary before pushover / NLRHA / DDM consume geometry.
"""
from __future__ import annotations

ENGINE_UNITS = {
    "force": "kip",
    "length": "in",
    "moment": "kip-in",  # reports often kip-ft
    "stress": "ksi",
    "pressure_area": "psf (legacy gravity path) / ksi (steel)",
    "note": (
        "Full SI (N-mm) engine rewrite is deferred. Convert metric briefs to kip+inch "
        "before run_pipeline; retain SI in load_plan provenance strings from RAG."
    ),
}

# Exact
M_TO_IN = 39.37007874015748
MM_TO_IN = M_TO_IN / 1000.0
KN_TO_KIP = 1.0 / 4.4482216152605
MPA_TO_KSI = 1.0 / 6.894757293168361
KNM_TO_KIPIN = KN_TO_KIP * M_TO_IN  # kN·m → kip·in
KNM_TO_KIPFT = KN_TO_KIP * (M_TO_IN / 12.0)
KN_PER_M2_TO_PSF = (1.0 / 4.4482216152605) / ((39.37007874015748 / 12.0) ** 2) * 1000.0  # ≈20.8854
# kN/m² → kip/in² first: (kN/m²)*(kip/kN)/(in/m)² = ksi, then *144 = psf
# Fix: 1 kN/m² = 1000 N / m². 1 ksi = 6.894757 MPa = 6894.757 kN/m².
# So kN/m² → ksi = 1/6894.757; psf = ksi * 144 * 1000? No: 1 ksi = 144 * 1000 psf? 
# 1 ksi = 1000 psi = 1000*144 psf = 144000 psf. So kN/m² → psf:
# 1 kN/m² = 20.885 psf approximately.


def metric_length_to_in(value, unit: str = "m") -> float:
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


def apply_metric_geometry(cfg: dict) -> dict:
    """Convert cfg geometry fields declared in metres to inches (in-place + return).

    Recognises:
      cfg['units'] in {'metric','SI','m','mm'} OR cfg['metric']=True
      story_heights / bay_x / bay_y / height / width / depth given in m (or mm if units=='mm')

    Sets cfg['_units_converted'] provenance; leaves load_plan RAG strings untouched.
    """
    units = str(cfg.get("units") or "").lower()
    metric = bool(cfg.get("metric")) or units in ("metric", "si", "m", "mm", "india_metric")
    if not metric:
        return cfg
    length_unit = "mm" if units == "mm" else "m"
    if cfg.get("_units_converted"):
        return cfg  # idempotent

    def conv_list(key):
        if key not in cfg or cfg[key] is None:
            return
        val = cfg[key]
        if isinstance(val, (list, tuple)):
            cfg[key] = [metric_length_to_in(v, length_unit) for v in val]
        else:
            cfg[key] = metric_length_to_in(val, length_unit)

    for k in ("story_heights", "storey_heights", "heights", "bay_x", "bay_y",
              "bay_spacing_x", "bay_spacing_y", "height", "width", "depth",
              "eave_height", "ridge_height"):
        conv_list(k)

    # nested geometry
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

    # Brief aliases → engine keys (inches already). Do not overwrite explicit values.
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

    cfg["_units_converted"] = {
        "from": length_unit,
        "to": "in",
        "engine": ENGINE_UNITS,
        "factors": {"m_to_in": M_TO_IN, "kN_to_kip": KN_TO_KIP, "MPa_to_ksi": MPA_TO_KSI},
    }
    cfg["units"] = "kip-in"
    return cfg


def conversion_cheatsheet() -> str:
    return (
        "India metric → engine kip+inch: L_in=L_m×39.3701; F_kip=F_kN/4.44822; "
        "σ_ksi=σ_MPa/6.89476; p_psf≈p_kN/m²×20.885. "
        "Call india_units.apply_metric_geometry(cfg) when cfg['units'] is metric/SI. "
        "Engine internals remain kip+inch (full SI rewrite deferred)."
    )
