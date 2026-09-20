"""fibre_model.py -- distributed-plasticity forceBeamColumn + fibre sections for NSP/NLRHA.

Ported from the MC4 fibre mesh-probe fork (proven L1 recipe: nseg=4, nip=5, nf_flange=8,4 / nf_web=16,2).
Braces remain nonlinear corotTruss. Panel zones are rigid on this path (scissors dropped — disclosed).
RBS remesh is N/A (distributed fibre along the full W-shape).

Env knobs (also accepted as kwargs from build_nonlinear):
  SNL_MEMBER_NSEG, SNL_FIBRE_NIP, SNL_FIBRE_NF_FLANGE, SNL_FIBRE_NF_WEB, SNL_FIBRE_RESIDUAL
"""
from __future__ import annotations
import math
import openseespy.opensees as ops
from . import hinge_models as HM
from .nonlinear_model import (
    E_KSI_AL, MAT_BASE, RIGID_T, RIGID_R,
    member_kind, strong_I_slot, strong_rot_dof, _dir_vec, brace_india,
)

SEG_NODE_BASE = 70_000_000
SEG_ELE_BASE = 80_000_000
FIB_SEC_BASE = 90_000_000
FIB_PIN_NODE = 92_000_000
FIB_PIN_ELE = 93_000_000


