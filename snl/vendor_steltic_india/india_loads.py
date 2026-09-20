"""
india_loads.py — India (IS/BIS) load path: LIVE RAG retrieval, not hardcoded formulas.

CRITICAL (steltic_india):
  USA steltic embeds ASCE 7-22 wind/seismic/LRFD combo math in the engine.
  India MUST NOT replace that with a permanent Python port of IS 875 / IS 1893.
  Every job the agent RAG-queries IS 875 Parts 1–5 and IS 1893 Part 1:2016 (same
  pattern as design RAG for IS 800), then writes the retrieved combination factors
  and story forces into cfg['load_plan']. This module only VALIDATES that plan and
  turns it into the (label, fD, fL, fLr, lateral, col_only) tuples the demand
  envelope already understands.

Schema (cfg['load_plan']):
  {
    "jurisdiction": "india",
    "partial_factors_cite": "IS 800:2007 Table 4 (or retrieved clause)",
    "retrieval": [   # REQUIRED — evidence of live RAG this job
      {"stem": "IS_875_Part_3_2015", "query": "...", "found": true,
       "cite": "§6.3 / Table …", "collection": "engineering_standards_IS875_P3"},
      {"stem": "IS_1893_Part_1_2016", "query": "...", "found": true, "cite": "…"},
      ...
    ],
    "story_forces_units": "N" | "kN",          # REQUIRED when story_forces are given (WP1.12)
    "story_forces": {"EQ_X": {"1": [Fx, Fy, Mz], ...}, "W_X": {...}, ...},  # UNFACTORED
    "combinations": [   # REQUIRED — explicit list, or "auto" -> india_combos.expand_combinations
      {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 1.5, "cite": "IS 800:2007 Table 4"},
      {"label": "1.2DL+1.2LL+1.2EQ_X", "fD": 1.2, "fL": 1.2, "fLr": 0.0,
       "fE": 1.2, "lateral_ref": "EQ_X", "cite": "IS 800 Table 4 + IS 1893 6.3"},
      {"label": "0.9DL-1.5W_Y", "fD": 0.9, "fL": 0.0, "fLr": 0.0, "fW": -1.5,
       "lateral_ref": "W_Y", "cite": "IS 800 Table 4"},
      ...
    ],
    "notes": "optional free text"
  }

WP1.1: story forces are UNFACTORED characteristic forces; every combination that references a
lateral pattern carries a REQUIRED lateral load factor fE (earthquake) or fW (wind) -- there is
no default -- and cases_from_load_plan multiplies every (fx, fy, mz) by it.  The factor must agree
with the label ("1.5EQ_X" -> |fE| = 1.5; a '-' before the term -> negative).
Engine units: N and N-mm (story_forces_units "kN" is converted x1000; kip is refused).
"""
from __future__ import annotations

import re as _re

# Canonical India load / seismic stems the agent must hit via RAG every job.
LOAD_STEMS = (
    "IS_875_Part_1_2026",   # dead loads
    "IS_875_Part_2_1987",   # imposed / live
    "IS_875_Part_3_2015",   # wind
    "IS_875_Part_4_1987",   # snow
    "IS_875_Part_5_1987",   # special loads / combinations notes
    "IS_1893_Part_1_2016",  # seismic
)

# Design stems (not loads, but listed for contract / retrieval plans).
DESIGN_STEMS = (
    "IS_800_2007",
    "IS_808_2021",
    "IS_816_1969",
    "IS_9595_1996",
    "IS_4000_1992",
    "IS_1161_2014",
    "IS_2062_Part_1_2025",
)

# Agent-facing RAG collection names → preferred document stem.
COLLECTION_TO_STEM = {
    "engineering_standards_IS800": "IS_800_2007",
    "engineering_standards_IS808": "IS_808_2021",
    "engineering_standards_IS816": "IS_816_1969",
    "engineering_standards_IS9595": "IS_9595_1996",
    "engineering_standards_IS4000": "IS_4000_1992",
    "engineering_standards_IS1161": "IS_1161_2014",
    "engineering_standards_IS2062": "IS_2062_Part_1_2025",
    "engineering_standards_IS875_P1": "IS_875_Part_1_2026",
    "engineering_standards_IS875_P2": "IS_875_Part_2_1987",
    "engineering_standards_IS875_P3": "IS_875_Part_3_2015",
    "engineering_standards_IS875_P4": "IS_875_Part_4_1987",
    "engineering_standards_IS875_P5": "IS_875_Part_5_1987",
    "engineering_standards_IS1893": "IS_1893_Part_1_2016",
    # short aliases
    "IS800": "IS_800_2007",
    "IS875_P3": "IS_875_Part_3_2015",
    "IS1893": "IS_1893_Part_1_2016",
}

STEM_TO_COLLECTION = {v: k for k, v in COLLECTION_TO_STEM.items()
                      if k.startswith("engineering_standards_")}


class LoadPlanError(ValueError):
    """cfg['load_plan'] missing, incomplete, or not RAG-backed."""


class Case(tuple):
    """A resolved load case.  Behaves like the legacy 6-tuple
    (label, fD, fL, fLr, lateral{k:(fx,fy,mz)} [already factored], col_only)
    and carries metadata in .meta: fLat, kind ('EQ'|'W'|None), direction, sign, torsion,
    fEv (vertical EQ factor x Av), rsa {dir: factor}, tags, family, cite, service, crane."""
    def __new__(cls, label, fD, fL, fLr, lateral, col_only, **meta):
        t = super().__new__(cls, (label, fD, fL, fLr, lateral, col_only))
        t.meta = dict(meta)
        return t

    def __reduce__(self):
        return (_rebuild_case, (tuple(self), self.meta))

    @property
    def label(self):
        return self[0]


def _rebuild_case(t, meta):
    return Case(*t, **meta)


LAT_FACTOR_KEYS = ("fE", "fW", "fLat")
# a lateral term in a label:  [+|-] factor (EQ|EL|WL|W) [_X|Y|Z]   e.g. "1.5DL-1.5EQ_X", "0.6WL_Y"
_LBL_LAT = _re.compile(r"([+-−]?)\s*\(?\s*([0-9]*\.?[0-9]+)\s*\)?\s*[\[(]?\s*(EQ|EL|WL|W)(?:_?([XYZ]))?(?![A-Za-z])", _re.I)


def lateral_kind(name) -> str | None:
    n = str(name or "").upper()
    if _re.match(r"^\s*(EQ|EL|E)(_|\b|[XYZ])", n) or n.startswith("RSA") or "EQ" in n or "EL_" in n:
        return "EQ"
    if _re.match(r"^\s*(WL|W)(_|\b|[XYZ])", n) or "WIND" in n:
        return "W"
    return None


def label_lateral_terms(label) -> list:
    """[(signed factor, kind, direction)] parsed from a combination label."""
    out = []
    for m in _LBL_LAT.finditer(str(label or "")):
        sgn = -1.0 if m.group(1) in ("-", "−") else 1.0
        kind = "EQ" if m.group(3).upper() in ("EQ", "EL") else "W"
        out.append((sgn * float(m.group(2)), kind, (m.group(4) or "").upper() or None))
    return out


