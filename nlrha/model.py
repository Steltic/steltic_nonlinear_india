"""model.py -- the NLRHA model is the Pushover Analyst's hinge model (steltic_pushover.nonlinear_model) plus
Chapter 16 gravity (16.3.2), Rayleigh damping <= 2.5% (16.3.5) on the elastic elements + mass, and modal data
for the period range (16.2.3.1). Nothing is re-derived from the Steltic package here -- one model, three analyses.
"""
from __future__ import annotations
import math
import numpy as np
import openseespy.opensees as ops
from pushover import nonlinear_model as NM

G_IN = 386.4  # legacy kip-in; prefer g_accel(cfg) for Stage D N-mm (9810 mm/s²)


def _g_for_pkg(pkg):
    """Analysis g (in/s² or mm/s²) from package calc bridge / analysis units."""
    try:
        from snl import india_units as U
        cfg = pkg.calc if isinstance(getattr(pkg, "calc", None), dict) else {}
        return U.g_accel(cfg)
    except Exception:
        return G_IN


def ch16_gravity(pkg, ch16, live_psf=None, roof_live_psf=20.0):
    """16.3.2: 1.0 D + 0.5 L, L = 40% of unreduced live (<= 100 psf) / 80% (> 100 psf). D from the recorded seismic
    mass (D + cladding). Spread equally over each level's column nodes (same idealisation as the pushover tool).

    Wave 5 / Stage D: when ANALYSIS_UNITS is N-mm, mass×g uses g=9810 and forces are N.
    Live idealisation remains ASCE 7 §16.3.2 psf-threshold rooted — IS suite found:false
    (snl.india_units.ch16_live_si_status). Do not invent IS 1893 Ch.16 live factors.
    """
    g = ch16["gravity"]
    lv = NM.levels(pkg)
    Lpsf = live_psf if live_psf is not None else (pkg.basis.L_floor_psf or 50.0)
    loads, table, sumD, sumL = {}, [], 0.0, 0.0
    G = _g_for_pkg(pkg)
    for k, z, master, slaves in lv:
        WD = pkg.model.masses.get(master, [0] * 6)[0] * G
        xs = [pkg.model.nodes[n][0] for n in slaves]; ys = [pkg.model.nodes[n][1] for n in slaves]
        span_x = (max(xs) - min(xs)); span_y = (max(ys) - min(ys))
        if abs(G - G_IN) < 1.0:  # kip-in
            area = span_x * span_y / 144.0  # ft²
            L0 = roof_live_psf if k == len(lv) else Lpsf
            f = g["live_factor_gt100psf"] if L0 > 100 else g["live_factor_le100psf"]
            Lexp = g["combination_factor"] * f * L0 * area / 1000.0
            force_key = "kip"
        else:
            # N-mm: area mm² → m²; live as kN/m² if cfg provides L_floor_kNm2 else convert psf
            area_m2 = span_x * span_y / 1.0e6
            try:
                from snl.india_units import PSF_TO_KN_PER_M2, KN_TO_N
                L0_psf = roof_live_psf if k == len(lv) else Lpsf
                L0 = L0_psf * PSF_TO_KN_PER_M2  # kN/m²
            except Exception:
                L0 = (roof_live_psf if k == len(lv) else Lpsf) * 0.04788
            f = g["live_factor_gt100psf"] if Lpsf > 100 else g["live_factor_le100psf"]
            Lexp = g["combination_factor"] * f * L0 * area_m2 * 1000.0  # kN → N
            force_key = "N"
        QG = WD + Lexp
        sumD += WD; sumL += Lexp
        for n in slaves:
            loads[n] = loads.get(n, 0.0) - QG / len(slaves)
        row = dict(level=k, z=z, nodes=len(slaves))
        if force_key == "kip":
            row.update(z_in=z, D_kip=round(WD, 1), Lexp_kip=round(Lexp, 1), QG_kip=round(QG, 1))
        else:
            row.update(z_mm=z, D_N=round(WD, 1), Lexp_N=round(Lexp, 1), QG_N=round(QG, 1))
        table.append(row)
    no_live_case_needed = not (sumL <= g["exception_live_over_dead"] * sumD and Lpsf < 100)
    return loads, table, dict(sum_D=sumD, sum_Lexp=sumL, ratio=sumL / sumD, no_live_case_needed=no_live_case_needed)


def build(pkg, prm, ch16, PG, member_nseg=None, plasticity=None):
    """Nonlinear model (same builder as the pushover) -> hinges registry + element lists for damping.

    Product default for NLRHA CLI is ModIMK (imk); fibre via ladder climb / --plasticity fibre.
    Override via args / SNL_* env / numerics.plasticity.
    """
    import os
    if member_nseg is not None:
        os.environ["SNL_MEMBER_NSEG"] = str(member_nseg)
    if plasticity is not None:
        os.environ["SNL_PLASTICITY"] = str(plasticity)
    hinges, stats = NM.build_nonlinear(pkg, prm, PG, verbose=True,
                                       member_nseg=member_nseg, plasticity=plasticity)
    # Fibre: all forceBeamColumn tags for Rayleigh region. IMK: elastic_ele_tags (RBS extras) or pack tags.
    if stats.get("plasticity") == "fibre" and stats.get("fibre_eles"):
        elastic_eles = list(stats["fibre_eles"])
    elif stats.get("elastic_ele_tags"):
        elastic_eles = list(stats["elastic_ele_tags"])
    else:
        elastic_eles = [e["tag"] for e in pkg.model.elements if "etype" not in e and NM.member_kind(pkg, e) in ("col", "beam")]
        nseg = max(1, int(stats.get("member_nseg") or os.environ.get("SNL_MEMBER_NSEG") or 1))
        if nseg > 1:
            from pushover.nonlinear_model import SEG_ELE_BASE
            for e in pkg.model.elements:
                if "etype" in e or NM.member_kind(pkg, e) not in ("col", "beam"):
                    continue
                for si in range(1, nseg):
                    elastic_eles.append(SEG_ELE_BASE + e["tag"] * 100 + si)
    return hinges, stats, elastic_eles


