"""cli.py -- Non Linear Dynamic Bot tool.

    python -m nlrha scale   <steltic package>  [--site-class D] [--n 11] [--out DIR]      # select + scale only (fast)
    python -m nlrha run     <steltic package>  [--pushover-dir DIR] [--n 11] [--dt 0.01] [--records 1-11] [--only-records 4] [--out DIR]
                                               [--xi 0.025] [--params hinge_params.json] [--free-vib 5]
Outputs (default <job>/nlrha/): nlrha_report.html, nlrha_package.json, gm_scaling.json, per-record peaks in the package.
"""
from __future__ import annotations
import argparse, json, os, sys, time


def _load(args):
    from pushover import package_reader as PR, hinge_models as HM, nonlinear_model as NM
    from . import model as MD
    pkg = PR.load(args.package); print(PR.summary(pkg))
    prm = HM.load_params(args.params, jurisdiction=(pkg.basis.jurisdiction or "usa"))
    from . import india_authority as IA
    ch16 = IA.load_ch16_params()
    print(IA.authority_banner().splitlines()[0])
    print("[india_authority] ch16_params india_authoritative=%s verified=%s" % (
        ch16.get("india_authoritative"), ch16.get("verified")))
    for sev, msg in IA.validate_nl_plan(job_dir=str(pkg.root)):
        print("[%s] %s" % (sev, msg[:160]))
    # WP4.10: the COMPLETE-gate file is written only at the END of `run` / `report` (never on load / hazard / scale)
    b = pkg.basis
    if b.jurisdiction != "india" and (b.SDS is None or b.SD1 is None):
        print("[WARN] USA scaffolding package without SDS/SD1.")
    TL = 8.0
    try:                                                  # TL from cfg if present
        import re
        src = open(os.path.join(str(pkg.root), "cfg.py")).read()
        m = re.search(r"TL\s*=\s*([0-9.]+)", src); TL = float(m.group(1)) if m else TL
    except Exception:
        pass
    return pkg, prm, ch16, TL


def _library(args):
    """The record library: the shipped set, or the sets / user folders named by --records-set (several allowed)."""
    dirs = getattr(args, "records_set", None) or []
    if isinstance(dirs, str):
        dirs = [dirs]
    if not dirs:
        from . import ground_motions as GM
        idx, recs = GM.library(None)
        return [dict(dir=None, set=idx.get("set"), n=len(recs))], recs
    from . import site_hazard as SH
    return SH.library_from([os.path.abspath(d) for d in dirs])


def _is_india(pkg):
    return getattr(pkg.basis, "jurisdiction", None) == "india"


def _target_kind(args, pkg):
    """--target default: is1893 for India, code for USA scaffolding. India refuses code|mcer|cs (D6) unless
    --usgs-scaffolding is given explicitly."""
    kind = getattr(args, "target", None)
    if _is_india(pkg):
        kind = kind or "is1893"
        if kind != "is1893" and not getattr(args, "usgs_scaffolding", False):
            sys.exit("India job: --target %s refused -- the NL target is the IS 1893 elastic spectrum (DBE/MCE, no R, "
                     "owner ruling D6). Use --target is1893 (default) or pass --usgs-scaffolding for a USA regression run." % kind)
        return kind
    return kind or "code"


def _levels(args, pkg):
    if not _is_india(pkg):
        return [None]
    lv = str(getattr(args, "level", None) or "both").upper()
    return ["DBE", "MCE"] if lv == "BOTH" else [lv]


def _india_hazard(args, pkg, T1x=None, T1y=None, lo=None, hi=None):
    """site_hazard for an India package: the file written by `nlrha hazard` if present, else built on the fly from
    the structured seismic_calc/load_plan values (so drivers that never pass --target still get the elastic target)."""
    from . import india_hazard as IH
    path = getattr(args, "site_hazard", None) or os.path.join(str(pkg.root), "nlrha", "site_hazard.json")
    if os.path.exists(path):
        hz = json.load(open(path, encoding="utf-8"))
        if "is1893_elastic_DBE" in (hz.get("targets") or {}):
            return hz
        print("[target] %s has no elastic targets (pre-D6 file) -- rebuilding from the package" % path)
    ind = pkg.basis.india or {}
    return IH.build_india_site_hazard(zone=ind.get("zone"), Z=ind.get("Z"), soil=ind.get("soil"), I=ind.get("I"),
                                      R=ind.get("R"), T1x=T1x or ind.get("Ta_x") or ind.get("Ta"),
                                      T1y=T1y or ind.get("Ta_y") or ind.get("Ta"), T_lower=lo, T_upper=hi)


def _target(args, pkg, level=None, modal=None, lo=None, hi=None):
    """(target tuple or None, deagg or None, pulse_fraction, hazard dict or None)."""
    kind = _target_kind(args, pkg)
    if kind == "is1893":
        from . import india_hazard as IH
        hz = _india_hazard(args, pkg, (modal or {}).get("T1x"), (modal or {}).get("T1y"), lo, hi)
        tgt = IH.target_from_india_hazard(hz, "is1893", level or "DBE")
        pf = float(getattr(args, "pulse_fraction", None) or 0.0)
        print("[target] %s; pulse share %.0f%%" % (tgt[2], 100 * pf))
        return tgt, None, pf, hz
    if kind == "code":
        return None, None, float(getattr(args, "pulse_fraction", 0) or 0), None
    from . import site_hazard as SH
    path = getattr(args, "site_hazard", None) or os.path.join(str(pkg.root), "nlrha", "site_hazard.json")
    if not os.path.exists(path):
        sys.exit("--target %s needs a site hazard file: run `python -m nlrha hazard <package> --lat .. --lon ..` first (looked for %s)" % (kind, path))
    hz = json.load(open(path, encoding="utf-8"))
    cs_i = 0
    if kind == "cs" and getattr(args, "cs_period", None):
        cs_i = min(range(len(hz["targets"]["cs"])), key=lambda i: abs(hz["targets"]["cs"][i]["T_star"] - float(args.cs_period)))
    tgt = SH.target_from_hazard(hz, kind, cs_i)
    key = "%.3f" % hz["targets"]["cs"][cs_i]["T_star"] if hz["targets"].get("cs") else None
    deagg = (hz.get("deagg") or {}).get(key) if key else None
    pf = getattr(args, "pulse_fraction", None)
    pf = float(pf) if pf is not None else float((hz.get("near_fault") or {}).get("pulse_fraction") or 0.0)
    print("[target] %s; disaggregation %s; pulse share %.0f%%" % (tgt[2], ("M %.2f R %.0f km eps %.2f" % (deagg["mean"]["M"], deagg["mean"]["R_km"], deagg["mean"]["eps"])) if deagg else "none", 100 * pf))
    return tgt, deagg, pf, hz