def combo_lateral_factor(c) -> tuple:
    """(factor, key) of a combination's lateral factor; (None, None) when absent."""
    for k in LAT_FACTOR_KEYS:
        if k in c and c.get(k) is not None:
            return float(c[k]), k
    return None, None


def _story_force_scale(plan, c=None) -> float:
    """Multiplier to N for story forces (WP1.12)."""
    u = str((c or {}).get("units") or (plan or {}).get("story_forces_units") or "").strip().lower()
    if u in ("n", "newton", "newtons"):
        return 1.0
    if u in ("kn", "kilonewton", "kilonewtons"):
        return 1000.0
    raise LoadPlanError("load_plan.story_forces_units must be 'N' or 'kN' (got %r); kip is refused on "
                        "the India path (WP1.12)" % u)


def _as_lateral(raw):
    """Normalize lateral story map to {int: (fx, fy, mz)}."""
    if not raw:
        return {}
    out = {}
    for k, v in dict(raw).items():
        ki = int(k)
        if isinstance(v, dict):
            out[ki] = (float(v.get("fx", 0)), float(v.get("fy", 0)), float(v.get("mz", 0)))
        else:
            seq = list(v)
            fx = float(seq[0]) if len(seq) > 0 else 0.0
            fy = float(seq[1]) if len(seq) > 1 else 0.0
            mz = float(seq[2]) if len(seq) > 2 else 0.0
            out[ki] = (fx, fy, mz)
    return out



def _retrieval_hits(plan, pred):
    """Return retrieval entries matching pred(stem_lower, hit)."""
    out = []
    for hit in (plan.get("retrieval") or []):
        if not isinstance(hit, dict):
            continue
        stem = str(hit.get("stem") or hit.get("doc") or "").lower()
        if pred(stem, hit):
            out.append(hit)
    return out


def _is_part3_stem(stem: str) -> bool:
    s = stem.lower()
    return (
        "875_part_3" in s or "875_p3" in s or "is875_p3" in s
        or "is_875_part_3" in s or "part3" in s and "875" in s
        or "part_3" in s and "875" in s
    )


def _no_wind_flag(cfg, plan):
    """Return (active: bool, reason: str|None)."""
    for src in (plan, cfg):
        if not isinstance(src, dict):
            continue
        for key in ("no_wind", "omit_wind", "wind_not_applicable", "wind_omitted"):
            val = src.get(key)
            if val is True:
                reason = (
                    src.get("no_wind_reason")
                    or src.get("omit_wind_reason")
                    or src.get("wind_omit_reason")
                    or ""
                )
                return True, str(reason).strip() or None
            if isinstance(val, str) and val.strip():
                return True, val.strip()
            if isinstance(val, dict):
                reason = str(val.get("reason") or val.get("note") or "").strip()
                return True, reason or None
    return False, None


def _has_wind_lateral_evidence(plan) -> bool:
    """True when wind story forces or WL combinations are present (not invented Ka/Cpe)."""
    if not isinstance(plan, dict):
        return False
    ws = plan.get("wind_summary") or plan.get("wind") or {}
    if isinstance(ws, dict) and ws:
        # Numeric base shear / story forces count as evidence; params-only without forces do not
        for k in ("VB_x_kN", "VB_y_kN", "VB_x", "VB_y", "Qi_x_kN", "Qi_y_kN", "story_forces", "Fx", "Fy"):
            if ws.get(k) not in (None, "", [], {}):
                return True
        if ws.get("applied") is True or ws.get("laterals_applied") is True:
            return True
    sf = plan.get("story_forces") or {}
    if isinstance(sf, dict):
        for name, forces in sf.items():
            n = str(name).lower()
            if any(t in n for t in ("wind", "wl", "w_x", "w_y", "wx", "wy")) and forces:
                return True
    for c in (plan.get("combinations") or []):
        if not isinstance(c, dict):
            continue
        lab = str(c.get("label") or "").upper()
        cite = str(c.get("cite") or "").upper()
        if not any(t in lab or t in cite for t in ("WL", "WIND", "+W", " W", "W+", "W-", "W_X", "W_Y")):
            # also accept bare W as load letter when combined with DL
            if "W" not in lab.replace("SW", "").replace("OWN", ""):
                continue
        lat = c.get("lateral") or {}
        ref = c.get("lateral_ref")
        if lat or ref:
            return True
    return False


def validate_wind_gate(cfg, plan: dict | None = None) -> list:
    """S5/H2: require wind retrieval evidence OR explicit found:false + documented no-wind.

    Never allow silent omission of wind laterals. found:false alone is honest but
    insufficient without ``no_wind`` + reason — do not invent Ka/Cpe.
    """
    out = []
    if not isinstance(cfg, dict):
        return out
    plan = plan if plan is not None else (cfg.get("load_plan") or {})
    if not isinstance(plan, dict) or not plan:
        return out

    no_wind, reason = _no_wind_flag(cfg, plan)
    part3 = _retrieval_hits(plan, lambda stem, _h: _is_part3_stem(stem))
    part3_found = [h for h in part3 if h.get("found") is True]
    part3_false = [h for h in part3 if h.get("found") is False]
    has_laterals = _has_wind_lateral_evidence(plan)

    if no_wind:
        if not reason:
            out.append((
                "ERROR",
                "load_plan declares no_wind/omit_wind but no reason is documented — "
                "set no_wind to a non-empty reason string (or no_wind_reason). "
                "found:false on Part 3 is honest; inventing Ka/Cpe is not.",
            ))
        elif not part3 and not part3_false:
            out.append((
                "WARN",
                "no_wind documented (%s) but load_plan.retrieval has no IS 875 Part 3 hit — "
                "prefer an explicit found:false Part 3 retrieval for provenance." % reason,
            ))
        return out

    # Wind is expected for a normal building job
    if not part3:
        out.append((
            "ERROR",
            "Wind gate (S5/H2): load_plan.retrieval has no IS 875 Part 3 stem — "
            "RAG-query Part 3 for Vb/k1/k2/Cp OR set load_plan.no_wind with a documented "
            "reason. Never silently omit wind laterals before design_and_report.",
        ))
        return out

    if not part3_found and part3_false:
        out.append((
            "ERROR",
            "Wind gate (S5/H2): IS 875 Part 3 retrieval is found:false and no_wind is not "
            "set — do not invent Ka/Cpe or silently drop wind laterals. Either retry RAG "
            "until found:true and apply wind forces, or set load_plan.no_wind='<reason>'.",
        ))
        return out

    if part3_found and not has_laterals:
        out.append((
            "ERROR",
            "Wind gate (S5/H2): Part 3 retrieved (found:true) but no wind laterals / "
            "wind_summary forces / WL combinations are present — never silently omit wind "
            "laterals. Write wind story forces into load_plan or set no_wind with reason.",
        ))
    return out


