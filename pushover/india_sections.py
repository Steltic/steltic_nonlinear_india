"""india_sections.py -- built-up welded BOX sections declared by the HR package (NL-4).

steltic_india registers built-up welded box columns per job (cfg['custom_sections'] -> sections.register_box):
two flange plates B x tf (outside) and two web plates (D - 2 tf) x tw at the outer faces, properties computed from
the four plates (never a catalogue). The HR package records the declaration in design/cfg_snapshot.json
(`custom_sections`). This module mirrors the HR formulae exactly (sections.register_box, 3ec586a) so the NL models
use the same A, I, Z and J as the design, and keeps the plate dimensions for the fibre section and for fy by plate
thickness (IS 2062 Table 3, HR AUD-2).

Registry values are in mm; `props_in()` gives the inch-unit record pushover.sections_db serves (the NL Stage-B
kip-in analysis units).
"""
from __future__ import annotations
import json
import math
import os
import re

MM_PER_IN = 25.4
CUSTOM: dict = {}          # normalised label -> mm property dict (+ plates, source)
_LABEL_RE = re.compile(r"^BOX(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")


def normalize_label(name) -> str:
    return str(name or "").strip().upper().replace(" ", "")


def box_props_mm(B_mm, D_mm, tf_mm, tw_mm) -> dict:
    """steltic_india sections.register_box formulae (mm): A, Ix (about the axis parallel to B, depth D), Iy, Zx, Zy,
    Sx, Sy, r, J (thin-walled closed section, Bredt), shear area of the two webs."""
    B, D, tf, tw = float(B_mm), float(D_mm), float(tf_mm), float(tw_mm)
    if min(B, D, tf, tw) <= 0 or 2 * tf >= D or 2 * tw >= B:
        raise ValueError("box plates B=%s D=%s tf=%s tw=%s are not a closed box" % (B_mm, D_mm, tf_mm, tw_mm))
    d = D - 2.0 * tf
    A = 2.0 * B * tf + 2.0 * d * tw
    Ix = 2.0 * (B * tf ** 3 / 12.0 + B * tf * ((D - tf) / 2.0) ** 2) + 2.0 * tw * d ** 3 / 12.0
    Iy = 2.0 * (tf * B ** 3 / 12.0) + 2.0 * (d * tw ** 3 / 12.0 + d * tw * ((B - tw) / 2.0) ** 2)
    Sx, Sy = 2.0 * Ix / D, 2.0 * Iy / B
    Zx = B * tf * (D - tf) + 2.0 * tw * (d / 2.0) ** 2
    Zy = d * tw * (B - tw) + 2.0 * tf * (B / 2.0) ** 2
    Am = (B - tw) * (D - tf)
    J = 4.0 * Am ** 2 / (2.0 * (B - tw) / tf + 2.0 * (D - tf) / tw)
    return {"_units": "mm", "section_type": "box", "Type": "BOX", "A": A, "Ix": Ix, "Iy": Iy, "Zx": Zx, "Zy": Zy,
            "Sx": Sx, "Sy": Sy, "rx": math.sqrt(Ix / A), "ry": math.sqrt(Iy / A), "d": D, "bf": B, "tf": tf, "tw": tw,
            "J": J, "Cw": 0.0, "Aw": 2.0 * d * tw, "Mass_kg_m": A * 7850.0 / 1e6, "welded": True,
            "plates": {"flange_mm": [B, tf], "web_mm": [d, tw]}}


def register_box(name, B_mm, D_mm, tf_mm, tw_mm, source="built-up welded box (HR package custom_sections)") -> dict:
    p = box_props_mm(B_mm, D_mm, tf_mm, tw_mm)
    p["source"] = source
    p["label"] = normalize_label(name)
    CUSTOM[p["label"]] = p
    return p


def register_custom_sections(custom: dict | None, origin: str = "cfg_snapshot.json") -> list:
    """{name: {'type': 'box', 'B_mm', 'D_mm', 'tf_mm', 'tw_mm', 'source'}} -> registry. Returns the labels."""
    out = []
    for nm, spec in (custom or {}).items():
        if str((spec or {}).get("type", "box")).lower() != "box":
            raise KeyError("custom section %r: only built-up welded 'box' sections are supported (HR contract)" % nm)
        register_box(nm, spec["B_mm"], spec["D_mm"], spec["tf_mm"], spec["tw_mm"],
                     source="%s (%s)" % (spec.get("source") or "built-up welded box", origin))
        out.append(normalize_label(nm))
    return out


def register_from_package(root) -> list:
    """Register the package's declared custom sections: design/cfg_snapshot.json `custom_sections` (the HR record of
    the cfg the design ran with). Returns the labels registered (empty when the package declares none)."""
    p = os.path.join(str(root), "design", "cfg_snapshot.json")
    if not os.path.exists(p):
        return []
    try:
        snap = json.load(open(p, encoding="utf-8")) or {}
    except Exception:
        return []
    return register_custom_sections(snap.get("custom_sections") or {}, origin="design/cfg_snapshot.json")


def from_label(label) -> dict | None:
    """Fallback when a BOX label is not declared: BOX{D}X{B}X{t} (the HR naming, e.g. BOX450X400X25 = 450 deep,
    400 wide, 25 mm plates). Registered with a source that says it was parsed from the label."""
    key = normalize_label(label)
    mo = _LABEL_RE.match(key)
    if not mo:
        return None
    D, B, t = (float(mo.group(i)) for i in (1, 2, 3))
    return register_box(key, B, D, t, t, source="parsed from the label BOX{D}X{B}X{t} (not declared in the package -- VERIFY)")


def get_mm(label) -> dict | None:
    key = normalize_label(label)
    if key in CUSTOM:
        return CUSTOM[key]
    if key.startswith("BOX"):
        return from_label(key)
    return None


def is_box(label) -> bool:
    return get_mm(label) is not None


def props_in(label) -> dict | None:
    """Inch-unit record in the shape of the IS 808 / AISC csv rows (A in^2, I in^4, Z in^3, d/bf/tf/tw in)."""
    p = get_mm(label)
    if p is None:
        return None
    s = MM_PER_IN
    out = {"Type": "BOX", "A": p["A"] / s ** 2, "Ix": p["Ix"] / s ** 4, "Iy": p["Iy"] / s ** 4, "J": p["J"] / s ** 4,
           "Zx": p["Zx"] / s ** 3, "Zy": p["Zy"] / s ** 3, "Sx": p["Sx"] / s ** 3, "Sy": p["Sy"] / s ** 3,
           "rx": p["rx"] / s, "ry": p["ry"] / s, "d": p["d"] / s, "bf": p["bf"] / s, "tf": p["tf"] / s,
           "tw": p["tw"] / s, "Cw": 0.0, "A_si_mm2": p["A"], "Mass_kg_m": p["Mass_kg_m"], "box": True,
           "custom_section": p["label"], "custom_note": p["source"], "_source_csv": "HR custom_sections"}
    out["h_tw"] = (p["d"] - 2 * p["tf"]) / p["tw"]
    out["bf_2tf"] = p["bf"] / (2 * p["tf"])
    return out
