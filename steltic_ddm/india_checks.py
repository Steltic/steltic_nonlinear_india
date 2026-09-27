"""india_checks.py -- DDM checks for India jobs (WP4.9).

* gravity_gate(): linear-elastic GMNIA under each gravity combination at lambda = 1; per member, beams max|M_major|
  and columns max N compared with design/member_schedule.csv (rows whose governing combination is that case) within
  +/-5 %. A mismatch means the GMNIA loads the frame differently from the design -> results withheld.
* b12_check(): IS 800:2007 Annex B-1.2 -- "it shall be sufficient to satisfy the section capacity requirements of
  Section 8 ... Section 7 ... Section 9 ... Section 10" -- member section capacities (gamma_m0 = 1.10) with the GMNIA
  member forces at lambda = 1 (instability / LTB / moment amplification excluded by B-1.2). This IS a code check.
* b11_preconditions(): B-1.1 applies to "members of compact section with full lateral restraint": section class
  from IS 800 Table 2 (rolled I: plastic b/tf <= 9.4 eps, d/tw <= 84 eps; compact 10.5 eps / 105 eps; CHS D/t <= 42
  eps^2 plastic, 52 eps^2 compact). Lateral restraint is an EOR statement (not checked here).
DDM runs in N-mm; results are reported in kN, kN·m, MPa.
"""
from __future__ import annotations
import csv
import math
import os

import openseespy.opensees as ops

B12_QUOTE = ("IS 800:2007 B-1.2: 'For the strength limit state, it shall be sufficient to satisfy the section capacity "
             "requirements of Section 8 ... Section 7 ... Section 9 ... Section 10.'")
B11_QUOTE = "IS 800:2007 B-1.1: 'For a frame, comprising members of compact section with full lateral restraint ...'"


def _schedule(job_dir):
    rows = {}
    p = os.path.join(job_dir, "design", "member_schedule.csv")
    if not os.path.exists(p):
        return rows
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows[int(r["ele_tag"])] = r
            except Exception:
                continue
    return rows


def _combo_forces(job_dir):
    """design/member_combo_forces.json (HR engine): {ele_tag: {combo: [N, Mmaj, ...]}}, N and N-mm; None if absent."""
    import json
    p = os.path.join(job_dir, "design", "member_combo_forces.json")
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None
    fields = d.get("fields") or []
    iN, iM = (fields.index("N") if "N" in fields else 0), (fields.index("Mmaj") if "Mmaj" in fields else 1)
    out = {}
    for t, rec in (d.get("elements") or {}).items():
        try:
            out[int(t)] = {c: (abs(float(v[iN])), abs(float(v[iM]))) for c, v in (rec.get("records") or {}).items()}
        except Exception:
            continue
    return out


def member_forces(g, lam_scale=1.0):
    """Per member: max |N| (compression +), max |M_major|, max |M_minor|, max |V| over its sub-element ends (N, N·mm)."""
    out = {}
    for e in g.elems:
        try:
            f = ops.eleResponse(e["tag"], "localForce")
        except Exception:
            continue
        if not f or len(f) < 12:
            continue
        N = max(f[0], -f[6])                      # OpenSees localForce: +N at end i = compression (as column_gravity_axials)
        Nabs = max(abs(f[0]), abs(f[6]))
        My = max(abs(f[4]), abs(f[10])); Mz = max(abs(f[5]), abs(f[11]))
        V = max(math.hypot(f[1], f[2]), math.hypot(f[7], f[8]))
        kind = e["kind"]
        # major axis: beams (transf 3, depth along local z) bend about local y; columns (depth along local y) about z
        Mmaj, Mmin = (My, Mz) if kind == "beam" else (Mz, My)
        cur = out.setdefault(e["mtag"], dict(kind=kind, role=e["role"], section=e["section"], N_comp=0.0, N_abs=0.0,
                                             M_major=0.0, M_minor=0.0, V=0.0))
        cur["N_comp"] = max(cur["N_comp"], N); cur["N_abs"] = max(cur["N_abs"], Nabs)
        # the axial force at the member's j end (top of a column), compression +: what the HR engine records as N
        # (static_model.member_records: localForce[6] of the single column element)
        s_ = e.get("s") if e.get("s") is not None else 0
        if s_ >= cur.get("_s_top", -10):
            cur["_s_top"] = s_; cur["N_top"] = -f[6]
        cur["M_major"] = max(cur["M_major"], Mmaj); cur["M_minor"] = max(cur["M_minor"], Mmin); cur["V"] = max(cur["V"], V)
    return out