def validate_load_plan(cfg) -> list:
    """Return a list of (level, message) findings. level in ERROR/WARN/INFO.

    ERRORs mean the demand envelope must not invent loads — agent must RAG-fill load_plan.
    """
    out = []
    plan = cfg.get("load_plan") if isinstance(cfg, dict) else None
    if not plan or not isinstance(plan, dict):
        out.append(("ERROR",
                    "cfg['load_plan'] missing. India jobs MUST RAG-query IS 875 Parts 1–5 and "
                    "IS 1893 Part 1:2016 LIVE this job, then write retrieved combination factors "
                    "and story forces into cfg['load_plan'] (see india_loads.py). The engine will "
                    "NOT compute ASCE 7 or hardcode IS load formulas."))
        return out

    if str(plan.get("jurisdiction", "")).lower() not in ("india", "is", "is_bis", "bis"):
        out.append(("WARN",
                    "cfg['load_plan'].jurisdiction should be 'india' (got %r)" % plan.get("jurisdiction")))

    retrieval = plan.get("retrieval") or []
    if not isinstance(retrieval, list) or len(retrieval) < 2:
        out.append(("ERROR",
                    "cfg['load_plan'].retrieval must list ≥2 LIVE RAG hits this job "
                    "(IS 875 family + IS 1893 as applicable). Do not invent citations; "
                    "found:false is honest."))
    else:
        stems_hit = set()
        found_any = False
        for i, hit in enumerate(retrieval):
            if not isinstance(hit, dict):
                out.append(("ERROR", "load_plan.retrieval[%d] must be an object" % i))
                continue
            stem = str(hit.get("stem") or hit.get("doc") or "")
            if stem:
                stems_hit.add(stem)
            if hit.get("found") is True:
                found_any = True
            if hit.get("found") is False:
                out.append(("WARN",
                            "load_plan.retrieval[%d] found:false for %s — do not invent; "
                            "retry FTS/exact or note gap" % (i, stem or "?")))
            if not (hit.get("query") or hit.get("cite")):
                out.append(("WARN", "load_plan.retrieval[%d] missing query/cite" % i))
        load_needed = set(LOAD_STEMS)
        # Always expect at least one IS 875 and IS 1893 when seismic is declared
        if not any(s.startswith("IS_875") for s in stems_hit):
            out.append(("ERROR",
                        "load_plan.retrieval has no IS_875_* stem — query dead/imposed/wind/snow "
                        "from IS 875 Parts 1–5 before running the pipeline."))
        seis = cfg.get("seis") or {}
        if seis and not any("1893" in s for s in stems_hit):
            out.append(("ERROR",
                        "cfg has seismic inputs but load_plan.retrieval has no IS_1893_* hit — "
                        "RAG-query IS 1893 Part 1:2016 for zone factor / design spectrum / base shear."))
        if not found_any:
            out.append(("ERROR",
                        "load_plan.retrieval has no found:true hits — refuse to invent load factors."))

    combos = plan.get("combinations") or []
    if combos == "auto" or (isinstance(combos, dict) and combos.get("generate")):
        try:
            _gen = expanded_combinations(cfg)
            out.extend(validate_table4(_gen, cfg))
        except (LoadPlanError, Exception) as ex:
            out.append(("ERROR", "combination generation failed: %s" % ex))
    elif not isinstance(combos, list) or len(combos) < 1:
        out.append(("ERROR",
                    "cfg['load_plan'].combinations empty — after RAG, write IS 800 Table 4 "
                    "(partial factors) combinations with fD/fL/fLr and any lateral story forces."))
    else:
        for i, c in enumerate(combos):
            if not isinstance(c, dict):
                out.append(("ERROR", "combinations[%d] must be an object" % i))
                continue
            if not c.get("label"):
                out.append(("ERROR", "combinations[%d] missing label" % i))
            for key in ("fD", "fL", "fLr"):
                if key not in c:
                    out.append(("ERROR", "combinations[%d] missing %s" % (i, key)))
            if not c.get("cite"):
                out.append(("WARN", "combinations[%d] (%s) has no cite — attach the retrieved clause"
                            % (i, c.get("label", "?"))))
            out.extend(validate_lateral_factor(c, i, plan))
        out.extend(validate_table4(combos, cfg))
        try:
            from india_combos import validate_combinations
            out.extend(validate_combinations(combos, cfg, plan))
        except ImportError as ex:
            out.append(("ERROR", "india_combos unavailable: %s" % ex))
    sf = plan.get("story_forces")
    if isinstance(sf, dict) and sf:
        u = str(plan.get("story_forces_units") or "").strip().lower()
        if u not in ("n", "kn"):
            out.append(("ERROR", "load_plan.story_forces_units missing/invalid (%r): declare 'N' or 'kN' "
                                 "(unfactored characteristic story forces, WP1.1/1.12)" % plan.get("story_forces_units")))

    # ---- P0 gates: wind (S5/H2) + Ta fail-closed (H1) ----
    out.extend(validate_wind_gate(cfg, plan))
    try:
        from india_seismic import validate_Ta_for_system as _vTa
        out.extend(_vTa(cfg, plan))
    except Exception as _ex:
        out.append(("WARN", "Ta fail-closed gate unavailable: %s" % _ex))

    # Hard ban: residual ASCE keys that imply the USA hardcoded path is still driving loads
    if cfg.get("use_asce7_engine_loads"):
        out.append(("ERROR",
                    "use_asce7_engine_loads is set — forbidden on steltic_india. "
                    "Remove it and supply cfg['load_plan'] from IS RAG."))

    return out


def validate_lateral_factor(c, i=0, plan=None) -> list:
    """WP1.1: a combination with a lateral pattern needs an explicit fE/fW that matches its label."""
    out = []
    has_lat = bool(c.get("lateral") or c.get("lateral_ref") or c.get("rsa") or c.get("terms"))
    f, key = combo_lateral_factor(c)
    terms = label_lateral_terms(c.get("label"))
    lab = c.get("label", "?")
    if has_lat and f is None:
        out.append(("ERROR", "combinations[%d] (%s) references a lateral pattern but has no lateral load "
                             "factor -- add fE (earthquake) or fW (wind); there is no default (IS 800 Table 4, "
                             "story forces are unfactored)" % (i, lab)))
        return out
    if f is not None and not has_lat:
        out.append(("ERROR", "combinations[%d] (%s) has %s=%g but no lateral / lateral_ref" % (i, lab, key, f)))
        return out
    if f is None:
        if terms:
            out.append(("ERROR", "combinations[%d] (%s): label names a lateral term but no lateral pattern "
                                 "and factor are given" % (i, lab)))
        return out
    kind_ref = lateral_kind(c.get("lateral_ref")) if c.get("lateral_ref") else None
    kind_key = {"fE": "EQ", "fW": "W"}.get(key)
    if kind_ref and kind_key and kind_ref != kind_key:
        out.append(("ERROR", "combinations[%d] (%s): %s used with a %s pattern" % (i, lab, key, kind_ref)))
    if not terms:
        out.append(("ERROR", "combinations[%d] (%s): the label does not state the lateral factor "
                             "(e.g. '1.5DL+1.5EQ_X')" % (i, lab)))
        return out
    horiz = [t for t in terms if t[2] != "Z"]
    if not horiz:
        out.append(("ERROR", "combinations[%d] (%s): no horizontal lateral term in the label" % (i, lab)))
        return out
    lf = horiz[0][0]
    if abs(abs(lf) - abs(f)) > 1e-6:
        out.append(("ERROR", "combinations[%d] (%s): %s=%g disagrees with the label factor %g"
                             % (i, lab, key, f, lf)))
    elif (lf < 0) != (f < 0) and "±" not in str(lab):
        out.append(("ERROR", "combinations[%d] (%s): sign of %s=%g disagrees with the label" % (i, lab, key, f)))
    return out


