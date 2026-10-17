"""imposed_reduction.py -- NL-37: the IS 875 (Part 2) 3.2.1 column imposed-load reduction in the DDM B-1.2 check,
applied exactly as the HR design applies it.

What the HR design does (steltic_india steel_engine/static_model.py, `column_imposed_load_reduction_factors` and the
member-record loop of the combination analysis, ~line 1765): with cfg['column_imposed_load_reduction'] set, a column
between levels k-1 and k carries the floors k .. NF (the roof counts as a floor) and its AXIAL FORCE RECORD ONLY is
reduced after the analysis,

    N = N_full - r x N_LL,     r = 0 / 0.10 / 0.20 / 0.30 / 0.40 / 0.50 for 1 / 2 / 3 / 4 / 5-10 / over 10 floors

N_LL being the column's axial force under the floor imposed load alone (no partitions, cladding, self-weight or roof
imposed load) at the combination's imposed-load factor. The analysis itself, the beams and the braces keep the full
imposed load. The reduction is never applied in a combination with earthquake (IS 875 (Part 5) 8.1; the HR tests
Case.meta kind 'EQ' and the column-only / capacity tags). r per column is recorded from the HR engine by
snl.hr_gravity (column_imposed_load_reduction).

Before NL-37 the DDM B-1.2 check compared the UNREDUCED GMNIA column force with a design that used the reduced one
(IN_Ex19 BOX400X400X28 gravity column under 1.5DL+1.5LL: N = 9 193 kN, D/C 1.035, while the HR design's governing
ratio is 0.904 from an earthquake combination). Only the gravity-transfer gate added the reduction back.

The DDM now does what the HR does: the GMNIA sweep carries the full imposed load (so lambda_u is the collapse factor
of the UNREDUCED load -- conservative), and the IS 800 Annex B-1.2 check at lambda = 1 reduces each column's axial
force by r x fL x N_LL in every combination without earthquake. N_LL comes from the GMNIA topology itself: one
linear-elastic analysis of the HR 'Lfloor' load state (snl.hr_gravity), N at the column top as the HR engine records it.

Why not a load: a self-equilibrated axial force pair on each column (tried first) also changes the beam moments of a
tall frame by up to 20 % (IN_Ex19 1.5DL+1.5LL floor WPB550 0.81 of the HR moment against 1.00 before): the columns
then shorten less, and the differential shortening bends the rigid beams. The HR reduction is a force-record
reduction, not a load, and is reproduced as one.
"""
from __future__ import annotations

import openseespy.opensees as ops

CITE = ("IS 875 (Part 2):1987 3.2.1 reduction of the floor imposed load carried by a column (1 floor 0 %, 2 10 %, 3 20 %, "
        "4 30 %, 5-10 40 %, over 10 50 %), applied as the HR design applies it (steltic_india static_model: column axial "
        "record N - r x N_imposed; beams and the analysis unreduced); never with earthquake -- IS 875 (Part 5) 8.1")
EQ_TAGS = {"col_only", "is800_12_2_3", "is18168_5_5"}


def is_eq_case(meta) -> bool:
    """The HR engine's test (static_model `_eq_case`): Case.meta kind / lateral_kind 'EQ', or a column-only / capacity
    tag. IS 875 (Part 5) 8.1: no reduced imposed load in combination with earthquake forces."""
    m = meta or {}
    return (str(m.get("kind") or m.get("lateral_kind") or "").upper() == "EQ"
            or bool(EQ_TAGS & set(m.get("tags") or [])))


def applies(fL, meta) -> bool:
    return bool(fL) and not is_eq_case(meta)


def factors(hr) -> dict:
    """{column member tag: r > 0} recorded from the HR engine (snl.hr_gravity column_imposed_load_reduction)."""
    out = {}
    for k, v in ((hr or {}).get("column_imposed_load_reduction") or {}).items():
        try:
            r = float(v)
        except (TypeError, ValueError):
            continue
        if r > 0:
            out[int(k)] = r
    return out