def _cfg_regex(root):
    """Last-resort cfg.py regex (word-boundary, case-sensitive keys) -- structured seismic_calc/load_plan win."""
    import re
    cfg = {}
    try:
        src = (root / "cfg.py").read_text(encoding="utf-8", errors="replace")
    except Exception:
        return cfg
    for key in ("seismic_zone", "soil_type", "importance_factor", "R", "jurisdiction"):
        mo = re.search(r"(?<![\w])[\"']?%s[\"']?\s*[:=]\s*[\"']?([\w.]+)[\"']?" % re.escape(key), src)
        if mo:
            cfg[key] = mo.group(1)
    return cfg


def cmd_hazard(args):
    """Site hazard -> nlrha/site_hazard.json.

    India fork: IS 1893 zone/Z/soil via nlrha.india_hazard when --india / --zone /
    cfg seismic fields are set. USGS ASCE 7-22 path remains scaffolding (--usgs).
    """
    from . import site_hazard as SH, model as MD, india_authority as IA
    pkg, prm, ch16, TL = _load(args)
    use_usgs = bool(getattr(args, "usgs", False))
    out = args.out or os.path.join(str(pkg.root), "nlrha"); os.makedirs(out, exist_ok=True)
    if not use_usgs:
        from . import india_hazard as IH
        ind = dict(pkg.basis.india or {})
        rx = _cfg_regex(pkg.root) if not _is_india(pkg) else {}
        zone = getattr(args, "zone", None) or ind.get("zone") or rx.get("seismic_zone")
        soil = getattr(args, "soil_type", None) or ind.get("soil") or rx.get("soil_type")
        I = getattr(args, "importance", None) if getattr(args, "importance", None) is not None else (ind.get("I") if ind.get("I") is not None else rx.get("importance_factor"))
        R = getattr(args, "R_factor", None) if getattr(args, "R_factor", None) is not None else (ind.get("R") if ind.get("R") is not None else rx.get("R"))
        Z = getattr(args, "Z", None) if getattr(args, "Z", None) is not None else ind.get("Z")
        # T1 for the hazard metadata: --t1, else the design Ta per direction from seismic_calc (no 1.0 s default)
        if args.t1:
            T1x = T1y = float(args.t1)
        else:
            T1x, T1y = ind.get("Ta_x") or ind.get("Ta"), ind.get("Ta_y") or ind.get("Ta")
        print("[hazard] India path: IS 1893 zone/Z/soil/I (structured: %s); USGS not used" % ", ".join(
            "%s<-%s" % (k, v) for k, v in (ind.get("sources") or {}).items() if k in ("zone", "Z", "soil", "I", "R", "Ta")))
        try:
            hz = IH.build_india_site_hazard(zone=zone, soil=soil, I=(float(I) if I is not None else None),
                                            R=(float(R) if R is not None else None), Z=Z, T1x=T1x, T1y=T1y)
        except ValueError as e:
            sys.exit("India hazard: %s\nPass --zone/--soil-type/--importance/--t1 or fix seismic_calc.json / load_plan.json." % e)
        path = os.path.join(out, "site_hazard.json")
        json.dump(hz, open(path, "w", encoding="utf-8"), indent=1)
        print("wrote", path)
        s_ = hz["site"]
        print("[hazard] zone %s Z=%.2f soil=%s I=%.2f (R=%s reference only) | T1x=%.3f T1y=%.3f (design Ta)" % (
            s_["seismic_zone"], s_["Z"], s_["soil_type"], s_["importance_I"], s_["response_reduction_R"], T1x, T1y))
        for lv in hz["design"]["levels"]:
            t = hz["targets"]["is1893_elastic_%s" % lv]
            print("[hazard] %s: plateau %.3f g (%s)" % (lv, max(t["sa"]), t["clause"]))
        for src in hz.get("sources") or []:
            print("[hazard] cite:", src)
        return
    if args.t1:
        T1x = T1y = float(args.t1); T90 = None
        lo, hi = 0.2 * T1x, 2.0 * T1x
    else:
        loads, gtab, split = MD.ch16_gravity(pkg, ch16)
        PG, modal, lo, hi = _modal_and_range(pkg, prm, ch16, loads)
        T1x, T1y, T90 = modal["T1x"], modal["T1y"], modal["T90"]

    if args.lat is None or args.lon is None:
        sys.exit("USGS hazard scaffolding needs --lat and --lon (or use --india --zone …)")
    from . import acceptance as AC
    rc = AC.risk_category(pkg, args.risk_category)
    design = json.load(open(args.design_json)) if args.design_json else None
    deaggs = json.load(open(args.deagg_json)) if args.deagg_json else None
    sigma = json.load(open(args.sigma)) if args.sigma else None
    cps = [float(x) for x in (args.cs_period or [])] or None
    print("[hazard] USGS ASCE scaffolding (india_authoritative=false) — not India authority")
    hz = SH.build_site_hazard(
        args.lat, args.lon, T1x, T1y, site_class=args.site_class,
        risk_category={"I_II": "II"}.get(rc, rc), vs30=args.vs30,
        return_period=args.return_period, T_lower=lo, T_upper=hi,
        conditioning_periods=cps, sigma_model=sigma,
        design=design, deaggs=deaggs, fetch=not args.offline,
    )
    hz = dict(hz)
    hz["india_authoritative"] = False
    hz["jurisdiction"] = "usa_scaffolding"
    path = os.path.join(out, "site_hazard.json")
    json.dump(hz, open(path, "w", encoding="utf-8"), indent=1)
    print("wrote", path)
    d = hz["design"]
    print("[hazard] SDS %.3f SD1 %.3f (package %.3f / %.3f) SMS %.3f SM1 %.3f TL %s SDC %s" % (
        d["sds"], d["sd1"], pkg.basis.SDS, pkg.basis.SD1, d["sms"], d["sm1"], d["tl"], d["sdc"]))
    for c in hz["targets"]["cs"]:
        print("[hazard] CS at T* %.2f s: M %.2f R %.1f km eps %.2f (%s, %d yr)" % (
            c["T_star"], c["M"] or 0, c["R_km"] or 0, c["eps"], c["imt"], c["return_period"]))
    if hz.get("envelope"):
        print("[hazard] CS envelope / MCE_R over %.2f-%.2f s: min %.2f, >= MCE_R over %.0f%% of the range" % (
            lo, hi, hz["envelope"]["min_ratio_to_mcer"], 100 * hz["envelope"]["covered_share"]))
    nf = hz["near_fault"]
    print("[hazard] near-fault: %s" % (
        "YES -- %s, pulse share %.0f%%" % (
            ", ".join("%s (M %.1f, %.0f km, %.0f%%)" % (x["name"], x["M"], x["R_km"], x["contribution_pct"])
                      for x in nf["sources"][:4]),
            100 * nf["pulse_fraction"],
        ) if nf["near_fault"] else "no"))
    if abs(d["sds"] - (pkg.basis.SDS or 0)) > 0.05 or abs(d["sd1"] - (pkg.basis.SD1 or 0)) > 0.05:
        print("!! the package's SDS/SD1 differ from the USGS values for this site -- the linear design basis needs a second look")
    try:
        _hazard_html(out, hz, lo, hi)
    except Exception as ex:  # noqa: BLE001
        print("[hazard] figure skipped:", ex)