# IS 800:2007 Table 4 factor sets (read from the PDF p.29 image): (DL, LL leading, lateral) --
# strength rows, the 12.2.3 rows and the serviceability rows.  LL accompanying (crane) is separate.
TABLE4_SETS = {
    "strength": [(1.5, 1.5, 0.0), (1.2, 1.2, 0.6), (1.2, 1.2, 1.2), (1.5, 0.0, 1.5), (0.9, 0.0, 1.5),
                 (1.5, 0.0, 0.0), (0.9, 0.0, 0.0)],
    "is800_12_2_3": [(1.2, 0.5, 2.5), (0.9, 0.0, 2.5)],
    # IS 18168:2023 5.5 (pdf p. 7): 1.2DL + gLL LL +- Omega EL, 0.9DL +- Omega EL; Omega 2.5 SCBF/EBF (= 12.2.3 set),
    # 3.0 SMRF; gLL 0.25 / 0.50 -- the generator keeps IS 800's 0.5 LL (stricter) with Omega 3.0
    "is18168_5_5": [(1.2, 0.5, 3.0), (0.9, 0.0, 3.0), (1.2, 0.25, 3.0), (1.2, 0.25, 2.5)],
    "service": [(1.0, 1.0, 0.0), (1.0, 0.8, 0.8), (1.0, 0.0, 1.0), (1.0, 0.0, 0.0)],
}


def validate_table4(combos, cfg=None) -> list:
    """Each explicit combination's (fD, fL, |f_lat|) must be an IS 800 Table 4 (or 12.2.3 / IS 18168 5.5) set."""
    out = []
    allowed = [t for v in TABLE4_SETS.values() for t in v]
    for i, c in enumerate(combos or []):
        if not isinstance(c, dict):
            continue
        try:
            fD = float(c.get("fD", 0) or 0)
            fL = float(c.get("fL", 0) or 0)
        except (TypeError, ValueError):
            continue
        f, _ = combo_lateral_factor(c)
        fl = abs(f) if f is not None else 0.0
        vert = c.get("vertical") if isinstance(c.get("vertical"), dict) else {}
        if f is not None and abs(abs(float(vert.get("coef", 0.0))) - 1.0) < 1e-9:
            fl = fl / 0.3                          # IS 1893 6.3.4.1(c): ELZ leading, 0.3 EL accompanying
        if not any(abs(fD - a) < 1e-6 and abs(fL - b) < 1e-6 and abs(fl - e) < 1e-6 for a, b, e in allowed):
            out.append(("ERROR", "combinations[%d] (%s): factors DL %g / LL %g / lateral %g are not an IS 800 "
                                 "Table 4 (or 12.2.3 / IS 18168 5.5) set" % (i, c.get("label", "?"), fD, fL, fl)))
    return out


def cases_from_load_plan(cfg) -> list:
    """Build design_pipeline combo tuples from cfg['load_plan']. Raises LoadPlanError on ERRORs."""
    findings = validate_load_plan(cfg)
    errors = [m for lvl, m in findings if lvl == "ERROR"]
    if errors:
        raise LoadPlanError("India load_plan invalid:\n- " + "\n- ".join(errors))

    plan = cfg["load_plan"]
    combos = plan["combinations"]
    if combos == "auto" or (isinstance(combos, dict) and combos.get("generate")):
        combos = expanded_combinations(cfg)
    cases = []
    for c in combos:
        cases.append(case_from_combination(c, plan))
    return cases


def expanded_combinations(cfg, eccentricity=None, method=None) -> list:
    """india_combos.expand_combinations with the 7.8.2 eccentricities from the engine
    (centre-of-rigidity unit-load analyses) -- validated; raises LoadPlanError on ERRORs."""
    from india_combos import expand_combinations, validate_combinations
    plan = cfg["load_plan"]
    if eccentricity is None and (plan.get("story_forces") or {}).get("EQ_X") is not None:
        try:
            import engine3d as _E
            eccentricity = _E.design_eccentricities(cfg)
        except Exception as ex:                                 # engine unavailable (unit tests)
            eccentricity = None
            plan.setdefault("_notes", []).append("7.8.2 esi not computed (%s): esi = 0 used" % ex)
    combos = expand_combinations(plan, cfg, eccentricity=eccentricity, method=method)
    errs = [m for s, m in validate_combinations(combos, cfg, plan) if s == "ERROR"]
    if errs:
        raise LoadPlanError("generated combinations incomplete:\n- " + "\n- ".join(errs))
    return combos


def case_from_combination(c, plan) -> Case:
    """One combination dict -> Case (lateral already multiplied by fE/fW and converted to N)."""
    label = str(c["label"])
    fD = float(c["fD"])
    fL = float(c.get("fL", 0.0))
    fLr = float(c.get("fLr", 0.0))
    f, key = combo_lateral_factor(c)
    raw = c.get("lateral") or {}
    ref = c.get("lateral_ref")
    if ref and not raw:
        raw = (plan.get("story_forces") or {}).get(ref)
        if raw is None:
            raise LoadPlanError("combinations entry %r lateral_ref=%r not in load_plan.story_forces"
                                % (label, ref))
    lateral = _as_lateral(raw)
    if lateral:
        if f is None:
            raise LoadPlanError("combination %r has a lateral pattern but no fE/fW (WP1.1)" % label)
        sc = _story_force_scale(plan, c) * f
        lateral = {k: (fx * sc, fy * sc, mz * sc) for k, (fx, fy, mz) in lateral.items()}
    tor = c.get("torsion_mz") or {}
    if tor:
        sc = _story_force_scale(plan, c)
        tor = {int(k): float(v) * sc * (f if f is not None else 1.0) for k, v in dict(tor).items()}
        lateral = dict(lateral)
        for k, mz in tor.items():
            fx, fy, m0 = lateral.get(k, (0.0, 0.0, 0.0))
            lateral[k] = (fx, fy, m0 + mz)
    for t in (c.get("terms") or []):                     # extra static terms (e.g. 6.3.2.2 0.3 ELY)
        if t.get("ref") and not t.get("rsa"):
            raw2 = (plan.get("story_forces") or {}).get(t["ref"])
            if raw2 is None:
                raise LoadPlanError("combination %r term ref %r not in story_forces" % (label, t["ref"]))
            sc2 = _story_force_scale(plan, c) * float(t["f"])
            lateral = dict(lateral)
            for k, (fx, fy, mz) in _as_lateral(raw2).items():
                a = lateral.get(k, (0.0, 0.0, 0.0))
                lateral[k] = (a[0] + fx * sc2, a[1] + fy * sc2, a[2] + mz * sc2)
    rsa = c.get("rsa")
    if isinstance(rsa, str):
        rsa = {rsa: float(f if f is not None else 1.0)}
    elif isinstance(rsa, dict):
        rsa = {str(k): float(v) for k, v in rsa.items()}
    else:
        rsa = {}
    for t in (c.get("terms") or []):
        if t.get("rsa"):
            rsa[str(t["rsa"])] = rsa.get(str(t["rsa"]), 0.0) + float(t["f"])
    tags = list(c.get("tags") or [])
    col_only = bool(c.get("col_only", False)) or "col_only" in tags
    kind = {"fE": "EQ", "fW": "W"}.get(key) or (lateral_kind(ref) if ref else None)
    return Case(label, fD, fL, fLr, lateral, col_only,
                fLat=f, kind=kind, direction=c.get("direction") or (str(ref)[-1] if ref else None),
                sign=(1 if (f or 0) >= 0 else -1), torsion=c.get("torsion"), fEv=float(c.get("fEv", 0.0) or 0.0),
                rsa=rsa, tags=tags, family=c.get("family"), cite=c.get("cite"),
                service=bool(c.get("service")), crane=c.get("crane"), fC=float(c.get("fC", 0.0) or 0.0),
                crane_pattern=(tuple(c["crane_pattern"]) if c.get("crane_pattern") else None),
                fS=float(c.get("fS", 0.0) or 0.0), notional=c.get("notional"), source=c,
                member_wind=c.get("member_wind"), fWM=float(c.get("fWM", 0.0) or 0.0))


