"""
solver.py -- load-factor sweep to collapse (proportional loading), peak detection, mechanism data.

sweep(model, combo, pres, ...) applies the factored combination at lambda = 1, probes the elastic
response, picks the control DOF (largest displacement -- roof drift for lateral cases, a beam
mid-span or column shortening for gravity cases), then drives the structure with adaptive
DisplacementControl: Newton, then (NL-24) an algorithm ladder at the same step -- KrylovNewton, NewtonLineSearch,
ModifiedNewton(-initial) with up to 200 iterations, then relaxed tolerances 1e-5 / 1e-4 -- step halving on failure,
step growth on recovery; when the displacement step is exhausted near the limit, arc-length control
(MinUnbalDispNorm, -det) takes over. A numerical stop with the structure still stiff is SOLVER_FAILURE. lambda_u is the peak load factor; the run continues into the
post-peak branch (to `post_peak` * lambda_u) to characterise ductility for the phi_s classification.

Mechanism data recorded at the peak: per-integration-point yield ratio (max fibre strain / eps_y,
from the section deformation and the section extents), per-member "hinge" flags, brace buckling
flags (compression + lateral mid-point offset beyond L/200), storey drifts.
"""
import math, time
import openseespy.opensees as ops
from .loads import lateral_direction


LADDER = (("KrylovNewton", (), 1e-6, 40), ("NewtonLineSearch", ("-type", "Bisection"), 1e-6, 60),
          ("ModifiedNewton", ("-initial",), 1e-6, 200), ("KrylovNewton", (), 1e-5, 80),
          ("Newton", (), 1e-4, 100))


def _ladder():
    """NL-24: Newton failed -> KrylovNewton, NewtonLineSearch, ModifiedNewton (initial tangent), then the same with a
    relaxed displacement-increment tolerance (1e-5, 1e-4: mm on the India N-mm model), same step. Returns (ok, rung)."""
    ok = -1; used = None
    for alg, extra, tol, iters in LADDER:
        ops.algorithm(alg, *extra); ops.test("NormDispIncr", tol, iters, 0)
        ok = ops.analyze(1)
        if ok == 0:
            used = "%s@%g" % (alg, tol); break
    ops.algorithm("Newton"); ops.test("NormDispIncr", 1e-6, 25, 0)
    return ok, used


def _arc_integrator(dl):
    """Minimum unbalanced displacement norm control (arc-length family; the load increment changes sign at a limit point
    through the stiffness determinant), first increment `dl`, bounded to [dl/64, 2 dl]."""
    ops.integrator("MinUnbalDispNorm", dl, 1, dl / 64.0, 2.0 * dl, "-det")


def _arc_rescue(dl_ref):
    """NL-24: from the last converged state try arc-length control at dl_ref, /4, /16 (Newton, then the ladder).
    Returns (ok, dl)."""
    for dl in (dl_ref, dl_ref / 4.0, dl_ref / 16.0):
        _arc_integrator(dl)
        if ops.analyze(1) == 0:
            return 0, dl
        ok, _ = _ladder()
        if ok == 0:
            return 0, dl
    return -1, dl_ref / 16.0


def _solver_settings(tol=1e-6, iters=25):
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", tol, iters, 0); ops.algorithm("Newton")


def _extents(sp):
    """(ymax, zmax) of a section in its local axes for max-strain estimates."""
    if sp["kind"] == "col":                 # depth along y
        return sp.get("d", sp.get("H", 1.0)) / 2, sp.get("bf", sp.get("B", 1.0)) / 2
    if sp["kind"] == "beam":                # depth along z
        return sp.get("bf", sp.get("B", 1.0)) / 2, sp.get("d", sp.get("H", 1.0)) / 2
    return sp.get("H", 1.0) / 2, sp.get("B", 1.0) / 2


