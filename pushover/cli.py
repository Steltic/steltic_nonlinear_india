"""cli.py -- one command turns a Steltic design package into a pushover supplement.

    python -m pushover run  <package.zip | job folder>  [--out DIR] [--dirs X Y] [--max-drift 0.08]
                                                        [--site-class D] [--params hinge_params.json]
    python -m pushover inspect <package.zip | job folder>        # read-only: what is in the package

Outputs (in --out, default <job>/pushover/): pushover_report.html, pushover_package.json, curve_X.csv, curve_Y.csv,
hinge_params_used.json, run_log.txt.
"""
from __future__ import annotations
import argparse, json, os, shutil, sys, time


def _run(args):
    from . import package_reader as PR, nonlinear_model as NM, hinge_models as HM, postprocess as PP, report_supplement as RS
    t0 = time.time()
    pkg = PR.load(args.package)
    print(PR.summary(pkg))
    # ---- max roof drift: India fibre needs headroom past 2% to see descending branch ----
    if getattr(args, "max_drift", None) is None:
        juris = ""
        try:
            cfg = getattr(pkg, "cfg", None) or {}
            if isinstance(cfg, dict):
                juris = str(cfg.get("jurisdiction") or (cfg.get("load_plan") or {}).get("jurisdiction") or "")
            if not juris and getattr(pkg, "basis", None) is not None:
                juris = str(getattr(pkg.basis, "jurisdiction", "") or "")
            if not juris:
                # package path / name heuristic for India handoffs
                root = str(getattr(pkg, "root", "") or args.package).lower()
                if "india" in root or root.startswith("in_") or "/in_" in root:
                    juris = "india"
        except Exception:
            pass
        plast = str(getattr(args, "plasticity", None) or "fibre").lower()
        indiaish = juris.lower() in ("india", "is", "is_bis", "bis", "in")
        if indiaish and plast in ("fibre", "fiber"):
            args.max_drift = 0.10
            print("[pushover] --max-drift defaulted to 0.10 for India fibre (descending-branch headroom; override with --max-drift)")
        else:
            args.max_drift = 0.08

    if args.system:
        pkg.basis.system = args.system; pkg.basis.sources["system"] = "--system override"
    india = getattr(pkg.basis, "jurisdiction", None) == "india"
    if india:
        return _run_india(args, pkg, t0)
    missing = [k for k in ("SDS", "SD1", "W_kip") if getattr(pkg.basis, k) is None]
    if missing:
        sys.exit("design basis incomplete (%s) -- add cfg.py to the package or pass --sds/--sd1" % missing)
    prm = HM.load_params(args.params)
    if getattr(args, "plasticity", None):
        os.environ["SNL_PLASTICITY"] = str(args.plasticity)
        prm.setdefault("numerics", {})["plasticity"] = args.plasticity
    if getattr(args, "member_nseg", None) is not None:
        os.environ["SNL_MEMBER_NSEG"] = str(args.member_nseg)
        prm.setdefault("numerics", {})["member_nseg"] = int(args.member_nseg)
    if args.post_cap_ratio is not None:
        prm.setdefault("numerics", {})["post_cap_ratio"] = args.post_cap_ratio
        prm["numerics"]["post_cap_ratio_overridden"] = True
        print("!! post_cap_ratio overridden to %.2f -- a MODELLING CHANGE; the report will disclose it" % args.post_cap_ratio)
    strategies = {"auto": ("fine_step", "arclength"), "fine_step": ("fine_step",), "arclength": ("arclength",), "none": ()}[args.tail]
    if not prm.get("verified"):
        print("!! hinge_params.json is UNVERIFIED -- the report will carry the red banner until the spec lookup is done")
    out = args.out or os.path.join(str(pkg.root), "pushover")
    os.makedirs(out, exist_ok=True)
    try:
        from nlrha.india_authority import (
            nsp_acceptance_tables_status,
            drift_relief_analogue,
            write_complete_gate_disclosures,
            design_status,
        )
        job = str(getattr(pkg, "root", "") or args.package)
        nsp_st = nsp_acceptance_tables_status(job_dir=job)
        dr_st = drift_relief_analogue(job_dir=job)
        print("[india_authority] india_nsp_acceptance_tables found:%s (prefer fibre; hinge_params UNVERIFIED; do not invent IO/LS/CP)" % nsp_st.get("found"))
        print("[india_authority] asce_16_1_2_drift_relief found:%s (feedback drift loop ineligible)" % dr_st.get("found"))
        plast = str(getattr(args, "plasticity", None) or "fibre")
        write_complete_gate_disclosures(out, job_dir=job, evidence={"plasticity": plast})
        st = design_status(job_dir=job, evidence={"plasticity": plast})
        print("[india_authority] wrote %s" % os.path.join(out, "complete_gate_disclosures.json"))
        print("[india_authority] COMPLETE gate design_status=%s complete_allowed=%s admin_notify=%s (policy %s)" % (
            st.get("status"), st.get("complete_allowed"), st.get("admin_notify"), st.get("policy_date")))
    except Exception as ex:
        print("[india_authority] status emit skipped:", ex)
    loads, gtable = NM.gravity_loads(pkg, prm)
    PG = NM.column_gravity_axials(pkg, loads)
    runs, results, stats = {}, {}, None
    for d in args.dirs:
        hinges, stats = NM.build_nonlinear(pkg, prm, PG)
        run = NM.pushover(pkg, hinges, d, loads, prm, max_roof_drift=args.max_drift, gravity_table=gtable, tail_strategies=strategies)
        nsp = {lvl: PP.nsp_target(run, pkg.basis, prm, f, args.site_class) for lvl, f in prm["nsp"]["hazard_levels"].items()}
        p695 = PP.p695_factors(run, pkg.basis, nsp["BSE-1N"])
        acc = {lvl: PP.acceptance(run, hinges, n["target_disp_in"], lvl) for lvl, n in nsp.items()}
        runs[d] = run; results[d] = dict(nsp=nsp, p695=p695, acc=acc, hinges=hinges)
        for lvl, n in nsp.items():
            print("  [%s %s] Te=%.2fs Sa=%.3fg C0=%.2f C1=%.2f C2=%.2f -> dt=%.2f in (%.2f%% H) mu_str=%.2f mu_max=%.2f NSP ok=%s reached1.5=%s | worst D/C IO %.2f LS %.2f CP %.2f"
                  % (d, lvl, n["Te"], n["Sa"], n["C0"], n["C1"], n["C2"], n["target_disp_in"], 100 * n["target_over_H"], n["mu_strength"],
                     n["mu_max"], n["nsp_permitted"], n["reached_150pct"], acc[lvl]["worst_DC"]["IO"], acc[lvl]["worst_DC"]["LS"], acc[lvl]["worst_DC"]["CP"]))
        print("  [%s P-695] Vmax=%.0f kip Omega=%s (Om0=%s) mu_T=%.2f (%s)" % (d, p695["Vmax_kip"], "%.2f" % p695["Omega"] if p695["Omega"] else "n/a",
                                                                          pkg.basis.Om0, p695["mu_T"], p695["delta_u_basis"]))
        t = run["tail"]
        print("  [%s TAIL] status=%s tried=%s max(theta_pl/a)=%.2f max(theta_pl/b)=%.2f -- %s" % (d, t["status"], [x["strategy"] for x in t["tried"]],
              run["rec"]["a_ratio"][-1], run["rec"]["b_ratio"][-1], t["message"]))
        if t["status"] in ("lower_bound", "max_drift"):
            print("  >> ACTION FOR THE BOT: descending branch not captured (status=%s, max_drift=%.3f). "
                  "Ask the user before rung 3 (--post-cap-ratio 0.5 = modelling change) or a larger "
                  "--max-drift (India fibre default 0.10; try 0.12–0.15); see descending-branch protocol."
                  % (t["status"], args.max_drift))
    html = RS.write(out, pkg, prm, runs, results, gtable, stats, time.time() - t0)
    # Rewrite the gate disclosure after the runs so max_drift/lower_bound is
    # visible in STATUS. Descending-branch incompleteness remains optional and
    # must not turn an otherwise valid fibre pack into PARTIAL.
    try:
        from nlrha.india_authority import write_complete_gate_disclosures
        write_complete_gate_disclosures(
            out,
            job_dir=str(getattr(pkg, "root", "") or args.package),
            evidence={
                "plasticity": str(getattr(args, "plasticity", None) or "fibre"),
                "descending_branch_runs": {
                    d: run.get("tail", {}) for d, run in runs.items()
                },
            },
        )
    except Exception as ex:
        print("[india_authority] descending-branch disclosure rewrite skipped:", ex)
    try:
        from . import viewer3d as V3
        print("viewer", V3.write(out, pkg, prm, runs, results, stats))
    except Exception as ex:
        print("viewer failed:", ex)
    _copy_params(args.params or os.path.join(os.path.dirname(__file__), "hinge_params.json"),
                 os.path.join(out, "hinge_params_used.json"))
    print("wrote", html, "(%.0f s)" % (time.time() - t0))


