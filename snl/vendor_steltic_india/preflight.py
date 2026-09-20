"""preflight.py -- R22 pre-analysis cfg linter. Cheap, engine-free checks run BEFORE the first
OpenSees solve so a mis-declared cfg is caught in seconds, not after a full pipeline run.
Returns a list of (severity, message); severity in {"ERROR","WARN"}. Non-blocking by design --
pipeline.design_and_report prints the findings and puts them in its return dict.

Legacy asce_sdc() is USA ASCE 7-22 (not authoritative on steltic_india; India zone/SD from IS 1893 RAG). Also --
engine-free so engine3d.py and report.py both import THIS implementation instead of keeping
divergent copies."""
import india_loads as _IL



def asce_sdc(SDS, SD1, S1=0.0, risk_cat="II"):
    """Seismic Design Category per ASCE 7-22 sec.11.6: the WORSE of Table 11.6-1 (SDS) and
    Table 11.6-2 (SD1), with the Risk Category IV column, after the S1 override:
    S1 >= 0.75 -> SDC E for Risk Category I-III, F for Risk Category IV."""
    rc4 = str(risk_cat).strip().upper() in ("IV", "4")
    if S1 is not None and float(S1) >= 0.75:
        return "F" if rc4 else "E"
    def _tab(x, rows):                       # rows: (upper_bound, SDC for RC I-III, SDC for RC IV)
        for thr, c123, c4 in rows:
            if float(x) < thr:
                return c4 if rc4 else c123
        return "D"                           # top row of both tables: D for every Risk Category
    c1 = _tab(SDS, [(0.167, "A", "A"), (0.33, "B", "C"), (0.50, "C", "D")])   # Table 11.6-1
    c2 = _tab(SD1, [(0.067, "A", "A"), (0.133, "B", "C"), (0.20, "C", "D")])  # Table 11.6-2
    return max(c1, c2)


def risk_cat_from_Ie(Ie):
    """Risk Category inferred from the seismic importance factor (Table 1.5-2)."""
    Ie = float(Ie or 1.0)
    return "IV" if Ie >= 1.5 else ("III" if Ie >= 1.25 else "II")


def sdc_of_cfg(cfg):
    """SDC for a cfg: explicit cfg['sdc'] wins, else derived from cfg['seis'] via asce_sdc()."""
    if cfg.get("sdc"):
        return str(cfg["sdc"]).strip().upper()
    s = cfg.get("seis") or {}
    return asce_sdc(float(s.get("SDS", 0) or 0), float(s.get("SD1", 0) or 0),
                    float(s.get("S1", 0) or 0), risk_cat_from_Ie(s.get("Ie", 1.0)))


# ---------------------------------------------------------------------------------------------
# ASCE 7-22 sec.16.1.2 drift relief -- cfg['drift_relief_16_1_2']
#
# "Where a nonlinear response history analysis (Chapter 16) is performed, ... the drift limits of
# sec.12.12.1 need not apply" -- for Risk Category I, II and III only. The Nonlinear module (SNL)
# writes this block when it hands a Chapter-16-verified design back for a lighter, drift-relaxed
# re-design; the agent copies it verbatim into cfg and sets cfg['drift_limit'] to 'linear_target'.
# The relief never applies to Risk Category IV (Ie >= 1.5), and the relaxed linear target may never
# exceed the Chapter 16 mean-drift limit itself. Every finding here is mirrored in consistency.py.
# ---------------------------------------------------------------------------------------------
RELIEF_KEY = "drift_relief_16_1_2"
RELIEF_REQUIRED = ("nlrha_mean_drift", "nlrha_limit", "linear_target")


def drift_relief(cfg):
    """The cfg['drift_relief_16_1_2'] block as a dict, or None when absent."""
    r = cfg.get(RELIEF_KEY) if isinstance(cfg, dict) else None
    return r if isinstance(r, dict) and r else None


def relief_active(cfg):
    """True when a well-formed 16.1.2 relief block is present AND the Risk Category permits it."""
    r = drift_relief(cfg)
    if r is None:
        return False
    Ie = float((cfg.get("seis") or {}).get("Ie", 1.0) or 1.0)
    if Ie >= 1.5:
        return False
    try:
        return all(float(r.get(k)) > 0 for k in RELIEF_REQUIRED)
    except (TypeError, ValueError):
        return False