def render_findings(findings) -> str:
    if not findings:
        return "[india_loads] load_plan OK"
    lines = ["[india_loads] load_plan check:"]
    for lvl, msg in findings:
        lines.append("  [%s] %s" % (lvl, msg))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# S6: Ka / Cpe — corpus exact_table prefer; india_wind_tables = fallback only
# ---------------------------------------------------------------------------
def wind_table_override_policy() -> dict:
    """Documented Ka/Cpe policy for agents (S6). See docs/IS875_P3_Ka_Cpe_OVERRIDES.md."""
    try:
        from india_wind_tables import override_policy
        return override_policy()
    except Exception as ex:
        return {"error": str(ex), "note": "india_wind_tables unavailable"}


def ka_fallback(A_m2: float) -> dict:
    """Table 4 Ka fallback when corpus exact_table 4 returns found:false."""
    from india_wind_tables import ka_for_area_m2
    return ka_for_area_m2(A_m2)


def cpe_walls_fallback(h_over_w: float, l_over_w: float, theta_deg: float = 0.0) -> dict:
    """Table 5 wall Cpe fallback when corpus exact_table 5 returns found:false."""
    from india_wind_tables import cpe_walls
    return cpe_walls(h_over_w, l_over_w, theta_deg)


# P1 alias — still fallback-only after corpus-prefer demotion.
cpe_walls_override = cpe_walls_fallback


def resolve_ka(A_m2: float, corpus_hit=None, *, allow_fallback: bool = True) -> dict:
    """Prefer corpus exact_table 4; fallback to in-repo Ka only if found:false."""
    from india_wind_tables import resolve_ka as _resolve
    return _resolve(A_m2, corpus_hit, allow_fallback=allow_fallback)


def resolve_cpe_walls(h_over_w: float, l_over_w: float, theta_deg: float = 0.0,
                      corpus_hit=None, *, allow_fallback: bool = True) -> dict:
    """Prefer corpus exact_table 5; fallback to in-repo Cpe only if found:false."""
    from india_wind_tables import resolve_cpe_walls as _resolve
    return _resolve(h_over_w, l_over_w, theta_deg, corpus_hit, allow_fallback=allow_fallback)



def resolve_k4(corpus_hit=None, *, eor_k4=None, eor_cite=None, eor_source=None,
               structure_class=None):
    """Prefer corpus §6.3.4 digits; else EOR-documented k4+cite (never invent)."""
    from india_wind_tables import resolve_k4 as _resolve
    return _resolve(
        corpus_hit, eor_k4=eor_k4, eor_cite=eor_cite, eor_source=eor_source,
        structure_class=structure_class,
    )


def resolve_building_length_m(cfg, *, bay_spacing_m=None, n_bays=None, n_frames=None):
    """Building length along portal spacing for wind l/w and Ka.

    Prefer explicit cfg keys (brief field). If missing, allow a *documented*
    assumption with cite — never a silent invented length.
    """
    cfg = cfg or {}
    for key in ("building_length_m", "length_m", "L_m", "plan_length_m"):
        if cfg.get(key) is not None:
            return {
                "found": True,
                "L_m": float(cfg[key]),
                "source": "cfg",
                "key": key,
                "cite": cfg.get("building_length_cite") or cfg.get("length_cite") or "cfg explicit",
            }
    # nested geometry
    geom = cfg.get("geometry") if isinstance(cfg.get("geometry"), dict) else {}
    if geom.get("length_m") is not None:
        return {
            "found": True, "L_m": float(geom["length_m"]), "source": "cfg.geometry",
            "cite": geom.get("length_cite") or "cfg.geometry.length_m",
        }
    # Documented assumption path
    assum = cfg.get("building_length_assumption_m")
    assum_cite = cfg.get("building_length_assumption_cite") or cfg.get("length_assumption_cite")
    if assum is not None and assum_cite:
        return {
            "found": True,
            "L_m": float(assum),
            "source": "documented_assumption",
            "cite": str(assum_cite),
            "note": "Brief omitted building length; documented assumption — not silent invent",
            "brief_field_required": "building_length_m (or n_frames × bay spacing stated in brief)",
        }
    # Derive only when spacing + count are explicit in cfg AND cite documents the assumption
    sp = bay_spacing_m if bay_spacing_m is not None else cfg.get("bay_spacing_m") or cfg.get("bay_y") or cfg.get("frame_spacing_m")
    nb = n_bays if n_bays is not None else cfg.get("n_bays_length") or cfg.get("NY")
    nf = n_frames if n_frames is not None else cfg.get("n_frames")
    derive_cite = cfg.get("building_length_derive_cite")
    if sp and (nb is not None) and derive_cite:
        L = float(sp) * float(nb)
        return {
            "found": True, "L_m": L, "source": "derived_documented",
            "cite": str(derive_cite),
            "bay_spacing_m": float(sp), "n_bays": float(nb),
            "note": "L = n_bays × spacing with documented cite; prefer brief building_length_m",
            "brief_field_required": "building_length_m",
        }
    if sp and nf is not None and derive_cite:
        # n_frames = n_bays + 1 → length = (n_frames-1)*spacing
        L = float(sp) * max(float(nf) - 1.0, 0.0)
        return {
            "found": True, "L_m": L, "source": "derived_documented",
            "cite": str(derive_cite),
            "bay_spacing_m": float(sp), "n_frames": float(nf),
            "note": "L = (n_frames-1) × spacing with documented cite",
            "brief_field_required": "building_length_m",
        }
    return {
        "found": False,
        "L_m": None,
        "required_inputs": [
            "cfg['building_length_m'] (preferred brief field)",
            "OR building_length_assumption_m + building_length_assumption_cite",
            "OR bay spacing + n_bays/n_frames + building_length_derive_cite",
        ],
        "brief_field_required": "building_length_m",
        "note": (
            "Brief gave frame spacing but not building length (IN_Ex3 pattern). "
            "Do not silently assume L=36 m — set cfg building_length_m or document the assumption with cite."
        ),
    }


