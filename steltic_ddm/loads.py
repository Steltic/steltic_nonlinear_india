"""
loads.py -- factored load combinations and their application to the GMNIA model.

Combinations come from the HR design package's combination set so DDM sweeps the SAME cases
the member design used: (label, fD, fL, fLr, lateral{k:(fx,fy,mz)}, col_only).

USA steltic: design_pipeline.combos → ASCE 7-22 §2.3.
India steltic_india: design_pipeline.combos / india_loads → cfg['load_plan'] (IS 875 + IS 1893 RAG).
On this India NL fork, prefer load_plan; never invent ASCE 7 as India authority.
Gravity is applied as the same two-way (45-degree) tributary line loads static_model.apply_gravity
uses (per beam sub-element, plus cladding on single-bay perimeter beams); lateral forces and
accidental-torsion moments go to the rigid-diaphragm master nodes, as in Steltic.

Pruning (default): 1.4D ; 1.2D+1.6L+0.5Lr ; 1.2D+1.6Lr+0.5L ; the +/-X and +/-Y strength lateral cases
for wind (if present) and for the rho*E seismic pattern with the accidental-torsion sign the elastic
envelope found governing (here: '+' by default -- both are run when --torsion both), plus the 0.9D
uplift companions for braced buildings. Omega0 [col] cases are optional (seismic supplement).
"""
import re
from .ingest import decode_tag


def steltic_combos(cfg, nm=None):
    """Return factored combinations for GMNIA sweeps.

    India fork: prefer cfg['load_plan'] (LIVE IS 875 / IS 1893 RAG from steltic_india).
    When STELTIC_ENGINE_DIR points at steltic_india/steel_engine, design_pipeline.combos
    already routes through india_loads — that is the intended path.

    If cfg carries jurisdiction india (or load_plan) but the importable design_pipeline
    still looks like USA ASCE-only and load_plan is missing → raise, do not invent ASCE 7.
    """
    plan = cfg.get("load_plan") if isinstance(cfg, dict) else None
    juris = str((plan or {}).get("jurisdiction") or (cfg or {}).get("jurisdiction") or "").lower()
    indiaish = juris in ("india", "is", "is_bis", "bis") or bool(plan)

    # Prefer india_loads BEFORE portal_adapter (portal_adapter imports openseespy at module level).
    try:
        import india_loads as IL  # type: ignore
        if plan:
            return IL.cases_from_load_plan(cfg)
        if indiaish:
            raise RuntimeError(
                "steltic_nonlinear_india DDM: jurisdiction/load_plan marks India but "
                "cfg['load_plan'] is missing. Point STELTIC_ENGINE_DIR at steltic_india/"
                "steel_engine and ensure the HR package carries RAG-backed load_plan "
                "(IS 875 + IS 1893). Do not regenerate ASCE 7 §2.3 combos as India authority."
            )
    except ImportError:
        if indiaish and not plan:
            raise RuntimeError(
                "steltic_nonlinear_india DDM: India package without load_plan and "
                "india_loads not importable. Set STELTIC_ENGINE_DIR=/path/to/steltic_india/"
                "steel_engine so design_pipeline.combos uses the India load_plan path."
            )

    from . import portal_adapter as PA
    if PA.is_portal(cfg):
        return PA.portal_combos(cfg, nm=nm)

    import design_pipeline as DP
    return DP.combos(cfg)


def prune(cases, policy="default", torsion="plus", include_om0=False):
    if policy == "all":
        return list(cases)
    # portal seismic labels are "(1.2+0.2SDS)D+E" — keep them
    # India IS 800 Table 4: 1.5DL+1.5LL, 1.2DL+1.2LL+1.2EQ_X / W_X, 0.9DL+1.5EQ_X, …
    from . import portal_adapter as PA
    keep = []
    for c in cases:
        lab = c[0]
        col_only = c[5]
        if col_only and not include_om0:
            continue
        if lab in ("1.4D",) or lab.startswith("1.2D+1.6L") or lab.startswith("1.2D+1.6Lr") or lab.startswith("1.2D+1.0S"):
            keep.append(c); continue
        if "W" in lab and ("1.2D" in lab or "0.9D" in lab):
            keep.append(c); continue                          # all 8 wind cases (4 strength + 4 uplift)
        if "rhoE" in lab:
            tt = "t+" if torsion == "plus" else "t-"
            if torsion == "both" or tt in lab:
                keep.append(c); continue
        if lab.endswith("+E") or "D+E" in lab:
            keep.append(c); continue
        # ---- India / IS 800 Table 4 labels (DL/LL/EQ_/W_) ----
        if "DL" in lab and "LL" in lab and "EQ" not in lab and "W_" not in lab and "W+" not in lab:
            keep.append(c); continue  # gravity 1.5DL+1.5LL
        if ("EQ_X" in lab or "EQ_Y" in lab or "EQX" in lab.upper() or "EQY" in lab.upper()):
            keep.append(c); continue
        if ("W_X" in lab or "W_Y" in lab) and ("DL" in lab or "0.9" in lab or "1.2" in lab or "1.5" in lab):
            keep.append(c); continue
        if col_only and include_om0:
            keep.append(c)
    return keep