def yield_state(model, eps_y):
    """Per element: max yield ratio over its integration points; returns dict tag -> ratio."""
    out = {}
    nip = model.nip
    for e in model.elems:
        if not e.get("secTag"):
            continue
        sp = model.sec_props[e["secTag"]]
        ymax, zmax = _extents(sp)
        ey = (sp["Fy"] / model.builder.E) if sp.get("Fy") else eps_y
        r = 0.0
        for ip in range(1, nip + 1):
            try:
                d = ops.eleResponse(e["tag"], "section", ip, "deformation")
            except Exception:
                continue
            if len(d) >= 3:
                eps, kz, ky = d[0], d[1], d[2]
                em = abs(eps) + abs(kz) * ymax + abs(ky) * zmax
                r = max(r, em / ey)
        out[e["tag"]] = r
    return out


def brace_state(model):
    """Per brace member: axial force (kip, +tension) and lateral offset of the mid node (in)."""
    out = {}
    for mtag, chain in model.sub_nodes.items():
        m = model._bt[mtag]
        if m.kind != "brace":
            continue
        first = [e for e in model.elems if e["mtag"] == mtag][0]
        try:
            N = ops.eleResponse(first["tag"], "basicForce")[0]
        except Exception:
            N = 0.0
        mid = chain[len(chain) // 2]
        d = ops.nodeDisp(mid)
        a = ops.nodeDisp(chain[0]); b = ops.nodeDisp(chain[-1])
        off = math.sqrt(sum((d[i] - 0.5 * (a[i] + b[i])) ** 2 for i in range(3)))
        L = first["L"] * (len(chain) - 1)
        out[mtag] = dict(N=N, offset=off, L=L, buckled=(N < 0 and off > L / 200.0))
    return out


def member_state(model, ys):
    """Per member: (max yield ratio over its sub-elements, fraction along the member of the worst sub-element)."""
    out = {}
    for e in model.elems:
        if not e.get("secTag"):
            continue
        r = ys.get(e["tag"], 0.0)
        n = max(1, len(model.sub_nodes[e["mtag"]]) - 1)
        cur = out.get(e["mtag"])
        if cur is None or r > cur[0]:
            out[e["mtag"]] = (r, (e["s"] + 0.5) / n)
    return out



def _track_nodes(model):
    """Diaphragm masters, or portal eave/apex nodes when no diaphragms."""
    if model.masters:
        return list(model.masters)
    # portal: unique highest-z nodes per (rounded x,y) wall/roof line — keep eaves + apex
    by = {}
    for t, (x, y, z) in model.nm.nodes.items():
        if t in model.nm.fixes:
            continue
        key = (round(x, 0), round(y, 0))
        if key not in by or z > by[key][1]:
            by[key] = (t, z)
    nodes = [t for t, z in sorted(by.values(), key=lambda tz: tz[1])]
    return nodes[-8:] if len(nodes) > 8 else nodes  # cap for viewer

def _frame(model, eps_y, step, lam, d, ys=None, bs=None):
    """Viewer frame: masters, members at/over 0.5 eps_y with the worst sub-element location, buckled braces."""
    ys = ys if ys is not None else yield_state(model, eps_y)
    bs = bs if bs is not None else brace_state(model)
    return dict(step=step, lam=lam, d=d, disp={t: ops.nodeDisp(t) for t in _track_nodes(model)},
                mem={m: (r, f) for m, (r, f) in member_state(model, ys).items() if r >= 0.5},
                buckled=[t for t, b in bs.items() if b["buckled"]])


def storey_drifts(model, dirn):
    dof = 1 if dirn == "X" else 2
    ms = _track_nodes(model)
    disp = [ops.nodeDisp(t, dof) for t in ms]
    z = [model.nm.nodes[t][2] for t in ms]
    dr = []
    prev_d, prev_z = 0.0, 0.0
    for d, zz in zip(disp, z):
        dr.append((d - prev_d) / max(zz - prev_z, 1e-9)); prev_d, prev_z = d, zz
    return disp, dr


LIMIT_STATUSES = ("LIMIT_POINT", "PLASTIC_PLATEAU", "DUCTILITY_CAP")


SOLVER_FAILURE_TERMS = ("step_exhausted", "too_many_failures")
GENUINE_STOP_TANGENT = 0.10        # NL-24: a numerical stop with the tangent below 10 % of the elastic one is at a limit


def stop_tangent_ratio(hist, k_el, n=3):
    """Tangent stiffness (d lambda / |d u|) over the last `n` converged steps as a fraction of the elastic one; None when
    there are too few steps."""
    if len(hist) < n + 1 or not k_el:
        return None
    (l0, d0), (l1, d1) = hist[-n - 1], hist[-1]
    return (l1 - l0) / max(abs(d1 - d0), 1e-12) / k_el


def limit_status(hist, hi_at_max, lam_max, plateau=False, capped=False, termination=None, tangent_ratio=None):
    """(status, n_descending): LIMIT_POINT needs >= 2 converged steps after the peak with lambda below it and the last
    step below it (negative tangent); a sweep still rising when it stopped is NO_LIMIT_POINT (WP4.9 / NLEX-X-06).
    NL-24: a sweep stopped by the equilibrium iterations (step exhausted / too many failures, after the algorithm ladder,
    the tolerance fallback, every step cut and the arc-length rescue) is SOLVER_FAILURE -- a numerical stop, never a
    structural result -- unless the structure was at a genuine limit when it stopped: tangent stiffness below
    GENUINE_STOP_TANGENT x elastic (a developed mechanism / plateau the step rule had not yet confirmed), which stays
    NO_LIMIT_POINT (lambda_u not reported, lambda_end = the limit reached)."""
    after = [lm for lm, _ in hist[hi_at_max + 1:]] if hi_at_max else []
    n_desc = sum(1 for lm in after if lm < lam_max * (1 - 1e-4))
    if plateau:
        return "PLASTIC_PLATEAU", n_desc
    if n_desc >= 2 and after and after[-1] < lam_max:
        return "LIMIT_POINT", n_desc
    if capped:
        return "DUCTILITY_CAP", n_desc
    if termination in SOLVER_FAILURE_TERMS and not (tangent_ratio is not None and tangent_ratio < GENUINE_STOP_TANGENT):
        # NL-24: the equilibrium iterations failed while the structure still had stiffness -- a NUMERICAL stop, not a
        # structural limit: never reported as a capacity or as the structure "not reaching" a load; the gate blocks
        return "SOLVER_FAILURE", n_desc
    return "NO_LIMIT_POINT", n_desc


def sweep(model, combo, pres, dlam=0.02, max_steps=600, post_peak=0.85, disp_cap_factor=60.0,
          verbose=True, snapshot_every=3, time_limit=None, post_peak_steps=8, plateau_frac=0.02, frame_every=2,
          strain_cap=None, capture_lambda1=False):
    """... WP4.9: returns `status` in LIMIT_POINT (lambda fell over >= 2 converged steps after the peak: negative
    tangent), PLASTIC_PLATEAU (tangent < plateau_frac of elastic at the peak), DUCTILITY_CAP (max fibre strain reached
    `strain_cap` x eps_y -- lambda at the cap), or NO_LIMIT_POINT (time / step exhaustion / max steps / displacement
    cap with lambda still rising). lambda_u is None for NO_LIMIT_POINT (lambda_end holds the last peak)."""
    label, fD, fL, fLr, lat, col_only = combo
    fS = float((getattr(combo, "meta", None) or {}).get("fS") or 0.0)
    t0 = time.time()
    model.build().prepare()
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    W = model.apply_gravity(fD, fL, fLr, pres, fS=fS, meta=getattr(combo, "meta", None))
    model.apply_lateral(lat)
    _solver_settings()
    ldir, lsgn = lateral_direction(lat)
    eps_y = model.Fy / model.builder.E

    # ---- elastic probe (adaptive: soft systems may fail at 0.05) ------------------------------
    ops.analysis("Static")
    lam_probe = None
    for trial in (0.05, 0.02, 0.01, 0.005, 0.002):
        ops.integrator("LoadControl", trial)
        if ops.analyze(1) == 0:
            lam_probe = trial
            break
        # rewind failed attempt before retrying a smaller step
        model.build().prepare()
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        W = model.apply_gravity(fD, fL, fLr, pres, fS=fS, meta=getattr(combo, "meta", None))
        model.apply_lateral(lat)
        _solver_settings()
        ops.analysis("Static")
    if lam_probe is None:
        raise RuntimeError("elastic probe failed for %s" % label)
    if verbose and lam_probe < 0.05:
        print("   note %-40s elastic probe used lambda=%.3f (0.05 failed)" % (label[:40], lam_probe))
    if ldir:
        if model.masters:
            top = model.masters[-1]
        else:
            # portal / no diaphragm: control the highest free node
            tops = sorted(((z, t) for t, (x, y, z) in model.nm.nodes.items()
                           if t not in model.nm.fixes), reverse=True)
            top = tops[0][1] if tops else max(model.nm.nodes)
        cdof = 1 if ldir == "X" else 2
        cnode = top
    else:
        # gravity case: control the largest VERTICAL beam deflection (never a brace bow or a sway DOF)
        best, cnode, cdof = 0.0, None, 3
        for e in model.elems:
            if e["kind"] != "beam" or e["s"] != model.nsub_beam // 2:
                continue
            t = e["n1"]
            v = abs(ops.nodeDisp(t, 3))
            if v > best:
                best, cnode = v, t
    d_probe = ops.nodeDisp(cnode, cdof)
    if abs(d_probe) < 1e-12:
        raise RuntimeError("zero probe displacement -- control DOF not excited")
    du0 = d_probe / lam_probe * dlam
    du = du0
    d_cap = abs(d_probe / lam_probe) * disp_cap_factor
    ops.integrator("DisplacementControl", cnode, cdof, du)

    hist = [(lam_probe, d_probe)]
    lam_max, step_at_max, d_at_max = lam_probe, 0, d_probe; hi_at_max = 0
    first_yield = None
    snap = dict(yield_ratio={}, braces={}, drifts=None, disp=None, step=0)
    frames = []                                   # viewer frames every `frame_every` steps (+ the peak)
    disp_hist = {}                                # hist index -> master displacements (cheap; lets the peak frame be exact)
    fails = 0; consecutive_fail = 0; ladder_used = {}
    mode = "disp"; dl0 = dl = None                # NL-24: "arc" after the arc-length rescue
    log = []; plateau = False; term = "max_steps"; capped = False; forces_at_1 = None; prev_f = None
    for step in range(1, max_steps + 1):
        ok = ops.analyze(1)
        if ok != 0:
            consecutive_fail += 1; fails += 1
            # NL-24: algorithm ladder before any step cut (failed steps are where the time goes, and a premature
            # "step size exhausted" was reported as NO_LIMIT_POINT below lambda 1 on a girder that was only yielding)
            ok, used = _ladder()
            if ok == 0:
                ladder_used[used] = ladder_used.get(used, 0) + 1
            if ok != 0 and mode == "disp":
                du *= 0.5
                if abs(du) >= abs(du0) / 64:
                    ops.integrator("DisplacementControl", cnode, cdof, du)
                    log.append("step %d: halved step to %.3g" % (step, du))
                    if consecutive_fail > 12:
                        log.append("too many failures"); term = "too_many_failures"; break
                    continue
                # NL-24: displacement control exhausted near the limit -> arc-length rescue (the control DOF may not be
                # the one that governs: another member reaching its limit, or a snap-through the DOF cannot follow)
                dlast = abs(hist[-1][0] - hist[-2][0]) if len(hist) >= 2 else dlam
                ok, dl = _arc_rescue(max(dlast, dlam / 64.0))
                if ok != 0:
                    log.append("step %d: step size exhausted (displacement control, algorithm ladder and arc-length "
                               "rescue) -- stopping" % step); term = "step_exhausted"; break
                mode, dl0 = "arc", max(dlast, dlam / 64.0)
                ladder_used["MinUnbalDispNorm"] = ladder_used.get("MinUnbalDispNorm", 0) + 1
                log.append("step %d: displacement control exhausted -- switched to arc-length control "
                           "(MinUnbalDispNorm, dlambda %.3g)" % (step, dl))
            elif ok != 0:
                dl *= 0.5
                if dl < dl0 / 64:
                    log.append("step %d: arc-length step exhausted -- stopping" % step); term = "step_exhausted"; break
                _arc_integrator(dl)
                log.append("step %d: halved arc-length step to dlambda %.3g" % (step, dl))
                if consecutive_fail > 12:
                    log.append("too many failures"); term = "too_many_failures"; break
                continue
        if step_at_max and step - step_at_max > post_peak_steps:
            log.append("post-peak budget (%d steps) used at step %d" % (post_peak_steps, step)); term = "post_peak_budget"; break
        consecutive_fail = 0
        if mode == "disp" and abs(du) < abs(du0):
            du = min(abs(du) * 1.5, abs(du0)) * (1 if du0 > 0 else -1)
            ops.integrator("DisplacementControl", cnode, cdof, du)
        elif mode == "arc" and dl < dl0:
            dl = min(dl * 1.5, dl0)
            _arc_integrator(dl)
        lam = ops.getLoadFactor(1); d = ops.nodeDisp(cnode, cdof)
        hist.append((lam, d))
        hi = len(hist) - 1                        # index of this converged step in hist (failed steps are not counted)
        disp_hist[hi] = {t: ops.nodeDisp(t) for t in _track_nodes(model)}
        ys = None
        if (first_yield is None and step % 2 == 0) or hi % frame_every == 0 or (strain_cap and step % 2 == 0):
            ys = yield_state(model, eps_y)
            if first_yield is None and max(ys.values(), default=0.0) >= 1.0:
                first_yield = lam
        if capture_lambda1 and forces_at_1 is None and lam >= 0.85:
            # NL-25: the B-1.2 forces AT lambda = 1, interpolated between the converged steps either side (the first
            # step past 1 can be up to one load step -- 5 % -- beyond it: gym NPB700 1008 vs 996.6 kN-m at lambda 1)
            from .india_checks import member_forces, forces_at_lambda
            cur_f = member_forces(model)
            if lam >= 1.0:
                forces_at_1 = forces_at_lambda(prev_f, (lam, cur_f), 1.0)
            else:
                prev_f = (lam, cur_f)
        if hi % frame_every == 0:
            frames.append(_frame(model, eps_y, hi, lam, d, ys=ys))
        if lam > lam_max:
            lam_max, step_at_max, d_at_max = lam, step, d; hi_at_max = hi
            if step - snap["step"] >= snapshot_every:
                snap = dict(yield_ratio=(ys if ys is not None else yield_state(model, eps_y)), braces=brace_state(model),
                            drifts=(storey_drifts(model, ldir) if ldir else None), step=step, hist_i=hi,
                            disp={t: ops.nodeDisp(t) for t in _track_nodes(model)})
        elif lam < post_peak * lam_max and step > step_at_max + 3:
            log.append("post-peak branch reached %.0f%% of lambda_u at step %d" % (100 * post_peak, step)); term = "post_peak_drop"; break
        if abs(d) > d_cap:
            log.append("control displacement cap reached at step %d" % step); term = "disp_cap"; break
        if strain_cap and ys is not None and max(ys.values(), default=0.0) >= strain_cap:
            capped = True
            if snap["step"] < step:
                snap = dict(yield_ratio=ys, braces=brace_state(model), drifts=(storey_drifts(model, ldir) if ldir else None),
                            step=step, hist_i=hi, disp={t: ops.nodeDisp(t) for t in _track_nodes(model)})
            log.append("ductility cap: max fibre strain %.1f eps_y >= %.1f at step %d (lambda %.3f)" % (
                max(ys.values()), strain_cap, step, lam)); term = "ductility_cap"; break
        # plateau rule: tangent stiffness over the last 10 steps below `plateau_frac` of the elastic
        # stiffness -> a plastic plateau (mechanism / squash with hardening); lambda_u is taken here
        if len(hist) > 12 and lam >= lam_max - 1e-9:
            l0, d0 = hist[-11]
            k_el = 0.05 / abs(d_probe)
            k_t = (lam - l0) / max(abs(d - d0), 1e-12)
            if k_t < plateau_frac * k_el:
                plateau = True
                if snap["step"] < step - 1:
                    snap = dict(yield_ratio=yield_state(model, eps_y), braces=brace_state(model),
                                drifts=(storey_drifts(model, ldir) if ldir else None), step=step, hist_i=len(hist) - 1,
                                disp={t: ops.nodeDisp(t) for t in _track_nodes(model)})
                log.append("plateau: tangent stiffness %.1f%% of elastic at step %d -- lambda_u taken at the plateau" % (100 * k_t / k_el, step)); term = "plateau"; break
        if time_limit and time.time() - t0 > time_limit:
            log.append("time limit reached at step %d" % step); term = "time_limit"; break
        if verbose and step % 10 == 0:
            print("   %-38s step %4d  lambda %.3f  d %.3f  (%.0f s)" % (label[:38], step, lam, d, time.time() - t0), flush=True)
    # make sure lambda_u itself is a viewer frame: exact masters (recorded every step); member states from the closest
    # earlier record (a frame or the peak snapshot, at most frame_every-1 steps before the peak)
    if hi_at_max and all(f["step"] != hi_at_max for f in frames) and hi_at_max < len(hist):
        src = max([f for f in frames if f["step"] <= hi_at_max], key=lambda f: f["step"], default=None)
        hi_pk = snap.get("hist_i", -1)
        if hi_pk <= hi_at_max and (src is None or hi_pk >= src["step"]) and snap.get("disp"):
            mem = {m: (r, f) for m, (r, f) in member_state(model, snap["yield_ratio"]).items() if r >= 0.5}
            buck = [t for t, b in snap["braces"].items() if b["buckled"]]
        elif src is not None:
            mem, buck = src["mem"], src["buckled"]
        else:
            mem, buck = {}, []
        frames.append(dict(step=hi_at_max, lam=hist[hi_at_max][0], d=hist[hi_at_max][1], disp=disp_hist.get(hi_at_max, snap.get("disp") or {}),
                           mem=mem, buckled=buck))
        frames.sort(key=lambda f: f["step"])
    # post-peak ductility: lambda at 1.25 * d_at_max (if reached)
    lam_125 = None
    for lam, d in hist:
        if abs(d) >= 1.25 * abs(d_at_max):
            lam_125 = lam; break
    # ---- WP4.9 limit-point classification
    k_el = lam_probe / max(abs(d_probe), 1e-12)
    t_ratio = stop_tangent_ratio(hist, k_el)
    status, n_desc = limit_status(hist, hi_at_max, lam_max, plateau, capped, termination=term, tangent_ratio=t_ratio)
    tangent_at_end = None
    if len(hist) >= 3:
        (l1, d1), (l2, d2) = hist[-2], hist[-1]
        tangent_at_end = (l2 - l1) / (abs(d2 - d1) or 1e-12)
    lam_reported = lam_max if status in LIMIT_STATUSES else None
    return dict(label=label, lambda_u=lam_reported, lambda_end=lam_max, status=status, termination=term, ladder_used=ladder_used,
                control_mode=mode, stop_tangent_ratio=(round(t_ratio, 4) if t_ratio is not None else None),
                n_descending_steps=n_desc, tangent_at_end=tangent_at_end, forces_at_1=forces_at_1,
                step_at_max=step_at_max, d_at_max=d_at_max,
                first_yield=first_yield, lam_at_1p25d=lam_125, hist=hist, control=(cnode, cdof),
                lateral=(ldir, lsgn), gravity_kip=W, steps=len(hist), fails=fails, log=log, plateau=plateau,
                snapshot=snap, frames=frames, seconds=round(time.time() - t0, 1))


def classify(res, model):
    """Mechanism classification from the peak snapshot."""
    snap = res["snapshot"]
    yr = snap.get("yield_ratio", {})
    bt = model._bt
    hinges = {}         # mtag -> max ratio
    for e in model.elems:
        if not e.get("secTag"):
            continue
        r = yr.get(e["tag"], 0.0)
        hinges[e["mtag"]] = max(hinges.get(e["mtag"], 0.0), r)
    hinge_members = [t for t, r in hinges.items() if r >= 3.0]
    yielded_members = [t for t, r in hinges.items() if r >= 1.0]
    by_kind = {}
    for t in hinge_members:
        k = bt[t].role
        by_kind[k] = by_kind.get(k, 0) + 1
    buckled = [t for t, s in snap.get("braces", {}).items() if s.get("buckled")]
    ductile_post = res.get("plateau", False) or (res["lam_at_1p25d"] is not None and res["lam_at_1p25d"] >= 0.9 * res["lambda_u"])
    nbeam_h = by_kind.get("floor", 0) + by_kind.get("roof", 0) + by_kind.get("link", 0)
    if buckled and not nbeam_h:
        mech = "brace buckling (%d brace%s) governs the peak" % (len(buckled), "s" if len(buckled) > 1 else "")
        cls = "instability"
    elif buckled and nbeam_h:
        mech = "brace buckling (%d braces) with %d beam member%s at hinge level at the peak (proportional scaling also scales gravity)" % (
            len(buckled), nbeam_h, "s" if nbeam_h > 1 else "")
        cls = "instability"
    elif by_kind.get("lateral_col", 0) + by_kind.get("gravity_col", 0) > 0 and (by_kind.get("floor", 0) + by_kind.get("roof", 0) + by_kind.get("link", 0)) == 0:
        mech = "column yielding / inelastic instability (%d column member%s at hinge level)" % (
            by_kind.get("lateral_col", 0) + by_kind.get("gravity_col", 0), "s" if by_kind.get("lateral_col", 0) + by_kind.get("gravity_col", 0) > 1 else "")
        cls = "instability"
    elif (by_kind.get("floor", 0) + by_kind.get("roof", 0) + by_kind.get("link", 0)) >= 3 and ductile_post:
        mech = "beam plastic mechanism (%d beam members at hinge level)" % (by_kind.get("floor", 0) + by_kind.get("roof", 0) + by_kind.get("link", 0))
        cls = "ductile"
    elif (by_kind.get("floor", 0) + by_kind.get("roof", 0) + by_kind.get("link", 0)) >= 1:
        mech = "beam yielding (%d beam members at hinge level), limited post-peak ductility" % (by_kind.get("floor", 0) + by_kind.get("roof", 0) + by_kind.get("link", 0))
        cls = "ductile" if ductile_post else "limited-ductility"
    else:
        yr_roles = {}
        for t in yielded_members:
            k = bt[t].role
            yr_roles[k] = yr_roles.get(k, 0) + 1
        ncol = yr_roles.get("lateral_col", 0) + yr_roles.get("gravity_col", 0)
        secs = sorted({bt[t].section for t in yielded_members if bt[t].kind == "col"})
        if ncol and ncol >= 0.6 * max(len(yielded_members), 1):
            mech = "inelastic column instability -- %d column%s yielded at the peak (%s), no beam hinge" % (
                ncol, "s" if ncol > 1 else "", ", ".join(secs[:4]))
        elif yr_roles.get("brace", 0):
            mech = "brace yielding at the peak (%d braces), no beam hinge" % yr_roles["brace"]
        elif yielded_members:
            mech = "partial yielding (%s) without a developed hinge at the peak" % ", ".join("%d %s" % (n, k) for k, n in yr_roles.items())
        elif res.get("status") == "LIMIT_POINT":
            mech = "limit point while elastic (negative tangent): geometric instability"
        else:
            mech = "no yielding and no limit point (terminated: %s) -- not a capacity" % res.get("termination")
        cls = "instability"
    return dict(mechanism=mech, cls=cls, hinge_members=hinge_members, yielded_members=yielded_members,
                hinges_by_role=by_kind, buckled_braces=buckled, ductile_post_peak=ductile_post)