def _hazard_html(out, hz, lo, hi):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from . import site_hazard as SH, report as RP
    import numpy as np
    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    t = hz["targets"]; mp = t["mcer_multi_period"]
    ax.plot([max(x, 0.01) for x in mp["periods"]], mp["sa"], color="#b3261e", lw=2.2, label="multi-period MCE$_R$ (USGS, 16.2.1.1)")
    d = hz["design"]
    if d.get("tl") and d.get("sds"):
        from . import ground_motions as GM
        T = np.geomspace(0.02, 10, 120); ax.plot(T, GM.target_mcer(T, d["sds"], d["sd1"], d["tl"]), color="#b3261e", lw=1, ls="--", label="1.5 x two-period design spectrum (11.4.6)")
    for c in t["cs"]:
        ax.plot(c["periods"], c["sa"], lw=1.8, label="CS at T* = %.2f s (M %.1f, R %.0f km, ε %.2f)" % (c["T_star"], c["M"] or 0, c["R_km"] or 0, c["eps"]))
        ax.axvline(c["T_star"], color="#999", lw=0.7, ls=":")
    ax.axvspan(lo, hi, color="#f0ad4e", alpha=0.15, label="period range 16.2.3.1: %.2f–%.2f s" % (lo, hi))
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("period (s)"); ax.set_ylabel("Sa (g), 5% damped, maximum direction"); ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7.5)
    ax.set_title("Site-specific targets for the Chapter 16 suite", fontsize=11)
    png = RP._png(fig)
    html = ("<style>%s</style><title>Site hazard</title><h1>Site-specific hazard for the Chapter 16 suite</h1>%s<figure><img src='%s'><figcaption>Targets: the USGS multi-period MCE<sub>R</sub> spectrum (Method 1) and the conditional spectra at the conditioning period(s) (Method 2, 16.2.1.2).</figcaption></figure>"
            "<p>Sources: %s.</p><p class='note'>The conditional spectra use a constant-ε reading of the disaggregation and the σ<sub>ln</sub>(T) curve recorded in site_hazard.json (%s); at T* the CS equals the MCE<sub>R</sub> regardless of σ.</p>"
            % (RP.CSS, SH.hazard_summary_html(hz), png, "; ".join(hz["sources"]), hz["sigma_model"]["source"]))
    open(os.path.join(out, "site_hazard.html"), "w", encoding="utf-8").write(html)
    print("wrote", os.path.join(out, "site_hazard.html"))


def cmd_criteria(args):
    from . import design_criteria as DC
    docx, html = DC.write(args.package, out=args.out, project=args.project, engineer=args.engineer, reviewer=args.reviewer, params_path=args.params, risk_category=args.risk_category)
    print("wrote", docx); print("wrote", html)


def cmd_library(args):
    from . import site_hazard as SH
    idx = SH.scan_folder(args.folder, write_index=True)
    known = sum(1 for r in idx["records"] if r.get("M") is not None)
    print("%s: %d pairs indexed (%d with M / R metadata, %d flagged pulse) -> %s" % (args.folder, len(idx["records"]), known, sum(1 for r in idx["records"] if r.get("pulse")), os.path.join(args.folder, "index.json")))


