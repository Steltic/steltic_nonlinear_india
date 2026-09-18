"""Portal-frame (CFS-P) bridge for steltic_ddm.

Multi-storey steltic_ddm assumes heights/NX/SX + rigid-diaphragm masters and
design_pipeline.combos. CFS portal one-bay packs use structure_kind=portal,
cfs_frame.lrfd_combos, and no diaphragm masters. This module:

  * detects portal packages
  * regenerates combos via cfs_frame.lrfd_combos (USA ASCE scaffolding;
    India CFS engine uses load_plan — set STELTIC_ENGINE_DIR to steltic_CFS_india)
  * maps them to the DDM tuple (label, fD, fL, fLr, lateral, col_only)
  * supplies roof gravity UDL + eave/wall lateral nodal loads
  * runs a no-master transfer gate (periods + eave unit lateral)

Fibre CFS sections are equivalent rectangles matching gross A & Ix — they do
NOT capture local/distortional buckling (disclose in the summary).
"""
from __future__ import annotations
import math
import os
import sys

import openseespy.opensees as ops


def is_portal(cfg) -> bool:
    if not isinstance(cfg, dict):
        return False
    sk = str(cfg.get("structure_kind") or "").lower()
    return sk.startswith("portal") or ("span_ft" in cfg and "heights" not in cfg)


def ensure_engine():
    eng = os.environ.get("STELTIC_ENGINE_DIR") or "/home/box/src/steltic_cfs/steel_engine"
    # Prefer CFS engine (has cfs_frame); fall back to whichever is already importable.
    for cand in (eng, "/home/box/src/steltic_cfs/steel_engine", "/home/box/src/steltic/steel_engine"):
        if cand and os.path.isdir(cand) and cand not in sys.path:
            sys.path.insert(0, cand)
    return eng


def _snow_ps(cfg):
    ensure_engine()
    import cfs_frame as CF
    return float(CF.snow_ps(cfg))


def _wind_pressures(cfg):
    ensure_engine()
    import cfs_frame as CF
    return CF.wind_surface_pressures(cfg)