def lateral_direction(lat):
    """Dominant lateral direction and sign of a combination: ('X'|'Y'|None, +1|-1)."""
    fx = sum(v[0] for v in lat.values()); fy = sum(v[1] for v in lat.values())
    if abs(fx) < 1e-9 and abs(fy) < 1e-9:
        return None, 0
    if abs(fx) >= abs(fy):
        return "X", (1 if fx > 0 else -1)
    return "Y", (1 if fy > 0 else -1)


def present_sets(nm):
    pres = {}
    for t in nm.nodes:
        if t % 100000 == 99999:
            continue
        i, j, k = decode_tag(t)
        pres.setdefault(k, set()).add((i, j))
    return pres


def _bays_adjacent(present_k, i, j, dirn):
    n = 0
    if dirn == "X":
        for jj in (j - 1, j):
            if all(c in present_k for c in ((i, jj), (i + 1, jj), (i, jj + 1), (i + 1, jj + 1))): n += 1
    else:
        for ii in (i - 1, i):
            if all(c in present_k for c in ((ii, j), (ii + 1, j), (ii, j + 1), (ii + 1, j + 1))): n += 1
    return n


def _analysis_is_nmm(cfg) -> bool:
    try:
        from snl import india_units as U
        return U.analysis_unit_system(cfg) == "N-mm" or U.wants_native_nmm_analysis(cfg)
    except Exception:
        return False


def beam_udl(cfg, nm, pres, member, seg_index, nseg, fD, fL, fLr):
    """Distributed gravity on grid beam sub-elements (OpenSees beamUniform local).

    Legacy: kip/in (psf × inch tributary). Stage D / wave 5 N-mm: N/mm (kN/m² × mm).
    Portal frames delegate to portal_beam_udl (already dual-path).
    """
    from . import portal_adapter as PA
    if PA.is_portal(cfg):
        return PA.portal_beam_udl(cfg, nm, member, seg_index, nseg, fD, fL, fLr)
    i, j, k = decode_tag(member.n1)
    NF = len(cfg["heights"])
    if not (1 <= k <= NF):
        return 0.0
    roof = (k == NF)
    extra = cfg.get("extra_mass_floors", {})
    byD = cfg.get("D_by_level") or {}
    pD = (byD.get(k) if k in byD else (cfg["D_roof"] if roof else cfg["D_floor"])) + extra.get(k, 0.0)
    byL = cfg.get("L_by_level") or {}
    pL = 0.0 if roof else (byL.get(k) if k in byL else cfg["L_floor"])
    nmm = _analysis_is_nmm(cfg)
    # Default snow: 20 psf (kip path) or 1.0 kN/m² (SI)
    snow_default = 1.0 if nmm else 20.0
    pLr = (cfg.get("snow") if cfg.get("snow") is not None else snow_default) if roof else 0.0
    p = fD * pD + fL * pL + fLr * pLr
    nb = _bays_adjacent(pres.get(k, set()), i, j, member.dirn)
    SX, SY = cfg["SX"], cfg["SY"]
    other = SY if member.dirn == "X" else SX
    wcap = other / 2.0
    clad = cfg.get("clad", 0.0)
    x1, y1, _ = nm.nodes[member.n1]; x2, y2, _ = nm.nodes[member.n2]
    L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    s0 = L * seg_index / nseg; s1 = L * (seg_index + 1) / nseg; smid = 0.5 * (s0 + s1)
    width = min(smid, L - smid, wcap)

    if nmm:
        # Pressures kN/m²; lengths mm → return N/mm (== kN/m numerically).
        # If pressures look like psf (typical floor > ~5 kN/m² is rare; >20 almost certainly psf), convert.
        try:
            from snl.india_units import PSF_TO_KN_PER_M2
        except Exception:
            PSF_TO_KN_PER_M2 = 0.04788025898033585
        if max(abs(pD), abs(pL), abs(pLr), abs(float(clad or 0.0))) > 20:
            p *= PSF_TO_KN_PER_M2
            clad = float(clad or 0.0) * PSF_TO_KN_PER_M2
        th_m = float(cfg["heights"][k - 1]) / 1000.0
        th_m = th_m / 2.0 if roof else th_m
        wclad = fD * float(clad or 0.0) * th_m if (clad and nb == 1) else 0.0  # kN/m = N/mm
        return nb * p * (width / 1000.0) + wclad

    th = cfg["heights"][k - 1] / 12.0
    th = th / 2.0 if roof else th
    wclad = fD * clad * th / 12000.0 if (clad and nb == 1) else 0.0
    return nb * p * (width / 12.0) / 12000.0 + wclad


def combo_summary(c, cfg=None):
    label, fD, fL, fLr, lat, col_only = c
    d, s = lateral_direction(lat)
    V = sum(abs(v[0]) + abs(v[1]) for v in lat.values())
    out = dict(label=label, fD=fD, fL=fL, fLr=fLr, lateral_dir=d, sign=s,
               col_only=col_only, kind=("gravity" if d is None else ("wind" if "W" in label else "seismic")))
    if cfg is not None and _analysis_is_nmm(cfg):
        out["base_shear_N"] = round(V, 1)
    else:
        out["base_shear_kip"] = round(V, 1)
    return out