def build_plan(nm, cfg, nsub=(2, 2, 4), rigid_end_offset=False) -> dict | None:
    """{columns: {mtag: dict(r, N_LL_N)}, ...} or None when the HR design applies no reduction (cfg
    column_imposed_load_reduction unset, or no HR gravity record). One linear-elastic analysis (P-Delta topology, as
    the gravity-transfer gate) of the HR 'Lfloor' state at factor 1."""
    from .model_gmnia import GMNIAModel
    try:
        from snl import hr_gravity as HG
        hr = HG.ensure(nm.job_dir)
    except Exception:                                          # noqa: BLE001
        hr = None
    r_by = factors(hr)
    if not r_by or not (hr.get("states") or {}).get("Lfloor"):
        return None
    g = GMNIAModel(nm, cfg, nsub=nsub, elastic=True, residual="none", out_of_plumb=(None, 0.0), bow=0.0, brace_bow=0.0,
                   rigid_end_offset=rigid_end_offset, transf_type="PDelta")
    g.build().prepare()
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    chains = {}
    for e in g.elems:
        sp, Lm = e.get("span"), e.get("Lm") or e.get("L")
        if sp and Lm:
            chains.setdefault(int(e["mtag"]), []).append((e["tag"], sp[0] / Lm, sp[1] / Lm))
    HG.apply(ops, HG.combine(hr, {"Lfloor": 1.0}), chains)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-8, 50, 0); ops.algorithm("Newton")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static")
    if ops.analyze(1) != 0:
        ops.wipe()
        print("[ddm] NL-37: the floor-imposed-only analysis failed -- no IS 875-2 3.2.1 reduction in B-1.2", flush=True)
        return dict(columns={}, error="floor-imposed-only analysis failed", cite=CITE)
    from .india_checks import member_forces
    mf = member_forces(g)
    ops.wipe()
    cols = {}
    for m in nm.members:
        t = int(m.tag)
        if m.kind != "col" or t not in r_by or t not in mf:
            continue
        N = float(mf[t].get("N_top") or 0.0)                       # compression +, N (the HR engine's N_LL)
        if N > 0:
            cols[t] = dict(r=r_by[t], N_LL_N=N)
    rs = sorted({c["r"] for c in cols.values()})
    return dict(columns=cols, cite=CITE, n_columns=len(cols), r_values=rs,
                basis=("IS 875-2 3.2.1 column imposed-load reduction as the HR design: r from the HR engine "
                       "(snl.hr_gravity column_imposed_load_reduction, %d columns, r %s); N_LL = column top axial force "
                       "under the HR floor imposed load alone (state 'Lfloor') on this model; the B-1.2 column axial force "
                       "at lambda = 1 is N - r x fL x N_LL in every combination without earthquake (IS 875-5 8.1); the "
                       "GMNIA sweep, beams and braces carry the full imposed load" % (len(cols), ", ".join("%.1f" % r for r in rs))))


def reduce_forces(forces, plan, fL, meta) -> dict:
    """The B-1.2 forces at lambda = 1 with each reduced column's compression lowered by r x fL x N_LL (a copy; the
    member dicts of reduced columns gain N_reduction_N). Unchanged when the reduction does not apply."""
    if not forces or not plan or not plan.get("columns") or not applies(fL, meta):
        return forces
    cols = {int(k): v for k, v in plan["columns"].items()}
    out = {}
    for tag, f in forces.items():
        c = cols.get(int(tag)) if not str(tag).startswith("_") else None
        if c is None or f.get("kind") != "col" or float(f.get("N_comp") or 0.0) <= 0.0:
            out[tag] = f
            continue
        R = float(fL) * c["r"] * c["N_LL_N"]
        g = dict(f)
        g["N_comp"] = max(float(f["N_comp"]) - R, 0.0)
        if float(f.get("N_abs") or 0.0) <= float(f["N_comp"]) + 1e-6:      # compression governs |N|
            g["N_abs"] = max(float(f["N_abs"]) - R, g["N_comp"])
        if f.get("N_top") is not None:
            g["N_top"] = float(f["N_top"]) - R
        g["N_reduction_N"] = R
        out[tag] = g
    out["_imposed_reduction"] = dict(fL=fL, n_columns=sum(1 for v in out.values() if isinstance(v, dict) and v.get("N_reduction_N")))
    return out


def report_line(plan, cfg=None) -> str:
    """One sentence for the DDM report (the imposed-load basis), whether or not a reduction applies."""
    if plan and plan.get("columns"):
        return ("Imposed load: the GMNIA sweeps carry the full floor imposed load (λu is for the unreduced load — "
                "conservative). The IS 875 (Part 2) 3.2.1 column reduction the HR design uses is applied in the B-1.2 check "
                "at λ = 1 exactly as the HR design applies it: each column's axial force is reduced by r × fL × (its axial "
                "force under the floor imposed load alone), r = %s by the number of floors carried (%d columns), in every "
                "combination without earthquake (IS 875 (Part 5) 8.1); beams and braces are not reduced."
                % ("/".join("%.1f" % r for r in plan.get("r_values") or []), plan.get("n_columns") or 0))
    if plan and plan.get("error"):
        return ("Imposed load: the HR design reduces column imposed load (IS 875-2 3.2.1) but the reduction could not be "
                "reproduced here (%s) -- the B-1.2 check uses the UNREDUCED column force (conservative)." % plan["error"])
    if cfg and cfg.get("column_imposed_load_reduction"):
        return ("Imposed load: the HR cfg sets column_imposed_load_reduction but no reduction factors were recorded -- the "
                "B-1.2 check uses the UNREDUCED column force (conservative).")
    return "Imposed load: as the HR design, unreduced (the HR design applies no IS 875 (Part 2) 3.2.1 column reduction)."