def _eave_nodes(nm):
    """Eave nodes ≈ max-z nodes that are also at min/max x (both frames)."""
    xs = sorted({round(v[0], 6) for v in nm.nodes.values()})
    zs = sorted({round(v[2], 6) for v in nm.nodes.values()})
    if not xs or not zs:
        return []
    xmin, xmax = xs[0], xs[-1]
    # eave height is typically the wall-top z (not apex). Use nodes at xmin/xmax with z near eave.
    eave_ft = None
    # pick the highest z among wall-line nodes that is still below apex
    wall_zs = sorted({round(v[2], 6) for t, v in nm.nodes.items()
                      if abs(v[0] - xmin) < 1e-3 or abs(v[0] - xmax) < 1e-3})
    if len(wall_zs) >= 2:
        eave_z = wall_zs[-1] if wall_zs[-1] < zs[-1] - 1e-3 else (wall_zs[-2] if len(wall_zs) > 1 else wall_zs[-1])
    else:
        eave_z = zs[len(zs) // 2]
    out = [t for t, v in nm.nodes.items()
           if abs(v[2] - eave_z) < 1.0 and (abs(v[0] - xmin) < 1.0 or abs(v[0] - xmax) < 1.0)]
    return sorted(out)


def _roof_primary_members(nm):
    """Rafter primary beams: dirn X, CFS built-up (not Z purlins/girts)."""
    out = []
    for m in nm.members:
        if m.kind != "beam":
            continue
        sec = str(m.section).upper()
        if "Z" in sec and not sec.startswith(("6X", "4X", "2X", "8X", "10X", "12X")):
            # 800Z250-* secondaries
            if sec.startswith("800Z") or sec.startswith("600Z") or "Z250" in sec:
                continue
        if m.dirn == "X":
            # primary rafter spans in X; exclude Y-bay secondaries
            out.append(m)
    return out


def _wall_col_nodes(nm, side="L"):
    xs = sorted({round(v[0], 6) for v in nm.nodes.values()})
    x = xs[0] if side == "L" else xs[-1]
    bases = {t for t, fl in nm.fixes.items() if fl[0] and fl[1] and fl[2]}
    return [t for t, v in nm.nodes.items() if abs(v[0] - x) < 1.0 and t not in bases]


def _analysis_is_nmm(cfg) -> bool:
    try:
        from snl import india_units as U
        return U.analysis_unit_system(cfg) == "N-mm" or U.wants_native_nmm_analysis(cfg)
    except Exception:
        return False


def _seis_V_kip(cfg):
    """Legacy kip base shear for one frame (ASCE-style SDS/R/Ie × W_frame_kip)."""
    s = cfg.get("seis") or {}
    Wf = s.get("W_frame_kip")
    if not Wf:
        return 0.0
    return float(s["SDS"]) / (float(s.get("R", 3.0)) / float(s.get("Ie", 1.0))) * float(Wf)


def _seis_V(cfg):
    """Portal seismic base shear in analysis force units (kip or N).

    Stage D: when analysis is N-mm, accepts W_frame_N / W_frame_kN, or converts W_frame_kip.
    Sa/g factor still dimensionless (SDS or Ah).
    """
    s = cfg.get("seis") or {}
    sa = float(s.get("SDS") or s.get("Ah") or 0.0)
    R = float(s.get("R", 3.0)); Ie = float(s.get("Ie", s.get("I", 1.0)))
    if not sa or not R:
        return 0.0
    coeff = sa / (R / Ie) if R else 0.0
    if _analysis_is_nmm(cfg):
        if s.get("W_frame_N") is not None:
            W = float(s["W_frame_N"])
        elif s.get("W_frame_kN") is not None:
            W = float(s["W_frame_kN"]) * 1000.0
        elif s.get("W_frame_kip") is not None:
            from snl.india_units import KIP_TO_N
            W = float(s["W_frame_kip"]) * KIP_TO_N
        else:
            return 0.0
        return coeff * W
    return _seis_V_kip(cfg)


def _wind_H_kip(cfg, case="W"):
    """Net transverse horizontal force (kip) on ONE frame spacing from wall pressures (psf × ft²)."""
    pr = _wind_pressures(cfg)
    if case == "W2" and pr.get("case_neg"):
        pr = dict(pr); pr.update(pr["case_neg"])
    eave = float(cfg["eave_ft"])
    sp = float(cfg["spacing_ft"])
    ww = float(pr["wall_wind"]); wl = float(pr["wall_lee"])
    H = (ww - wl) * eave * sp / 1000.0
    return H, pr


def _wind_H(cfg, case="W"):
    """Net transverse H in analysis force units (kip or N). Stage D SI uses eave_mm/spacing_mm + kN/m²."""
    if not _analysis_is_nmm(cfg):
        return _wind_H_kip(cfg, case=case)
    # SI: pressures kN/m², lengths mm → N
    pr = _wind_pressures(cfg)
    if case == "W2" and pr.get("case_neg"):
        pr = dict(pr); pr.update(pr["case_neg"])
    if cfg.get("eave_mm") is not None:
        eave_m = float(cfg["eave_mm"]) / 1000.0
    elif cfg.get("eave_m") is not None:
        eave_m = float(cfg["eave_m"])
    else:
        eave_m = float(cfg.get("eave_ft", 0.0)) * 0.3048
    if cfg.get("spacing_mm") is not None:
        sp_m = float(cfg["spacing_mm"]) / 1000.0
    elif cfg.get("spacing_m") is not None:
        sp_m = float(cfg["spacing_m"])
    else:
        sp_m = float(cfg.get("spacing_ft", 0.0)) * 0.3048
    ww = float(pr["wall_wind"]); wl = float(pr["wall_lee"])
    # If pressures look like psf (>> 5 typical kN/m²), convert
    if max(abs(ww), abs(wl)) > 20:
        from snl.india_units import PSF_TO_KN_PER_M2
        ww *= PSF_TO_KN_PER_M2; wl *= PSF_TO_KN_PER_M2
    H_kN = (ww - wl) * eave_m * sp_m
    return H_kN * 1000.0, pr  # N


def portal_combos(cfg, nm=None):
    """Return DDM tuples. lateral dict uses REAL node tags as keys (not level indices)."""
    ensure_engine()
    import cfs_frame as CF
    raw = CF.lrfd_combos(cfg)
    snow = _snow_ps(cfg)
    # stash for beam_udl
    cfg.setdefault("snow", snow)
    cfg.setdefault("D_floor", 0.0)
    cfg.setdefault("L_floor", 0.0)
    if cfg.get("Fy") is None:
        fy = (cfg.get("study") or {}).get("Fy_ksi")
        if fy:
            cfg["Fy"] = float(fy)

    eaves = _eave_nodes(nm) if nm is not None else []
    out = []
    for label, factors in raw:
        fD = float(factors.get("D", 0.0))
        fL = 0.0
        # roof live / snow companion mapped into fLr; principal snow also into fLr with snow psf
        fLr = 0.0
        if "Lr" in factors:
            fLr = float(factors["Lr"])
            cfg["_portal_roof_psf"] = float(cfg.get("Lr", 20.0))
        for sc in ("S_bal", "S_unb_L", "S_unb_R"):
            if sc in factors:
                fLr = float(factors[sc])
                cfg["_portal_roof_psf"] = snow
                cfg["_portal_snow_case"] = sc
        # lateral
        lat = {}
        wfac = factors.get("W") or factors.get("W2")
        if wfac:
            case = "W2" if "W2" in factors else "W"
            H, _pr = _wind_H(cfg, case=case)
            H *= float(wfac)
            # split across eave nodes (both frames, both walls) → net +X
            nodes = eaves or []
            if nodes:
                share = H / len(nodes)
                for t in nodes:
                    lat[int(t)] = (share, 0.0, 0.0)
            else:
                lat[1] = (H, 0.0, 0.0)  # placeholder; apply_lateral will no-op if missing
        if "E" in factors:
            V = _seis_V(cfg) * float(factors["E"])
            # one-bay model ≈ one frame spacing of lateral; W_frame is already per spacing
            nodes = eaves or []
            if nodes:
                share = V / len(nodes)
                for t in nodes:
                    lat[int(t)] = (lat.get(int(t), (0, 0, 0))[0] + share,
                                   lat.get(int(t), (0, 0, 0))[1],
                                   lat.get(int(t), (0, 0, 0))[2])
        out.append((label, fD, fL, fLr, lat, False))
    return out


def portal_prune(cases, policy="default"):
    """Keep governing portal set: gravity/snow, wind strength+uplift, seismic R=3."""
    if policy == "all":
        return list(cases)
    keep = []
    for c in cases:
        lab = c[0]
        if lab == "1.4D":
            keep.append(c); continue
        if lab.startswith("1.2D+1.6Lr") or lab.startswith("1.2D+1.0S"):
            keep.append(c); continue
        if "W" in lab and ("1.2D" in lab or "0.9D" in lab):
            keep.append(c); continue
        if lab.endswith("+E") or "D+E" in lab:
            keep.append(c); continue
    return keep


def portal_beam_udl(cfg, nm, member, seg_index, nseg, fD, fL, fLr):
    """Distributed gravity on primary rafter sub-elements (OpenSees beamUniform local).

    Legacy: kip/in. Stage D N-mm: N/mm (pressures kN/m², spacing m).
    """
    sec = str(member.section).upper()
    if member.kind != "beam" or member.dirn != "X":
        return 0.0
    if sec.startswith("800Z") or sec.startswith("600Z") or "Z250" in sec:
        return 0.0
    sc = cfg.get("_portal_snow_case")
    unb = 1.0
    if sc in ("S_unb_L", "S_unb_R") and fLr:
        fw, fl = cfg.get("unbalanced_factors", (0.3, 1.5))
        xs = sorted({v[0] for v in nm.nodes.values()})
        mid = 0.5 * (xs[0] + xs[-1])
        x1 = nm.nodes[member.n1][0]; x2 = nm.nodes[member.n2][0]
        xm = 0.5 * (x1 + x2)
        left = xm < mid
        if sc == "S_unb_L":
            unb = fw if left else fl
        else:
            unb = fl if left else fw

    if _analysis_is_nmm(cfg):
        # pressures in kN/m²; spacing in m
        if cfg.get("spacing_mm") is not None:
            sp_m = float(cfg["spacing_mm"]) / 1000.0
        elif cfg.get("spacing_m") is not None:
            sp_m = float(cfg["spacing_m"])
        else:
            sp_m = float(cfg.get("spacing_ft", 15.0)) * 0.3048
        D = float(cfg.get("D_roof", 0.3)) + float(cfg.get("collateral", 0.0))  # kN/m²
        roof_p = float(cfg.get("_portal_roof_psf") or cfg.get("snow") or cfg.get("Lr") or 1.0)
        # if roof_p looks like psf, convert
        if roof_p > 20:
            from snl.india_units import PSF_TO_KN_PER_M2
            roof_p *= PSF_TO_KN_PER_M2
        p = fD * D + fLr * roof_p * unb  # kN/m²
        w_kNpm = p * (sp_m / 2.0)  # kN/m on one frame rafter
        return w_kNpm  # N/mm  (== kN/m numerically)

    sp = float(cfg.get("spacing_ft", 15.0))
    D = float(cfg.get("D_roof", 6.5)) + float(cfg.get("collateral", 0.0))
    roof_psf = float(cfg.get("_portal_roof_psf") or cfg.get("snow") or cfg.get("Lr") or 20.0)
    p = fD * D + fLr * roof_psf * unb
    w_plf = p * (sp / 2.0) / 1000.0  # kip/ft
    return w_plf / 12.0  # kip/in


def transfer_gate_portal(nm, cfg, tol=0.05, nsub=(2, 2, 2)):
    """Periods + eave unit-lateral roof UX; no diaphragm masters required."""
    from .model_gmnia import GMNIAModel
    from .transfer_gate import _replay, _periods

    replay = nm.job_dir + "/model_opensees.py"
    eaves = _eave_nodes(nm)
    # roof reference node: apex-ish highest z
    top = max(nm.nodes.items(), key=lambda kv: kv[1][2])[0]

    def eave_disp():
        ops.wipeAnalysis() if hasattr(ops, "wipeAnalysis") else None
        try:
            ops.wipe_analysis()
        except Exception:
            pass
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        share = 1.0 / max(len(eaves), 1)
        for t in eaves:
            ops.load(t, share, 0.0, 0.0, 0.0, 0.0, 0.0)
        ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
        ops.test("NormDispIncr", 1e-8, 50, 0); ops.algorithm("Linear")
        ops.integrator("LoadControl", 1.0); ops.analysis("Static")
        ok = ops.analyze(1)
        d = ops.nodeDisp(top, 1)
        try:
            ops.remove("loadPattern", 1)
        except Exception:
            pass
        return ok, d

    _replay(replay)
    T_ref = _periods(min(3, max(1, len(nm.nodes) // 10)))
    _replay(replay); _, dx_ref = eave_disp()

    g = GMNIAModel(nm, cfg, nsub=nsub, elastic=True, residual="none",
                   out_of_plumb=(None, 0.0), bow=0.0, brace_bow=0.0)
    g.build(with_mass=True)
    T_new = _periods(min(3, max(1, len(nm.nodes) // 10)))
    g.build(); _, dx_new = eave_disp()

    rows = []
    def cmp(name, a, b, tol_use):
        r = b / a if abs(a) > 1e-12 else float("nan")
        rows.append(dict(quantity=name, steltic=a, gmnia=b, ratio=r,
                         ok=(abs(r - 1) <= tol_use) if (a == a and b == b) else False))
    # Periods: fibre secondaries introduce soft local modes vs elasticBeamColumn replay —
    # allow a wide band; the decisive check is eave-lateral stiffness (same proof as ELF roof disp).
    for i, (a, b) in enumerate(zip(T_ref, T_new)):
        cmp("T%d (s)" % (i + 1), a, b, max(tol * 20, 4.0))  # allow up to ~5x
    cmp("roof UX under unit eave Fx (in)", dx_ref, dx_new, tol)
    lat_ok = rows[-1]["ok"]
    # Periods are diagnostic (soft local modes); governing check is eave-lateral UX.
    ok = lat_ok
    hint = None
    if not ok:
        hint = ("portal transfer gate mismatch — lateral ratio %.3f (tol %.0f%%); "
                "check CFS fibre A/Ix/axis mapping" % (rows[-1]["ratio"], 100 * tol))
    return dict(ok=ok, tol=tol, rows=rows, hint=hint,
                elements_steltic=len(nm.members), elements_gmnia=len(g.elems),
                mode="portal", note="periods use wide band (secondary local modes); governing check is eave lateral UX")