def _modal_and_range(pkg, prm, ch16, loads):
    from pushover import nonlinear_model as NM
    from . import model as MD, ground_motions as GM
    PG = NM.column_gravity_axials(pkg, loads)
    hinges, stats, elastic = MD.build(pkg, prm, ch16, PG)
    modal = MD.modal(pkg, 12)
    lo, hi = GM.period_range(modal["T1x"], modal["T1y"], modal["T90"], ch16["period_range"]["upper_factor"])
    print("[modal] T1x=%.3f T1y=%.3f T90=%s  cum mass X %.2f Y %.2f -> period range %.2f-%.2f s" % (modal["T1x"], modal["T1y"], modal["T90"], modal["cum_x"], modal["cum_y"], lo, hi))
    return PG, modal, lo, hi


def _damping(args, pkg, ch16, prm=None):
    """Viscous damping as a parameter (WP4.11): nl_plan.damping.xi / --xi; above the cap -> WARNING, never exit."""
    from pushover import india_model as IMD
    plan = IMD.load_nl_plan(pkg) if _is_india(pkg) else {}
    dp = (plan.get("damping") or {}) if isinstance(plan, dict) else {}
    pdmp = (prm.get("damping") or {}) if isinstance(prm, dict) else {}          # NL-6: India parameter-file block
    src = ("--xi" if getattr(args, "xi", None) is not None else
           ("nl_plan.damping.xi (EOR)" if dp.get("xi") else "hinge_params damping.xi_default (modelling assumption)"))
    xi = float(args.xi if getattr(args, "xi", None) is not None else (dp.get("xi") or pdmp.get("xi_default") or 0.025))
    # the reference is IS 1893 (Part 1):2016 7.2.4 (5 %: the damping of the elastic spectrum the records are scaled to);
    # no ASCE 16.3.5 cap on the India path
    cap = float(dp.get("xi_cap") or pdmp.get("xi_cap") or 0.05)
    basis = dp.get("basis") or (
        "Rayleigh %.1f %% at T1 and 0.2 T1 (%s); mass-proportional on all nodes, stiffness-proportional on the frame "
        "elements only. IS 1893 (Part 1):2016 7.2.4: 5 %% for estimating Ah -- the target spectrum is 5 %%-damped; the "
        "hysteretic energy is modelled by the fibres, so the viscous part is a modelling assumption below the 7.2.4 "
        "value" % (100 * xi, src))
    warn = None
    if xi > cap:
        warn = ("xi %.3f exceeds %.3f (IS 1893 7.2.4 reference) -- continuing; viscous damping above the code value "
                "double-counts the hysteretic dissipation (EOR parameter)" % (xi, cap))
        print("[damping] WARNING:", warn)
    ch16["damping"]["xi_used"] = xi
    return dict(xi=xi, cap=cap, basis=basis, warning=warn, source=src,
                reference=dict(value=0.05, clause="IS 1893 (Part 1):2016 7.2.4", role="reference (Ah); not the model's viscous damping"))


def _india_prepare(args, pkg, prm, ch16):
    """India gravity (IS seismic weight, WP4.8), model build, modal to 90 %% and the period range."""
    from pushover import india_model as IMD, nonlinear_model as NM
    from . import ground_motions as GM
    loads, gtab = IMD.is_gravity_loads(pkg)
    W = sum(r["W_kN"] for r in gtab)
    split = dict(sum_D=sum(r["QG_kip"] for r in gtab), sum_Lexp=0.0, ratio=0.0, no_live_case_needed=False,
                 basis="IS 1893 seismic weight per level (D + Table 10 imposed share); W = %.1f kN" % W)
    print("[gravity IS] sum W = %.1f kN (= mass·g, gate %s)" % (W, (pkg.calc or {}).get("_is_mass_gate", {}).get("ok")))
    PG, modal, lo, hi = _modal_and_range(pkg, prm, ch16, loads)
    return loads, gtab, split, PG, modal, lo, hi


def _gm_select(args, pkg, recs, sets, TL, lo, hi, level, modal):
    from . import ground_motions as GM
    tgt, deagg, pf, hz = _target(args, pkg, level, modal, lo, hi)
    gm, chosen = GM.select_and_scale(recs, pkg.basis.SDS, pkg.basis.SD1, TL, lo, hi, n_select=args.n, target=tgt, deagg=deagg,
                                     pulse_fraction=pf, sf_bounds=_sf_bounds(args, pkg), sets=sets)
    if _is_india(pkg):
        from .report_india import GM_BASIS_INDIA
        gm["gm_basis"] = GM_BASIS_INDIA; gm["level"] = level
    return gm, chosen, hz