def section_capacity_250(sec, quantity):
    """M_p = 250 Z_p (kN-m) for a moment quantity, P_y = 250 A (kN) otherwise; 0 when the section is unknown."""
    from pushover import india_materials as _IM
    try:
        sp = _IM.section_props_mm(sec)
        return 250.0 * (float(sp["Zx"]) / 1e6 if str(quantity).startswith("M") else float(sp["A"]) / 1e3)
    except Exception:
        return 0.0


def apply_noise_floor(rows, abs_frac=0.02, capacity=section_capacity_250):
    """NL-16: rows outside the ratio band pass when |gmnia - design| <= abs_frac x capacity(section, quantity);
    they are flagged ok_by_floor. Returns the number of rows passed by the floor."""
    n, cache = 0, {}
    for r in rows:
        if r.get("ok") is False and not r.get("error"):
            k = (r["section"], r["quantity"])
            if k not in cache:
                cache[k] = capacity(*k)
            if abs(r["gmnia"] - r["design"]) <= abs_frac * cache[k]:
                r["ok"] = True; r["ok_by_floor"] = True; n += 1
    return n


def gravity_gate(nm, cfg, cases, tol=0.05, nsub=(2, 4, 4), rigid_end_offset=False, min_design=1.0, abs_frac=0.02):
    from .model_gmnia import GMNIAModel
    from .loads import lateral_direction, present_sets
    sched = _schedule(nm.job_dir)
    pres = present_sets(nm)
    grav = [c for c in cases if lateral_direction(c[4])[0] is None and not c[5]]
    rows, worst = [], None
    # NL-14: when the HR design reduced the column imposed load (IS 875-2 3.2.1), compare like with like
    hr = None
    try:
        from snl import hr_gravity as HG
        hr = HG.ensure(nm.job_dir)
    except Exception:
        hr = None
    llr = {int(k): float(v) for k, v in ((hr or {}).get("column_imposed_load_reduction") or {}).items()}
    llr_used = False
    for c in grav:
        label, fD, fL, fLr, lat, _ = c
        g = GMNIAModel(nm, cfg, nsub=nsub, elastic=True, residual="none", out_of_plumb=(None, 0.0), bow=0.0, brace_bow=0.0,
                       rigid_end_offset=rigid_end_offset, transf_type="PDelta")
        g.build().prepare()
        ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
        g.apply_gravity(fD, fL, fLr, pres, fS=float((getattr(c, "meta", None) or {}).get("fS") or 0.0),
                        meta=getattr(c, "meta", None))
        ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
        ops.test("NormDispIncr", 1e-8, 50, 0); ops.algorithm("Newton")
        ops.integrator("LoadControl", 1.0); ops.analysis("Static")
        if ops.analyze(1) != 0:
            rows.append(dict(combo=label, error="elastic gravity analysis failed")); continue
        mf = member_forces(g)
        NLL = {}
        if llr and fL and hr and (hr.get("states") or {}).get("Lfloor"):
            g2 = GMNIAModel(nm, cfg, nsub=nsub, elastic=True, residual="none", out_of_plumb=(None, 0.0), bow=0.0,
                            brace_bow=0.0, rigid_end_offset=rigid_end_offset, transf_type="PDelta")
            g2.build().prepare()
            ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
            from snl import hr_gravity as HG
            chains = {}
            for e in g2.elems:
                sp, Lm = e.get("span"), e.get("Lm") or e.get("L")
                if sp and Lm:
                    chains.setdefault(int(e["mtag"]), []).append((e["tag"], sp[0] / Lm, sp[1] / Lm))
            HG.apply(ops, HG.combine(hr, {"Lfloor": 1.0}), chains)
            ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
            ops.test("NormDispIncr", 1e-8, 50, 0); ops.algorithm("Newton")
            ops.integrator("LoadControl", 1.0); ops.analysis("Static")
            if ops.analyze(1) == 0:
                NLL = {t: (v.get("N_top") or 0.0) / 1e3 for t, v in member_forces(g2).items() if v["kind"] == "col"}
            # the main model is gone from OpenSees after g2: the member forces mf above were read before
        # NL-14: every member against the HR engine's own forces for THIS combination (member_combo_forces.json);
        # the old path compared only members whose governing combination happened to be gravity, through schedule
        # columns (Mx_kNm, P_comp_N) the current package no longer writes -> 0 comparisons and a failed gate
        cf = _combo_forces(nm.job_dir)
        pairs = []
        if cf is not None:
            for tag, recs in cf.items():
                if label in recs and tag in mf:
                    pairs.append((tag, recs[label][0] / 1e3, recs[label][1] / 1e6))
        else:
            for tag, r in sched.items():
                if (r.get("governing_combo") or "").strip() != label or tag not in mf:
                    continue
                P = r.get("P_comp_kN") if r.get("P_comp_kN") not in (None, "") else (float(r.get("P_comp_N") or 0.0) / 1e3)
                M = r.get("M_major_kNm") if r.get("M_major_kNm") not in (None, "") else r.get("Mx_kNm")
                pairs.append((tag, float(P or 0.0), float(M or 0.0)))
        for tag, P_des, M_des in pairs:
            m = mf[tag]
            if m["kind"] == "beam":
                des = M_des; got = m["M_major"] / 1e6; q = "M (kN·m)"
            elif m["kind"] == "col":
                des = P_des
                if tag in llr and tag in NLL:
                    des = P_des + fL * llr[tag] * NLL[tag]     # the HR N before the 3.2.1 reduction (llr = the reduction)
                    llr_used = True
                got = (m.get("N_top") if cf is not None and m.get("N_top") is not None else m["N_comp"]) / 1e3
                q = "P (kN)" if cf is None else "P top (kN)"
            else:
                continue
            if abs(des) < min_design:
                continue
            ratio = got / des
            row = dict(combo=label, ele=tag, kind=m["kind"], role=m["role"], section=m["section"], quantity=q,
                       design=round(des, 2), gmnia=round(got, 2), ratio=round(ratio, 3), ok=abs(ratio - 1.0) <= tol)
            rows.append(row)
            if worst is None or abs(ratio - 1) > abs(worst["ratio"] - 1):
                worst = row
    # NL-16: a noise floor. A +/-5 % ratio on a near-zero force is not a load-transfer test (IN_Ex9 stem floor beams:
    # 8.0 vs 8.6 kN-m on a WPB320X300X126.66, M_p = 535 kN-m at 250 MPa). A row outside the ratio band still passes when the
    # absolute difference is <= abs_frac (2 %) of the member's own plastic capacity at 250 MPa (M_p = 250 Z_p for
    # beams, P_y = 250 A for columns -- the lowest IS 2062 grade, so the floor is never larger than 2 % of the real
    # capacity). Such rows are flagged ok_by_floor and counted in the summary.
    apply_noise_floor(rows, abs_frac)
    bad = [r for r in rows if r.get("ok") is False or r.get("error")]
    ok = bool(rows) and not bad
    worst_ok = [r for r in rows if not r.get("error") and not r.get("ok_by_floor")]
    worst = max(worst_ok, key=lambda r: abs(r["ratio"] - 1.0)) if worst_ok else worst
    llr_note = ("columns: the HR N is IS 875-2 3.2.1 reduced (cfg column_imposed_load_reduction); compared as "
                "N_HR + fL x reduction x N_LL(top), N_LL = the floor-imposed-only axial of the same GMNIA") if llr_used else None
    n_floor = sum(1 for r in rows if r.get("ok_by_floor"))
    summary = ("%d member comparisons, %d outside +/-%.0f %%%s; worst %s" % (
        len(rows), len(bad), 100 * tol, (" (%d small forces within the %.0f %% noise floor)" % (n_floor, 100 * abs_frac)) if n_floor else "", ("%s ele %s %s ratio %.3f" % (worst["combo"], worst["ele"], worst["quantity"], worst["ratio"])) if worst else "n/a"))
    by_group = {}
    for r in rows:
        if r.get("error"):
            continue
        k = (r["combo"], r["role"], r["section"], r["quantity"])
        b = by_group.setdefault(k, dict(combo=r["combo"], role=r["role"], section=r["section"], quantity=r["quantity"], n=0,
                                        ratio_min=9e9, ratio_max=-9e9, n_bad=0))
        b["n"] += 1; b["ratio_min"] = min(b["ratio_min"], r["ratio"]); b["ratio_max"] = max(b["ratio_max"], r["ratio"])
        b["n_bad"] += int(not r["ok"])
    return dict(ok=ok, tol=tol, summary=summary, rows=rows[:400], groups=list(by_group.values()), worst=worst,
                n_compared=len(rows), n_bad=len(bad), n_ok_by_floor=n_floor, abs_frac=abs_frac, imposed_load_reduction=llr_note,
                basis=("linear-elastic GMNIA topology (P-Delta transformation, as the HR static model) at lambda = 1 vs the HR engine's member forces for the same combination "
                       "(design/member_combo_forces.json; member_schedule.csv when absent), +/-5 %, or an absolute difference within "
                       "2 % of the member's plastic capacity at 250 MPa (noise floor)"))