def relief_findings(cfg):
    """(severity, message) findings for a cfg that carries the 16.1.2 relief block."""
    out = []
    r = drift_relief(cfg)
    if r is None:
        return out
    s = cfg.get("seis") or {}
    Ie = float(s.get("Ie", 1.0) or 1.0)
    dl = float(cfg.get("drift_limit", 0.020) or 0.020)
    if Ie >= 1.5:
        out.append(("ERROR", "cfg['%s'] present but Ie=%.2f (Risk Category IV): USA ASCE 7-22 16.1.2 (not India authority) keeps the "
                             "12.12.1 drift limits for RC IV -- remove the relief block and design to Table "
                             "12.12-1 (0.010)" % (RELIEF_KEY, Ie)))
        return out
    missing = [k for k in RELIEF_REQUIRED if not isinstance(r.get(k), (int, float)) or float(r.get(k)) <= 0]
    if missing:
        out.append(("ERROR", "cfg['%s'] is missing %s -- the relief must record the Chapter 16 result it rests "
                             "on (SNL writes these; do not invent them)" % (RELIEF_KEY, missing)))
        return out
    lim16 = float(r["nlrha_limit"]); tgt = float(r["linear_target"]); mean16 = float(r["nlrha_mean_drift"])
    if dl > lim16 + 1e-9:
        out.append(("ERROR", "drift_limit=%.4f exceeds the Chapter 16 mean-drift limit %.4f recorded in cfg['%s'] "
                             "-- a linear target above the 16.4.1.2 limit is not a relief, it is a mistake"
                             % (dl, lim16, RELIEF_KEY)))
    if abs(dl - tgt) > 1e-6:
        out.append(("WARN", "drift_limit=%.4f differs from the relief's linear_target=%.4f -- set cfg['drift_limit'] "
                            "to the target the Nonlinear module derived, or record why it changed" % (dl, tgt)))
    if mean16 > lim16:
        out.append(("ERROR", "cfg['%s'] records a Chapter 16 mean drift %.4f ABOVE its limit %.4f -- the relief "
                             "rests on an analysis that did not pass 16.4.1.2" % (RELIEF_KEY, mean16, lim16)))
    out.append(("WARN", "legacy ASCE 7-22 16.1.2 drift relief in force (defer India equivalent) (Risk Category %s): Table 12.12-1 need not apply; "
                        "linear design target %.4f from the Chapter 16 result (mean MCE_R drift %.4f vs %.4f). "
                        "The final design must be re-verified by a Chapter 16 analysis before issue."
                        % (risk_cat_from_Ie(Ie), tgt, mean16, lim16)))
    return out

# ASCE 7-22 Table 12.2-1 anchor values for the common steel SFRS (R, Cd, Om0, SDC-D height ft)
_SYS = {
    "smf":  (8.0, 5.5, 3.0, None), "imf": (4.5, 4.0, 3.0, 35.0),
    "ebf":  (8.0, 4.0, 2.0, 160.0), "brbf": (8.0, 5.0, 2.5, 160.0),
    "scbf": (6.0, 5.0, 2.0, 160.0), "ocbf": (3.25, 3.25, 2.0, 35.0),
    "spsw": (7.0, 6.0, 2.0, 160.0), "dual": (None, None, None, None),
    "c-psw": (6.5, 5.5, 2.5, 160.0), "stmf": (7.0, 5.5, 3.0, 160.0),
}


def _is_india_cfg(cfg):
    if not isinstance(cfg, dict):
        return False
    j = str(cfg.get("jurisdiction") or "").lower()
    lp = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    return j in ("india", "in", "bis", "is", "is_bis") or str(lp.get("jurisdiction") or "").lower() in ("india", "is", "bis")


INDIA_UNITS_OK = ("n-mm", "n-mm-s", "n-mm-sec", "m", "mm", "metric", "si", "india_si", "india_metric")