def cmd_scale(args):
    from . import ground_motions as GM, model as MD
    pkg, prm, ch16, TL = _load(args)
    if _is_india(pkg):
        _target_kind(args, pkg)
        loads, gtab, split, PG, modal, lo, hi = _india_prepare(args, pkg, prm, ch16)
        sets, recs = _library(args)
        out = args.out or os.path.join(str(pkg.root), "nlrha"); os.makedirs(out, exist_ok=True)
        allgm = {}
        for lv in _levels(args, pkg):
            gm, chosen, hz = _gm_select(args, pkg, recs, sets, TL, lo, hi, lv, modal)
            allgm[lv] = gm
            os.makedirs(os.path.join(out, lv), exist_ok=True)
            json.dump(dict(modal=modal, gm=gm), open(os.path.join(out, lv, "gm_scaling.json"), "w"), indent=1, default=str)
        json.dump(dict(modal=modal, levels=allgm), open(os.path.join(out, "gm_scaling.json"), "w"), indent=1, default=str)
        print("wrote", os.path.join(out, "gm_scaling.json"))
        return
    loads, gtab, split = MD.ch16_gravity(pkg, ch16)
    PG, modal, lo, hi = _modal_and_range(pkg, prm, ch16, loads)
    sets, recs = _library(args)
    tgt, deagg, pf, hz = _target(args, pkg)
    gm, chosen = GM.select_and_scale(recs, pkg.basis.SDS, pkg.basis.SD1, TL, lo, hi, n_select=args.n, target=tgt, deagg=deagg, pulse_fraction=pf, sf_bounds=_sf_bounds(args), sets=sets)
    out = args.out or os.path.join(str(pkg.root), "nlrha"); os.makedirs(out, exist_ok=True)
    json.dump(dict(modal=modal, gm={k: v for k, v in gm.items()}), open(os.path.join(out, "gm_scaling.json"), "w"), indent=1, default=str)
    print("wrote", os.path.join(out, "gm_scaling.json"))


def cmd_report(args):
    """Rebuild the report from raw_results.pkl (after a report-code fix; no re-analysis)."""
    import pickle
    from . import acceptance as AC, report as RP
    pkg, prm, ch16, TL = _load(args)
    out = args.out or os.path.join(str(pkg.root), "nlrha")
    if _is_india(pkg):
        return _report_india(args, pkg, prm, out)
    d = pickle.load(open(os.path.join(out, "raw_results.pkl"), "rb"))
    rc = AC.risk_category(pkg, args.risk_category); print("[16.4] Risk Category", rc.replace("_", "/"))
    acc = AC.evaluate(d["results"], pkg, d["ch16"], d["PG"], d["split"], 1.5 * pkg.basis.SDS, Ie=pkg.basis.Ie or 1.0, rc=rc)
    pdir = args.pushover_dir or os.path.join(str(pkg.root), "pushover"); pp = None
    if os.path.exists(os.path.join(pdir, "pushover_package.json")):
        pp = json.load(open(os.path.join(pdir, "pushover_package.json")))
    print("wrote", RP.write(out, pkg, d["ch16"], prm, d["gm"], d["results"], acc, d["gtab"], d["split"], d["modal"], sum(r["seconds"] for r in d["results"]), pushover_pkg=pp))
    _viewer(out, pkg, prm, d["ch16"], d["gm"], d["results"], acc, d["modal"], d["ch16"]["damping"].get("xi_used", 0.025), pp)


def _pushover_pkg(args, pkg):
    pdir = getattr(args, "pushover_dir", None) or os.path.join(str(pkg.root), "pushover")
    pth = os.path.join(pdir, "pushover_package.json")
    return json.load(open(pth)) if os.path.exists(pth) else None


def _summarise_level(pkg, d, level, pp):
    from . import response_summary as RS
    modal = d["modal"]
    T1 = max(modal["T1x"], modal["T1y"])
    fc = RS.fc_columns(d["results"], pkg, d["PG"])
    return RS.summarise(d["results"], pkg, level, d["gm"].get("target_label"), T1=T1, pushover_pkg=pp, fc_rows=fc)


def _finish_india(args, pkg, prm, out, per_level, modal, numerics, hz, t0):
    """Write per-level reports, the index package and -- at the END -- the COMPLETE-gate file (WP4.10)."""
    from . import report_india as RI, india_authority as IA
    level_summaries = {}
    for lv, (d, summ) in per_level.items():
        odir = os.path.join(out, lv)
        rp = RI.write_level(odir, pkg, d["gm"], d["results"], summ, modal, numerics, sum(r.get("seconds", 0) for r in d["results"]), prm=prm)
        level_summaries[lv] = (summ, os.path.join(odir, "nlrha_package.json"))
        print("[%s] wrote %s | records %d/%d converged | max mean drift %s | mean V/VB %s | non-vacuous %s" % (
            lv, rp, summ["n_converged"], summ["n_records"],
            ("%.3f%%" % (100 * summ["max_mean_drift"])) if summ["max_mean_drift"] is not None else "n/a",
            ("%.2f" % summ["base_shear"]["mean_over_VB"]) if summ["base_shear"].get("mean_over_VB") else "n/a",
            summ["non_vacuous"]["ok"]))
    idx = RI.write_index(out, pkg, level_summaries, modal, numerics, hz)
    print("wrote", idx, "(%.0f s)" % (time.time() - t0))
    try:
        st = IA.write_complete_gate(str(pkg.root))
        print("[gate] design_status=%s reasons=%s" % (st["status"], "; ".join(st["reasons"])[:300]))
    except Exception as ex:  # noqa: BLE001
        print("[gate] skipped:", ex)


def _report_india(args, pkg, prm, out):
    import pickle
    t0 = time.time()
    pp = _pushover_pkg(args, pkg)
    per_level, modal, numerics, hz = {}, None, {}, None
    for lv in ("DBE", "MCE"):
        pth = os.path.join(out, lv, "raw_results.pkl")
        if not os.path.exists(pth):
            continue
        d = pickle.load(open(pth, "rb"))
        modal = d["modal"]; numerics = d.get("numerics") or {}; hz = d.get("hazard")
        per_level[lv] = (d, _summarise_level(pkg, d, lv, pp))
    if not per_level:
        sys.exit("no <out>/DBE|MCE/raw_results.pkl to report from")
    _finish_india(args, pkg, prm, out, per_level, modal, numerics, hz, t0)