def build_fibre(pkg, prm, PG, verbose=True, nseg=4, nip=5, nf_flange=(8, 4), nf_web=(16, 2), residual="none"):
    """Distributed-plasticity NLRHA probe: forceBeamColumn + fibre W/HSS sections; no IMK end springs.

    Braces remain nonlinear corotTruss (same as IMK path). Released major-axis beam/col ends use
    rigid zeroLength pins (GMNIA-style). Plasticity is along the member via fibres + Lobatto IP.
    """
    from steltic_ddm.sections_fiber import FiberSectionBuilder
    m = pkg.model
    ops.wipe(); ops.model("basic", "-ndm", m.ndm, "-ndf", m.ndf)
    for t, xyz in m.nodes.items():
        ops.node(t, *xyz)
    for t, fl in m.fixes.items():
        ops.fix(t, *fl)
    tiny = 1e-8 * min(v[0] for v in m.masses.values())
    for t in m.nodes:
        ops.mass(t, *([tiny] * 6))
    for t, mv in m.masses.items():
        ops.mass(t, *[mv[i] + tiny for i in range(6)])
    for t, (ty, vx, vy, vz) in m.transfs.items():
        ops.geomTransf(ty, t, vx, vy, vz)
    for t, a in m.materials.items():
        if t not in (1, 2):
            ops.uniaxialMaterial(*a)
    ops.uniaxialMaterial("Elastic", 1, RIGID_T)
    ops.uniaxialMaterial("Elastic", 2, RIGID_R)
    mt = (prm.get("material") or {})
    # Stage C: analysis units from package calc / prm → SI fibre E/Fy/areas when N-mm
    cfg_u = {}
    if isinstance(getattr(pkg, "calc", None), dict):
        cfg_u.update(pkg.calc)
    if isinstance(prm, dict):
        cfg_u.update({k: prm[k] for k in ("units", "_nl_analysis_units", "analysis_units",
                                          "analysis_si", "native_nmm", "force_kip_in") if k in prm})
    try:
        from snl import india_units as U
        anal = U.analysis_unit_system(cfg_u) if cfg_u else U.ANALYSIS_UNITS
        if anal == "N-mm" or U.wants_native_nmm_analysis(cfg_u):
            units = "N-mm"
            Fy = float(mt.get("Fy_MPa", mt.get("Fy", U.steel_Fy_default(cfg_u))))
            Fy *= float(mt.get("Ry_expected", 1.0))
            E = float(mt.get("E_MPa", U.steel_E({"_nl_analysis_units": "N-mm"})))
        else:
            units = "kip-in"
            Fy = float(mt.get("Fy_ksi", 50.0)) * float(mt.get("Ry_expected", 1.0))
            E = None
    except Exception:
        units = "kip-in"
        Fy = float(mt.get("Fy_ksi", 50.0)) * float(mt.get("Ry_expected", 1.0))
        E = None
    india = getattr(pkg.basis, "jurisdiction", None) == "india"
    if india:
        units = "kip-in"      # Stage B is forced for India (WP4.7); fy comes per section from IS 2062 (WP4.5)
        E = None
    builder = FiberSectionBuilder(ops, Fy=Fy, E=E, hardening=0.01, residual=residual,
                                  elastic=False, mat_tag0=1000, units=units)
    builders = {}           # India: one builder per distinct fye (distinct material tags)

    def _builder_for(sec, kind):
        if not india:
            return builder
        from . import india_model as IMD
        from snl.india_units import MPA_TO_KSI
        f = IMD.fy_section(pkg, sec, kind)
        fk = round(f["fye_MPa"] * MPA_TO_KSI, 6)
        if fk not in builders:
            builders[fk] = FiberSectionBuilder(ops, Fy=fk, E=None, hardening=0.01, residual=residual, elastic=False,
                                               mat_tag0=100000 + 1000 * len(builders), units="kip-in")
        return builders[fk]
    # denser fibre grid than default GMNIA (8,2)/(12,1) — probe "finer mesh for plasticity"
    builder_nf = dict(nf_flange=nf_flange, nf_web=nf_web)
    hinges = {}
    mat = MAT_BASE
    stats = dict(col=0, beam=0, brace=0, brace_nonlinear=0, force_controlled=0, released_ends=0,
                 panel_zones=0, panel_zone_mode="rigid", plasticity="fibre", member_nseg=nseg,
                 fibre_eles=[], fibre_secs=0, fibre_units=units)
    sec_cache = {}  # (section, kind) -> secTag
    cover = stats.setdefault("_dof_cover", {})

    def _cov(n, dofs):
        cover.setdefault(n, set()).update(dofs)
    nseg = max(1, int(nseg))
    pin_count = 0

    def _fibre_sec(sec, kind):
        key = (str(sec).upper(), kind)
        if key in sec_cache:
            return sec_cache[key]
        tag = FIB_SEC_BASE + len(sec_cache) + 1
        axis = "y" if kind == "col" else "z"
        lab = str(sec)
        bld = _builder_for(sec, kind)
        from . import india_materials as IMAT
        try:
            if IMAT.is_tube(lab):
                typ = str((IMAT.section_props_mm(lab) if india else {}).get("type") or "").upper()
                if typ == "CHS" or lab.upper().startswith("CHS"):
                    bld.hss_round(tag, lab, residual=residual)
                else:
                    bld.hss_rect(tag, lab, t_design_factor=(1.0 if india else 0.93),
                                 n_per_side=max(8, nf_web[0] // 2), n_thick=2, residual=residual)
            else:
                bld.w_shape(tag, lab, axis=axis, nf_flange=nf_flange, nf_web=nf_web, residual=residual)
        except Exception as ex:
            # fallback elastic properties from element if shape missing
            raise RuntimeError("fibre section %s (%s): %s" % (lab, kind, ex))
        ops.beamIntegration("Lobatto", tag, tag, nip)
        sec_cache[key] = tag
        stats["fibre_secs"] += 1
        return tag

    def _pin(grid, dup, released_dofs):
        nonlocal pin_count
        pin_count += 1
        dirs = [d for d in range(1, 7) if d not in released_dofs]
        mats = [1 if d <= 3 else 2 for d in dirs]
        zl = FIB_PIN_ELE + pin_count
        ops.element("zeroLength", zl, grid, dup, "-mat", *mats, "-dir", *dirs)
        _cov(grid, dirs); _cov(dup, dirs)
        return zl

    for e in m.elements:
        if "etype" in e:
            kind = member_kind(pkg, e); sec = pkg.schedule.get(e["tag"], {}).get("section")
            if e["etype"] in ("Truss", "truss", "corotTruss") and kind == "brace" and sec and str(sec).upper() != "GHOST":
                p1, p2 = m.nodes[e["n1"]], m.nodes[e["n2"]]; _, L = _dir_vec(p1, p2)
                spec = HM.brace_spec(sec, L, prm, india=brace_india(pkg, sec))
                mat += 1; HM.make_brace_material(mat, spec, prm)
                ops.element("corotTruss", e["tag"], e["n1"], e["n2"], spec.A, mat)
                _cov(e["n1"], (1, 2, 3)); _cov(e["n2"], (1, 2, 3))
                hinges[e["tag"]] = dict(ele=e["tag"], end=0, kind="brace", section=sec, dof=0, K0=E_KSI_AL(spec), mat=mat,
                                        node=e["n1"], z=max(p1[2], p2[2]), spec=spec)
                stats["brace_nonlinear"] += 1
            else:
                ops.element(*e["raw"])
                rawt = str(e["etype"]).lower()
                d_ = (1, 2, 3) if "truss" in rawt else (1, 2, 3, 4, 5, 6)
                _cov(e["n1"], d_); _cov(e["n2"], d_)
            stats["brace"] += 1; continue
        kind = member_kind(pkg, e)
        sec = pkg.schedule.get(e["tag"], {}).get("section")
        p1, p2 = m.nodes[e["n1"]], m.nodes[e["n2"]]
        d, L = _dir_vec(p1, p2)
        if kind == "brace" and sec:
            spec = HM.brace_spec(sec, L, prm, india=brace_india(pkg, sec))
            mat += 1; HM.make_brace_material(mat, spec, prm)
            ops.element("corotTruss", e["tag"], e["n1"], e["n2"], spec.A, mat)
            _cov(e["n1"], (1, 2, 3)); _cov(e["n2"], (1, 2, 3))
            hinges[e["tag"]] = dict(ele=e["tag"], end=0, kind="brace", section=sec, dof=0, K0=E_KSI_AL(spec), mat=mat,
                                    node=e["n1"], z=max(p1[2], p2[2]), spec=spec)
            stats["brace"] += 1; stats["brace_nonlinear"] += 1
            continue
        if sec is None or kind not in ("col", "beam"):
            args = [e["A"], e["E"], e["G"], e["J"], e["Iy"], e["Iz"], e["transf"]] + (e["release"] or [])
            ops.element("elasticBeamColumn", e["tag"], e["n1"], e["n2"], *args); stats["brace"] += 1
            _cov(e["n1"], range(1, 7)); _cov(e["n2"], range(1, 7))
            continue
        slot = strong_I_slot(pkg, e, kind)
        rel = e["release"] or []
        flag = "-releasey" if slot == "Iy" else "-releasez"
        relz = int(rel[rel.index(flag) + 1]) if flag in rel else 0
        # force-controlled columns: still fibre (distributed) but note them
        if HM.column_hinge(sec, L, PG.get(e["tag"], 0.0), prm).force_controlled if kind == "col" else False:
            stats["force_controlled"] += 1
        end1, end2 = e["n1"], e["n2"]
        # major-axis releases -> pin (no rotational continuity); unreleased -> continuous fibre
        if relz in (1, 3):
            end1 = FIB_PIN_NODE + e["tag"] * 10 + 1; ops.node(end1, *p1); ops.mass(end1, *([tiny] * 6))
            dof = strong_rot_dof(pkg, e, kind); _pin(e["n1"], end1, {dof}); stats["released_ends"] += 1
        if relz in (2, 3):
            end2 = FIB_PIN_NODE + e["tag"] * 10 + 2; ops.node(end2, *p2); ops.mass(end2, *([tiny] * 6))
            dof = strong_rot_dof(pkg, e, kind); _pin(e["n2"], end2, {dof}); stats["released_ends"] += 1
        secTag = _fibre_sec(sec, kind)
        chain = [end1]
        for si in range(1, nseg):
            f = si / float(nseg)
            xyz = [p1[k] + (p2[k] - p1[k]) * f for k in range(3)]
            mid = SEG_NODE_BASE + e["tag"] * 100 + si
            ops.node(mid, *xyz); ops.mass(mid, *([tiny] * 6))
            chain.append(mid)
        chain.append(end2)
        for si in range(nseg):
            etag = e["tag"] if si == 0 else (SEG_ELE_BASE + e["tag"] * 100 + si)
            ops.element("forceBeamColumn", etag, chain[si], chain[si + 1], e["transf"], secTag, "-iter", 20, 1e-8)
            _cov(chain[si], range(1, 7)); _cov(chain[si + 1], range(1, 7))
            stats["fibre_eles"].append(etag)
        stats[kind] += 1
    stats["panel_zone_registry"] = {}
    for perp, master, slaves in m.diaphragms:
        ops.rigidDiaphragm(perp, master, *slaves)
        for n in slaves:
            _cov(n, (1, 2, 6))
        _cov(master, (1, 2, 6))
    stats["fibre_fy_ksi"] = sorted(builders) if india else [Fy]
    stats["fibre_units"] = units
    if india:
        from . import india_model as IMD
        stats["material_india"] = IMD.material_report(pkg)
    # WP4.12: restrain DOFs that no element stiffens (released/pinned framing, truss-only nodes)
    stats["restrained_zero_stiffness_dofs"] = restrain_zero_stiffness_dofs(pkg, stats.get("_dof_cover", {}))
    stats.pop("_dof_cover", None)
    if verbose:
        allb = [builder] + list(builders.values())
        nfib = sum(x[3] for b in allb for x in (b.log or []))
        print("[nonlinear_model] FIBRE plasticity: cols %d beams %d braces %d (nl %d) nseg=%d nip=%d secs=%d fibres~%d released_ends=%d"
              % (stats["col"], stats["beam"], stats["brace"], stats["brace_nonlinear"], nseg, nip,
                 stats["fibre_secs"], nfib, stats["released_ends"]))
    return hinges, stats




def restrain_zero_stiffness_dofs(pkg, cover: dict) -> dict:
    """WP4.12 model hygiene: fix ROTATIONAL DOFs that no element stiffens (e.g. a node where every framing member is
    pinned about that axis, or a truss-only node). Those DOFs carry only the 1e-8 'tiny' mass and produce the
    spurious 10-500 s modes. Unstiffened TRANSLATIONAL DOFs indicate a mechanism: they are reported, not hidden."""
    fixed = {t: list(fl) for t, fl in pkg.model.fixes.items()}
    rot_fixed, trans_free = [], []
    for n in ops.getNodeTags():
        cov = cover.get(n)
        if cov is None:
            continue
        fl = fixed.get(n, [0] * 6)
        add = [0] * 6
        for d in (4, 5, 6):
            if d not in cov and not fl[d - 1]:
                add[d - 1] = 1
        for d in (1, 2, 3):
            if d not in cov and not fl[d - 1]:
                trans_free.append((n, d))
        if any(add):
            ops.fix(n, *add)
            rot_fixed.append((n, [i + 1 for i, v in enumerate(add) if v]))
    return dict(n_rotational_fixed=len(rot_fixed), rotational_fixed=rot_fixed[:50],
                n_translational_unstiffened=len(trans_free), translational_unstiffened=trans_free[:50])