def _participation(pkg, nmodes):
    """Eigen solve + effective modal mass fractions using the FULL nodal mass vector (all nodes, all DOFs), so that
    each fraction is <= 1 and the sum over a complete basis is 1 (WP4.12: fixes local modes reporting 100 %)."""
    ops.wipeAnalysis()
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    w2 = ops.eigen("-genBandArpack", nmodes)
    lv = NM.levels(pkg)
    tags = ops.getNodeTags()
    mass = {t: ops.nodeMass(t) for t in tags}
    mass = {t: m for t, m in mass.items() if any(abs(v) > 0 for v in m)}
    Mx = sum(m[0] for m in mass.values()); My = sum(m[1] for m in mass.values())
    Jz = sum(m[5] for m in mass.values())
    modes = []
    for i, w in enumerate(w2):
        T = 2 * math.pi / math.sqrt(max(w, 1e-12))
        Mn = Lx = Ly = Lr = 0.0
        for t, m in mass.items():
            v = ops.nodeEigenvector(t, i + 1)
            Mn += sum(m[j] * v[j] * v[j] for j in range(6))
            Lx += m[0] * v[0]; Ly += m[1] * v[1]; Lr += m[5] * v[5]
        fx = (Lx * Lx / Mn / Mx) if Mn > 0 and Mx > 0 else 0.0
        fy = (Ly * Ly / Mn / My) if Mn > 0 and My > 0 else 0.0
        fr = (Lr * Lr / Mn / Jz) if Mn > 0 and Jz > 0 else 0.0
        modes.append(dict(mode=i + 1, T=T, fx=fx, fy=fy, frz=fr))
    return modes


def modal(pkg, nmodes=12, target=0.90, max_modes=60):
    """Periods + effective modal mass fractions in X, Y (and torsion). Solves more modes until the cumulative mass
    reaches `target` in both directions (IS 1893 7.7.5.2 90 % rule; WP4.12), and flags spurious modes
    (T > 5 x the fundamental with < 1 % mass in every direction)."""
    n = int(nmodes)
    while True:
        modes = _participation(pkg, n)
        cx = sum(m["fx"] for m in modes); cy = sum(m["fy"] for m in modes)
        if (cx >= target and cy >= target) or n >= max_modes:
            break
        n = min(max_modes, n * 2)
    T1x = max(modes, key=lambda m: m["fx"])["T"]; T1y = max(modes, key=lambda m: m["fy"])["T"]
    Tf = max(T1x, T1y)
    spurious = [m for m in modes if m["T"] > 5.0 * Tf and max(m["fx"], m["fy"], m["frz"]) < 0.01]
    cx = cy = 0.0; T90 = None
    for m in modes:                                 # cumulative mass, both directions -> the period at which both reach 90%
        cx += m["fx"]; cy += m["fy"]
        if T90 is None and cx >= target and cy >= target:
            T90 = m["T"]
    tors = max(modes, key=lambda m: m["frz"]) if modes else None
    return dict(modes=modes, T1x=T1x, T1y=T1y, T90=T90, cum_x=cx, cum_y=cy, n_modes=len(modes),
                T_torsion=(tors["T"] if tors else None), spurious_modes=[m["mode"] for m in spurious],
                spurious_ok=not spurious, participation_sum_ok=bool(cx <= 1.0 + 1e-6 and cy <= 1.0 + 1e-6),
                basis="full nodal mass vector; spurious = T > 5 x T1 with < 1 % mass")


def set_damping(xi, T1, elastic_eles, T_upper_ratio=0.2):
    """Rayleigh damping xi at T1 and at 0.2 T1; mass-proportional on all nodes, initial-stiffness-proportional only
    on the elastic beam-column elements (the rigid hinge springs would otherwise attract spurious damping forces)."""
    w1 = 2 * math.pi / T1; w2 = 2 * math.pi / (T_upper_ratio * T1)
    a0 = xi * 2 * w1 * w2 / (w1 + w2); a1 = xi * 2 / (w1 + w2)
    ops.rayleigh(a0, 0.0, 0.0, 0.0)                              # mass-proportional, whole model
    ops.region(99, "-ele", *elastic_eles, "-rayleigh", 0.0, 0.0, a1, 0.0)   # K_init-proportional, elastic elements only
    return dict(xi=xi, a0=a0, a1=a1, T1=T1, T2=T_upper_ratio * T1)