def _run_india(args, pkg, prm, ch16, TL, t0):
    import pickle
    from . import run as RN
    _target_kind(args, pkg)
    plast = str(getattr(args, "plasticity", None) or "fibre").lower()
    if plast not in ("fibre", "fiber"):
        print("[nlrha] India: fibre plasticity is used (member strains/rotations and IS 2062 steel per section); "
              "--plasticity %s ignored" % plast)
    os.environ["SNL_PLASTICITY"] = "fibre"; prm.setdefault("numerics", {})["plasticity"] = "fibre"
    damp = _damping(args, pkg, ch16, prm)
    loads, gtab, split, PG, modal, lo, hi = _india_prepare(args, pkg, prm, ch16)
    if not modal.get("spurious_ok", True):
        print("[modal] WARNING spurious modes %s (T > 5 T1, < 1 %% mass)" % modal.get("spurious_modes"))
    tors_mode = str(getattr(args, "accidental_torsion", None) or "pos").lower()
    torsion = None if tors_mode == "off" else dict(sx=(1 if tors_mode == "pos" else -1), sy=(1 if tors_mode == "pos" else -1), e_ratio=0.05)
    numerics = dict(plasticity="fibre", member_nseg=int(os.environ.get("SNL_MEMBER_NSEG") or 4), damping=damp,
                    torsion=dict(mode=tors_mode, **(torsion or {}), clause="IS 1893 7.8.2 (0.05 b), default on for India"),
                    integrator=args.integrator, dt_s=args.dt, gravity=split["basis"])
    sets, recs = _library(args)
    out = args.out or os.path.join(str(pkg.root), "nlrha"); os.makedirs(out, exist_ok=True)
    pp = _pushover_pkg(args, pkg)
    per_level, hz = {}, None
    for lv in _levels(args, pkg):
        gm, chosen, hz = _gm_select(args, pkg, recs, sets, TL, lo, hi, lv, modal)
        sel = list(range(1, len(chosen) + 1))
        only = getattr(args, "only_records", None)
        if only:
            sel = [int(x) for x in str(only).replace(" ", "").split(",") if x]
        elif args.records:
            a, b = args.records.split("-"); sel = list(range(int(a), int(b) + 1))
        sample_brace = None
        jobs = [(str(pkg.root), args.params, ch16, PG, loads, chosen[i - 1], damp["xi"], args.dt, args.free_vib, sample_brace,
                 args.integrator, torsion) for i in sel]
        print("[nlrha %s] %d records (suite of %d), scale factors %.3f-%.3f" % (lv, len(jobs), len(chosen),
              min(r["sf"] for r in chosen), max(r["sf"] for r in chosen)), flush=True)
        if args.parallel > 1:
            import multiprocessing as mp
            with mp.get_context("spawn").Pool(args.parallel) as pool:
                results = pool.map(RN.run_record_worker, jobs)
        else:
            results = [RN.run_record_worker(j) for j in jobs]
        odir = os.path.join(out, lv); os.makedirs(odir, exist_ok=True)
        d = dict(results=results, gm=gm, modal=modal, gtab=gtab, split=split, PG=PG, ch16=ch16, numerics=numerics,
                 hazard=hz, level=lv, selected_indices=sel)
        with open(os.path.join(odir, "raw_results.pkl"), "wb") as f:
            pickle.dump(d, f)
        json.dump(dict(modal=modal, gm=gm), open(os.path.join(odir, "gm_scaling.json"), "w"), indent=1, default=str)
        per_level[lv] = (d, _summarise_level(pkg, d, lv, pp))
    _finish_india(args, pkg, prm, out, per_level, modal, numerics, hz, t0)