def india_checks(cfg):
    """WP1.3-1.13 India preflight block (replaces every ASCE requirement on India jobs)."""
    out = []
    say = lambda sev, msg: out.append((sev, msg))
    u = str(cfg.get("units") or "").strip().lower()
    if u not in INDIA_UNITS_OK:
        say("ERROR", "India jobs need an explicit cfg['units'] ('m' or 'mm' for geometry; engine runs N-mm) -- "
                     "got %r; the engine never guesses units (WP1.12)" % cfg.get("units"))
        return out
    try:
        from india_units import apply_metric_geometry
        apply_metric_geometry(cfg)
    except Exception as ex:
        say("ERROR", "unit conversion failed: %s" % ex)
        return out
    for sev, msg in _IL.validate_load_plan(cfg):
        say(sev, msg)
    H = [float(h) for h in (cfg.get("heights") or []) if isinstance(h, (int, float))]
    if not H:
        say("ERROR", "cfg['heights'] missing/empty"); return out
    dex = set(int(k) for k in (cfg.get("drift_exempt_stories") or {}))
    small = [(i, h) for i, h in enumerate(H, start=1) if h < 1800 and i not in dex]
    if small:
        say("ERROR", "storey height %s mm at storey %s looks like METRES -- engine lengths are mm" % (small[0][1], small[0][0]))
    for k in ("SX", "SY"):
        v = cfg.get(k)
        if isinstance(v, (int, float)) and 0 < v < 1500:
            say("ERROR", "%s=%g mm is < 1.5 m: bay spacing looks like METRES" % (k, v))
    for k in ("xcoords", "ycoords"):
        v = cfg.get(k)
        if v and max(abs(float(x)) for x in v) < 500:
            say("ERROR", "cfg['%s'] looks like METRES (max %g) -- give mm (they are not converted, WP1.12)" % (k, max(v)))
    # ---- gravity magnitudes (kN/m2) ----
    for k in ("D_floor", "D_roof", "L_floor", "Lr", "clad", "snow"):
        v = cfg.get(k)
        if isinstance(v, (int, float)) and v > 25.0:
            say("ERROR", "%s=%g kN/m2 is implausible (> 25) -- psf entered on the SI path? (WP1.12)" % (k, v))
    if cfg.get("Lr") is None:
        say("ERROR", "cfg['Lr'] (roof imposed load, IS 875 Part 2 Table 2: 0.75 or 1.5 kN/m2) required (WP2.1)")
    fs = str(cfg.get("floor_system") or "").lower()
    if "one-way" in fs or "one way" in fs:
        if str(cfg.get("deck_span") or "").upper() not in ("X", "Y"):
            say("ERROR", "floor_system is one-way: declare cfg['deck_span'] = 'X' or 'Y' (the deck span direction; "
                         "girders perpendicular to it carry the floor) -- WP2.7")
    # ---- seismic: IS 1893 inputs, no ASCE shims (WP1.13) ----
    import india_seismic_gates as G
    lp = cfg.get("load_plan") or {}
    ss = lp.get("seismic_summary") or {}
    if not cfg.get("no_seismic"):
        for k in ("Z", "zone", "I", "R", "soil", "Sa_g", "Ah", "Ta_s", "VB_kN", "W_kN"):
            if ss.get(k) is None and (cfg.get("seis") or {}).get(k) is None:
                say("ERROR", "load_plan.seismic_summary.%s missing (IS 1893 inputs replace SDS/SD1/Cd/Om0)" % k)
        for sev, msg in G.system_zone_findings(cfg):
            say(sev, msg)
        for msg in G.occupancy_findings(cfg):
            say("ERROR", "IS 1893 Table 8: " + msg)
        # 7.7.1 gate (WP1.3)
        ok_esm, why = G.esm_permitted(cfg, None)
        an = [str(a).upper() for a in (cfg.get("analyses") or [])]
        if not ok_esm and an and not any(a in ("RSA", "RS", "MRSA") for a in an):
            say("ERROR", "IS 1893 7.7.1: linear dynamic analysis required (%s) but analyses=%s -- add 'RSA' "
                         "(ESM alone only for regular buildings < 15 m in Zone II)" % (", ".join(why), an))
        # Ah / VB recomputed (6.4.2, 7.6.1, Table 7)
        try:
            import india_seismic as IS
            Z, I, R = float(ss["Z"]), float(ss["I"]), float(ss["R"])
            Ta = float(ss.get("Ta_s"))
            Ah = IS.design_Ah(Z, I, R, Ta, ss.get("soil"), "ESM")
            rho_min = {"II": 0.007, "III": 0.011, "IV": 0.016, "V": 0.024}.get(G.zone_of(cfg))
            Ah_d = max(Ah, rho_min or 0.0)
            if abs(float(ss["Ah"]) - Ah_d) > 0.01 * Ah_d:
                say("ERROR", "seismic_summary.Ah = %.5f but (Z/2)(I/R)(Sa/g)(Ta=%.3f s, ESM) = %.5f%s (6.4.2 / Table 7)"
                    % (float(ss["Ah"]), Ta, Ah, (" -> Table 7 minimum %.3f" % rho_min) if rho_min and rho_min > Ah else ""))
            VB, W = float(ss["VB_kN"]), float(ss["W_kN"])
            if abs(VB - float(ss["Ah"]) * W) > 0.01 * VB:
                say("ERROR", "seismic_summary VB_kN %.1f != Ah x W = %.1f (7.6.1)" % (VB, float(ss["Ah"]) * W))
            import engine3d as E
            try:
                E.build(cfg, "Linear")
                NF = len(cfg["heights"])
                We = sum(E.floor_w(cfg, k) for k in range(1, NF + 1)) / 1000.0
            except Exception as ex:
                say("ERROR", "model build failed (%s: %s) -- geometry / units inconsistent" % (type(ex).__name__, ex))
                return out
            if abs(We - W) > 0.02 * W:
                say("ERROR", "engine seismic weight %.1f kN differs from design W %.1f kN by %.1f %% (> 2 %%): W must be "
                             "full DL + self-weight + partitions (7.3.6) + Table 10 IL + 7.3.5 snow (WP1.6)"
                             % (We, W, 100 * (We - W) / W))
            if abs(VB - float(ss["Ah"]) * We) > 0.15 * VB:
                say("ERROR", "|VB - Ah x W_engine| > 15 %% (VB %.1f kN, Ah x W_engine %.1f kN) -- units? (WP1.12)"
                    % (VB, float(ss["Ah"]) * We))
            sc = _IL._story_force_scale(lp) if (lp.get("story_forces") or {}) else None
            for d in ("X", "Y"):
                sf = (lp.get("story_forces") or {}).get("EQ_" + d)
                if not sf:
                    say("ERROR", "load_plan.story_forces.EQ_%s missing" % d); continue
                tot = abs(sum(float((list(v) + [0, 0])[0 if d == "X" else 1]) for v in dict(sf).values())) * sc / 1000.0
                VBd = float(ss.get("VB_%s_kN" % d.lower(), VB))
                if abs(tot - VBd) > 0.02 * VBd:
                    say("ERROR", "sum of EQ_%s story forces %.1f kN differs from VB %.1f kN by > 2 %% (units / factored? "
                                 "story forces are UNFACTORED, WP1.1/1.12)" % (d, tot, VBd))
                if tot < 0.001 * We:
                    say("ERROR", "EQ_%s story forces sum to < 0.1 %% of W -- kip/kN entered as N? (WP1.12)" % d)
        except (KeyError, TypeError, ValueError) as ex:
            say("ERROR", "IS 1893 seismic summary incomplete / invalid: %s" % ex)
    if cfg.get("drift_relief_16_1_2"):
        say("ERROR", "cfg['drift_relief_16_1_2'] is an ASCE 7-22 16.1.2 artefact -- no drift relief exists in "
                     "IS 1893 (D3/D7); remove it")
    # ---- drift limit (WP1.9) ----
    dl = cfg.get("drift_limit")
    if dl not in (None, "") and float(dl) > 0.004 + 1e-12:
        say("ERROR", "drift_limit=%.4f exceeds IS 1893 7.11.1.1 (0.004 h); larger limits are not permitted" % float(dl))
    # ---- model declaration ----
    md = cfg.get("model")
    if not (isinstance(md, dict) and {"bases", "joints", "gravity"} <= set(md)):
        say("ERROR", "cfg['model'] = {'bases','joints','gravity'} declaration missing")
    dia = cfg.get("diaphragm", "rigid")
    if dia not in ("rigid", "flexible", "semi-rigid"):
        say("ERROR", "cfg['diaphragm'] must be 'rigid' | 'flexible' | 'semi-rigid' (got %r)" % (dia,))
    if not cfg.get("steel_grade"):
        say("ERROR", "cfg['steel_grade'] (IS 2062 grade, e.g. 'E250BR' / 'E350') required -- no default fy (WP2.3)")
    if cfg.get("braces") or "brace" in str(cfg.get("system") or "").lower() or "bf" in str(cfg.get("system") or "").lower():
        if str(cfg.get("brace") or "").upper().startswith(("CHS", "NB")) and not (cfg.get("brace_grade") and cfg.get("brace_process")):
            say("ERROR", "CHS braces need cfg['brace_grade'] (IS 1161 YSt ...) and cfg['brace_process'] (HFS/CDS/ERW)")
    try:
        from india_wind_tables import wind_findings
        for sev, msg in wind_findings(cfg):
            say(sev, msg)
    except ImportError:
        pass
    for sev, msg in _IL.crane_findings(cfg):
        say(sev, msg)
    return out