def section_class(section: str, fy: float) -> dict:
    """IS 800 Table 2 class (plastic / compact / semi-compact) for B-1.1 (rolled I and CHS)."""
    from pushover import india_materials as IM
    sp = IM.section_props_mm(section)
    eps = math.sqrt(250.0 / fy)
    if sp.get("tube") and str(sp.get("type")).upper() == "CHS":
        r = (sp.get("D") or 0) / (sp.get("t") or 1)
        cls = "plastic" if r <= 42 * eps * eps else ("compact" if r <= 52 * eps * eps else "semi-compact")
        return dict(section=sp["label"], cls=cls, D_t=round(r, 1), limits=dict(plastic=42 * eps * eps, compact=52 * eps * eps))
    bt = (sp.get("bf") or 0) / 2.0 / (sp.get("tf") or 1)
    dtw = ((sp.get("d") or 0) - 2 * (sp.get("tf") or 0)) / (sp.get("tw") or 1)
    if bt <= 9.4 * eps and dtw <= 84 * eps:
        cls = "plastic"
    elif bt <= 10.5 * eps and dtw <= 105 * eps:
        cls = "compact"
    else:
        cls = "semi-compact"
    return dict(section=sp["label"], cls=cls, b_tf=round(bt, 2), d_tw=round(dtw, 1),
                limits=dict(flange_plastic=9.4 * eps, flange_compact=10.5 * eps, web_plastic=84 * eps, web_compact=105 * eps))