def cmd_run(args):
    from . import ground_motions as GM, model as MD, run as RN, acceptance as AC, report as RP
    from pushover import nonlinear_model as NM
    t0 = time.time()
    if getattr(args, "member_nseg", None) is not None:
        os.environ["SNL_MEMBER_NSEG"] = str(args.member_nseg)
    if getattr(args, "member_nseg", None) is not None:
        os.environ["SNL_MEMBER_NSEG"] = str(args.member_nseg)
    if getattr(args, "plasticity", None):
        os.environ["SNL_PLASTICITY"] = str(args.plasticity)
    pkg, prm, ch16, TL = _load(args)
    if _is_india(pkg):
        return _run_india(args, pkg, prm, ch16, TL, t0)
    if args.xi is None:
        args.xi = 0.025
    if not getattr(args, "plasticity", None):
        args.plasticity = "imk"
    if getattr(args, "plasticity", None):
        os.environ["SNL_PLASTICITY"] = str(args.plasticity)
        prm.setdefault("numerics", {})["plasticity"] = args.plasticity
    if getattr(args, "member_nseg", None) is not None:
        prm.setdefault("numerics", {})["member_nseg"] = int(args.member_nseg)
    if args.xi > ch16["damping"]["xi_max"]:
        print("[damping] WARNING: xi %.3f exceeds the 16.3.5 cap of %.3f (USA scaffolding) -- continuing" % (args.xi, ch16["damping"]["xi_max"]))
    ch16["damping"]["xi_used"] = args.xi
    loads, gtab, split = MD.ch16_gravity(pkg, ch16)
    print("[gravity 16.3.2] sum D %.0f kip, sum 0.5L %.0f kip, ratio %.2f -> no-live case %s" % (split["sum_D"], split["sum_Lexp"], split["ratio"], "REQUIRED" if split["no_live_case_needed"] else "not required"))
    PG, modal, lo, hi = _modal_and_range(pkg, prm, ch16, loads)
    sets, recs = _library(args)
    tgt, deagg, pf, hz = _target(args, pkg)
    gm, chosen = GM.select_and_scale(recs, pkg.basis.SDS, pkg.basis.SD1, TL, lo, hi, n_select=args.n, target=tgt, deagg=deagg, pulse_fraction=pf, sf_bounds=_sf_bounds(args), sets=sets)
    sel = range(1, len(chosen) + 1)
    only = getattr(args, "only_records", None)
    if only:
        sel = [int(x) for x in str(only).replace(" ", "").split(",") if x]
        bad = [i for i in sel if i < 1 or i > len(chosen)]
        if bad:
            sys.exit("--only-records out of range for --n %d suite: %s" % (args.n, bad))
    elif args.records:
        a, b = args.records.split("-"); sel = range(int(a), int(b) + 1)
    sample_brace = next((t for t, e in ((e["tag"], e) for e in pkg.model.elements) if pkg.schedule.get(t, {}).get("member") == "brace"), None)
    results = []
    jobs = [(str(pkg.root), args.params, ch16, PG, loads, chosen[i - 1], args.xi, args.dt, args.free_vib, sample_brace, args.integrator) for i in sel]
    ch16["damping"]["integrator"] = args.integrator; ch16["damping"]["dt_s"] = args.dt
    early_nc = int(getattr(args, "early_abort_nc", 0) or 0)
    early_aborted = False
    if args.parallel > 1 and early_nc <= 0:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(args.parallel) as pool:
            results = pool.map(RN.run_record_worker, jobs)
    elif args.parallel > 1 and early_nc > 0:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(args.parallel) as pool:
            for out in pool.imap(RN.run_record_worker, jobs):
                results.append(out)
                n_nc = sum(1 for r in results if not r.get("converged"))
                if n_nc >= early_nc:
                    early_aborted = True
                    print("[nlrha] early abort: %d NC (≥%d) — abandoning remaining records; next mesh/method"
                          % (n_nc, early_nc), flush=True)
                    pool.terminate()
                    break
    else:
        for j in jobs:
            results.append(RN.run_record_worker(j))
            if early_nc > 0:
                n_nc = sum(1 for r in results if not r.get("converged"))
                if n_nc >= early_nc:
                    early_aborted = True
                    print("[nlrha] early abort: %d NC (≥%d) — abandoning remaining records; next mesh/method"
                          % (n_nc, early_nc), flush=True)
                    break
    out = args.out or os.path.join(str(pkg.root), "nlrha"); os.makedirs(out, exist_ok=True)
    import pickle
    with open(os.path.join(out, "raw_results.pkl"), "wb") as f:            # never lose a 30-minute suite to a report bug
        pickle.dump(dict(results=results, gm=gm, modal=modal, gtab=gtab, split=split, PG=PG, ch16=ch16), f)
    SMS = 1.5 * pkg.basis.SDS
    rc = AC.risk_category(pkg, args.risk_category); print("[16.4] Risk Category", rc.replace("_", "/"))
    acc = AC.evaluate(results, pkg, ch16, PG, split, SMS, Ie=pkg.basis.Ie or 1.0, rc=rc)
    acc.setdefault("meta", {})["early_aborted"] = bool(early_aborted)
    acc["meta"]["early_abort_nc"] = early_nc
    acc["meta"]["n_nc"] = sum(1 for r in results if not r.get("converged"))
    v = acc["verdict"]
    print("[16.4] unacceptable %d/%d (allowed %d) | mean drift max %.2f%% vs %.2f%% -> %s | deformation CP ok %s valid-range ok %s | force-controlled ok %s | OVERALL %s"
          % (v["n_unacceptable"], v["n_records"], v["unacceptable_allowed"], 100 * (v["mean_drift_max"] or 0), 100 * acc["limits"]["mean_limit"], v["mean_drift_ok"],
             v["deformation_ok"], v["valid_range_ok"], v["force_controlled_ok"], "ACCEPTABLE" if v["overall"] else "NOT ACCEPTABLE"))
    pp = None
    pdir = args.pushover_dir or os.path.join(str(pkg.root), "pushover")
    if os.path.exists(os.path.join(pdir, "pushover_package.json")):
        pp = json.load(open(os.path.join(pdir, "pushover_package.json")))
    html = RP.write(out, pkg, ch16, prm, gm, results, acc, gtab, split, modal, time.time() - t0, pushover_pkg=pp)
    print("wrote", html, "(%.0f s)" % (time.time() - t0))
    _viewer(out, pkg, prm, ch16, gm, results, acc, modal, args.xi, pp)


def _viewer(out, pkg, prm, ch16, gm, results, acc, modal, xi, pp):
    """nlrha_viewer_3d.html (Steltic viewer bundle). Never lets a viewer problem hide the report."""
    try:
        from . import viewer3d as V3
        print("wrote", V3.write(out, pkg, prm, ch16, gm, results, acc, modal, xi, pushover_pkg=pp))
    except Exception as ex:                                            # noqa: BLE001
        print("[viewer] skipped:", ex)


