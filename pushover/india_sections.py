"""india_sections.py -- built-up welded BOX sections (NL-4) and welded plate I / web-tapered I sections (NL-33, the
PEB release of steltic_india, 2026-10) declared by the HR package.

Welded plate I (`welded_I`, label WI<D>X<bf>X<tf>X<tw>): two flange plates bf x tf and a web plate (D - 2 tf) x tw,
properties from the plates exactly as steltic_india sections.register_welded_I. Web-tapered I (`tapered_I`, label
TI<D0>-<D1>X<bf>X<tf>X<tw>): the HR stepped model splits the member into n_seg prismatic welded I segments (depth at
each segment's mid-length, rounded to 1 mm, sections.register_tapered_I); the analysis elements carry the segment WI
labels, so the NL models are built from the segments, as the design was.

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
_WI_RE = re.compile(r"^WI(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")
TAPERED: dict = {}         # TI label -> member record (segments, depths)


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


def _fmt_mm(v) -> str:
    v = float(v)
    return ("%d" % round(v)) if abs(v - round(v)) < 1e-6 else ("%g" % v)


def welded_i_label(D_mm, bf_mm, tf_mm, tw_mm) -> str:
    """WI<D>X<bf>X<tf>X<tw> (mm) -- steltic_india sections.welded_I_label."""
    return "WI%sX%sX%sX%s" % tuple(_fmt_mm(v) for v in (D_mm, bf_mm, tf_mm, tw_mm))


def welded_i_props_mm(D_mm, bf_mm, tf_mm, tw_mm) -> dict:
    """steltic_india sections.register_welded_I formulae (mm): doubly symmetric welded plate I, flanges bf x tf, web
    (D - 2 tf) x tw, no root fillets. A, Ix (major), Iy, Sx, Sy, Zx, Zy, J (open thin-walled), Cw, shear area of the
    web d tw (IS 800 8.4.1.1 welded)."""
    D, B, tf, tw = float(D_mm), float(bf_mm), float(tf_mm), float(tw_mm)
    if not (D > 2.0 * tf and B > tw and tf > 0 and tw > 0):
        raise ValueError("welded I plates D=%s bf=%s tf=%s tw=%s are inconsistent" % (D_mm, bf_mm, tf_mm, tw_mm))
    hw = D - 2.0 * tf
    A = 2.0 * B * tf + hw * tw
    Ix = (B * D ** 3 - (B - tw) * hw ** 3) / 12.0
    Iy = 2.0 * tf * B ** 3 / 12.0 + hw * tw ** 3 / 12.0
    Sx, Sy = 2.0 * Ix / D, 2.0 * Iy / B
    Zx = B * tf * (D - tf) + tw * hw ** 2 / 4.0
    Zy = tf * B ** 2 / 2.0 + hw * tw ** 2 / 4.0
    J = (2.0 * B * tf ** 3 + hw * tw ** 3) / 3.0
    ho = D - tf
    Cw = tf * B ** 3 * ho ** 2 / 24.0
    return {"_units": "mm", "section_type": "welded_i", "Type": "WELDED_I", "A": A, "Ix": Ix, "Iy": Iy, "Zx": Zx,
            "Zy": Zy, "Sx": Sx, "Sy": Sy, "rx": math.sqrt(Ix / A), "ry": math.sqrt(Iy / A), "d": D, "bf": B, "tf": tf,
            "tw": tw, "J": J, "Cw": Cw, "ho": ho, "Aw": hw * tw, "Mass_kg_m": A * 7850.0 / 1e6, "welded": True,
            "plates": {"flange_mm": [B, tf], "web_mm": [hw, tw]}}


def register_welded_i(name, D_mm, bf_mm, tf_mm, tw_mm, source="welded plate I (HR package custom_sections)") -> dict:
    p = welded_i_props_mm(D_mm, bf_mm, tf_mm, tw_mm)
    p["source"] = source
    p["label"] = normalize_label(name)
    CUSTOM[p["label"]] = p
    return p


def register_tapered_i(name, D_start_mm, D_end_mm, bf_mm, tf_mm, tw_mm, n_seg=8, source=None, round_mm=1.0) -> dict:
    """The n_seg stepped segments of a web-tapered welded I member, as steltic_india sections.register_tapered_I:
    segment s is a prismatic welded I at the depth of its mid-length, D0 + (D1 - D0)(s + 0.5)/n, rounded to round_mm;
    its label is the WI designation. Returns the member record (also in TAPERED)."""
    n = int(n_seg)
    D0, D1 = float(D_start_mm), float(D_end_mm)
    segs, depths = [], []
    for k in range(n):
        Dm = D0 + (D1 - D0) * (k + 0.5) / n
        if round_mm:
            Dm = round(Dm / float(round_mm)) * float(round_mm)
        lab = welded_i_label(Dm, bf_mm, tf_mm, tw_mm)
        if normalize_label(lab) not in CUSTOM:
            register_welded_i(lab, Dm, bf_mm, tf_mm, tw_mm,
                              source=source or "segment of web-tapered welded I %s (HR package custom_sections)" % name)
        segs.append(lab)
        depths.append(Dm)
    rec = {"name": normalize_label(name), "D_start_mm": D0, "D_end_mm": D1, "bf_mm": float(bf_mm), "tf_mm": float(tf_mm),
           "tw_mm": float(tw_mm), "n_seg": n, "segments": segs, "depths_mm": depths}
    TAPERED[normalize_label(name)] = rec
    return rec


def double_angle_props_mm(angle, gap_mm, connected_leg="D") -> dict:
    """Third wave (IN_Ex21): two IS 808 angles back to back on a gusset of thickness gap_mm -- the formulae of steltic_india
    sections.register_double_angle (MSME branch): the connected legs lie against the gusset, in the truss plane.
      x (in-plane bending, the engine's major slot): Ix = 2 I1 about the component's own axis;
      y (out of plane, about the gusset centre): Iy = 2 (I1' + A1 (c + g/2)^2), c = the component centroid from the back
      of its connected leg; Zx = 2 Zp1, Zy = 2 A1 (c + g/2); J = 2 J1; r_min = sqrt(min(Ix, Iy) / A).
    Component values from the IS 808:2021 row (mm columns)."""
    from . import sections_db as SDB
    p1 = SDB.props(angle)
    if str(p1.get("Type") or "").upper() != "ISA":
        raise ValueError("double angle: component %r is not an IS 808 angle" % angle)
    g = float(gap_mm)
    A1, t = float(p1["A_si_mm2"]), float(p1["tw_mm"])
    leg = str(connected_leg or "D").upper()
    if leg == "D":
        Dc, Bo, I_in1, I_out1 = float(p1["D_mm"]), float(p1["B_mm"]), float(p1["Izz_si_mm4"]), float(p1["Iyy_si_mm4"])
        c_back, c_toe_in, Zp_in1 = float(p1["Cz_mm"]), float(p1["Cy_mm"]), float(p1["Zpz_mm3"])
    elif leg == "B":
        Dc, Bo, I_in1, I_out1 = float(p1["B_mm"]), float(p1["D_mm"]), float(p1["Iyy_si_mm4"]), float(p1["Izz_si_mm4"])
        c_back, c_toe_in, Zp_in1 = float(p1["Cy_mm"]), float(p1["Cz_mm"]), float(p1["Zpy_mm3"])
    else:
        raise ValueError("double angle: connected_leg must be 'D' or 'B', not %r" % connected_leg)
    A, Ix = 2.0 * A1, 2.0 * I_in1
    a = c_back + g / 2.0
    Iy = 2.0 * (I_out1 + A1 * a ** 2)
    return {"_units": "mm", "section_type": "double_angle", "Type": "DOUBLE_ANGLE", "A": A, "Ix": Ix, "Iy": Iy,
            "Zx": 2.0 * Zp_in1, "Zy": 2.0 * A1 * a, "Sx": Ix / max(Dc - c_toe_in, c_toe_in), "Sy": Iy / (Bo + g / 2.0),
            "rx": math.sqrt(Ix / A), "ry": math.sqrt(Iy / A), "r_min": math.sqrt(min(Ix, Iy) / A), "d": Dc,
            "bf": 2.0 * Bo + g, "tf": t, "tw": t, "J": 2.0 * float(p1.get("It_mm4") or 0.0), "Cw": 0.0, "Aw": 2.0 * Dc * t,
            "Mass_kg_m": 2.0 * float(p1.get("Mass_kg_m") or A1 * 7850.0 / 1e6), "component": normalize_label(angle),
            "gap_mm": g, "connected_leg": leg, "leg_connected_mm": Dc, "leg_outstanding_mm": Bo, "t_mm": t, "A1_mm2": A1,
            "c_back_mm": c_back, "c_toe_mm": c_toe_in, "welded": False}


def register_double_angle(name, angle, gap_mm, connected_leg="D", source=None) -> dict:
    p = double_angle_props_mm(angle, gap_mm, connected_leg)
    p["label"] = normalize_label(name)
    p["source"] = source or "two IS 808 %s back to back, %g mm gusset (HR package custom_sections)" % (angle, float(gap_mm))
    CUSTOM[p["label"]] = p
    return p


_DA_RE = re.compile(r"^2(ISA\d+(?:\.\d+)?X\d+(?:\.\d+)?X\d+(?:\.\d+)?)$")


def register_custom_sections(custom: dict | None, origin: str = "cfg_snapshot.json") -> list:
    """{name: {'type': 'box' | 'welded_I' | 'tapered_I', ...}} -> registry. Returns the labels registered.
    box: B_mm, D_mm, tf_mm, tw_mm; welded_I: D_mm, bf_mm, tf_mm, tw_mm; tapered_I: D_start_mm, D_end_mm, bf_mm, tf_mm,
    tw_mm, n_seg (its segments are registered as welded I)."""
    out = []
    for nm, spec in (custom or {}).items():
        typ = str((spec or {}).get("type", "box")).lower()
        src = "%s (%s)" % (spec.get("source") or {"box": "built-up welded box", "welded_i": "welded plate I",
                                                    "tapered_i": "web-tapered welded I"}.get(typ, typ), origin)
        if typ == "box":
            register_box(nm, spec["B_mm"], spec["D_mm"], spec["tf_mm"], spec["tw_mm"], source=src)
            out.append(normalize_label(nm))
        elif typ in ("welded_i", "i_welded"):
            register_welded_i(nm, spec["D_mm"], spec["bf_mm"], spec["tf_mm"], spec["tw_mm"], source=src)
            out.append(normalize_label(nm))
        elif typ in ("tapered_i", "i_tapered"):
            rec = register_tapered_i(nm, spec["D_start_mm"], spec["D_end_mm"], spec["bf_mm"], spec["tf_mm"], spec["tw_mm"],
                                     n_seg=spec.get("n_seg") or 8, round_mm=spec.get("round_mm", 1.0),
                                     source="segment of %s" % src)
            out.extend(rec["segments"])
        elif typ == "double_angle":                   # third wave (IN_Ex21 angle-truss shed)
            register_double_angle(nm, spec["angle"], spec.get("gap_mm") or 0.0, spec.get("connected_leg") or "D", source=src)
            out.append(normalize_label(nm))
        else:
            raise KeyError("custom section %r: type %r is not supported (box | welded_I | tapered_I, HR contract)"
                           % (nm, spec.get("type")))
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


def welded_i_from_label(label) -> dict | None:
    """Fallback when a WI label is not declared: WI{D}X{bf}X{tf}X{tw} is self-describing (the HR designation; the
    segments of a tapered member are named this way). Registered with a source that says so."""
    key = normalize_label(label)
    mo = _WI_RE.match(key)
    if not mo:
        return None
    D, B, tf, tw = (float(mo.group(i)) for i in (1, 2, 3, 4))
    return register_welded_i(key, D, B, tf, tw, source="welded plate I, plates read from the designation WI{D}X{bf}X{tf}X{tw}")


def get_mm(label) -> dict | None:
    key = normalize_label(label)
    if key in CUSTOM:
        return CUSTOM[key]
    if key.startswith("BOX"):
        return from_label(key)
    if key.startswith("WI"):
        return welded_i_from_label(key)
    mo = _DA_RE.match(key)
    if mo:                                         # 2ISA... not declared: the HR label, gap unknown -> 0 (VERIFY)
        return register_double_angle(key, mo.group(1), 0.0, source="two IS 808 %s back to back, gap not declared in the "
                                     "package (0 mm assumed -- VERIFY)" % mo.group(1))
    return None


def is_double_angle(label) -> bool:
    p = get_mm(label)
    return p is not None and p.get("section_type") == "double_angle"


def is_box(label) -> bool:
    p = get_mm(label)
    return p is not None and p.get("section_type") == "box"


def is_welded_i(label) -> bool:
    p = get_mm(label)
    return p is not None and p.get("section_type") == "welded_i"


def props_in(label) -> dict | None:
    """Inch-unit record in the shape of the IS 808 / AISC csv rows (A in^2, I in^4, Z in^3, d/bf/tf/tw in)."""
    p = get_mm(label)
    if p is None:
        return None
    s = MM_PER_IN
    box = p.get("section_type") == "box"
    da = p.get("section_type") == "double_angle"
    out = {"Type": "BOX" if box else ("DOUBLE_ANGLE" if da else "WELDED_I"), "A": p["A"] / s ** 2, "Ix": p["Ix"] / s ** 4, "Iy": p["Iy"] / s ** 4,
           "J": p["J"] / s ** 4, "Zx": p["Zx"] / s ** 3, "Zy": p["Zy"] / s ** 3, "Sx": p["Sx"] / s ** 3,
           "Sy": p["Sy"] / s ** 3, "rx": p["rx"] / s, "ry": p["ry"] / s, "d": p["d"] / s, "bf": p["bf"] / s,
           "tf": p["tf"] / s, "tw": p["tw"] / s, "Cw": (p.get("Cw") or 0.0) / s ** 6, "A_si_mm2": p["A"],
           "Mass_kg_m": p["Mass_kg_m"], "box": box, "welded_i": not box and not da, "double_angle": da,
           "r_min_mm": p.get("r_min"),
           "custom_section": p["label"], "custom_note": p["source"], "_source_csv": "HR custom_sections"}
    out["h_tw"] = (p["d"] - 2 * p["tf"]) / p["tw"]
    out["bf_2tf"] = p["bf"] / (2 * p["tf"])
    return out