def b11_preconditions(nm, fy_fn) -> dict:
    rows = {}
    for m in nm.members:
        key = str(m.section).upper()
        if key in rows:
            continue
        try:
            rows[key] = section_class(m.section, fy_fn(m.section, m.role or m.kind))
        except Exception as ex:  # noqa: BLE001
            rows[key] = dict(section=key, cls="unknown", note=str(ex))
    ok = all(r["cls"] in ("plastic", "compact") for r in rows.values())
    return dict(ok=ok, sections=list(rows.values()), lateral_restraint="EOR statement required (not checked)",
                quote=B11_QUOTE, clause="IS 800:2007 B-1.1; Table 2")


def b12_check(forces_at_1: dict | None, fy_fn, lam_reached: float | None, label: str) -> dict:
    """Section-capacity D/C per member group at lambda = 1 (IS 800 B-1.2)."""
    from pushover import india_materials as IM
    if not forces_at_1:
        return dict(combo=label, ok=False, reached_lambda_1=False, lambda_reached=lam_reached,
                    note="lambda = 1 not reached by the GMNIA sweep -> B-1.2 not satisfied", groups=[], quote=B12_QUOTE)
    groups = {}
    for tag, f in forces_at_1.items():
        cap = IM.section_capacity(f["section"], fy_fn(f["section"], f.get("role") or f["kind"]))
        r = IM.b12_interaction(f["N_abs"], f["M_major"], f["M_minor"], f["V"], cap)
        k = (f["role"], f["section"])
        g = groups.setdefault(k, dict(role=f["role"], section=f["section"], n=0, dc_max=0.0, dc_shear_max=0.0, ele=None))
        g["n"] += 1
        if r["dc"] > g["dc_max"]:
            g.update(dc_max=round(r["dc"], 3), ele=tag, N_kN=round(f["N_abs"] / 1e3, 1), M_major_kNm=round(f["M_major"] / 1e6, 1),
                     M_minor_kNm=round(f["M_minor"] / 1e6, 1), Nd_kN=round(cap["Nd_N"] / 1e3, 1),
                     Md_kNm=round(cap["Mdz_Nmm"] / 1e6, 1), fy_MPa=cap["fy_MPa"])
        g["dc_shear_max"] = round(max(g["dc_shear_max"], r["dc_shear"]), 3)
    gl = sorted(groups.values(), key=lambda g: -g["dc_max"])
    ok = all(g["dc_max"] <= 1.0 and g["dc_shear_max"] <= 1.0 for g in gl)
    return dict(combo=label, ok=ok, reached_lambda_1=True, groups=gl, quote=B12_QUOTE,
                clause="IS 800:2007 Annex B-1.2 -> 6.2, 7 (section), 8.2.1.2, 8.4, 9.3.1.1; gamma_m0 = 1.10")