def _sf_bounds(args, pkg=None):
    """EOR scale-factor bounds: --sf-bounds, else nl_plan.gm_selection.sf_bounds (India)."""
    v = getattr(args, "sf_bounds", None)
    if not v and pkg is not None and _is_india(pkg):
        from pushover import india_model as IMD
        b = ((IMD.load_nl_plan(pkg).get("gm_selection") or {}).get("sf_bounds"))
        if b:
            return (float(b[0]), float(b[1]))
    if not v:
        return None
    lo, hi = str(v).split("-") if "-" in str(v) else str(v).split(",")
    return (float(lo), float(hi))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nlrha"); sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scale", "run", "report", "hazard"):
        p = sub.add_parser(name); p.add_argument("package"); p.add_argument("--out"); p.add_argument("--n", type=int, default=11)
        p.add_argument("--params"); p.add_argument("--site-class", default="D")
        p.add_argument("--records-set", nargs="*", default=None, help="record set folder(s): indexed sets (index.json) and/or user folders of PEER .AT2 / CSV pairs (indexed on the fly); default = the shipped FEMA P-695 far-field set")
        p.add_argument("--risk-category", help="I, II, III or IV (default: read from cfg.py, else from Ie)")
        if name in ("scale", "run"):
            p.add_argument("--target", default=None, choices=["code", "mcer", "cs", "is1893"], help="scaling target (default: is1893 for India = IS 1893 ELASTIC spectrum, no R; code for USA). India refuses code/mcer/cs without --usgs-scaffolding")
            p.add_argument("--usgs-scaffolding", action="store_true", help="allow the USA code/mcer/cs targets on an India package (regression only)")
            p.add_argument("--level", default="both", choices=["DBE", "MCE", "both", "dbe", "mce"], help="India NL hazard level(s): DBE=(Z/2)·I·Sa/g, MCE=Z·I·Sa/g (default both)")
            p.add_argument("--accidental-torsion", default="pos", choices=["off", "pos", "neg"], help="India: shift the centre of mass by ±0.05 b in X and Y (IS 1893 7.8.2); default pos")
            p.add_argument("--site-hazard", help="site_hazard.json written by `nlrha hazard` (default <package>/nlrha/site_hazard.json)")
            p.add_argument("--cs-period", type=float, help="which conditioning period of the site hazard to use with --target cs (default: the first)")
            p.add_argument("--pulse-fraction", type=float, default=None, help="share of the suite reserved for pulse-type records (default: the near-fault screen of the site hazard, else 0)")
            p.add_argument("--sf-bounds", help="keep only records whose shape-fit scale factor lies in lo-hi (e.g. 0.25-4)")
        if name == "hazard":
            p.add_argument("--lat", type=float, default=None, help="latitude (USGS scaffolding path)")
            p.add_argument("--lon", type=float, default=None, help="longitude (USGS scaffolding path)")
            p.add_argument("--india", action="store_true", help="force IS 1893 zone/Z hazard path (default on this fork when zone set)")
            p.add_argument("--usgs", action="store_true", help="force USGS ASCE 7-22 scaffolding (not India authority)")
            p.add_argument("--zone", help="IS 1893 seismic zone II|III|IV|V")
            p.add_argument("--soil-type", dest="soil_type", help="IS 1893 soil type I|II|III (rock/medium/soft)")
            p.add_argument("--importance", type=float, help="IS 1893 importance factor I (Table 8)")
            p.add_argument("--R-factor", dest="R_factor", type=float, help="IS 1893 response reduction factor R")
            p.add_argument("--Z", type=float, help="override zone factor Z (cite in nl_plan if not Table 3)")
            p.add_argument("--vs30", type=float, help="Vs30 for USGS disaggregation (scaffolding)")
            p.add_argument("--return-period", type=int, default=2475, help="USGS disaggregation return period years (default 2475)")
            p.add_argument("--cs-period", nargs="*", help="conditioning period(s) for USGS conditional spectra")
            p.add_argument("--t1", type=float, help="skip the model build and use this first-mode period (s)")
            p.add_argument("--sigma", help="JSON {periods:[...], sigma:[...]} overriding sigma_ln(T) (USGS CS)")
            p.add_argument("--offline", action="store_true", help="do not call USGS; use --design-json / --deagg-json")
            p.add_argument("--design-json", help="saved USGS ASCE 7-22 fetch_design output (scaffolding)")
            p.add_argument("--deagg-json", help="saved USGS disaggregations (scaffolding)")
        if name == "report":
            p.add_argument("--pushover-dir"); p.add_argument("--site-hazard")
        if name == "run":
            p.add_argument("--pushover-dir"); p.add_argument("--dt", type=float, default=0.02); p.add_argument("--records")
            p.add_argument("--only-records", help="comma-separated 1-based suite indices to run (e.g. 4 or 4,5); preferred for Gate B FC refine")
            p.add_argument("--xi", type=float, default=None, help="viscous damping ratio (default nl_plan.damping.xi or 0.025); above the cap -> warning"); p.add_argument("--free-vib", type=float, default=5.0)
            p.add_argument("--parallel", type=int, default=1, help="worker processes (one OpenSees instance each)")
            p.add_argument("--integrator", default="hht", choices=["hht", "newmark"], help="HHT alpha=0.9 (default; damps spurious high modes) or Newmark average acceleration")
            p.add_argument("--member-nseg", type=int, default=None, help="member subdivisions (default: 4 fibre / 1 imk)")
            p.add_argument("--plasticity", default=None, choices=["fibre", "fiber", "imk"], help="India: fibre (always). USA: default imk=ModIMK; fibre=distributed forceBeamColumn")
            p.add_argument("--early-abort-nc", type=int, default=2, help="abandon remaining records once N are NC (0=disable; product default 2)")
    lib = sub.add_parser("library", help="index a folder of PEER .AT2 / CSV record pairs (writes index.json; reads PEER _SearchResults.csv metadata when present)")
    lib.add_argument("folder")
    cr = sub.add_parser("criteria", help="draft the 16.1.4 design criteria document (docx + html) from the package and whatever analyses exist")
    cr.add_argument("package"); cr.add_argument("--out", help="folder for design_criteria_16_1_4.docx/.html (default: the job folder)")
    cr.add_argument("--project"); cr.add_argument("--engineer"); cr.add_argument("--reviewer"); cr.add_argument("--params"); cr.add_argument("--risk-category")
    args = ap.parse_args(argv)
    {"scale": cmd_scale, "run": cmd_run, "report": cmd_report, "hazard": cmd_hazard, "library": cmd_library, "criteria": cmd_criteria}[args.cmd](args)


if __name__ == "__main__":
    main()
