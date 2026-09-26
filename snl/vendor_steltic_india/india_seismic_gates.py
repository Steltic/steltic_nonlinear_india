"""India HR seismic gates -- the SINGLE COMPLETE authority for steltic_india (WP0.2).

``design_status(cfg, pkg)`` is the only function that may label a job COMPLETE. It returns
``status`` in {"complete", "partial", "example_only"} plus the list of reasons. Everything
else (the agent completion gate, consistency.check, the report banner, STATUS.md writers)
must call it rather than re-implementing a subset of the rules.

Basis (verified against the licensed PDFs, see IMPL_BRIEF):
  * IS 1893 (Part 1):2016 + Amd 1 (2017) + Amd 2 (2020): Table 8 (I), Table 9 (R) and
    Note 1 as amended ("Structures in Seismic Zones III, IV and V shall be designed to be
    ductile. Hence, this system is not allowed in these seismic zones"), 7.7.1 (dynamic
    analysis), Tables 5/6 (irregularity consequences).
  * IS 800:2007 12.2.3 (+-2.5 EL), 12.7.1.1 (OCBF), 12.10.1.1 (OMF).
  * Owner decisions D3 (no foreign design basis, no eor_documented bypass) and D4 (Table 9
    Note 1 bans steel OMRF and OBF in Zones III-V).

A check record anywhere in a package is expected to look like
``{value, limit, dc, ok, clause, cite, source}`` (demand, capacity, demand/capacity ...).
``dc`` is always recomputed here from value/limit; a stored DC is never trusted.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re

# ---------------------------------------------------------------------------
# Table 9 (with Amd 2) -- steel rows only.  R values read from the PDF p.20.
# ---------------------------------------------------------------------------
TABLE9_STEEL = {
    "steel_omrf": {
        "R": 3.0, "row": "IS 1893 Table 9 (i)(c)", "name": "Steel OMRF (IS 800 OMF, 12.10)",
        "note1_banned_zones": ("III", "IV", "V"), "is800": "12.10",
        "is800_ban": "IS 800 12.10.1.1: OMF shall not be used in zones IV and V, nor in zone III with I > 1.0",
    },
    "steel_smrf": {
        "R": 5.0, "row": "IS 1893 Table 9 (i)(d)", "name": "Steel SMRF (IS 800 SMF, 12.11)",
        "note1_banned_zones": (), "is800": "12.11", "is800_ban": None,
    },
    "obf": {
        "R": 4.0, "row": "IS 1893 Table 9 (ii)(a) [Amd 2: 'see Note 1']",
        "name": "OBF, concentric braces (IS 800 OCBF, 12.7)",
        "note1_banned_zones": ("III", "IV", "V"), "is800": "12.7",
        "is800_ban": "IS 800 12.7.1.1: OCBF shall not be used in zones IV and V, nor in zone III with I > 1.0",
    },
    "sbf_concentric": {
        "R": 4.5, "row": "IS 1893 Table 9 (ii)(b)", "name": "SBF, concentric braces (IS 800 SCBF, 12.8)",
        "note1_banned_zones": (), "is800": "12.8", "is800_ban": None,
    },
    "sbf_eccentric": {
        "R": 5.0, "row": "IS 1893 Table 9 (ii)(c)",
        "name": "SBF, eccentric braces (IS 800 12.9 -> IS 18168 links)",
        "note1_banned_zones": (), "is800": "12.9", "is800_ban": None,
    },
}
TABLE9_NOTE1_CITE = ("IS 1893 (Part 1):2016 Table 9 Note 1 as amended by Amd 2 (2020): "
                     "'Structures in Seismic Zones III, IV and V shall be designed to be ductile'")

# Systems with no IS 1893 Table 9 / IS 800 Section 12 / IS 18168 basis (owner ruling D3).
NO_IS_BASIS = {
    "brbf": "BRBF (buckling-restrained braces) has no IS 1893 Table 9 row and no IS 800 Section 12 rules",
    "spsw": "SPSW (steel plate shear wall) has no IS 1893 Table 9 row and no IS 800 Section 12 rules",
    "dual": ("IS 1893 Table 9 has no steel dual system; declare the governing Table 9 system "
             "(e.g. SBF concentric R 4.5 or SMRF R 5) without a dual claim"),
    "cfs_wall": "cold-formed sheathed / strap walls are not an IS 1893 Table 9 steel SFRS",
    "stmf": "STMF has no IS 1893 Table 9 row",
    "cpsw": "composite plate shear walls have no IS 1893 Table 9 row",
}

_TOKEN_MAP = (
    # (regex on normalised text, canonical)
    (r"\bdual\b", "nobasis:dual"),
    (r"\bbrbf\b|\bbrb\b|buckling[ _]restrained", "nobasis:brbf"),
    (r"\bspsw\b|plate[ _]shear[ _]wall", "nobasis:spsw"),
    (r"\bstmf\b|truss[ _]moment", "nobasis:stmf"),
    (r"c[ _-]?psw|speedcore", "nobasis:cpsw"),
    (r"shear[ _]wall|\bwsp\b|strap[ _]brac|sheathed", "nobasis:cfs_wall"),
    (r"\bebf\b|eccentric", "sbf_eccentric"),
    (r"\bscbf\b|\bsbf\b|special[ _]concentric|special[ _]brac", "sbf_concentric"),
    (r"\bocbf\b|\bobf\b|ordinary[ _]concentric|ordinary[ _]brac|tension[ _]only|\bcbf\b", "obf"),
    (r"\bsmrf\b|\bsmf\b|special[ _]moment", "steel_smrf"),
    (r"\bomrf\b|\bomf\b|ordinary[ _]moment", "steel_omrf"),
    (r"\bimf\b|\bimrf\b|intermediate[ _]moment", "imf"),
)

R_PROXY_SOURCES = frozenset({
    "proxy", "silent_proxy", "silent", "invented", "assumed", "assumption", "guess",
    "placeholder", "todo", "tbd", "sbf_proxy", "smrf_proxy", "table9_proxy", "silent_sbf",
    "silent_smrf", "is800_omrf", "is_800_omrf", "omrf_proxy", "silent_omrf", "imf_proxy",
    "brbf_proxy", "spsw_proxy", "ebf_proxy", "is800_proxy", "is_800_proxy",
    "is800_table23", "is_800_table23",
})
# D3: there is no EOR-adopted foreign R any more.  Table 9 is the only source.
R_OK_SOURCES = frozenset({"is1893_table9", "is_1893_table9", "table9", "is1893", "rag", "explicit"})

OMEGA0_OK_SOURCES = frozenset({
    "eor_documented", "eor", "documented", "explicit", "eor_explicit",
    "is1893", "rag",  # only if corpus actually has Ω0 (it does not today)
    # IS 18168 is the preferred India steel-SFRS corpus source for Ω. Keep
    # both spellings because retrieval metadata uses both forms.
    "is18168", "is_18168",
})
OMEGA0_REFUSED = frozenset({
    "assumed", "assumption", "silent", "silent_default", "invented",
    "asce7", "asce_7", "asce722", "proxy", "placeholder", "todo", "tbd", "guess",
    # Concrete seismic / ductile detailing — never India steel SFRS Ω sources
    "is15988", "is_15988", "is15988_2013", "is_15988_2013",
    "is13920", "is_13920", "is13920_2016", "is_13920_2016",
})

# Steel corpus sources accepted for Ω when found:true (concrete refused above).
OMEGA0_STEEL_CORPUS_SOURCES = frozenset({
    "is18168", "is_18168",
    "is1893", "is_1893", "rag",  # rare IS 1893 hit; do not invent
})

# India policy: IS 1893 does not tabulate an ASCE-style Ω0. For steel SFRS,
# prefer the IS 18168 Ω/ELm=Ω·EL corpus path when it is actually ingested; do
# not manufacture the familiar SCBF/EBF/SMRF values from memory.
OMEGA0_POLICY = {
    "blocks_complete": False,
    "preferred_source_when_available": "is18168",
    "honest_is1893_found_false_blocks_complete": False,
    "is18168_values_require_corpus_hit": True,
    "note": (
        "Steel Ω path is IS 18168 only (corpus found:true; ELm=Ω·EL). "
        "IS 15988 / IS 13920 are concrete and refused for steel overstrength. "
        "IS 1893 has no ASCE-style Ω0; never invent Ω without a found:true hit."
    ),
}


def _omega0_policy() -> dict:
    """Return a fresh Ω0 policy/disclosure object for public result payloads."""
    return dict(OMEGA0_POLICY)

EXAMPLE_RE = re.compile(r"example|acme|not.for.construction|placeholder|synthetic", re.I)
# report / screen strings that mean the configuration itself is not acceptable
REVISE_RE = re.compile(r"revise configuration|revise the (structural )?configuration|prohibited|"
                       r"not permitted|shall not be permitted|shall be revised", re.I)

ZONE_BY_Z = {0.10: "II", 0.16: "III", 0.24: "IV", 0.36: "V"}
Z_BY_ZONE = {v: k for k, v in ZONE_BY_Z.items()}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _norm(s) -> str:
    return str(s or "").strip().lower().replace("-", "_").replace(" ", "_")


def _summary(cfg):
    plan = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    ss = plan.get("seismic_summary") if isinstance(plan.get("seismic_summary"), dict) else {}
    return plan, ss


def _seis(cfg):
    return cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}


def _f(x):
    try:
        if x is None or isinstance(x, bool):
            return None
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _roman(z):
    s = str(z or "").strip().upper().replace("ZONE", "").strip()
    return s if s in ("II", "III", "IV", "V") else None


def zone_of(cfg) -> str | None:
    """Seismic zone (II..V) from seismic_summary.zone / cfg zone keys, else from Z."""
    cfg = cfg or {}
    _, ss = _summary(cfg)
    for src in (ss.get("zone"), _seis(cfg).get("zone"), cfg.get("zone"), cfg.get("seismic_zone")):
        z = _roman(src)
        if z:
            return z
    for src in (ss.get("Z"), _seis(cfg).get("Z"), cfg.get("Z")):
        Z = _f(src)
        if Z is not None:
            for k, v in ZONE_BY_Z.items():
                if abs(Z - k) < 1e-3:
                    return v
    return None


def system_text(cfg) -> str:
    cfg = cfg or {}
    _, ss = _summary(cfg)
    parts = [cfg.get("system"), cfg.get("system_x"), cfg.get("system_y")]
    if not any(parts):
        parts.append(ss.get("system"))
    return " + ".join(str(p) for p in parts if p)


def parse_systems(text, *, imf_as_smrf=False) -> list:
    """Canonical Table 9 keys (or 'nobasis:<x>') named in a system string."""
    t = " " + re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()) + " "
    found = []
    for rx, canon in _TOKEN_MAP:
        if re.search(rx, t):
            if canon == "imf":
                canon = "steel_smrf" if imf_as_smrf else "steel_omrf"
            if canon == "obf" and "sbf_concentric" in found and not re.search(r"\bocbf\b|\bobf\b|ordinary", t):
                continue                                   # 'SCBF' also matched the bare \bcbf\b rule
            if canon not in found:
                found.append(canon)
    return found


def resolve_system_R(cfg) -> dict:
    """Table 9 R for the declared system(s).

    R_table9 = min over all components (the default design R for both directions).  H06: per-direction R is
    honoured when declared -- cfg['R_x'] / cfg['R_y'] (or seis / seismic_summary R_x, R_y).  Each declared value
    is validated against the Table 9 R of that direction's system (cfg['system_x'] / cfg['system_y'] when given,
    else every declared component): a declared R above that value is refused (errors[], the Table 9 value is
    used), a lower one is kept (conservative).  R_x / R_y in the result are the values ESM and RSA use."""
    cfg = cfg or {}
    txt = system_text(cfg)
    imf = bool(cfg.get("imf_as_smrf"))
    comps = parse_systems(txt, imf_as_smrf=imf)
    rows = [TABLE9_STEEL[c] for c in comps if c in TABLE9_STEEL]
    nob = [c.split(":", 1)[1] for c in comps if c.startswith("nobasis:")]
    R = min((r["R"] for r in rows), default=None)
    _, ss = _summary(cfg)
    out = {"system_text": txt, "components": comps, "table9_rows": [r["row"] for r in rows],
           "R_table9": R, "no_basis": nob,
           "cite": "; ".join("%s R = %.1f" % (r["row"], r["R"]) for r in rows) or None,
           "errors": []}
    for d in ("x", "y"):
        dsys = cfg.get("system_" + d)
        dcomps = parse_systems(dsys, imf_as_smrf=imf) if dsys else comps
        drows = [TABLE9_STEEL[c] for c in dcomps if c in TABLE9_STEEL]
        Rt = min((r["R"] for r in drows), default=R)
        decl = None
        for src in (cfg, _seis(cfg), ss):
            v = _f(src.get("R_" + d))
            if v is not None:
                decl = v
                break
        use, basis = R, "min over components (Table 9)"
        if decl is not None:
            if Rt is not None and decl > Rt + 1e-9:
                out["errors"].append("R_%s = %.2f exceeds the IS 1893 Table 9 value %.2f for the %s-direction system %s"
                                     % (d, decl, Rt, d.upper(), "/".join(dcomps) or "?"))
                use, basis = Rt, "declared R_%s refused (> Table 9); Table 9 value of the %s-direction system" % (d, d.upper())
            else:
                use, basis = decl, "declared R_%s (<= Table 9 %s for %s)" % (d, Rt, "/".join(dcomps) or "?")
        out["R_" + d] = use
        out["R_%s_table9" % d] = Rt
        out["R_%s_declared" % d] = decl
        out["R_%s_basis" % d] = basis
    return out


def declared_R(cfg):
    cfg = cfg or {}
    _, ss = _summary(cfg)
    for src in (cfg.get("R"), _seis(cfg).get("R"), ss.get("R")):
        v = _f(src)
        if v is not None:
            return v
    return None


# ---------------------------------------------------------------------------
# legacy provenance API (kept; semantics tightened per D3)
# ---------------------------------------------------------------------------
TABLE9_SYSTEM_FLAGS = (
    (("R_steel_dual_table9_found", "steel_dual_table9_found"), ("dual",), "steel_dual_table9_found"),
    (("R_steel_brbf_table9_found", "steel_brbf_table9_found", "R_steel_brb_table9_found"),
     ("brbf", "brb", "buckling_restrained"), "steel_brbf_table9_found"),
    (("R_steel_spsw_table9_found", "steel_spsw_table9_found"),
     ("spsw", "steel_plate_shear", "plate_shear_wall"), "steel_spsw_table9_found"),
    # EBF is NOT a Table 9 miss: Table 9 (ii)(c) SBF eccentric R = 5.0 (HRLOAD-22).
    (("R_steel_imf_table9_found", "steel_imf_table9_found"), ("imf", "intermediate_moment"),
     "steel_imf_table9_found"),
)


def table9_system_flags(cfg) -> dict:
    cfg = cfg or {}
    _, ss = _summary(cfg)
    out = {}
    for keys, _subs, out_key in TABLE9_SYSTEM_FLAGS:
        val = None
        for k in keys:
            for src in (cfg, _seis(cfg), ss):
                if src.get(k) is not None:
                    val = src.get(k)
                    break
            if val is not None:
                break
        out[out_key] = val
    return out


def needs_table9_miss_gate(cfg) -> bool:
    return bool(resolve_system_R(cfg or {})["no_basis"]) or any(
        v is False for v in table9_system_flags(cfg or {}).values())


def resolve_R(cfg) -> dict:
    cfg = cfg or {}
    _, ss = _summary(cfg)
    seis = _seis(cfg)
    src = (cfg.get("R_source") or seis.get("R_source") or ss.get("R_source")
           or cfg.get("r_source") or ss.get("response_reduction_source"))
    cite = cfg.get("R_cite") or seis.get("R_cite") or ss.get("R_cite")
    flags = table9_system_flags(cfg)
    sysr = resolve_system_R(cfg)
    return {"R": declared_R(cfg), "source": src, "cite": cite, "raw_source": _norm(src),
            "R_table9": sysr["R_table9"], "components": sysr["components"],
            "table9_misses": [k for k, v in flags.items() if v is False] + sysr["no_basis"],
            **flags}


def validate_R(cfg) -> list:
    """(sev, msg): declared R must be the Table 9 value of the declared system (D3)."""
    out = []
    if not isinstance(cfg, dict):
        return [("ERROR", "cfg is not a dict")]
    info = resolve_R(cfg)
    R, src = info["R"], info["raw_source"]
    if src in R_PROXY_SOURCES or "proxy" in src or "silent" in src or "invent" in src:
        out.append(("ERROR", "R_source=%r is a proxy/silent path (incl. is800_omrf / IS 800 Table 23); "
                             "R must come from IS 1893 Table 9 for the declared system" % info["source"]))
    if src in ("eor_documented", "eor", "documented", "eor_explicit", "sbf_concentric_for_dual",
               "table9_sbf_for_dual"):
        out.append(("ERROR", "R_source=%r: owner ruling D3 removed the EOR-adopted R path -- R comes "
                             "from IS 1893 Table 9 only" % info["source"]))
    Rt = info["R_table9"]
    if R is None:
        out.append(("ERROR", "R not declared (cfg['R'] / seis.R / seismic_summary.R)"))
    elif Rt is not None:
        if R > Rt + 1e-9:
            out.append(("ERROR", "R = %.2f exceeds the IS 1893 Table 9 value %.2f for %s" %
                        (R, Rt, "/".join(info["components"]))))
        elif R < Rt - 1e-9:
            out.append(("WARN", "R = %.2f is below the Table 9 value %.2f (conservative)" % (R, Rt)))
    for msg in resolve_system_R(cfg).get("errors") or []:          # H06: per-direction R_x / R_y
        out.append(("ERROR", msg))
    return out


def R_is_proxy(cfg, pkg=None) -> bool:
    info = resolve_R(cfg or {})
    src = info["raw_source"]
    return bool(src in R_PROXY_SOURCES or "proxy" in src or "silent" in src or "invent" in src
                or info["table9_misses"])


def _is_concrete_omega_source(src) -> bool:
    """True when source names IS 15988 / IS 13920 (concrete — N/A for steel Ω)."""
    s = _norm(src)
    if not s:
        return False
    if s in {
        "is15988", "is_15988", "is15988_2013", "is_15988_2013",
        "is13920", "is_13920", "is13920_2016", "is_13920_2016",
    }:
        return True
    # Containment covers spellings like is_15988_clause_x / rag_is13920
    if "15988" in s or "13920" in s:
        return True
    return False


def _concrete_omega_refuse(src, *, via="refused") -> dict:
    """found:false payload when a concrete code is offered as steel Ω."""
    policy = _omega0_policy()
    src_n = _norm(src) or "concrete"
    return {
        "found": False,
        "Omega0": None,
        "corpus_found": False,
        "source": src_n,
        "resolved_via": via,
        "cite": "IS 15988 / IS 13920 are concrete — N/A for steel overstrength",
        "note": (
            "Refused Ω source=%r. IS 15988 and IS 13920 are concrete seismic/"
            "ductile-detailing codes, not steel SFRS overstrength sources. "
            "Use corpus IS 18168 Ω (found:true) for steel; do not invent values."
            % (src_n,)
        ),
        "required_inputs": [
            "corpus_hit={found:true, source:is18168, cite, Ω}",
            "OR Omega0_source=eor_documented + Omega0_cite",
        ],
        "is1893_omega0_present": False,
        "omega0_policy": policy,
        "disclosure": policy,
    }


def resolve_Omega0(cfg=None, *, eor_Omega0=None, eor_cite=None, eor_source=None,
                   corpus_hit=None) -> dict:
    """Resolve India steel overstrength without inventing ASCE-style Ω0.

    IS 1893 has no Ω0 — default found:false. The preferred path, when the
    corpus is available, is IS 18168 Ω for steel SFRS (ELm=Ω·EL), not an ASCE
    Ω0 term. An ``is18168`` value is accepted only from a found:true corpus
    hit; do not hardcode the familiar 2.5/3.0 values. The optional
    eor_documented hook remains valid for a project EOR value + cite.
    Honest found:false does not block COMPLETE and does not invent IS-native Ω.
    """
    cfg = cfg or {}
    seis = cfg.get("seis") if isinstance(cfg.get("seis"), dict) else {}
    plan = cfg.get("load_plan") if isinstance(cfg.get("load_plan"), dict) else {}
    summ = plan.get("seismic_summary") if isinstance(plan.get("seismic_summary"), dict) else {}

    # Corpus path (almost always miss for IS 1893). IS 18168 calls this Ω;
    # accept common Ω/Ω0 key spellings but preserve the public Omega0 field for
    # compatibility with existing India disclosures.
    if isinstance(corpus_hit, dict) and corpus_hit.get("found") is True:
        corpus_source = _norm(corpus_hit.get("source"))
        om = (corpus_hit.get("Omega") or corpus_hit.get("omega")
              or corpus_hit.get("Omega0") or corpus_hit.get("Om0")
              or corpus_hit.get("omega0"))
        # Concrete codes are never steel overstrength sources (even if HIT).
        if _is_concrete_omega_source(corpus_source):
            return _concrete_omega_refuse(corpus_source, via="refused_concrete_corpus")
        # Accept steel corpus hits from IS 18168 (preferred) or rare IS 1893;
        # ASCE / refused / other non-steel sources are not India Ω.
        if (om is not None
                and corpus_source in OMEGA0_STEEL_CORPUS_SOURCES
                and corpus_source not in OMEGA0_REFUSED
                and "asce" not in corpus_source):
            policy = _omega0_policy()
            return {
                "found": True,
                "Omega0": float(om),
                "source": corpus_source or "corpus",
                "resolved_via": "corpus",
                # In particular, an IS 18168 result must disclose the cite
                # returned by that hit rather than a made-up/default cite.
                "cite": corpus_hit.get("cite") or "IS 1893 (corpus)",
                "note": (
                    "Ω from corpus IS 18168 hit (ELm=Ω·EL); use the hit cite."
                    if corpus_source in {"is18168", "is_18168"}
                    else "Ω0 from corpus hit — rare for IS 1893; confirm clause."
                ),
                "omega0_policy": policy,
                "disclosure": policy,
            }

    om = eor_Omega0
    if om is None:
        om = cfg.get("Omega0") or cfg.get("Om0") or seis.get("Omega0") or seis.get("Om0")
        if om is None:
            om = summ.get("Omega0") or summ.get("Om0")
    src = _norm(eor_source or cfg.get("Omega0_source") or seis.get("Omega0_source")
                or summ.get("Omega0_source"))
    cite = (eor_cite or cfg.get("Omega0_cite") or seis.get("Omega0_cite")
            or summ.get("Omega0_cite"))

    # Concrete Omega0_source (with or without a cite/value) is never steel Ω.
    if _is_concrete_omega_source(src):
        return _concrete_omega_refuse(src, via="refused_concrete_source")

    # Explicit found:false disclosure (preferred India path)
    flagged_false = (
        cfg.get("Omega0_found") is False
        or seis.get("Omega0_found") is False
        or summ.get("Omega0_found") is False
        or (isinstance(corpus_hit, dict) and corpus_hit.get("found") is False)
    )

    if om is not None and src in OMEGA0_OK_SOURCES and cite and src not in {"is18168", "is_18168"}:
        # Owner ruling D3: no EOR-adopted Omega0.  IS 800 12.2.3 (2.5 EL) is the India
        # capacity-design load; an Omega is accepted only from a found:true IS 18168 corpus hit.
        policy = _omega0_policy()
        return {
            "found": False, "Omega0": None, "source": src, "resolved_via": "refused",
            "cite": "IS 1893 has no Omega0 -- refuse an EOR literal (D3); use IS 800 12.2.3 (2.5EL)",
            "note": "Refused Omega0 source=%r: owner ruling D3 removed the EOR-adopted Omega path; "
                    "use IS 800 12.2.3 (1.2DL+0.5LL+-2.5EL / 0.9DL+-2.5EL) or an IS 18168 corpus hit." % (src,),
            "required_inputs": ["corpus_hit={found:true, source:is18168, cite, Omega}"],
            "omega0_policy": policy, "disclosure": policy,
        }
    if om is not None and src in OMEGA0_OK_SOURCES and cite:
        # IS 18168 values are not an EOR alias and may not be supplied as an
        # unexplained literal. They must come from the found:true corpus
        # branch above; this prevents inventing 2.5/3.0 without the PDF hit.
        if src in {"is18168", "is_18168"}:
            policy = _omega0_policy()
            return {
                "found": False,
                "Omega0": None,
                "corpus_found": False,
                "source": src,
                "resolved_via": "found_false",
                "cite": "IS 18168 Ω requires a found:true corpus hit",
                "note": (
                    "Refused literal IS 18168 Ω without a found:true corpus hit; "
                    "do not hardcode SCBF/EBF/SMRF values."
                ),
                "required_inputs": ["corpus_hit={found:true, source:is18168, cite, Ω}"],
                "is1893_omega0_present": False,
                "flagged_false": bool(flagged_false) or True,
                "omega0_policy": policy,
                "disclosure": policy,
            }
        if src in OMEGA0_REFUSED or "asce" in src:
            policy = _omega0_policy()
            return {
                "found": False,
                "Omega0": None,
                "source": src,
                "resolved_via": "refused",
                "cite": "IS 1893 has no Ω0 — refuse silent ASCE invent",
                "note": (
                    "Refused Ω0 source=%r. Do not invent ASCE 7 Ω0 for India. "
                    "Use IS 800 §12 capacity-design factors, or supply "
                    "Omega0_source='eor_documented' with Omega0_cite (project EOR)."
                    % (src,)
                ),
                "required_inputs": ["Omega0_source in eor_documented/explicit", "Omega0_cite"],
                "omega0_policy": policy,
                "disclosure": policy,
            }
        policy = _omega0_policy()
        return {
            "found": True,
            "Omega0": float(om),
            "corpus_found": False,
            "source": src,
            "resolved_via": "eor_documented" if ("eor" in src or src == "documented") else src,
            "cite": str(cite),
            "note": (
                "Ω0 from EOR/documented path — IS 1893 has no tabulated Ω0. "
                "Not invented silently. Prefer IS 800 §12 factors for capacity design."
            ),
            "policy": "eor_documented_ok_when_is1893_miss",
            "omega0_policy": policy,
            "disclosure": policy,
        }

    # Default honest miss
    refused = []
    if om is not None and (src in OMEGA0_REFUSED or "asce" in src or not src):
        refused.append("Omega0_source must be eor_documented/explicit (not asce/assumed/silent)")
    if om is not None and not cite:
        refused.append("Omega0_cite")
    policy = _omega0_policy()
    return {
        "found": False,
        "Omega0": None,
        "corpus_found": False,
        "source": src or None,
        "resolved_via": "found_false",
        "cite": "IS 1893 (Part 1):2016 — no ASCE-style Ω0; use IS 800 §12.2.3 (2.5EL) combinations",
        "note": (
            "Ω0 found:false (honest). Do not invent ASCE 7 Ω0: use IS 800 12.2.3 (2.5EL) "
            "combinations and the Section 12 capacity rules (1.2 fy Ag, 1.1 fy Ag, 1.2 Mp ...)."
        ),
        "required_inputs": refused or [
            "leave Omega0_found=false",
            "OR Omega0 + Omega0_source=eor_documented + Omega0_cite",
        ],
        "is1893_omega0_present": False,
        "flagged_false": bool(flagged_false) or True,
        "omega0_policy": policy,
        "disclosure": policy,
    }


def omega0_blocks_complete(cfg=None, pkg=None) -> bool:
    """Omega0 itself never blocks (IS 800 12.2.3 replaces it); missing 12.2.3 cases do."""
    return False


# ---------------------------------------------------------------------------
# WP1.5 -- zone / system gate
# ---------------------------------------------------------------------------
def importance_of(cfg):
    _, ss = _summary(cfg or {})
    for src in ((cfg or {}).get("I"), _seis(cfg or {}).get("I"), _seis(cfg or {}).get("Ie"), ss.get("I")):
        v = _f(src)
        if v is not None:
            return v
    return None


def system_zone_findings(cfg) -> list:
    """ERROR for banned / non-IS systems (IS 1893 Table 9 Note 1 with Amd 2 = D4; IS 800 12.7.1.1,
    12.10.1.1; D3 no foreign basis).  Returns [(sev, msg), ...]."""
    out = []
    cfg = cfg or {}
    sysr = resolve_system_R(cfg)
    if not sysr["system_text"]:
        return [("ERROR", "cfg['system'] not declared -- name the IS 1893 Table 9 system (e.g. 'SCBF', 'SMRF')")]
    if not sysr["components"]:
        out.append(("ERROR", "system %r is not recognised as an IS 1893 Table 9 steel system" % sysr["system_text"]))
    for nb in sysr["no_basis"]:
        out.append(("ERROR", "no Indian design basis: %s (owner ruling D3)" % NO_IS_BASIS.get(nb, nb)))
    if re.search(r"\bimf\b|\bimrf\b|intermediate", " " + re.sub(r"[^a-z0-9]+", " ", sysr["system_text"].lower()) + " "):
        out.append(("WARN", "IMF is not an IS 1893 Table 9 system: treated as %s" %
                    ("SMRF (full IS 800 12.11 compliance required)" if cfg.get("imf_as_smrf") else
                     "OMRF (Table 9 (i)(c), R 3, banned in Zones III-V)")))
    z = zone_of(cfg)
    if z is None:
        out.append(("ERROR", "seismic zone not resolvable (seismic_summary.zone or Z)"))
    I = importance_of(cfg)
    for c in sysr["components"]:
        row = TABLE9_STEEL.get(c)
        if not row or z is None:
            continue
        if z in row["note1_banned_zones"]:
            msg = "%s is not allowed in Seismic Zone %s -- %s" % (row["name"], z, TABLE9_NOTE1_CITE)
            if row.get("is800_ban"):
                msg += "; " + row["is800_ban"]
            out.append(("ERROR", msg))
        elif z == "III" and row.get("is800_ban") and I is not None and I > 1.0:
            out.append(("ERROR", "%s with I = %.1f in Zone III -- %s" % (row["name"], I, row["is800_ban"])))
    for sev, msg in validate_R(cfg):
        out.append((sev, msg))
    return out


# ---------------------------------------------------------------------------
# package walkers
# ---------------------------------------------------------------------------
_PAIR_KEYS = (("value", "limit"), ("demand", "capacity"), ("demand_N", "capacity_N"),
              ("demand_Nmm", "capacity_Nmm"), ("demand_kN", "capacity_kN"),
              ("demand_kNm", "capacity_kNm"), ("demand_MPa", "capacity_MPa"),
              ("demand_mm", "capacity_mm"))


def _pair(d):
    if not isinstance(d, dict):
        return None, None
    for a, b in _PAIR_KEYS:
        if a in d or b in d:
            return _f(d.get(a)), _f(d.get(b))
    return None, None


def _checks_of(entry):
    """All check-like dicts of a member / connection entry (top-level + checks list/dict + component_checks)."""
    out = []
    if not isinstance(entry, dict):
        return out
    ch = entry.get("checks")
    if isinstance(ch, list):
        out += [c for c in ch if isinstance(c, dict)]
    elif isinstance(ch, dict):
        out += [dict(v, name=k) for k, v in ch.items() if isinstance(v, dict)]
    cc = entry.get("component_checks")
    if isinstance(cc, dict):
        out += [dict(v, name=k) for k, v in cc.items() if isinstance(v, dict)]
    v, l = _pair(entry)
    if v is not None or l is not None:
        out.append(dict(entry, name=entry.get("limit_state") or "headline"))
    return out


def _dc_stored(c):
    for k in ("dc", "DC", "D/C"):
        if k in c:
            return c.get(k), True
    return None, False


def entry_findings(kind, entry) -> list:
    """Numeric demand/capacity rules of 0.2 for one package entry."""
    out = []
    eid = entry.get("id") or entry.get("name") or "?"
    waived = entry.get("waived")
    checks = _checks_of(entry)
    if waived:
        numeric = [c for c in checks if _pair(c)[0] is not None and _pair(c)[1] not in (None, 0.0)]
        if not (numeric and entry.get("waiver_approved_by")):
            out.append("%s '%s' is waived without a numeric replacement check + waiver_approved_by" % (kind, eid))
    if not checks:
        out.append("%s '%s' has no check with numeric demand and capacity" % (kind, eid))
        return out
    for c in checks:
        nm = c.get("name") or c.get("limit_state") or c.get("clause") or "check"
        val, lim = _pair(c)
        stored, has = _dc_stored(c)
        if val is None or lim is None:
            if c.get("gate") is True and c.get("ok") is not None:
                if c.get("ok") is False:
                    out.append("%s '%s' / %s: ok:false" % (kind, eid, nm))
                continue                     # boolean detailing gate (12.4.1 / 12.4.2 / 12.4.3): no D/C by nature
            if c.get("ok") is True or (_f(stored) is not None):
                out.append("%s '%s' / %s: D/C or ok without numeric demand AND capacity" % (kind, eid, nm))
            elif c.get("found") is False or stored is None:
                out.append("%s '%s' / %s: not evaluated (found:false / DC None)" % (kind, eid, nm))
            continue
        if lim <= 0:
            out.append("%s '%s' / %s: capacity %.4g is not positive" % (kind, eid, nm, lim))
            continue
        dc = abs(val) / lim
        if dc > 1.0 + 1e-6:
            out.append("%s '%s' / %s: D/C = %.3f > 1.0 (demand %.4g / capacity %.4g)" % (kind, eid, nm, dc, val, lim))
        s = _f(stored)
        if s is not None and abs(s - dc) > 0.02 * max(dc, 1e-3) + 1e-4:
            out.append("%s '%s' / %s: stored D/C %.3f != recomputed demand/capacity %.3f" % (kind, eid, nm, s, dc))
        if val == 0.0 and entry.get("inputs", {}).get("V_N") is None and kind == "connection":
            out.append("%s '%s' / %s: zero demand with no shear demand recorded" % (kind, eid, nm))
        if c.get("ok") is False:
            out.append("%s '%s' / %s: ok:false" % (kind, eid, nm))
    return out


def _walk_strings(o, path="", acc=None):
    acc = [] if acc is None else acc
    if isinstance(o, dict):
        for k, v in o.items():
            _walk_strings(v, path + "." + str(k), acc)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk_strings(v, path + "[%d]" % i, acc)
    elif isinstance(o, str):
        acc.append((path, o))
    return acc


def example_label_hits(*objs) -> list:
    """(path, text) of cite/_label/source/basis strings matching the EXAMPLE regex.  H32: free-text note leaves
    ('note', 'notes', '*_note', '*_notes') are exempt -- a note may say "EXAMPLE EOR json not used"; only the
    provenance leaves (cite, label, source, basis) are scanned."""
    hits = []
    for o in objs:
        for p, s in _walk_strings(o):
            leaf = re.sub(r"(\[\d+\])+$", "", p.rsplit(".", 1)[-1]).lower()
            if leaf in ("note", "notes") or leaf.endswith("_note") or leaf.endswith("_notes"):
                continue
            if any(t in leaf for t in ("cite", "label", "source", "basis")) and EXAMPLE_RE.search(s):
                hits.append((p, s[:120]))
    return hits


def _load_pkg(pkg, job_dir):
    if isinstance(pkg, dict):
        return pkg
    for cand in ([pkg] if isinstance(pkg, str) else []) + (
            [os.path.join(job_dir, "design", "calc_package.json")] if job_dir else []):
        try:
            if cand and os.path.exists(cand):
                return json.load(open(cand, encoding="utf-8"))
        except Exception:
            return None
    return None


def _sha(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return None


def provenance_findings(pkg, job_dir) -> list:
    """0.2 last bullet: the hash of the fill script + cfg recorded in the package matches the shipped files."""
    out = []
    prov = (pkg or {}).get("provenance") if isinstance(pkg, dict) else None
    if not isinstance(prov, dict) or not prov.get("files"):
        return ["package has no provenance.files hash record (fill script + cfg) -- regenerate via design_pipeline"]
    for rel, h in dict(prov["files"]).items():
        p = os.path.join(job_dir, rel) if job_dir else rel
        if not os.path.exists(p):
            out.append("provenance file %s is not shipped" % rel)
        elif _sha(p) != h:
            out.append("provenance hash mismatch for %s (package is stale relative to the shipped script/cfg)" % rel)
    return out


# ---------------------------------------------------------------------------
# method / combination / irregularity / occupancy rules
# ---------------------------------------------------------------------------
def building_height_m(cfg):
    H = cfg.get("heights") or []
    try:
        tot = float(sum(float(h) for h in H))
    except Exception:
        return None
    try:
        from india_units import is_si
        si = is_si(cfg)
    except Exception:
        si = True
    if si:
        return tot / 1000.0 if tot > 200 else tot
    return tot * 0.0254


def esm_permitted(cfg, pkg=None) -> tuple:
    """IS 1893 7.6 / 7.7.1: ESM alone only for regular buildings < 15 m in Zone II."""
    z = zone_of(cfg)
    h = building_height_m(cfg)
    irr = irregularity_reasons(cfg, pkg)
    ok = (z == "II" and h is not None and h < 15.0 and not irr and cfg.get("regular") is not False)
    why = []
    if z != "II":
        why.append("Zone %s" % z)
    if h is None or h >= 15.0:
        why.append("height %s m >= 15 m" % (round(h, 2) if h is not None else "?"))
    if irr:
        why.append("irregular (%s)" % "; ".join(irr[:3]))
    return ok, why


def irregularity_reasons(cfg, pkg=None) -> list:
    out = []
    scr = {}
    if isinstance(pkg, dict):
        scr = pkg.get("irregularity") or {}
    for k in ("torsion", "soft_storey", "mass", "vertical_geometric", "reentrant", "in_plane_discontinuity",
              "strength", "floating_columns", "modes", "out_of_plane_offset", "diaphragm_openings",
              "nonparallel"):
        v = scr.get(k) if isinstance(scr, dict) else None
        if isinstance(v, dict) and v.get("irregular"):
            out.append(k)
    for k in ("reentrant", "setback", "nonparallel"):
        if (pkg or {}).get("framework_screen", {}).get("plan", {}).get(k) if isinstance(pkg, dict) else False:
            if k not in out:
                out.append(k)
    if cfg.get("irregular") is True:
        out.append("declared irregular")
    return out


FLEX_EOR_KEYS = ("analysis_ref", "results", "source", "cite")


def flexible_diaphragm_eor(cfg):
    """H01: a verified EOR record of the Table 5(ii) flexible-diaphragm 3D dynamic analysis.
    cfg['flexible_diaphragm_eor'] = {analysis_ref, results, source, cite}, all four non-empty.
    Returns (record | None, missing keys).  The private cfg key '_flexible_diaphragm_run' is NOT evidence."""
    rec = (cfg or {}).get("flexible_diaphragm_eor")
    if not isinstance(rec, dict):
        return None, list(FLEX_EOR_KEYS) if rec is not None else []

    def _empty(v):
        return v is None or (isinstance(v, (str, list, tuple, dict)) and not (v.strip() if isinstance(v, str) else v))
    miss = [k for k in FLEX_EOR_KEYS if _empty(rec.get(k))]
    if miss:
        return None, miss
    return dict(rec, basis="EOR-documented"), []


def analysis_findings(cfg, pkg) -> list:
    out = []
    ok_esm, why = esm_permitted(cfg, pkg)
    an = (pkg or {}).get("seismic_analysis") if isinstance(pkg, dict) else None
    an = an if isinstance(an, dict) else {}
    rsa = bool(an.get("rsa_used_in_demands"))
    if not ok_esm and not rsa:
        out.append("IS 1893 7.7.1: linear dynamic analysis required (%s) but scaled RSA forces were not "
                   "used in the member demands" % ", ".join(why))
    if rsa:
        for d in ("X", "Y"):
            s = (an.get("scale") or {}).get(d) if isinstance(an.get("scale"), dict) else None
            if not isinstance(s, dict) or _f(s.get("VB_scaled_kN")) is None:
                out.append("RSA %s: 7.7.3.1 scaling record missing" % d)
            elif _f(s.get("VBbar_kN")) and _f(s["VB_scaled_kN"]) < _f(s["VBbar_kN"]) * 0.999:
                out.append("RSA %s: scaled base shear %.1f kN < VB(Ta) %.1f kN (7.7.3.1)"
                           % (d, _f(s["VB_scaled_kN"]), _f(s["VBbar_kN"])))
            if isinstance(s, dict) and _f(s.get("mass_participation")) is not None and _f(s["mass_participation"]) < 0.90:
                out.append("RSA %s: modal mass %.1f %% < 90 %% (7.7.5.2)" % (d, 100 * _f(s["mass_participation"])))
    if an.get("reentrant_flexible_required"):
        # H01: the flag counts only when an engine flexible-diaphragm run recorded it, or with a complete EOR record
        basis = an.get("flexible_diaphragm_basis")
        eor = an.get("flexible_diaphragm_eor") if isinstance(an.get("flexible_diaphragm_eor"), dict) else {}
        ok_flex = an.get("flexible_diaphragm_run") is True and (
            basis == "engine" or (basis == "EOR-documented" and all(eor.get(k) for k in FLEX_EOR_KEYS)))
        if not ok_flex:
            eng_err = an.get("flexible_diaphragm_engine_error")
            out.append("Amd 2 Table 5(ii): re-entrant plan requires a flexible-diaphragm 3D dynamic analysis in "
                       "addition to the rigid case -- not performed (no engine run and no complete "
                       "cfg['flexible_diaphragm_eor'] {analysis_ref, results, source, cite})"
                       + ("; engine run: %s" % eng_err if eng_err else ""))
    fd = an.get("flexible_diaphragm") if isinstance(an.get("flexible_diaphragm"), dict) else {}
    if an.get("flexible_diaphragm_engine_error") and not an.get("reentrant_flexible_required"):
        out.append("flexible-diaphragm analysis requested (cfg['flexible_diaphragm_analysis']) but not run: %s"
                   % an["flexible_diaphragm_engine_error"])
    if an.get("flexible_diaphragm_basis") == "engine":
        # X01: the engine run counts only with its own 7.7.5.2 / 7.7.3.1 / drift records evaluated and passing
        for c in fd.get("checks") or []:
            if isinstance(c, dict) and c.get("ok") is not True:
                out.append("Table 5(ii) flexible-diaphragm run: %s %s (%s)" % (
                    c.get("name"), "fails" if c.get("ok") is False else "not evaluated",
                    c.get("reason") or "value %s, limit %s" % (c.get("value"), c.get("limit"))))
    return out


def G_zone_needs_7112(cfg) -> bool:
    return zone_of(cfg) in ("III", "IV", "V")


def section12_system(cfg) -> bool:
    """IS 800 12.1: Section 12 applies to frames resisting EQ in all zones (incl. OMF/OBF)."""
    comps = resolve_system_R(cfg)["components"]
    return any(c in TABLE9_STEEL for c in comps)


def combination_findings(cfg, pkg) -> list:
    out = []
    combos = (pkg or {}).get("load_combinations") if isinstance(pkg, dict) else None
    if not isinstance(combos, list) or not combos:
        return ["package has no load_combinations record (expanded case list)"]
    labels = [str(c.get("label", "")) for c in combos if isinstance(c, dict)]
    seismic = [c for c in combos if isinstance(c, dict) and str(c.get("lateral_kind") or "").upper() == "EQ"]
    if not seismic and not cfg.get("no_seismic"):
        out.append("no earthquake combinations in the package")
        return out
    if section12_system(cfg):
        has = [c for c in combos if isinstance(c, dict) and ("col_only" in (c.get("tags") or [])
               or "conn_only" in (c.get("tags") or [])) and abs(abs(float(c.get("fE") or 0)) - 2.5) < 1e-6]
        if not has:
            out.append("IS 800 12.2.3 (1.2DL+0.5LL+-2.5EL / 0.9DL+-2.5EL) cases absent for a Section 12 system")
    # fE in the package record is the SIGNED lateral factor (india_loads.Case.meta fLat); 'sign' repeats its sign
    signs = {(c.get("direction"), 1 if float(c.get("fE") if c.get("fE") is not None else c.get("sign") or 1) > 0 else -1)
             for c in seismic}
    for d in ("X", "Y"):
        if (d, 1) not in signs or (d, -1) not in signs:
            out.append("EQ %s: both +/- load reversal cases are required" % d)
    if not any(c.get("torsion") for c in seismic):
        out.append("IS 1893 7.8.2 design-eccentricity (torsion) cases absent")
    return out


def occupancy_findings(cfg) -> list:
    try:
        from india_seismic import importance_factor
    except Exception as ex:
        return ["importance-factor resolver unavailable: %s" % ex]
    occ = (cfg or {}).get("occupancy")
    if occ is None:
        _, ss = _summary(cfg or {})
        occ = ss.get("occupancy")
    r = importance_factor(occ)
    if not r.get("found"):
        return ["I not resolved from occupancy (IS 1893 Table 8): %s" % r.get("note")]
    I = importance_of(cfg)
    if I is None:
        return ["I not declared"]
    if I + 1e-9 < r["I"]:
        # H20: the matched keyword / flag and the ruling label (R2) are part of the message
        via = (" via %s" % r["matched_keyword"]) if r.get("matched_keyword") else ""
        return ["I = %.2f is below the %s value %.2f%s" % (
            I, "Table 8" if str(r.get("row") or "").startswith("Table 8") else "resolved", r["I"],
            " (%s%s)" % (r.get("row"), via))]
    return []


def occupancy_warnings(cfg) -> list:
    """H20: non-blocking Table 8 notes (storage use without food_storage declared, keyword-only row (i),
    residential precedence over an institution name)."""
    try:
        from india_seismic import importance_factor
    except Exception:
        return []
    occ = (cfg or {}).get("occupancy")
    if occ is None:
        _, ss = _summary(cfg or {})
        occ = ss.get("occupancy")
    return list(importance_factor(occ).get("warnings") or [])


def _R_system_agreement(cfg, pkg) -> list:
    out = []
    Rs = {}
    R0 = declared_R(cfg)
    if R0 is not None:
        Rs["cfg"] = R0
    if isinstance(pkg, dict):
        for key in ("seismic_calc", "capacity_design"):
            blk = pkg.get(key)
            if isinstance(blk, dict) and _f(blk.get("R")) is not None:
                Rs[key] = _f(blk.get("R"))
        lp = pkg.get("load_plan") or {}
        ss = lp.get("seismic_summary") if isinstance(lp, dict) else None
        if isinstance(ss, dict) and _f(ss.get("R")) is not None:
            Rs["load_plan"] = _f(ss.get("R"))
    vals = set(round(v, 3) for v in Rs.values())
    if len(vals) > 1:
        out.append("R disagrees between %s" % ", ".join("%s=%s" % kv for kv in Rs.items()))
    comps0 = set(resolve_system_R(cfg)["components"])
    if isinstance(pkg, dict):
        cd = pkg.get("capacity_design")
        if isinstance(cd, dict) and cd.get("system"):
            c2 = set(parse_systems(cd.get("system"), imf_as_smrf=bool(cfg.get("imf_as_smrf"))))
            if c2 and comps0 and c2 != comps0:
                out.append("capacity_design.system %r does not match cfg system %r" % (cd.get("system"), cfg.get("system")))
    return out


def _grounding_findings(pkg, job_dir) -> list:
    g = (pkg or {}).get("grounding") if isinstance(pkg, dict) else None
    if isinstance(g, dict) and g.get("rows"):
        miss = [r.get("topic") for r in g["rows"] if isinstance(r, dict) and str(r.get("status")).upper() == "MISSING"]
        return ["report grounding table has MISSING row(s): %s" % ", ".join(map(str, miss))] if miss else []
    if job_dir:
        rp = os.path.join(job_dir, "report.html")
        if os.path.exists(rp):
            try:
                txt = open(rp, encoding="utf-8", errors="replace").read()
                if re.search(r">\s*MISSING\s*<", txt):
                    return ["report grounding table has a MISSING row"]
                return []
            except Exception:
                pass
    return ["grounding record not available (report not built)"]


def _screen_findings(pkg, cfg_hint=None) -> list:
    out = []
    cfg_hint = cfg_hint or {}
    if not isinstance(pkg, dict):
        return out
    cd = pkg.get("capacity_design") or {}
    chk = cd.get("checks") if isinstance(cd, dict) else None
    if isinstance(cd, dict) and cd.get("error"):
        out.append("capacity_design (Section 12) not evaluated: %s" % cd["error"])
    elif isinstance(cd, dict) and section12_system(cfg_hint) and not chk:
        out.append("capacity_design.checks is empty for a Section 12 system")
    if isinstance(chk, dict):
        for k, v in chk.items():
            if isinstance(v, dict) and (v.get("pass") is False or v.get("ok") is False):
                out.append("capacity_design.checks.%s fails (pass/ok false)" % k)
            elif isinstance(v, dict) and (v.get("found") is False or v.get("ok") is None and v.get("pass") is None):
                out.append("capacity_design.checks.%s not evaluated" % k)
    for row in (pkg.get("drift_table") or []):
        if isinstance(row, dict) and row.get("ok") is False:
            out.append("drift_table storey %s fails" % row.get("storey"))
    d764 = pkg.get("diaphragm_7_6_4")
    if isinstance(d764, dict) and d764.get("ok") is None:
        out.append("IS 1893 7.6.4 diaphragm classification not evaluated: %s" % (d764.get("reason") or d764.get("error")))
    pond = pkg.get("ponding")
    if isinstance(pond, dict) and pond.get("ok") is None:
        out.append("IS 875 (Part 4) 4.4 ponding screen not evaluated: %s" % (pond.get("reason") or pond.get("error")))
    elif isinstance(pond, dict) and pond.get("ok") is False:
        out.append("IS 875 (Part 4) 4.4 ponding screen fails: delta %.1f mm >= fall %.1f mm over the half span" % (
            float(pond.get("value") or 0.0), float(pond.get("limit") or 0.0)))
    comp = pkg.get("composite_design")
    if isinstance(comp, dict) and comp.get("blocks_complete"):
        out.append("composite_design: IS 11384 not in the corpus -- record the scope (bare_steel + construction "
                   "stage, or delegated); unresolved slots block COMPLETE (WP2.9)")
    if isinstance(comp, dict):
        for s_ in ((comp.get("chI_worksheet") or {}).get("slots") or []):
            if isinstance(s_, dict) and isinstance(s_.get("DC"), (int, float)) and s_["DC"] > 1.0 + 1e-6:
                out.append("composite_design.%s: D/C = %.3f > 1.0 (%s)" % (s_.get("component"), s_["DC"], s_.get("cited")))
    for blk in ("irregularity", "framework_screen"):
        for p, s in _walk_strings(pkg.get(blk) or {}):
            if REVISE_RE.search(s):
                out.append("%s%s: %s" % (blk, p, s[:100]))
    return out


# ---------------------------------------------------------------------------
# THE authority
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------
# RR-BUG-4: reasons ordered by class and per-check element rows grouped, so a cap never drops a blocking class
# ---------------------------------------------------------------------------------------------------------------
REASON_CLASSES = ("analysis", "irregularity", "gates", "evidence", "system", "other", "elements")
_RC_ELEM_AT = re.compile(r"^(?P<pre>.*?)@(?P<el>(?:base-|conn-)?e\d+)\b(?P<post>.*)$")
_RC_ELEM_ENTRY = re.compile(r"^(?P<kind>member|connection|anchorage|hold_down|collector|schedule|secondary_member|"
                            r"gantry girder|7\.11\.2/7\.11\.3) '(?P<id>[^']*)' / (?P<name>.*?): (?P<msg>.*)$")
_RC_GROUPED = re.compile(r"^check .* on \d+ \S+ \(e\.g\. ")      # a row summarize_reasons already grouped
_RC_RULES = (
    ("irregularity", re.compile(r"Table 5|Table 6|irregular|re-?entrant|flexible.diaphragm|7\.6\.4|torsion", re.I)),
    ("gates", re.compile(r"\bgate\b|capacity_design|FAILS|across.wind|dynamic_wind|ponding|composite_design", re.I)),
    ("analysis", re.compile(r"analysis|7\.7\.1|\bRSA\b|\bESM\b|modal|drift|calc_package|collector / chord|"
                            r"crane present|deformation.compatibility|combination|cases absent|reversal", re.I)),
    ("evidence", re.compile(r"consistency|retrieval|provenance|grounding|EOR|evidence|found:false without|"
                            r"US-residue|residue|example/placeholder|rag\b", re.I)),
    ("system", re.compile(r"Table 9|Table 8|system|zone|\bR\b|\bI\b = |occupancy|banned|importance", re.I)),
)


def reason_class(r) -> str:
    """RR-BUG-4: class of one design_status reason (REASON_CLASSES); per-element rows are 'elements'."""
    s = str(r)
    if _RC_ELEM_AT.match(s) or _RC_ELEM_ENTRY.match(s) or _RC_GROUPED.match(s):
        return "elements"
    for cls, rx in _RC_RULES:
        if rx.search(s):
            return cls
    return "other"


def summarize_reasons(reasons, limit=200) -> dict:
    """RR-BUG-4: design_status reasons -> {reasons, n_reasons, n_listed, classes, truncated}.

    Order: analysis / irregularity / gates / evidence / system / other first (in their original order within a
    class), then the per-check element rows grouped as 'check X fails on N elements (e.g. e12, e40, e41, ...)'.
    n_reasons is the full (ungrouped) count; a cap at ``limit`` never drops a class -- every class keeps at least its
    first row, and the cut is reported in a closing line."""
    reasons = [str(r) for r in (reasons or [])]
    heads = {c: [] for c in REASON_CLASSES}
    groups, order = {}, []
    for r in reasons:
        cls = reason_class(r)
        if cls != "elements":
            if r not in heads[cls]:
                heads[cls].append(r)
            continue
        m = _RC_ELEM_AT.match(r)
        if _RC_GROUPED.match(r):
            key, el, m = ("grouped", r), None, None
            groups.setdefault(key, {"first": r, "els": [None], "msg": None})
            if key not in order:
                order.append(key)
            continue
        if m:
            key = ("at", m.group("pre"), m.group("post"))
            el = m.group("el")
        else:
            m = _RC_ELEM_ENTRY.match(r)
            key = ("entry", m.group("kind"), m.group("name"), re.sub(r"-?\d+(\.\d+)?(e[-+]?\d+)?", "#", m.group("msg")))
            el = m.group("id")
        if key not in groups:
            groups[key] = {"first": r, "els": [], "msg": (m.group("msg") if key[0] == "entry" else None)}
            order.append(key)
        if el not in groups[key]["els"]:
            groups[key]["els"].append(el)
    elem_rows = []
    for key in order:
        g = groups[key]
        n = len(g["els"])
        if n == 1:
            elem_rows.append(g["first"])
            continue
        eg = ", ".join(g["els"][:3]) + (", ..." if n > 3 else "")
        if key[0] == "at":
            elem_rows.append("check %s%s on %d elements (e.g. %s)" % (key[1], key[2], n, eg))
        else:
            elem_rows.append("check %s / %s fails on %d %ss (e.g. %s): %s" % (key[1], key[2], n, key[1], eg, g["msg"]))
    heads["elements"] = elem_rows
    ordered = [r for c in REASON_CLASSES for r in heads[c]]
    classes = {c: len(heads[c]) for c in REASON_CLASSES if heads[c]}
    n_raw = {c: 0 for c in REASON_CLASSES}
    for r in reasons:
        n_raw[reason_class(r)] += 1
    out, truncated = ordered, False
    if limit is not None and len(ordered) > limit:
        truncated = True
        keep = set(id(heads[c][0]) for c in REASON_CLASSES if heads[c])   # the first row of every class survives
        room = max(limit - len(keep), 0)
        sel = []
        for r in ordered:
            if id(r) in keep:
                sel.append(r)
            elif room > 0:
                sel.append(r)
                room -= 1
        out = sel + ["... %d more reason rows not listed here (n_reasons = %d; see STATUS.engine.md)"
                     % (len(ordered) - len(sel), len(reasons))]
    return {"reasons": out, "n_reasons": len(reasons), "n_listed": len(out), "truncated": truncated,
            "classes": classes, "classes_raw": {c: v for c, v in n_raw.items() if v}}


def status_record(st, limit=200) -> dict:
    """RR-BUG-4: the design_status record stored in the package / returned by the pipeline -- ordered and grouped
    reasons (summarize_reasons), the full count and the reason classes."""
    sm = summarize_reasons(st.get("reasons") or [], limit=limit)
    return {"status": st["status"], "n_reasons": sm["n_reasons"], "reasons": sm["reasons"],
            "reason_classes": sm["classes_raw"], "reasons_truncated": sm["truncated"], "authority": st["authority"],
            "warnings": list(st.get("warnings") or [])}


def design_status(cfg, pkg=None, *, job_dir=None, report_html=None) -> dict:
    """Single COMPLETE authority (spec 0.2).  Returns
    {status: complete|partial|example_only, complete_allowed, reasons, example_hits, ...}."""
    cfg = cfg or {}
    reasons = []
    pk = _load_pkg(pkg, job_dir)
    if job_dir is None and isinstance(pkg, str) and os.path.exists(pkg):
        job_dir = os.path.dirname(os.path.dirname(os.path.abspath(pkg)))
    # --- system / zone / R / I ---
    reasons += [m for s, m in system_zone_findings(cfg) if s == "ERROR"]
    reasons += occupancy_findings(cfg)
    ex_hits = example_label_hits(cfg, pk or {})
    if pk is None:
        reasons.append("no calc_package -- nothing designed yet")
    else:
        mem = pk.get("members") or []
        con = pk.get("connections") or []
        if not mem:
            reasons.append("calc_package has no members")
        if not con:
            reasons.append("calc_package has no connections")
        for m in mem:
            if isinstance(m, dict):
                reasons += entry_findings("member", m)
        for c in con:
            if isinstance(c, dict):
                reasons += entry_findings("connection", c)
        for key in ("anchorages", "hold_downs", "collectors", "schedule", "secondary_members"):
            for e in (pk.get(key) or []):
                if isinstance(e, dict):
                    reasons += entry_findings(key.rstrip("s"), e)
        for g, ok in (pk.get("gates") or {}).items():
            if ok is False:
                reasons.append("analysis gate %s FAILS (engine3d.run_india)" % g)
        col_ = pk.get("collectors")
        if isinstance(col_, dict) and col_.get("error"):
            reasons.append("collector / chord forces not computed: %s (WP2.6)" % col_["error"])
        elif isinstance(col_, dict) and any("error" in r for r in (col_.get("rows") or []) if isinstance(r, dict)):
            reasons.append("collector / chord forces not computed: %s (WP2.6)"
                           % next(r["error"] for r in col_["rows"] if isinstance(r, dict) and "error" in r))
        if cfg.get("crane") or cfg.get("cranes"):
            gg = pk.get("gantry_girder")
            if not isinstance(gg, dict):
                reasons.append("crane present but no gantry girder design (WP2.7)")
            else:
                reasons += entry_findings("gantry girder", dict(gg, id="gantry"))
            if not isinstance(pk.get("crane_sway"), dict):
                reasons.append("crane present but the IS 800 Table 6 crane sway was not evaluated (WP2.7)")
        dc_ = pk.get("deformation_compatibility")
        if isinstance(dc_, dict):
            for i, c in enumerate((dc_.get("checks") or []) + (dc_.get("separation") or [])):
                reasons += entry_findings("7.11.2/7.11.3", {"id": c.get("element") or c.get("unit") or i,
                                                             "checks": [c]})
            if G_zone_needs_7112(cfg) and not dc_.get("checks") and not dc_.get("no_non_sfrs_columns"):
                reasons.append("IS 1893 7.11.2 deformation-compatibility check of the gravity columns missing")
        reasons += _screen_findings(pk, cfg)
        reasons += analysis_findings(cfg, pk)
        reasons += combination_findings(cfg, pk)
        reasons += _R_system_agreement(cfg, pk)
        reasons += _grounding_findings(pk, job_dir)
        reasons += provenance_findings(pk, job_dir) if job_dir else [
            "job folder unknown -- provenance hashes not verified"]
        # H30: one completion authority -- the consistency rules that are free of false positives also gate
        try:
            import consistency as _CC
            if job_dir:
                reasons += ["consistency: " + s for s in _CC.script_grep_issues(job_dir)]
            reasons += ["consistency: " + s for s in _CC.literal_dc_issues(pk)]
            plan_ = _CC.plan_of(cfg, pk, job_dir)
            if job_dir:
                reasons += ["consistency: " + s for s in _CC.rag_evidence_issues(plan_, job_dir)]
            reasons += ["consistency: " + s for s in _CC.retrieval_assumption_issues(plan_, cfg)]
        except Exception as ex:
            reasons.append("consistency rules unavailable: %s" % ex)
        if report_html is None and job_dir and os.path.exists(os.path.join(job_dir, "report.html")):
            report_html = os.path.join(job_dir, "report.html")
    if report_html:
        try:
            from india_contract_residue import residue_hits
            txt = open(report_html, encoding="utf-8", errors="replace").read()
            h = residue_hits(txt)
            if h:
                reasons.append("report has %d US-residue hit(s), e.g. %r" % (len(h), h[0]))
        except Exception:
            pass
    reasons += ["example/placeholder label at %s: %r" % hp for hp in ex_hits]
    seen, uniq = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    status = "example_only" if ex_hits else ("complete" if not uniq else "partial")
    try:                                                # AUD-3 / AUD-4: non-blocking findings (never a reason)
        import consistency as _CCw
        warns = _CCw.package_warnings(cfg, pk)
    except Exception as ex:
        warns = ["package warnings unavailable: %s" % ex]
    return {"status": status, "complete_allowed": status == "complete", "reasons": uniq, "warnings": warns,
            "example_hits": ex_hits, "zone": zone_of(cfg), "R": resolve_R(cfg),
            "system": resolve_system_R(cfg),
            "authority": "india_seismic_gates.design_status (spec WP0.2)"}


def complete_allowed(cfg, pkg=None, **kw) -> tuple:
    st = design_status(cfg, pkg, **kw)
    return st["complete_allowed"], st["reasons"]


def complete_gate_disclosure(cfg, pkg=None, **kw) -> dict:
    st = design_status(cfg, pkg, **kw)
    om = resolve_Omega0(cfg)
    return {"complete_allowed": st["complete_allowed"], "status": st["status"], "reasons": st["reasons"],
            "Omega0": om, "table9": {"misses": st["R"]["table9_misses"], "flags": table9_system_flags(cfg)},
            "R_source": st["R"]["source"], "R_cite": st["R"]["cite"],
            "policy": "India path never invents Omega0 or R: R from IS 1893 Table 9 only (D3); "
                      "capacity design via IS 800 12.2.3 and Section 12."}


# --- IS 18168 live Omega corpus helper (re-export) ------------------------------
try:
    from india_omega_is18168 import (  # noqa: E402,F401
        fetch_is18168_omega, fetch_is18168_section_55, resolve_Omega0_with_is18168,
        normalize_sfrs as normalize_omega_sfrs, parse_omega_table_from_hit_text,
        corpus_available as is18168_corpus_available, IS18168_CITE, IS18168_DOC, IS18168_SECTION,
    )
except ImportError:  # pragma: no cover
    pass
