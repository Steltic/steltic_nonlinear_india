"""india_model.py -- India (IS) adjustments applied to the NL model after the Stage-B unit bridge.

WP4.8  mass and gravity = IS 1893 seismic weight:
       * level mass = W_i / g from seismic_calc.json W_kN (7.4.1: full dead load + Table 10 imposed share;
         7.3.2 roof imposed load not considered) -- rotational inertia scaled by the same ratio so the
         radius of gyration of the HR model is kept;
       * NL gravity per level = W_i (the same D + Table 10 share), spread over that level's column nodes;
         no ASCE 41 1.1(QD+0.25QL), no ASCE 7 16.3.2 0.5x0.4L, no psf defaults;
       * gate |sum(m)·g - W| <= 1 %.
WP4.5  material context (IS 2062 fy by grade/thickness, EOR expected-strength factor default 1.0).
"""
from __future__ import annotations
import json
import os

G_IN = 386.08858  # in/s^2 (9806.65 mm/s^2 / 25.4)


def is_india(pkg) -> bool:
    return getattr(getattr(pkg, "basis", None), "jurisdiction", None) == "india"


def load_nl_plan(pkg) -> dict:
    for cand in (os.path.join(str(pkg.root), "nl_plan.json"), os.path.join(os.path.dirname(str(pkg.root)), "nl_plan.json")):
        if os.path.exists(cand):
            try:
                return json.load(open(cand, encoding="utf-8")) or {}
            except Exception:
                return {}
    return {}


def material_ctx(pkg) -> dict:
    """Cached India material plan + per-section fy table (reported per section in the outputs)."""
    ctx = getattr(pkg, "_india_mat", None)
    if ctx is None:
        from . import india_materials as IM
        ctx = dict(plan=IM.material_plan(load_nl_plan(pkg), IM.package_materials(pkg.root)), by_section={})
        setattr(pkg, "_india_mat", ctx)
    return ctx


def fy_section(pkg, section, role=None, tag=None) -> dict:
    """fy for a member (NL-5). With `tag`, the element's schedule role (lateral_col, floor, link, brace, ...) selects
    the HR package's own material record; `role` may also be given directly or as a kind (col / beam / brace)."""
    from . import india_materials as IM
    ctx = material_ctx(pkg)
    if tag is not None:
        role = (pkg.schedule.get(tag) or {}).get("role") or role
    key = (str(section).upper().replace(" ", ""), str(role or ""))
    if key not in ctx["by_section"]:
        ctx["by_section"][key] = IM.fy_for_member(section, role, ctx["plan"])
    return ctx["by_section"][key]


def material_report(pkg) -> list:
    ctx = material_ctx(pkg)
    rows = []
    for (sec, role), r in sorted(ctx["by_section"].items()):
        rows.append(dict(r, role=role))
    return rows


def _levels(pkg):
    from .nonlinear_model import levels
    return levels(pkg)


def apply_is_seismic_mass(pkg) -> dict:
    """Set each diaphragm master's translational mass to W_i/g (kip·s²/in). Idempotent. Returns the gate."""
    if not is_india(pkg):
        return {}
    if isinstance(pkg.calc, dict) and pkg.calc.get("_is_mass_gate"):
        return pkg.calc["_is_mass_gate"]
    from snl.india_units import KN_TO_KIP
    ind = pkg.basis.india or {}
    W = ind.get("W_by_floor_kN")
    lv = _levels(pkg)
    if not W or len(W) != len(lv):
        raise ValueError("IS seismic weight by floor (seismic_calc.W_kN) has %s entries, the model has %d diaphragm "
                         "levels -- cannot set mass = W (WP4.8)" % (len(W) if W else 0, len(lv)))
    rows = []
    for (k, z, master, slaves), Wi in zip(lv, W):
        m_old = list(pkg.model.masses.get(master, [0.0] * 6))
        m_new = float(Wi) * KN_TO_KIP / G_IN
        ratio = m_new / m_old[0] if m_old[0] > 0 else 1.0
        mv = [m_new, m_new, 0.0, 0.0, 0.0, m_old[5] * ratio]
        pkg.model.masses[master] = mv
        rows.append(dict(level=k, master=master, W_kN=float(Wi), model_mass_before_kN=m_old[0] * G_IN / KN_TO_KIP,
                         scale=ratio))
    sum_mg_kN = sum(pkg.model.masses[m][0] for _, _, m, _ in lv) * G_IN / KN_TO_KIP
    Wt = float(sum(W))
    err = abs(sum_mg_kN - Wt) / Wt
    gate = dict(ok=bool(err <= 0.01), sum_mg_kN=sum_mg_kN, W_kN=Wt, rel_error=err, rows=rows,
                basis="IS 1893 7.3.1 / 7.4.1 seismic weight (full DL + Table 10 imposed share; roof imposed per 7.3.2) "
                      "from seismic_calc.json W_kN; rotational inertia scaled by the same ratio",
                clause="gate |sum(m)g - W| <= 1 %")
    if isinstance(pkg.calc, dict):
        pkg.calc["_is_mass_gate"] = gate
    if not gate["ok"]:
        raise ValueError("mass = W gate failed: sum m·g = %.1f kN vs W = %.1f kN" % (sum_mg_kN, Wt))
    return gate


def is_gravity_loads(pkg):
    """NL gravity = IS seismic weight per level (D + Table 10 imposed share), equal shares on the level's column
    nodes (same idealisation as the pushover). Returns ({node: Pz kip}, table)."""
    from snl.india_units import KN_TO_KIP
    ind = pkg.basis.india or {}
    W = ind.get("W_by_floor_kN")
    lv = _levels(pkg)
    if not W or len(W) != len(lv):
        raise ValueError("IS gravity: W_by_floor missing or level count mismatch (WP4.8)")
    loads, table = {}, []
    for (k, z, master, slaves), Wi in zip(lv, W):
        QG = float(Wi) * KN_TO_KIP
        for n in slaves:
            loads[n] = loads.get(n, 0.0) - QG / len(slaves)
        table.append(dict(level=k, z_in=z, z_mm=z * 25.4, W_kN=float(Wi), QG_kN=float(Wi), QG_kip=round(QG, 2),
                          WD_kip=round(QG, 2), QL25_kip=0.0, nodes=len(slaves),
                          basis="IS 1893 seismic weight W_i (7.4.1; Table 10 imposed share; 7.3.2 roof)"))
    return loads, table