def _copy_params(src, dst):
    """Copy the parameters the run used into the job folder, keeping any grounding already recorded.

    This copy is what used to erase `snl revise`'s work: the engineer ran Revise, was told to re-run
    the analyses to "pick the citation up", and the re-run put the un-annotated file straight back --
    a loop with no exit. The record itself lives in revise_evidence.json at the job root, which the
    run never writes, so it is simply re-applied here when it was taken against these same numbers.
    India: the record grounds the IS clauses (no IS hinge table exists to ground a backbone), so the
    file's `source` is only rewritten when a component group was grounded; the backbones otherwise stay
    modelling assumptions (information / EOR input).
    """
    import shutil as _sh
    from snl import grounding as _G
    _sh.copy(src, dst)
    try:
        prm = json.load(open(dst, encoding="utf-8"))
        st, ev = _G.state(prm, os.path.dirname(dst))
        if st == _G.GROUNDED and ev:
            prm["grounding"] = (prm.get("grounding") or {}) | {
                "asked": ev.get("asked"),
                "groups": {g: {k: r.get(k) for k in ("document", "citation", "section", "page")}
                           for g, r in (ev.get("groups") or {}).items() if r.get("grounded")},
                "clauses": {c: (r.get("citation") if isinstance(r, dict) else r)
                            for c, r in (ev.get("clauses") or {}).items()
                            if (r.get("grounded") if isinstance(r, dict) else r)},
                "evidence": _G.EVIDENCE, "reapplied_by": "pushover run"}
            cites = "; ".join(_G.citations(ev))
            if cites:
                prm["source"] = ("cited from the corpus on this PC %s -- %s. The numeric backbone values in this "
                                 "file were NOT read out of those tables; `verified` stays false until "
                                 "they are." % (ev.get("asked") or "", cites))
            json.dump(prm, open(dst, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            print("params: grounding from %s re-applied (%d groups, %d IS clauses)"
                  % (_G.EVIDENCE, len(_G.citations(ev)), len(_G.clause_citations(ev))))
    except Exception as ex:                       # never fail a completed run over a provenance note
        print("params: could not re-apply grounding:", ex)


def _run_india(args, pkg, t0):
    """India (D6/D7): NSP at IS-DBE and IS-MCE from the IS 1893 elastic spectrum; informative response at delta_t;
    fibre plasticity; IS 2062 steel; mass/gravity = IS seismic weight. No IO/LS/CP/BPON verdict."""
    import math
    from . import nonlinear_model as NM, hinge_models as HM, postprocess as PP, report_india as RI, member_response as MR
    from . import india_materials as IM
    from nlrha import india_hazard as IH
    prm = HM.load_params(args.params)
    plast = str(getattr(args, "plasticity", None) or "fibre").lower()
    if plast not in ("fibre", "fiber"):
        print("[pushover] India: fibre plasticity is used (member strains/rotations are recorded from fibres); "
              "--plasticity %s ignored" % plast)
    os.environ["SNL_PLASTICITY"] = "fibre"; prm.setdefault("numerics", {})["plasticity"] = "fibre"
    if getattr(args, "member_nseg", None) is not None:
        os.environ["SNL_MEMBER_NSEG"] = str(args.member_nseg); prm["numerics"]["member_nseg"] = int(args.member_nseg)
    strategies = {"auto": ("fine_step", "arclength"), "fine_step": ("fine_step",), "arclength": ("arclength",), "none": ()}[args.tail]
    out = args.out or os.path.join(str(pkg.root), "pushover")
    os.makedirs(out, exist_ok=True)
    ind = pkg.basis.india or {}
    ref = IM.reference_rotation(pkg.basis.system)
    levels = PP.india_levels(prm)
    loads, gtable = NM.gravity_loads(pkg, prm)
    PG = NM.column_gravity_axials(pkg, loads)
    print("[pushover] India: gravity = IS seismic weight %.1f kN; mass gate %s" % (
        sum(r["W_kN"] for r in gtable), (pkg.calc or {}).get("_is_mass_gate", {}).get("ok")))
    runs, results, stats = {}, {}, None

    def estimator(pat):
        T = pat["T1"]; out_ = []
        for lv in ("DBE", "MCE"):
            sa = IH.elastic_sa(T, Z=ind["Z"], I=ind["I"], soil=ind["soil"], level=lv)
            out_.append(1.0 * sa * T * T / (4 * math.pi ** 2) * 386.09)   # C0·C1·C2 ~ 1 (lower estimate -> finer step)
        return out_

    for d in args.dirs:
        hinges, stats = NM.build_nonlinear(pkg, prm, PG)
        rec = MR.MemberRecorder(pkg, hinges, stats)
        run = NM.pushover(pkg, hinges, d, loads, prm, max_roof_drift=args.max_drift, gravity_table=gtable,
                          tail_strategies=strategies, recorder=rec, target_estimator=estimator)
        nsp = {lvn: PP.nsp_target(run, pkg.basis, prm, lv) for lvn, lv in levels.items()}
        from snl.india_units import KN_TO_KIP
        vbd = IH.vb_direction_kN(ind, d)                  # NL-4: V-bar_B of THIS direction (per-direction R)
        vbd_kip = vbd * KN_TO_KIP if vbd is not None else None
        cap = PP.capacity_summary(run, pkg.basis, nsp["IS-DBE"], V_design_kip=vbd_kip)
        resp = {lvn: PP.response_at(run, n["target_disp_in"], lvn, rec.meta(), ref, pkg.basis, V_design_kip=vbd_kip)
                for lvn, n in nsp.items()}
        runs[d] = run; results[d] = dict(nsp=nsp, capacity=cap, resp=resp, ref_rot=ref, meta=rec.meta())
        for lvn, n in nsp.items():
            a = resp[lvn]
            print("  [%s %s] Te=%.3fs Sa=%.3fg C0=%.2f C1=%.2f C2=%.2f -> dt=%.1f mm (%.3f%% H) | V=%.0f kN (V/VB %.2f) "
                  "max drift %.3f%% | census %s" % (d, lvn, n["Te"], n["Sa"], n["C0"], n["C1"], n["C2"], n["target_disp_in"] * 25.4,
                                                   100 * n["target_over_H"], a["base_shear_kN"], a["V_over_VB"] or 0,
                                                   100 * a["max_story_drift"], a.get("census")))
        print("  [%s capacity] Vmax=%.0f kN Vmax/VB=%.2f stop=%s" % (d, cap["Vmax_kN"], cap["Vmax_over_VB"] or 0, run["stop_reason"]))
    html_path = RI.write(out, pkg, prm, runs, results, gtable, stats, time.time() - t0)
    for d, run in runs.items():
        with open(os.path.join(out, "curve_%s.csv" % d), "w") as f:
            f.write("roof_disp_mm,base_shear_kN\n")
            for u, v in zip(run["rec"]["u"], run["rec"]["V"]):
                f.write("%.3f,%.2f\n" % (u * 25.4, v * 4.4482216152605))
    _copy_params(args.params or os.path.join(os.path.dirname(__file__), "hinge_params.json"),
                 os.path.join(out, "hinge_params_used.json"))
    print("wrote", html_path, "(%.0f s)" % (time.time() - t0))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pushover")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("package"); r.add_argument("--out"); r.add_argument("--dirs", nargs="+", default=["X", "Y"])
    r.add_argument("--max-drift", type=float, default=None,
                   help="max roof drift ratio H (default: 0.10 India fibre, else 0.08). Raise to capture descending branch.")
    r.add_argument("--site-class", default="D"); r.add_argument("--params")
    r.add_argument("--system")
    r.add_argument("--tail", default="auto", help="descending-branch escalation: auto (fine_step then arclength) | fine_step | arclength | none")
    r.add_argument("--post-cap-ratio", type=float, help="RUNG 3 (modelling change, user consent): fraction of `a` over which hinges descend to residual (default 0.15; try 0.5)")
    r.add_argument("--plasticity", default="fibre", choices=["fibre", "fiber", "imk"], help="fibre=distributed forceBeamColumn (default); imk=concentrated ModIMK")
    r.add_argument("--member-nseg", type=int, default=4, help="member subdivisions (default 4 for fibre)")
    i = sub.add_parser("inspect"); i.add_argument("package")
    args = ap.parse_args(argv)
    if args.cmd == "inspect":
        from . import package_reader as PR
        print(PR.summary(PR.load(args.package)))
    else:
        _run(args)


if __name__ == "__main__":
    main()