def resolve_storage_height_m(cfg=None, *, eor_h_m=None, eor_cite=None, eor_source=None,
                             unit_load_kNpm2_per_m=2.0):
    """Mezz/warehouse storage height for IS 875 Part 2 storage UDL (kN/m² per m height).

    Prefer cfg['storage_height_m'] (brief). Else documented assumption with cite.
    Never invent a silent 2.5 m.
    Returns L_floor = unit_load × height when resolved.
    """
    cfg = cfg or {}
    for key in ("storage_height_m", "mezz_storage_height_m", "stack_height_m"):
        if cfg.get(key) is not None:
            h = float(cfg[key])
            return {
                "found": True,
                "h_m": h,
                "L_kNpm2": float(unit_load_kNpm2_per_m) * h,
                "unit_load_kNpm2_per_m": float(unit_load_kNpm2_per_m),
                "source": "cfg",
                "key": key,
                "cite": cfg.get("storage_height_cite") or "cfg explicit storage height",
            }
    h = eor_h_m if eor_h_m is not None else cfg.get("storage_height_assumption_m")
    cite = eor_cite or cfg.get("storage_height_assumption_cite")
    src = (eor_source or cfg.get("storage_height_source") or "").strip().lower().replace(" ", "_")
    ok = {"eor_documented", "eor", "documented", "explicit", "documented_assumption", "assumption_documented"}
    if h is not None and cite and (src in ok or src == "" or "document" in src or "eor" in src or "assum" in src):
        return {
            "found": True,
            "h_m": float(h),
            "L_kNpm2": float(unit_load_kNpm2_per_m) * float(h),
            "unit_load_kNpm2_per_m": float(unit_load_kNpm2_per_m),
            "source": src or "documented_assumption",
            "resolved_via": "eor_documented" if "eor" in (src or "documented") else "documented_assumption",
            "cite": str(cite),
            "note": (
                "Storage height documented (not silent invent). Prefer brief storage_height_m. "
                "IS 875 P2 Table 1 warehouses 2.0 kN/m² per m of storage height."
            ),
            "brief_field_required": "storage_height_m",
        }
    return {
        "found": False,
        "h_m": None,
        "L_kNpm2": None,
        "required_inputs": [
            "cfg['storage_height_m'] (preferred brief field)",
            "OR storage_height_assumption_m + storage_height_assumption_cite",
        ],
        "brief_field_required": "storage_height_m",
        "cite": "IS 875 (Part 2):1987 Table 1 STORAGE — 2.0 kN/m² per m of storage height",
        "note": "Do not silently assume 2.5 m stack height — set cfg or document with cite.",
    }



# --- HR polish Wave D: Annex town / site proxy disclosure ---------------------

SITE_PROXY_OK_SOURCES = frozenset({
    "site_proxy", "annex_proxy", "disclosed_proxy", "eor_documented", "eor",
    "documented", "explicit", "documented_proxy",
})
SITE_PROXY_REFUSED = frozenset({
    "silent", "silent_proxy", "assumed", "assumption", "invented", "guess",
    "placeholder", "todo", "tbd", "wrong_city_silent",
})


def _site_norm(s) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


def resolve_site_annex_proxy(
    cfg=None,
    *,
    town=None,
    annex_hit=None,
    quantity="Vb",  # "Vb" | "Z" | "zone"
    proxy_town=None,
    proxy_value=None,
    proxy_cite=None,
    proxy_source=None,
):
    """Resolve Annex A (Vb) / Annex E (Z) town values with explicit site_proxy.

    When the requested town is found:false in Annex tables, refuse silent
    wrong-city Vb/Z. Accept a disclosed proxy (Kochi→Kozhikode/Trivandrum Vb=39,
    Indore→Bhopal Z/Vb, Noida→Delhi Z/Vb) only with site_proxy source + cite.
    Never invent.
    """
    cfg = cfg or {}
    town = town or cfg.get("town") or cfg.get("site_town") or cfg.get("city")
    quantity = str(quantity or "Vb").strip()
    q_l = quantity.lower()

    # Direct corpus / annex hit
    if isinstance(annex_hit, dict) and annex_hit.get("found") is True:
        if q_l in ("vb", "vb_mps", "wind"):
            val = annex_hit.get("Vb_mps", annex_hit.get("Vb"))
        elif q_l in ("z", "zone_factor"):
            val = annex_hit.get("Z", annex_hit.get("zone_factor"))
        else:
            val = annex_hit.get("zone", annex_hit.get("Zone"))
        if val is not None:
            return {
                "found": True,
                "town": town,
                "town_found": True,
                "quantity": quantity,
                "value": val,
                "site_proxy": False,
                "source": annex_hit.get("source") or "annex",
                "resolved_via": "annex_corpus",
                "cite": annex_hit.get("cite") or "IS 875/1893 Annex (corpus)",
                "note": "Annex town row found:true — not a site_proxy.",
            }

    proxy_town = proxy_town or cfg.get("site_proxy_town") or cfg.get("proxy_town")
    proxy_cite = proxy_cite or cfg.get("site_proxy_cite") or cfg.get("proxy_cite")
    src = _site_norm(
        proxy_source or cfg.get("site_proxy_source") or cfg.get("proxy_source")
        or ("site_proxy" if cfg.get("site_proxy") is True else "")
    )

    if proxy_value is None:
        if cfg.get("site_proxy") is True or src in SITE_PROXY_OK_SOURCES:
            if q_l in ("vb", "vb_mps", "wind"):
                for k in ("site_proxy_value", "proxy_Vb_mps", "proxy_Vb"):
                    if cfg.get(k) is not None:
                        proxy_value = cfg[k]
                        break
            elif q_l in ("z", "zone_factor"):
                for k in ("site_proxy_value", "proxy_Z"):
                    if cfg.get(k) is not None:
                        proxy_value = cfg[k]
                        break
            else:
                for k in ("site_proxy_value", "proxy_zone"):
                    if cfg.get(k) is not None:
                        proxy_value = cfg[k]
                        break

    # Disclosed site_proxy path
    if proxy_value is not None and src in SITE_PROXY_OK_SOURCES and proxy_cite:
        if src in SITE_PROXY_REFUSED:
            return {
                "found": False,
                "town": town,
                "town_found": False,
                "quantity": quantity,
                "value": None,
                "site_proxy": False,
                "source": src,
                "resolved_via": "refused",
                "cite": "refuse silent/assumed site invent",
                "note": "Refused site_proxy source=%r." % (src,),
                "required_inputs": [
                    "site_proxy_source in site_proxy/eor_documented",
                    "site_proxy_cite",
                ],
                "policy": "refuse_silent_wrong_city",
            }
        return {
            "found": True,
            "town": town,
            "town_found": False,
            "quantity": quantity,
            "value": float(proxy_value) if q_l != "zone" else proxy_value,
            "site_proxy": True,
            "proxy_town": proxy_town,
            "source": src,
            "resolved_via": "site_proxy",
            "cite": str(proxy_cite),
            "note": (
                "Annex town %r found:false — using disclosed site_proxy %s=%r via %r. "
                "Not a silent wrong-city invent."
                % (town, quantity, proxy_value, proxy_town)
            ),
            "policy": "site_proxy_ok_when_annex_town_miss",
        }

    # Silent cfg value without disclosure → refuse
    silent_val = None
    if q_l in ("vb", "vb_mps", "wind"):
        silent_val = cfg.get("Vb", cfg.get("Vb_mps"))
    elif q_l in ("z", "zone_factor"):
        silent_val = cfg.get("Z")
    else:
        silent_val = cfg.get("zone")

    refused = []
    if silent_val is not None and not (src in SITE_PROXY_OK_SOURCES and proxy_cite):
        refused.append(
            "silent %s=%r without site_proxy + cite — refuse wrong-city invent"
            % (quantity, silent_val)
        )
    if proxy_value is not None and src not in SITE_PROXY_OK_SOURCES:
        refused.append("site_proxy_source must be site_proxy/eor_documented/documented")
    if proxy_value is not None and not proxy_cite:
        refused.append("site_proxy_cite")

    return {
        "found": False,
        "town": town,
        "town_found": False,
        "quantity": quantity,
        "value": None,
        "site_proxy": False,
        "source": src or None,
        "resolved_via": "found_false",
        "cite": (
            "IS 875 Part 3 Annex A (Vb) / IS 1893 Annex E (Z) — town row missing; "
            "disclose site_proxy + cite or leave found:false"
        ),
        "note": (
            "Annex town %r found:false for %s. Do not silently use another city's "
            "Vb/Z. Set site_proxy=True + site_proxy_town + site_proxy_value + "
            "site_proxy_cite (e.g. Kochi→Kozhikode Vb=39; Indore→Bhopal Z=0.10/Vb=39; "
            "Noida→Delhi Z=0.24/Vb=47)."
            % (town, quantity)
        ),
        "required_inputs": refused or [
            "annex corpus hit for town",
            "OR site_proxy=True + site_proxy_town + site_proxy_value + site_proxy_cite",
        ],
        "policy": "refuse_silent_wrong_city",
    }