def check(cfg):
    if _is_india_cfg(cfg):
        return india_checks(cfg)
    # India metric briefs → SI-native N-mm (wave 1); kip-in only if units/force_kip_in opt-in
    try:
        from india_units import apply_metric_geometry, is_si
        apply_metric_geometry(cfg)
    except Exception:
        is_si = lambda _c=None: False  # noqa: E731

    out = []
    say = lambda sev, msg: out.append((sev, msg))
    if not isinstance(cfg, dict):
        return [("ERROR", "cfg is not a dict")]
    # ---- India load_plan (LIVE IS 875 / IS 1893 RAG) — mandatory ----
    for sev, msg in _IL.validate_load_plan(cfg):
        say(sev, msg)
    # ---- units ----
    H = [float(h) for h in (cfg.get("heights") or []) if isinstance(h, (int, float))]
    if not H:
        say("ERROR", "cfg['heights'] missing/empty")
    _dex0 = set(int(k) for k in (cfg.get("drift_exempt_stories") or {}))
    _si = False
    try:
        _si = is_si(cfg)
    except Exception:
        _si = str(cfg.get("units") or "").upper() in ("N-MM", "SI", "METRIC")
    if _si:
        # SI: heights in mm — storey < 1800 mm (~6 ft) looks like metres left unscaled
        _small = [(i, h) for i, h in enumerate(H, start=1) if h < 1800]
        _undeclared = [(i, h) for i, h in _small if i not in _dex0]
        if _undeclared:
            say("ERROR", "story height < 1800 mm found (%s mm, story %s): heights look like METRES "
                         "-- engine SI units are MILLIMETRES (3.6 m storey = 3600). Call "
                         "india_units.apply_si_geometry(cfg). If a small offset is INTENTIONAL, "
                         "declare cfg['drift_exempt_stories']."
                         % (_undeclared[0][1], _undeclared[0][0]))
        elif _small:
            say("WARN", "sub-1800-mm story height(s) at %s are DECLARED inter-diaphragm offsets "
                        "(drift_exempt_stories) -- OK" % [i for i, _ in _small])
        for k in ("SX", "SY"):
            v = cfg.get(k)
            if isinstance(v, (int, float)) and 0 < v < 1500:
                say("ERROR", "%s=%g mm is < 1.5 m: bay spacing looks like METRES "
                             "(engine SI uses millimetres)" % (k, v))
    else:
        _small = [(i, h) for i, h in enumerate(H, start=1) if h < 72]
        _undeclared = [(i, h) for i, h in _small if i not in _dex0]
        if _undeclared:
            say("ERROR", "story height < 6 ft found (%s in, story %s): heights look like FEET -- engine "
                         "units are INCHES (13 ft story = 156). If a small inter-level offset is "
                         "INTENTIONAL (split-level), declare it in cfg['drift_exempt_stories'] with a reason."
                         % (_undeclared[0][1], _undeclared[0][0]))
        elif _small:
            say("WARN", "sub-6-ft story height(s) at %s are DECLARED inter-diaphragm offsets "
                        "(drift_exempt_stories) -- OK; design the step transfer detail"
                        % [i for i, _ in _small])
        for k in ("SX", "SY"):
            v = cfg.get(k)
            if isinstance(v, (int, float)) and 0 < v < 60:
                say("ERROR", "%s=%g in is < 5 ft: bay spacing looks like FEET (engine uses inches)" % (k, v))
    # ---- seismic block ----
    s = cfg.get("seis") or {}
    for k in ("SDS", "SD1", "R", "Cd", "Ie"):
        if k not in s:
            say("ERROR", "cfg['seis'] missing '%s'" % k)
    sysname = str(cfg.get("system") or "").lower()
    if not sysname:
        say("ERROR", "cfg['system'] not declared (consistency.check will FAIL) -- set the exact SFRS")
    R = float(s.get("R") or 0)
    for key, (r0, cd0, om0, hlim) in _SYS.items():
        if key in sysname and key != "dual" and r0 is not None:
            if R and abs(R - r0) > 0.51 and "dual" not in sysname:
                say("WARN", "cfg['seis'] R=%.2f but system '%s' is normally R=%.2f (Table 12.2-1) -- "
                            "confirm the brief" % (R, cfg.get("system"), r0))
            if H and hlim and float(s.get("SDS", 0) or 0) >= 0.50:
                hn = sum(H) / 12.0
                if hn > hlim + 0.5:
                    say("WARN", "h_n=%.0f ft exceeds the ~%.0f ft SDC-D Table 12.2-1 limit for '%s' -- "
                                "FLAG and resolve (12.2.5.4 increase / dual system / 12.2.1.1)"
                                % (hn, hlim, key.upper()))
            break
    # ---- IS 1893 Part 1:2016 storey drift limit (cl.7.11.1.1) ----
    # Default 0.004 h under VB with γ=1.0. ASCE Table 12.12-1 / ρ rules: found:false (see india_seismic.TODO).
    Ie = float(s.get("Ie", 1.0) or 1.0)
    dl = float(cfg.get("drift_limit", 0.004) or 0.004)
    relief = drift_relief(cfg)
    if relief is not None:
        say("WARN", "cfg['%s'] is a USA ASCE 7-22 16.1.2 artefact — India analogue found:false; "
                    "do not treat as IS 1893 authority (see india_seismic.TODO)" % RELIEF_KEY)
        for sev, msg in relief_findings(cfg):
            say(sev, msg)
    if dl > 0.00401 and not cfg.get("drift_limit_rag_cite"):
        say("WARN", "drift_limit=%.4f exceeds IS 1893 cl.7.11.1.1 default 0.004 — set "
                    "cfg['drift_limit_rag_cite'] if a stricter/special limit was RAG-retrieved "
                    "(e.g. 0.002 for URM-infill storeys per Table 6 notes), else use 0.004" % dl)
    if dl < 0.001:
        say("WARN", "drift_limit=%.5f is unusually tight — confirm RAG cite" % dl)
    # Accidental: agent may still set ASCE-shaped SDC; do not apply 12.12.1.1 ρ divisor on India path.
    if cfg.get("rho") and float(cfg.get("rho") or 1) > 1.01:
        say("WARN", "cfg['rho']=%.2f present but IS 1893 has no ASCE 12.12.1.1 ρ drift divisor "
                    "(found:false) — drift gate uses cl.7.11.1.1 limit without /ρ" % float(cfg["rho"]))
    # ---- analyses vs R=3 ----
    if R and R <= 3.0 and "341" in str(cfg.get("system", "")):
        say("WARN", "R<=3: AISC 341 does NOT apply -- design to AISC 360 only and prove wind-vs-seismic")
    # ---- model declaration ----
    md = cfg.get("model")
    if not (isinstance(md, dict) and {"bases", "joints", "gravity"} <= set(md)):
        say("ERROR", "cfg['model'] = {'bases','joints','gravity'} declaration missing (HARD GATE "
                     "model_declared will FAIL)")
    # ---- diaphragm / split-level declarations (F-1) ----
    dia = cfg.get("diaphragm", "rigid")
    if dia not in ("rigid", "flexible", "semi-rigid"):
        say("ERROR", "cfg['diaphragm'] must be 'rigid' | 'flexible' | 'semi-rigid' (got %r)" % (dia,))
    dex = cfg.get("drift_exempt_stories") or {}
    if dex:
        for k, why in dict(dex).items():
            if not str(why).strip():
                say("ERROR", "drift_exempt_stories[%s] has no reason -- each exemption must carry a "
                             "one-line justification (e.g. 'split-level inter-diaphragm offset, step "
                             "ties designed')" % k)
        say("WARN", "drift gate will SKIP stories %s (declared inter-diaphragm offsets) -- their "
                    "racking must be addressed as a designed detail in calc_package"
                    % sorted(dict(dex).keys()))
    # ---- load sanity ----
    for k in ("D_floor", "L_floor"):
        v = cfg.get(k)
        if isinstance(v, (int, float)) and v > 400:
            say("WARN", "%s=%g psf is unusually high -- confirm units (psf)" % (k, v))
    _Lf = cfg.get("L_floor")
    if isinstance(_Lf, (int, float)) and _Lf >= 125 and not cfg.get("storage") \
            and not cfg.get("storage_levels"):
        say("WARN", "floor live suggests storage occupancy -- 12.7.2 requires >=25%% of storage live "
                    "in W; set cfg['storage'] (all floors) or cfg['storage_levels'] (L_floor=%g psf)" % _Lf)
    # ---- Tier A/B consultancy guards (EDGE_CASE_SWEEP) ----
    arch = (str(cfg.get("arch", "")) + " " + str(cfg.get("system", ""))).lower()
    if any(k in arch for k in ("gable", "pitch", "slope", "monoslope", "sloped")):
        say("WARN", "A2 sloped roof keywords in cfg: the engine models FLAT levels only -- model at the "
                    "mean roof height, then HAND-CHECK unbalanced/sliding snow (ASCE 7-22 7.6/7.9), eave "
                    "drift, and rafter thrust; state the idealization")
    if any(k in arch for k in ("platform", "rack", "vessel", "tank", "bin", "silo")):
        say("WARN", "B2 nonbuilding-structure keywords in cfg: Ch. 15 (NOT Ch. 12) R-values and "
                    "detailing apply -- confirm the system row in Table 15.4-1/2 before using any "
                    "building R")
    try:
        # B5 expansion/thermal screen — unit-aware (wave3).
        # USA kip-in: SX/SY in inches → plan ft = N*S/12; threshold ~300 ft.
        # India SI N-mm: SX/SY in mm → plan m = N*S/1000; threshold ~91.4 m (~300 ft).
        # Do NOT treat millimetre plan lengths as feet (SI false-positive).
        if _si:
            LX_m = float(cfg.get("NX", 0)) * float(cfg.get("SX", 0)) / 1000.0
            LY_m = float(cfg.get("NY", 0)) * float(cfg.get("SY", 0)) / 1000.0
            Lmax_m = max(LX_m, LY_m)
            if Lmax_m > 91.44:  # ~300 ft
                say("WARN", "B5 plan dimension %.1f m > ~91 m (~300 ft) jointless: record the "
                            "expansion/thermal decision in calc_package (joint located, or thermal "
                            "force statement). SI N-mm geometry." % Lmax_m)
            # else: short SI plan — no expansion_thermal WARN (not a false-positive seed)
        else:
            LX = float(cfg.get("NX", 0)) * float(cfg.get("SX", 0)) / 12.0
            LY = float(cfg.get("NY", 0)) * float(cfg.get("SY", 0)) / 12.0
            if max(LX, LY) > 300.0:
                say("WARN", "B5 plan dimension %.0f ft > ~300 ft jointless: record the expansion/thermal "
                            "decision in calc_package (joint located, or thermal force statement)" % max(LX, LY))
    except Exception:
        pass
    for k, v in dict(cfg.get("extra_mass_floors") or {}).items():
        try:
            if abs(float(v)) > float(cfg.get("D_floor", 100) or 100):
                say("WARN", "extra_mass_floors[%s]=%g psf exceeds |D_floor| -- confirm the sign/magnitude" % (k, v))
        except Exception:
            pass
    return out



def render(res):
    if not res:
        return "[preflight] R22: no findings -- cfg passes the pre-analysis checks"
    lines = ["[preflight] R22 cfg linter: %d finding(s) -- fix ERRORs BEFORE trusting any analysis:" % len(res)]
    for sev, msg in res:
        lines.append("  [%s] %s" % (sev, msg))
    return "\n".join(lines)