# ---------------------------------------------------------------------------
# IS 800:2007 Table 6 deflection limits (read from the PDF p.31 image) -- WP2.1 / WP1.11
# ---------------------------------------------------------------------------
IS800_TABLE6 = {
    # other buildings
    "floor_roof_live_not_cracking": 300.0, "floor_roof_live_cracking": 360.0,
    "cantilever_live_not_cracking": 150.0, "cantilever_live_cracking": 180.0,
    "building_wind_elastic": 300.0, "building_wind_brittle": 500.0, "storey_wind": 300.0,
    # industrial buildings
    "purlin_girt_elastic": 150.0, "purlin_girt_brittle": 180.0,
    "industrial_simple_span_live_elastic": 240.0, "industrial_simple_span_live_brittle": 300.0,
    "industrial_cantilever_live_elastic": 120.0, "industrial_cantilever_live_brittle": 150.0,
    "rafter_profiled_sheeting": 180.0, "rafter_plastered_sheeting": 240.0,
    "gantry_manual": 500.0, "gantry_electric_upto_50t": 750.0, "gantry_electric_over_50t": 1000.0,
    "column_no_crane_elastic": 150.0, "column_no_crane_brittle": 240.0,
    "gantry_lateral_crane_absolute": 400.0, "gantry_lateral_rails_relative_mm": 10.0,
    "frame_crane_pendant_elastic": 200.0, "frame_crane_cab_brittle": 400.0,
}
IS800_TABLE6_CITE = "IS 800:2007 Table 6 (5.6.1), serviceability loads at gamma_f = 1.0"


def floor_deflection_limit(cfg) -> tuple:
    """(span divisor, cite) for floor/roof live-load deflection per IS 800 Table 6."""
    ind = str(cfg.get("building_type") or "").lower().startswith("industrial")
    crack = bool(cfg.get("finishes_susceptible_to_cracking", True))
    if ind:
        key = "industrial_simple_span_live_brittle" if crack else "industrial_simple_span_live_elastic"
    else:
        key = "floor_roof_live_cracking" if crack else "floor_roof_live_not_cracking"
    return IS800_TABLE6[key], "%s: %s -> span/%d" % (IS800_TABLE6_CITE, key, IS800_TABLE6[key])


# ---------------------------------------------------------------------------------------------
# WP2.7 crane loads (IS 875 (Part 2):1987 6.3 / 6.4, read from the PDF pp.15-16)
# ---------------------------------------------------------------------------------------------
CRANE_CITE = ("IS 875 (Part 2):1987 6.3: vertical impact 25 % of max static loads for crane girders (all "
              "classes), 25 % for columns supporting Class III/IV and 10 % for Class I/II cranes, none for "
              "foundations; hand-operated 10 % for girders only; transverse surge 10 % (rigid mast) or 5 % "
              "(other) of crab + lifted weight on one rail, one side of the frame at a time, either "
              "direction; traction 5 % of static wheel loads along the rails; (c) and (d) at rail level, "
              "not simultaneous (6.4.3 Note)")
CRANE_PATTERNS = (("L", "S+"), ("L", "S-"), ("R", "S+"), ("R", "S-"), ("L", "T+"), ("L", "T-"))


class CraneError(LoadPlanError):
    pass


def _crane_def(cfg):
    cr = cfg.get("crane") or cfg.get("cranes")
    if isinstance(cr, list):
        if len(cr) != 1:
            raise CraneError("multi-crane aisles (IS 875-2 6.4.1/6.4.2) need explicit per-crane load patterns; "
                             "only one crane per job is supported by crane_frame_loads")
        cr = cr[0]
    if not isinstance(cr, dict):
        raise CraneError("cfg['crane'] must be a dict (see india_loads.crane_reactions)")
    return cr


def crane_reactions(cr):
    """Static wheel/column reactions for one crane (N, mm).

    cr keys: capacity_kN (Q), crab_kN (Pt), bridge_kN (Ph), span_mm (S, rail centres),
    hook_approach_mm (a, minimum hook approach), wheels_per_side (default 2), wheel_base_mm,
    gantry_span_mm (column spacing along the rail), class ('I'..'IV'), type ('electric'|'hand'),
    rigid_mast (bool).
    Rmax (per rail) = Ph/2 + (Pt + Q)(S - a)/S ; Rmin = Ph/2 + (Pt + Q) a / S."""
    need = ("capacity_kN", "crab_kN", "bridge_kN", "span_mm", "hook_approach_mm", "wheel_base_mm",
            "gantry_span_mm", "class")
    miss = [k for k in need if cr.get(k) is None]
    if miss:
        raise CraneError("cfg['crane'] missing %s (IS 875-2 6.3 / manufacturer data)" % ", ".join(miss))
    Q, Pt, Ph = (float(cr[k]) * 1000.0 for k in ("capacity_kN", "crab_kN", "bridge_kN"))
    S, a = float(cr["span_mm"]), float(cr["hook_approach_mm"])
    n = int(cr.get("wheels_per_side") or 2)
    c = float(cr["wheel_base_mm"]); Lg = float(cr["gantry_span_mm"])
    Rmax = Ph / 2.0 + (Pt + Q) * (S - a) / S
    Rmin = Ph / 2.0 + (Pt + Q) * a / S
    # column reaction: wheel group with one wheel over the column, simply supported girders both sides
    xs = [i * c for i in range(n)] if n > 1 else [0.0]
    best = 0.0
    for shift in xs:
        infl = sum(max(0.0, 1.0 - abs(x - shift) / Lg) for x in xs)
        best = max(best, infl)
    col_factor = best                                     # sum of influence ordinates (wheel loads)
    cls = str(cr["class"]).upper().replace("CLASS", "").strip()
    typ = str(cr.get("type") or "electric").lower()
    if typ.startswith("hand"):
        imp_girder, imp_col = 0.10, 0.0
    else:
        imp_girder = 0.25
        imp_col = 0.25 if cls in ("III", "IV", "3", "4") else 0.10
    surge_pct = 0.10 if cr.get("rigid_mast") else 0.05
    H_total = surge_pct * (Pt + Q)                         # on one rail, shared by that rail's wheels
    return {"Rmax_N": Rmax, "Rmin_N": Rmin, "wheel_max_N": Rmax / n, "wheel_min_N": Rmin / n,
            "col_factor": col_factor, "col_Rmax_N": Rmax / n * col_factor, "col_Rmin_N": Rmin / n * col_factor,
            "impact_girder": imp_girder, "impact_column": imp_col, "surge_pct": surge_pct,
            "surge_rail_N": H_total, "col_surge_N": H_total / n * col_factor,
            "traction_rail_N": 0.05 * Rmax, "col_traction_N": 0.05 * Rmax,   # 5 % of the static wheel loads on that rail
            "cite": CRANE_CITE}


def crane_frame_loads(cfg, pattern=("L", "S+")):
    """Nodal loads {node: (Fx, Fy, Fz, Mx, My, Mz)} in N / N-mm for ONE crane pattern at fC = 1.

    pattern = (side with Rmax 'L'|'R', 'S+'|'S-' surge | 'T+'|'T-' traction | None vertical only).
    cr['bracket_nodes'] = {'L': node, 'R': node} (model nodes at rail/bracket level of the loaded frame),
    cr['span_axis'] 'X'|'Y' (direction of the crane bridge span), cr['bracket_eccentricity_mm'] (e,
    positive towards the crane).  Vertical loads include the column impact allowance (6.3(a)), with
    the moment R e; surge on the Rmax-side rail transverse to the rails, traction along the rails."""
    cr = _crane_def(cfg)
    R = crane_reactions(cr)
    bn = cr.get("bracket_nodes") or {}
    if not (bn.get("L") and bn.get("R")):
        raise CraneError("cfg['crane']['bracket_nodes'] = {'L': node, 'R': node} (bracket/rail-level nodes) required")
    ax = str(cr.get("span_axis") or "").upper()
    if ax not in ("X", "Y"):
        raise CraneError("cfg['crane']['span_axis'] ('X' or 'Y', direction of the crane bridge span) required")
    e = float(cr.get("bracket_eccentricity_mm") or 0.0)
    side, hz = (pattern or ("L", None))[0], (pattern or ("L", None))[1] if pattern else None
    fimp = 1.0 + R["impact_column"]
    out = {}
    for s_, sgn_in in (("L", 1.0), ("R", -1.0)):
        V = (R["col_Rmax_N"] if s_ == side else R["col_Rmin_N"]) * fimp
        f = [0.0] * 6
        f[2] = -V
        # moment of the eccentric reaction: bracket offset e towards the crane (inward)
        if ax == "X":
            f[4] = sgn_in * e * V              # r = (+-e, 0, 0), F = (0, 0, -V) -> My = +-e V
        else:
            f[3] = -sgn_in * e * V             # r = (0, +-e, 0) -> Mx = -(+-e) V
        out[int(bn[s_])] = f
    if hz:
        kind, sg = hz[0], (1.0 if hz[1] == "+" else -1.0)
        nd = int(bn[side])
        f = out[nd]
        if kind == "S":
            f[0 if ax == "X" else 1] += sg * R["col_surge_N"]
        elif kind == "T":
            f[1 if ax == "X" else 0] += sg * R["col_traction_N"]
    return {n: tuple(v) for n, v in out.items()}


def crane_findings(cfg) -> list:
    """Preflight: crane declared completely (WP2.7)."""
    if not (cfg.get("crane") or cfg.get("cranes")):
        return []
    out = []
    try:
        cr = _crane_def(cfg)
        crane_reactions(cr)
        if not (cr.get("bracket_nodes") or {}).get("L"):
            out.append(("ERROR", "crane: bracket_nodes {'L','R'} (rail-level nodes of the crane frame) required"))
        if str(cr.get("span_axis") or "").upper() not in ("X", "Y"):
            out.append(("ERROR", "crane: span_axis 'X'|'Y' required"))
        if str(cr.get("operation") or "").lower() not in ("pendant", "cab"):
            out.append(("ERROR", "crane: operation 'pendant' or 'cab' must be declared (IS 800 Table 6 crane "
                                 "sway H/200 pendant, H/400 cab)"))
        if cr.get("rail_height_mm") is None:
            out.append(("ERROR", "crane: rail_height_mm (for the IS 800 Table 6 crane sway limit) required"))
    except CraneError as ex:
        out.append(("ERROR", str(ex)))
    return out


def gantry_girder_demands(cfg):
    """Gantry girder demand set for the member module (HR-MEMBERS capacity checks):
    max sagging moment under the moving wheel group (simply supported, absolute-max position by
    scanning), with the 25 % girder impact (6.3(a)); surge moment on the top flange (lateral,
    same influence), shear, and the IS 800 Table 6 limits span/750 (vertical, static wheel loads,
    electric <= 50 t) or span/500 (manual) / span/1000 (> 50 t), and 10 mm relative lateral."""
    cr = _crane_def(cfg)
    R = crane_reactions(cr)
    L = float(cr["gantry_span_mm"]); c = float(cr["wheel_base_mm"]); n = int(cr.get("wheels_per_side") or 2)
    W = R["wheel_max_N"]; H = R["surge_rail_N"] / n
    xs0 = [i * c for i in range(n)]
    Mmax, Vmax = 0.0, 0.0
    steps = 400
    for s in range(steps + 1):
        off = -xs0[-1] + (L + xs0[-1]) * s / steps
        pos = [x + off for x in xs0 if 0.0 <= x + off <= L]
        if not pos:
            continue
        Rb = sum(W * p / L for p in pos); Ra = W * len(pos) - Rb
        Vmax = max(Vmax, Ra, Rb)
        for p in pos:
            M = Ra * p - sum(W * (p - q) for q in pos if q < p)
            Mmax = max(Mmax, M)
    cap = float(cr["capacity_kN"])
    typ = str(cr.get("type") or "electric").lower()
    div = 500.0 if typ.startswith("hand") else (750.0 if cap <= 500.0 else 1000.0)
    return {"M_static_Nmm": Mmax, "M_vertical_Nmm": Mmax * (1.0 + R["impact_girder"]),
            "V_vertical_N": Vmax * (1.0 + R["impact_girder"]), "M_surge_Nmm": Mmax * H / W,
            "wheel_load_N": W, "wheel_load_with_impact_N": W * (1.0 + R["impact_girder"]),
            "defl_limit_vertical_mm": L / div, "defl_limit_basis": "IS 800 Table 6 gantry span/%d (static wheel loads)" % div,
            "lateral_limit_mm": L / 400.0, "lateral_relative_rails_limit_mm": 10.0,
            "note": "Checks (HR-MEMBERS): biaxial bending with top-flange surge, LTB with the actual restraint, web "
                    "bearing/buckling under the wheel, Section 13 fatigue by crane class", "cite": CRANE_CITE}
