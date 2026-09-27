"""India NL authority — LIVE RAG gates; never invent ASCE→IS mappings.

steltic_nonlinear_india is the India fork of USA steltic_nonlinear (ASCE 41 NSP +
ASCE 7-22 Ch.16 NLRHA + DDM). On this fork:

  * Design packages come from **steltic_india** (IS 800 / IS 808 / load_plan), not
    AISC-only forever. Point STELTIC_ENGINE_DIR at steltic_india/steel_engine.
  * Corpus: the user's IS corpus only, built in the Steltic hub from licensed BIS PDFs (stems IS_1893_Part_1_2016,
    IS_800_2007, IS_875_Part_* …). Never the USA engineering_rag.
  * ASCE 7 Ch.16 numeric rules in ch16_params.json are **scaffolding only** —
    not India authority. Job-level cfg['nl_plan'] (or job/nl_plan.json) must carry
    LIVE RAG retrieval for every rule the deliverable quotes.
  * ASCE 41 NSP / AISC 342 component tables: **found:false** in the India corpus —
    hinge_params stay UNVERIFIED until an India-accepted analogue is retrieved
    (or the AHJ accepts a cited foreign standard). Do not invent.
  * ASCE 7 §16.1.2 drift relief: **found:false** — no IS 1893 clause frees the
    linear drift limit after a time-history run. Feedback drift loop stays
    ineligible unless nl_plan documents a retrieved India analogue (wave 2+).
  * COMPLETE gate (Michael 2026-09-20): fibre preferred/used + honest found:false
    disclosures for NSP tables and §16.1.2 analogue allow COMPLETE. Disclosed
    found:false no longer forces PARTIAL. Hinge-only UNVERIFIED without EOR
    still refuses COMPLETE. Do not invent NSP tables or fake §16.1.2 relief.

Reuse helpers from steltic_india (india_seismic, india_loads) when useful; do not
re-hardcode IS formulas here.
"""
from __future__ import annotations

import json
import os
from typing import Any

JURISDICTION = "india"
try:                                             # NL-3: $INDIA_CORPUS_ROOT, sibling corpus folder, else /workspace
    from snl.india_collections import corpus_root as _corpus_root
    CORPUS_ROOT = _corpus_root()
except Exception:                                # pragma: no cover - snl always importable in this repo
    CORPUS_ROOT = "/workspace/engineering_rag_india"   # historical builder-box path (snl.india_collections)
PRIMARY_STEM = "IS_1893_Part_1_2016"
DESIGN_STEM = "IS_800_2007"

# Canonical stems the NL agent must hit via RAG for seismic/time-history jobs.
NL_STEMS = (
    "IS_1893_Part_1_2016",
    "IS_800_2007",
    "IS_875_Part_1_2026",
    "IS_875_Part_2_1987",
    "IS_875_Part_3_2015",
    "IS_875_Part_5_1987",
)

# Anchors verified against India RAG / steltic_india india_seismic (clause ids exist).
# Numeric acceptance for NLRHA-style checks still requires LIVE retrieval into nl_plan.
IS_ANCHORS = {
    "storey_drift_limit": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "7.11.1.1",
        "note": "Storey drift ≤ 0.004 h under VB with γ = 1.0 (no Cd/Ie).",
        "limit_ratio": 0.004,
    },
    "dynamic_disp_no_scale": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "7.11.1.2",
        "note": "Amd 2: 'Displacement estimates obtained from dynamic analysis need not be scaled, as stated in 7.7.3.2.'",
    },
    "dynamic_analysis_method": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "7.7",
        "note": "Dynamic Analysis Method (RSA / time history — see 7.7.3–7.7.5).",
    },
    "time_history_method": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "7.7.4",
        "note": "Time History Method — retrieve full clause LIVE before implementing acceptance.",
    },
    "response_spectrum_method": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "7.7.5",
        "note": "Response Spectrum Method — not a drop-in for ASCE 7 Ch.16 suite rules.",
    },
    "zone_factor_Z": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "Table 3",
        "cite": "Clause 6.4.2",
        "note": "Seismic Zone Factor Z: II=0.10, III=0.16, IV=0.24, V=0.36.",
        "Z": {"II": 0.10, "III": 0.16, "IV": 0.24, "V": 0.36},
    },
    "design_Ah": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "6.4.2",
        "note": "Ah = (Z/2)·(Sa/g)/(R/I); Sa/g from soil-type expressions in 6.4.2.",
        "excerpt": (
            "The design horizontal seismic coefficient Ah for a structure shall be determined by: "
            "Ah = (Z/2)·(Sa/g)/(R/I) where Z = seismic zone factor given in Table 3; "
            "I = importance factor; R = response reduction factor; "
            "(Sa/g) = design acceleration coefficient for different soil types."
        ),
    },
    "importance_factor": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "7.2.3 / Table 8",
        "note": "I = 1.5 important/lifeline; 1.2 residential/commercial >200 persons; 1.0 other. Not ASCE Risk Category.",
        "I_default_rows": {"important_lifeline": 1.5, "residential_commercial_gt200": 1.2, "other": 1.0},
    },
    "time_history_excerpt": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "7.7.4",
        "excerpt": (
            "Time history method shall be based on an appropriate ground motion "
            "(preferably compatible with the design acceleration spectrum in the desired "
            "range of natural periods) and shall be performed using accepted principles of "
            "earthquake structural dynamics."
        ),
        "note": (
            "This is the honest India replacement for Ch.16 *selection compatibility* intent. "
            "It does NOT supply suite size, RotD100 floor, 2×Table 12.12-1, or RC unacceptable counts."
        ),
    },
    "storey_drift_excerpt": {
        "found": True,
        "stem": PRIMARY_STEM,
        "clause": "7.11.1.1",
        "limit_ratio": 0.004,
        "excerpt": (
            "Storey drift in any storey shall not exceed 0.004 times the storey height, "
            "under the action of design base of shear VB with no load factors mentioned in 6.3, "
            "that is, with partial safety factor for all loads taken as 1.0."
        ),
        "note": "Replaces ASCE Table 12.12-1 / Cd·δe/Ie and Ch.16 2×Table 12.12-1 mean drift for India deliverables.",
    },
}

# Explicit gaps — do NOT fabricate ASCE analogues.
ASCE_GAPS = [
    {
        "id": "asce_41_nsp",
        "found": False,
        "usa": "ASCE/SEI 41-23 NSP + AISC 342-22 component tables",
        "note": (
            "No IS 1893 / IS 800 pushover (NSP) procedure or steel hinge / acceptance "
            "(IO/LS/CP) tables in the India corpus. IS 800:2007 §4.5 Plastic Analysis addresses "
            "static plastic design (plastic/compact sections, hinge stiffeners) — NOT an ASCE 41 "
            "analogue for nonlinear static performance acceptance. Pushover hinge_params stay "
            "verified:false until an AHJ-accepted source is retrieved and cited. Do not invent."
        ),
        "corpus_checks": {
            "IS_1893 plastic hinge|pushover|acceptance criteria": "found:false",
            "IS_800_2007 plastic hinge (4.5.x)": "found:true but static plastic analysis only — not NSP acceptance",
        },
    },
    {
        "id": "asce_7_ch16_suite_acceptance",
        "found": False,
        "usa": "ASCE 7-22 §§16.2–16.4 (11 motions, RotD100, 2×Table 12.12-1, RC rules)",
        "note": (
            "IS 1893 7.7.4 Time History Method is not a verbatim Ch.16 suite code. "
            "Do not copy Table 12.12-1, Risk Category rows, or 16.4.1.1 unacceptable-response "
            "counts into India deliverables without retrieved IS text."
        ),
    },
    {
        "id": "asce_16_1_2_drift_relief",
        "found": False,
        "usa": "ASCE 7-22 §16.1.2 (12.12.1 drift need not apply RC I–III after Ch.16)",
        "note": (
            "No IS 1893 analogue found that waives 7.11.1.1 (0.004 h) after a time-history "
            "run. Feedback drift_relief_16_1_2 stays WARN / ineligible on this fork."
        ),
    },
    {
        "id": "asce_table_12_12_1",
        "found": False,
        "usa": "ASCE 7 Table 12.12-1 Risk Category drift limits",
        "note": "Use IS 1893 7.11.1.1 (0.004 h); no RC-tiered table in IS 1893 Part 1:2016.",
    },
    {
        "id": "asce_mcer_usgs",
        "found": False,
        "usa": "USGS ASCE 7-22 multi-period MCE_R + NSHM disaggregation",
        "note": (
            "India site hazard is zone factor Z / design spectrum Ah(T) from IS 1893 "
            "6.4.2 / Table 3 via nlrha.india_hazard.build_india_site_hazard (or cfg "
            "seismic_zone / india_hazard / nl_plan.hazard). USGS MCE_R path is USA "
            "scaffolding only — do not assume USGS for India jobs."
        ),
    },
    {
        "id": "asce_risk_category_ie",
        "found": False,
        "usa": "ASCE 7 Risk Category I–IV / Ie",
        "note": "IS 1893 Importance Factor I (cl.7.2.3) — do not map RC↔I inventively.",
    },
]


class NLPlanError(ValueError):
    """cfg['nl_plan'] / job nl_plan.json missing or not RAG-backed for an India claim."""


def _as_plan(obj: Any) -> dict | None:
    if isinstance(obj, dict) and (
        obj.get("jurisdiction") or obj.get("retrieval") or obj.get("rules")
    ):
        return obj
    if isinstance(obj, dict) and "nl_plan" in obj:
        p = obj.get("nl_plan")
        return p if isinstance(p, dict) else None
    return None


def find_nl_plan(cfg_or_job=None, job_dir: str | None = None) -> dict | None:
    """Locate nl_plan from cfg dict, cfg['nl_plan'], or <job>/nl_plan.json / nlrha/nl_plan.json."""
    plan = _as_plan(cfg_or_job)
    if plan is not None and "retrieval" in plan:
        return plan
    if isinstance(cfg_or_job, dict) and isinstance(cfg_or_job.get("nl_plan"), dict):
        return cfg_or_job["nl_plan"]
    roots = []
    if job_dir:
        roots.append(job_dir)
    if isinstance(cfg_or_job, str) and os.path.isdir(cfg_or_job):
        roots.append(cfg_or_job)
    for root in roots:
        for rel in ("nl_plan.json", os.path.join("nlrha", "nl_plan.json")):
            path = os.path.join(root, rel)
            if os.path.isfile(path):
                try:
                    return json.load(open(path, encoding="utf-8"))
                except Exception:
                    continue
    return None


def validate_nl_plan(cfg_or_job=None, job_dir: str | None = None) -> list[tuple[str, str]]:
    """Return (level, message) findings for India NL RAG gate.

    ERRORs = claiming India-authoritative Ch.16/ASCE numbers without retrieval.
    Missing nl_plan is WARN in wave 1 (scaffolding may still run) but ERROR when
    cfg asserts jurisdiction india AND a deliverable quotes acceptance limits.
    """
    out: list[tuple[str, str]] = []
    plan = find_nl_plan(cfg_or_job, job_dir=job_dir)
    if not plan:
        out.append((
            "WARN",
            "nl_plan missing. India NLRHA deliverables MUST RAG-query IS 1893 Part 1:2016 "
            "(§7.7 / 7.7.4 time history, §7.11.1 drift) LIVE this job and write evidence into "
            "cfg['nl_plan'] or nlrha/nl_plan.json. ch16_params.json is ASCE scaffolding only "
            "(india_authoritative=false). found:false is honest — do not invent ASCE→IS maps.",
        ))
        return out

    if str(plan.get("jurisdiction", "")).lower() not in ("india", "is", "is_bis", "bis"):
        out.append((
            "WARN",
            "nl_plan.jurisdiction should be 'india' (got %r)" % plan.get("jurisdiction"),
        ))

    retrieval = plan.get("retrieval") or []
    if not isinstance(retrieval, list) or len(retrieval) < 1:
        out.append((
            "ERROR",
            "nl_plan.retrieval must list LIVE RAG hits (at least IS_1893_Part_1_2016 for "
            "time-history / drift). Do not invent citations.",
        ))
    else:
        stems_hit: set[str] = set()
        found_any = False
        for i, hit in enumerate(retrieval):
            if not isinstance(hit, dict):
                out.append(("ERROR", "nl_plan.retrieval[%d] must be an object" % i))
                continue
            stem = str(hit.get("stem") or hit.get("doc") or "")
            if stem:
                stems_hit.add(stem)
            if hit.get("found") is True:
                found_any = True
            if hit.get("found") is False:
                out.append((
                    "WARN",
                    "nl_plan.retrieval[%d] found:false for %s — do not invent; retry FTS/exact "
                    "or leave gap" % (i, stem or "?"),
                ))
        if not any("1893" in s for s in stems_hit):
            out.append((
                "ERROR",
                "nl_plan.retrieval has no IS_1893_* stem — query 7.7 / 7.7.4 / 7.11.1 before "
                "quoting India NL acceptance.",
            ))
        if not found_any:
            out.append((
                "ERROR",
                "nl_plan.retrieval has no found:true hits — refuse to invent India NL rules.",
            ))

    # Drift-relief analogue: only honour if explicitly retrieved
    relief = plan.get("drift_relief_analogue")
    if relief is not None:
        if not isinstance(relief, dict) or relief.get("found") is not True:
            out.append((
                "WARN",
                "nl_plan.drift_relief_analogue is not found:true — ASCE 16.1.2 relief stays "
                "disabled (ASCE_GAPS id=asce_16_1_2_drift_relief).",
            ))
        elif not (relief.get("stem") and relief.get("clause") and relief.get("cite")):
            out.append((
                "ERROR",
                "nl_plan.drift_relief_analogue claimed found:true but missing stem/clause/cite.",
            ))

    return out


def drift_relief_analogue(cfg_or_job=None, job_dir: str | None = None) -> dict:
    """Return India drift-relief analogue status. Default found:false (no fabrication)."""
    gap = next(g for g in ASCE_GAPS if g["id"] == "asce_16_1_2_drift_relief")
    plan = find_nl_plan(cfg_or_job, job_dir=job_dir)
    relief = (plan or {}).get("drift_relief_analogue") if plan else None
    if isinstance(relief, dict) and relief.get("found") is True and relief.get("clause"):
        return {
            "found": True,
            "stem": relief.get("stem"),
            "clause": relief.get("clause"),
            "cite": relief.get("cite"),
            "note": relief.get("note") or "Retrieved India analogue — verify before applying.",
            "usa_gap": gap,
        }
    return {
        "found": False,
        "stem": PRIMARY_STEM,
        "clause": None,
        "note": gap["note"],
        "usa_gap": gap,
        "is_anchor_instead": IS_ANCHORS["storey_drift_limit"],
    }


def load_ch16_params(path: str | None = None) -> dict:
    """Load USA ch16_params.json stamped as non-authoritative on the India fork."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = path or os.path.join(here, "ch16_params.json")
    data = json.load(open(path, encoding="utf-8"))
    data = dict(data)
    data["india_authoritative"] = False
    data["authority"] = "asce_scaffolding_only"
    data["jurisdiction"] = JURISDICTION
    data["corpus"] = CORPUS_ROOT
    data["verified"] = False  # force re-verify via India RAG; do not trust USA verified:true
    data["_INDIA_README"] = [
        "On steltic_nonlinear_india this file is ASCE 7-22 scaffolding retained for engine wiring.",
        "It is NOT India authority. Quote IS 1893 / IS 800 only from LIVE RAG into nl_plan.",
        "Gaps: see nlrha.india_authority.ASCE_GAPS (found:false).",
    ]
    return data


def authority_banner() -> str:
    lines = [
        "[india_authority] jurisdiction=%s corpus=%s" % (JURISDICTION, CORPUS_ROOT),
        "[india_authority] ch16_params.json = ASCE scaffolding only (india_authoritative=false)",
    ]
    for g in ASCE_GAPS:
        lines.append("[india_authority] GAP %s found:false — %s" % (g["id"], g["usa"]))
    for k, a in IS_ANCHORS.items():
        lines.append(
            "[india_authority] ANCHOR %s found:true %s §%s" % (k, a["stem"], a["clause"])
        )
    return "\n".join(lines)


def summary_findings(findings: list[tuple[str, str]]) -> str:
    if not findings:
        return "[india_authority] nl_plan OK"
    lines = ["[india_authority] nl_plan check:"]
    for sev, msg in findings:
        lines.append("  %s: %s" % (sev, msg))
    return "\n".join(lines)


def india_acceptance_rules() -> dict:
    """Honest India replacements for Ch.16 *numerics* that RAG supports.

    Implement / cite only these. Everything else in ch16_params.json stays scaffolding.
    """
    drift = IS_ANCHORS["storey_drift_excerpt"]
    th = IS_ANCHORS["time_history_excerpt"]
    return {
        "jurisdiction": JURISDICTION,
        "stem": PRIMARY_STEM,
        "replace_ch16_where_honest": {
            "storey_drift_limit_ratio": {
                "value": drift["limit_ratio"],
                "clause": drift["clause"],
                "excerpt": drift["excerpt"],
                "replaces": "ASCE Table 12.12-1 and Ch.16 2×Table 12.12-1 mean drift limits",
            },
            "dynamic_disp_no_7_7_3_scale": {
                "clause": IS_ANCHORS["dynamic_disp_no_scale"]["clause"],
                "note": IS_ANCHORS["dynamic_disp_no_scale"]["note"],
                "replaces": "ASCE Cd/Ie drift amplification handling (not applicable)",
            },
            "time_history_spectrum_compatibility": {
                "clause": th["clause"],
                "excerpt": th["excerpt"],
                "replaces": "ASCE 16.2 target-spectrum selection intent (NOT suite size / RotD100 / RC counts)",
                "hazard_module": "nlrha.india_hazard",
            },
            "design_spectrum_Ah": {
                "clause": IS_ANCHORS["design_Ah"]["clause"],
                "excerpt": IS_ANCHORS["design_Ah"]["excerpt"],
                "zone_Z": IS_ANCHORS["zone_factor_Z"]["Z"],
            },
        },
        "still_found_false": [g["id"] for g in ASCE_GAPS],
        "note": (
            "Do not copy n_motions=11, RotD100 ≥ 90% floor, peak-drift unacceptable "
            "factors, or Risk-Category rows into India deliverables without retrieved IS text."
        ),
    }


def hinge_analogue_status() -> dict:
    """ASCE 41 / AISC 342 hinge + acceptance analogue — always found:false unless plan overrides."""
    gap = next(g for g in ASCE_GAPS if g["id"] == "asce_41_nsp")
    return {
        "found": False,
        "usa": gap["usa"],
        "note": gap["note"],
        "corpus_checks": gap.get("corpus_checks"),
        "hinge_params_path": "pushover/hinge_params.json",
        "hinge_params_verified": False,
        "action": (
            "Leave UNVERIFIED banner; do not invent IO/LS/CP from IS 800 §4.5 plastic analysis. "
            "If AHJ accepts a foreign standard, cite it in nl_plan.hinge_source with found:true."
        ),
    }


def storey_drift_limit_ratio(cfg_or_job=None, job_dir: str | None = None) -> dict:
    """Return the India storey drift limit (0.004) with citation; honour nl_plan override if retrieved."""
    plan = find_nl_plan(cfg_or_job, job_dir=job_dir) or {}
    rules = plan.get("rules") if isinstance(plan.get("rules"), dict) else {}
    if isinstance(rules.get("storey_drift_limit_ratio"), dict):
        r = rules["storey_drift_limit_ratio"]
        if r.get("found") is True and r.get("value") is not None:
            return {
                "found": True,
                "value": float(r["value"]),
                "stem": r.get("stem") or PRIMARY_STEM,
                "clause": r.get("clause") or "7.11.1.1",
                "cite": r.get("cite"),
                "source": "nl_plan.rules",
            }
    a = IS_ANCHORS["storey_drift_limit"]
    return {
        "found": True,
        "value": float(a["limit_ratio"]),
        "stem": a["stem"],
        "clause": a["clause"],
        "cite": "%s §%s" % (a["stem"], a["clause"]),
        "excerpt": IS_ANCHORS["storey_drift_excerpt"]["excerpt"],
        "source": "IS_ANCHORS",
    }


def nsp_acceptance_tables_status(cfg_or_job=None, job_dir: str | None = None) -> dict:
    """India NSP / hinge acceptance tables — found:false (do not invent).

    Explicit COMPLETE-gate object. Fibre path remains the preferred India modelling
    route; hinge_params stay UNVERIFIED when ASCE 41 scaffolding is used.
    """
    h = hinge_analogue_status()
    plan = find_nl_plan(cfg_or_job, job_dir=job_dir) or {}
    # Only nsp_acceptance_tables may flip found:true. hinge_source is EOR params
    # (see hinge_eor_documented) — do not invent India NSP IO/LS/CP tables via EOR.
    override = plan.get("nsp_acceptance_tables")
    if isinstance(override, dict) and override.get("found") is True and override.get("clause"):
        return {
            "id": "india_nsp_acceptance_tables",
            "found": True,
            "stem": override.get("stem"),
            "clause": override.get("clause"),
            "cite": override.get("cite"),
            "note": override.get("note") or "Retrieved India NSP acceptance — verify before use.",
            "hinge_params_verified": bool(override.get("hinge_params_verified")),
            "prefer_fibre": True,
        }
    return {
        "id": "india_nsp_acceptance_tables",
        "found": False,
        "usa": h.get("usa"),
        "note": h.get("note"),
        "hinge_params_verified": False,
        "prefer_fibre": True,
        "action": h.get("action"),
        "asce_gap_id": "asce_41_nsp",
    }


def method_disclosures(job_dir) -> list[dict]:
    """NL-21 method choices read back from the analysis packages: elastic gravity members (with their yield check) and
    record trimming. Empty when the job has no packages yet."""
    rows = []
    if not job_dir:
        return rows
    po = _read_json(os.path.join(job_dir, "pushover", "pushover_package.json")) or {}
    lv = {x: _read_json(os.path.join(job_dir, "nlrha", x, "nlrha_package.json")) or {} for x in ("DBE", "MCE")}
    ems = [p.get("elastic_members") for p in [po] + list(lv.values()) if p.get("elastic_members")]
    if any(e.get("n_elastic") for e in ems):
        rows.append(dict(id="gravity_members_elastic", found=True, disclosed=True,
                         n_elastic=max(e.get("n_elastic") or 0 for e in ems),
                         max_ratio=max(e.get("max_ratio") or 0.0 for e in ems),
                         flagged_elastic=sorted({t for e in ems for t in (e.get("flagged_elastic") or [])}),
                         note=ems[0].get("basis") or "gravity-only members elastic with a first-yield check"))
    trims = [p.get("record_trim") for p in lv.values() if p.get("record_trim")]
    if trims and trims[0].get("method") not in (None, "none"):
        rows.append(dict(id="record_trimming", found=True, disclosed=True, method=trims[0].get("method"),
                         free_vib_s=trims[0].get("free_vib_s"), note=trims[0].get("basis")))
    return rows


def complete_gate_disclosures(cfg_or_job=None, job_dir: str | None = None) -> list[dict]:
    """Status objects the COMPLETE gate must disclose (found:false kept honest)."""
    nsp = nsp_acceptance_tables_status(cfg_or_job, job_dir=job_dir)
    drift = drift_relief_analogue(cfg_or_job, job_dir=job_dir)
    return method_disclosures(job_dir) + [
        nsp,
        {
            "id": "asce_16_1_2_drift_relief_analogue",
            "found": bool(drift.get("found")),
            "stem": drift.get("stem"),
            "clause": drift.get("clause"),
            "note": drift.get("note"),
            "feedback_drift_loop": "ineligible" if not drift.get("found") else "eligible_if_cited",
            "usa_gap": drift.get("usa_gap") or drift.get("usa"),
            "is_anchor_instead": drift.get("is_anchor_instead"),
        },
        {
            "id": "india_nsp_hinge_params",
            "found": False,
            "hinge_params_verified": False,
            "prefer_fibre": True,
            "note": (
                "Mark hinge_params UNVERIFIED when ASCE 41 scaffolding is used. "
                "Keep fibre path. Emit found:false for India NSP acceptance tables — no invent."
            ),
        },
    ]



# ---------------------------------------------------------------------------
# COMPLETE gate (Michael policy 2026-09-20)
# Disclosed found:false for NSP tables + §16.1.2 analogue does NOT force PARTIAL
# when fibre is preferred/used. Refuse hinge-only UNVERIFIED without EOR, or
# missing disclosures. Do not invent NSP tables or enable fake §16.1.2 relief.
# ---------------------------------------------------------------------------

COMPLETE_GATE_POLICY = "michael_nl_complete_gate_2026_09_20"
COMPLETE_GATE_POLICY_DATE = "2026-09-20"

REQUIRED_COMPLETE_DISCLOSURE_IDS = (
    "india_nsp_acceptance_tables",
    "asce_16_1_2_drift_relief_analogue",
)

_FIBRE_ALIASES = frozenset({"fibre", "fiber", "distributed"})
_HINGE_ONLY_ALIASES = frozenset({
    "imk", "hinge", "hinges", "concentrated", "concentrated_plasticity",
    "modimk", "concentrated_plasticity_fbc",
})


def _norm_plasticity(val) -> str:
    s = str(val or "").strip().lower()
    if s in ("fiber", "distributed"):
        return "fibre"
    return s


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _cfg_dict(cfg_or_job) -> dict:
    if isinstance(cfg_or_job, dict):
        return cfg_or_job
    cfg = getattr(cfg_or_job, "cfg", None)
    return cfg if isinstance(cfg, dict) else {}


# Descending-branch evidence is informative only. A fibre run that stops at
# max_drift/lower_bound before a 20% Vmax drop remains COMPLETE-eligible; the
# limitation is disclosed for STATUS/review rather than turned into PARTIAL.
_DESCENDING_CAPTURED_STATUSES = frozenset({"captured", "not_needed", "component_limit"})
_DESCENDING_INCOMPLETE_STATUSES = frozenset({"max_drift", "lower_bound", "not_captured"})


def _descending_tail_records(value, direction=None):
    """Flatten the small tail/run shapes emitted by pushover into tail records."""
    if not isinstance(value, dict):
        return []
    if "status" in value or "captured" in value:
        return [(direction, value)]
    out = []
    for key, item in value.items():
        if isinstance(item, dict):
            out.extend(_descending_tail_records(item, direction=str(key)))
    return out


def descending_branch_disclosure(
    cfg_or_job=None,
    job_dir: str | None = None,
    *,
    evidence=None,
) -> dict:
    """Return descending-branch evidence without making it a COMPLETE gate.

    ``pushover_package.json`` is consulted when available. Callers may provide
    live ``descending_branch_runs``/``tail`` evidence so the disclosure can be
    written after a run. No evidence is deliberately reported as not_observed,
    not as a blocking failure.
    """
    evidence = evidence if isinstance(evidence, dict) else {}
    records = []
    source = None

    if isinstance(evidence.get("descending_branch_captured"), bool):
        records.append((None, {
            "captured": evidence["descending_branch_captured"],
            "status": evidence.get("descending_branch_status"),
        }))
        source = "evidence.descending_branch_captured"
    else:
        for key in ("descending_branch_runs", "tails", "tail"):
            if key in evidence:
                records.extend(_descending_tail_records(evidence[key]))
                source = "evidence.%s" % key
                if records:
                    break

    # Explicit/live evidence is authoritative for the current run; do not
    # contaminate it with a stale package from an earlier run in the same job.
    if not records:
        roots = []
        if job_dir:
            roots.append(str(job_dir))
        if isinstance(cfg_or_job, str) and os.path.isdir(cfg_or_job):
            roots.append(str(cfg_or_job))
        pkg_root = getattr(cfg_or_job, "root", None)
        if pkg_root:
            roots.append(str(pkg_root))
        seen = set()
        for root in roots:
            for rel in (
                "pushover_package.json",
                os.path.join("pushover", "pushover_package.json"),
                os.path.join("job_out", "pushover", "pushover_package.json"),
            ):
                path = os.path.join(root, rel)
                if path in seen:
                    continue
                seen.add(path)
                data = _read_json(path)
                dirs = data.get("directions") if isinstance(data, dict) else None
                if isinstance(dirs, dict):
                    for direction, run in dirs.items():
                        tail = run.get("tail") if isinstance(run, dict) else None
                        records.extend(_descending_tail_records(tail, direction=str(direction)))
                    if records and source is None:
                        source = path
                    if records:
                        break
            if records and source:
                break

    if not records:
        return {
            "descending_branch_captured": False,
            "captured": False,
            "status": "not_observed",
            "directions": {},
            "source": None,
            "required_for_complete": False,
            "note": (
                "Descending branch was not observed in this gate emission; incomplete "
                "capture is optional and does not force PARTIAL."
            ),
        }

    directions = {}
    normalized = []
    for direction, tail in records:
        status = str(tail.get("status") or "").strip().lower()
        captured = tail.get("captured")
        if not isinstance(captured, bool):
            captured = status in _DESCENDING_CAPTURED_STATUSES
        if not status:
            status = "captured" if captured else "not_captured"
        item = {"captured": bool(captured), "status": status}
        if direction is not None:
            directions[str(direction)] = item
        normalized.append(item)

    all_captured = all(item["captured"] for item in normalized)
    statuses = [item["status"] for item in normalized]
    if all_captured:
        status = statuses[0] if len(set(statuses)) == 1 else "captured_all_directions"
    elif "max_drift" in statuses:
        status = "max_drift"
    elif "lower_bound" in statuses:
        status = "lower_bound"
    else:
        status = "not_captured"
    return {
        "descending_branch_captured": all_captured,
        "captured": all_captured,
        "status": status,
        "directions": directions,
        "source": source,
        "required_for_complete": False,
        "note": (
            "Descending branch incomplete (%s) is optional under Michael policy; "
            "it is disclosed for STATUS and does not force PARTIAL."
            % status
            if not all_captured else
            "Descending branch captured/valid; this evidence is disclosed and is not a COMPLETE gate requirement."
        ),
    }


def hinge_eor_documented(cfg_or_job=None, job_dir: str | None = None) -> dict:
    """Optional EOR hinge fixture — not required for COMPLETE when fibre is used."""
    plan = find_nl_plan(cfg_or_job, job_dir=job_dir) or {}
    cfg = _cfg_dict(cfg_or_job)
    for src in (
        plan.get("hinge_source"),
        plan.get("nsp_acceptance_tables"),
        cfg.get("hinge_source"),
        cfg.get("hinge_eor"),
    ):
        if isinstance(src, dict) and src.get("found") is True and (
            src.get("clause") or src.get("cite") or src.get("source")
        ):
            return {
                "found": True,
                "eor_documented": True,
                "stem": src.get("stem"),
                "clause": src.get("clause"),
                "cite": src.get("cite") or src.get("source"),
                "note": src.get("note") or "EOR / AHJ hinge source cited in nl_plan.",
            }
    if cfg.get("hinge_eor_documented") is True and (
        cfg.get("hinge_eor_cite") or cfg.get("R_cite")
    ):
        return {
            "found": True,
            "eor_documented": True,
            "cite": cfg.get("hinge_eor_cite") or cfg.get("R_cite"),
            "note": "cfg hinge_eor_documented",
        }
    return {
        "found": False,
        "eor_documented": False,
        "note": (
            "Optional EOR hinge fixture not present — not required for COMPLETE when "
            "fibre is preferred/used (policy %s)." % COMPLETE_GATE_POLICY_DATE
        ),
    }


def resolve_plasticity(cfg_or_job=None, job_dir: str | None = None, evidence=None) -> dict:
    """Resolve modelling plasticity for the COMPLETE gate (fibre vs hinge-only)."""
    evidence = evidence if isinstance(evidence, dict) else {}
    cfg = _cfg_dict(cfg_or_job)
    num = cfg.get("numerics") if isinstance(cfg.get("numerics"), dict) else {}
    candidates = []

    def _add(val, source):
        if val is None or val == "":
            return
        candidates.append((_norm_plasticity(val), source))

    if evidence.get("from_artifact"):
        _add(evidence.get("plasticity"), "artifact:evidence.plasticity")
        if evidence.get("fibre_used") is True:
            candidates.append(("fibre", "artifact:evidence.fibre_used"))
    else:
        _add(evidence.get("plasticity"), "evidence.plasticity")
    _add(cfg.get("plasticity"), "cfg.plasticity")
    _add(num.get("plasticity"), "cfg.numerics.plasticity")
    _add(os.environ.get("SNL_PLASTICITY"), "env.SNL_PLASTICITY")

    roots = []
    if job_dir:
        roots.append(job_dir)
    if isinstance(cfg_or_job, str) and os.path.isdir(cfg_or_job):
        roots.append(cfg_or_job)
    pkg_root = getattr(cfg_or_job, "root", None)
    if pkg_root:
        roots.append(str(pkg_root))
    for root in roots:
        for rel in (
            os.path.join("pushover", "pushover_package.json"),
            "pushover_package.json",
            os.path.join("nlrha", "nlrha_package.json"),
            "nlrha_package.json",
            os.path.join("job_out", "pushover", "pushover_package.json"),
            os.path.join("job_out", "nlrha", "nlrha_package.json"),
        ):
            data = _read_json(os.path.join(root, rel))
            if not data:
                continue
            _add(data.get("plasticity"), "artifact:" + rel)
            num2 = data.get("numerics") if isinstance(data.get("numerics"), dict) else {}
            _add(num2.get("plasticity"), "artifact:" + rel + ".numerics")
            if data.get("fibre_eles") or data.get("fibre_secs"):
                candidates.insert(0, ("fibre", "artifact:" + rel + ".fibre_*"))

    plasticity = None
    source = None
    for val, src in candidates:
        if val:
            plasticity, source = val, src
            break
    if plasticity is None:
        # India default modelling path is fibre (prefer_fibre); not yet proven "used".
        plasticity = "fibre"
        source = "default_prefer_fibre"

    fibre = plasticity in _FIBRE_ALIASES
    hinge_only = plasticity in _HINGE_ONLY_ALIASES
    from_artifact = str(source or "").startswith("artifact:")
    return {
        "plasticity": plasticity,
        "source": source,
        "fibre_preferred": True,
        "fibre_used": bool(fibre and from_artifact),
        # WP4.10: fibre counts only when an analysis artefact proves it (never a default / env / claim)
        "fibre_ok": bool(fibre and from_artifact),
        "hinge_only": bool(hinge_only),
        "candidates": [{"plasticity": a, "source": b} for a, b in candidates[:12]],
    }


def load_complete_gate_disclosures(
    cfg_or_job=None,
    job_dir: str | None = None,
    disclosures=None,
) -> list[dict]:
    """Return disclosure rows from arg, durable JSON under job, or live emitters."""
    if isinstance(disclosures, list) and disclosures:
        return disclosures
    if isinstance(disclosures, dict) and isinstance(disclosures.get("disclosures"), list):
        return disclosures["disclosures"]

    roots = []
    if job_dir:
        roots.append(job_dir)
    if isinstance(cfg_or_job, str) and os.path.isdir(cfg_or_job):
        roots.append(cfg_or_job)
    pkg_root = getattr(cfg_or_job, "root", None)
    if pkg_root:
        roots.append(str(pkg_root))
    for root in roots:
        for rel in (
            "complete_gate_disclosures.json",
            os.path.join("pushover", "complete_gate_disclosures.json"),
            os.path.join("nlrha", "complete_gate_disclosures.json"),
            os.path.join("job_out", "complete_gate_disclosures.json"),
            os.path.join("job_out", "pushover", "complete_gate_disclosures.json"),
            os.path.join("job_out", "nlrha", "complete_gate_disclosures.json"),
        ):
            data = _read_json(os.path.join(root, rel))
            if data and isinstance(data.get("disclosures"), list):
                return data["disclosures"]
    return complete_gate_disclosures(cfg_or_job, job_dir=job_dir)


def disclosures_satisfy_complete_gate(rows: list[dict] | None) -> dict:
    """Require both honest found:false IDs disclosed; drift loop ineligible; IS 7.11.1 anchor."""
    rows = rows or []
    by_id = {r.get("id"): r for r in rows if isinstance(r, dict) and r.get("id")}
    missing = [i for i in REQUIRED_COMPLETE_DISCLOSURE_IDS if i not in by_id]
    problems = []
    details = {}

    for rid in REQUIRED_COMPLETE_DISCLOSURE_IDS:
        row = by_id.get(rid)
        if row is None:
            problems.append("missing disclosure id=%s" % rid)
            details[rid] = {"present": False}
            continue
        info = {"present": True, "found": row.get("found")}
        if row.get("found") is not False:
            problems.append(
                "%s must be disclosed found:false (got found=%r) — do not invent India analogue"
                % (rid, row.get("found"))
            )
        if rid == "india_nsp_acceptance_tables":
            if row.get("prefer_fibre") is False:
                problems.append("india_nsp_acceptance_tables.prefer_fibre must stay true")
            info["prefer_fibre"] = row.get("prefer_fibre")
            info["hinge_params_verified"] = row.get("hinge_params_verified")
        if rid == "asce_16_1_2_drift_relief_analogue":
            loop = row.get("feedback_drift_loop")
            info["feedback_drift_loop"] = loop
            if loop != "ineligible":
                problems.append(
                    "asce_16_1_2_drift_relief_analogue.feedback_drift_loop must be "
                    "'ineligible' when found:false (got %r)" % (loop,)
                )
            anchor = row.get("is_anchor_instead") or {}
            info["is_anchor_instead"] = anchor
            clause = str(anchor.get("clause") or "")
            if clause and not clause.startswith("7.11.1"):
                problems.append(
                    "India drift check must remain IS 1893 §7.11.1 "
                    "(got is_anchor_instead.clause=%r)" % clause
                )
        details[rid] = info

    # 7.11.1.1 (0.004 h under VB) is the LINEAR design check of the HR package -- informational here, never an
    # NL acceptance criterion and never a gate condition (NLREPO-05).
    drift_limit = dict(storey_drift_limit_ratio(), role="linear design check under VB (HR package); not an NL criterion")
    return {
        "ok": len(problems) == 0 and not missing,
        "missing_ids": missing,
        "problems": problems,
        "details": details,
        "india_drift_limit": drift_limit,
        "required_ids": list(REQUIRED_COMPLETE_DISCLOSURE_IDS),
    }


def complete_allowed(
    cfg_or_job=None,
    job_dir: str | None = None,
    *,
    evidence=None,
    disclosures=None,
) -> tuple:
    """Refuse COMPLETE only when fibre missing + hinge UNVERIFIED without EOR, or disclosures missing.

    Disclosed found:false for NSP tables / §16.1.2 analogue does **not** force PARTIAL when
    fibre is preferred/used. Optional EOR hinge fixture is not required when fibre is used.
    """
    reasons: list[str] = []
    plast = resolve_plasticity(cfg_or_job, job_dir=job_dir, evidence=evidence)
    rows = load_complete_gate_disclosures(
        cfg_or_job, job_dir=job_dir, disclosures=disclosures
    )
    disc = disclosures_satisfy_complete_gate(rows)
    eor = hinge_eor_documented(cfg_or_job, job_dir=job_dir)
    nsp = nsp_acceptance_tables_status(cfg_or_job, job_dir=job_dir)
    hinge_verified = bool(nsp.get("hinge_params_verified")) or eor.get("eor_documented")

    if not disc["ok"]:
        reasons.extend(disc["problems"] or [])
        if disc["missing_ids"]:
            reasons.append(
                "COMPLETE-gate disclosures missing ids: %s"
                % ", ".join(disc["missing_ids"])
            )

    if plast["fibre_ok"]:
        pass
    elif hinge_verified:
        pass
    else:
        reasons.append(
            "fibre not used and hinge path UNVERIFIED without EOR — refuse COMPLETE "
            "(use fibre plasticity, or cite EOR hinge_source found:true). "
            "plasticity=%r source=%s" % (plast.get("plasticity"), plast.get("source"))
        )

    art = artefact_gate(job_dir or (cfg_or_job if isinstance(cfg_or_job, str) else None))
    reasons.extend(art["reasons"])

    drift = drift_relief_analogue(cfg_or_job, job_dir=job_dir)
    if drift.get("found") is True and not drift.get("clause"):
        reasons.append(
            "asce_16_1_2_drift_relief claimed found:true without clause — do not invent"
        )

    seen = set()
    uniq = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return (len(uniq) == 0, uniq)


def design_status(
    cfg_or_job=None,
    job_dir: str | None = None,
    *,
    evidence=None,
    disclosures=None,
) -> dict:
    """COMPLETE vs PARTIAL for India NL packs (Michael 2026-09-20 policy)."""
    ok, reasons = complete_allowed(
        cfg_or_job, job_dir=job_dir, evidence=evidence, disclosures=disclosures
    )
    plast = resolve_plasticity(cfg_or_job, job_dir=job_dir, evidence=evidence)
    rows = load_complete_gate_disclosures(
        cfg_or_job, job_dir=job_dir, disclosures=disclosures
    )
    disc = disclosures_satisfy_complete_gate(rows)
    eor = hinge_eor_documented(cfg_or_job, job_dir=job_dir)
    nsp = nsp_acceptance_tables_status(cfg_or_job, job_dir=job_dir)
    descending = descending_branch_disclosure(
        cfg_or_job, job_dir=job_dir, evidence=evidence
    )
    drift = next(
        (
            r for r in rows
            if isinstance(r, dict) and r.get("id") == "asce_16_1_2_drift_relief_analogue"
        ),
        None,
    ) or {
        "id": "asce_16_1_2_drift_relief_analogue",
        "found": False,
        "feedback_drift_loop": "ineligible",
    }
    art = artefact_gate(job_dir or (cfg_or_job if isinstance(cfg_or_job, str) else None))
    status = "complete" if ok else "partial"
    if ok and art.get("capacity_shortfall"):
        status = "complete_with_capacity_shortfall"
    note = (
        "COMPLETE allowed: fibre preferred/used + NSP tables found:false disclosed + "
        "ASCE §16.1.2 drift-relief analogue found:false disclosed (feedback loop "
        "ineligible; IS 1893 §7.11.1 remains India drift check). Disclosed found:false "
        "does not force PARTIAL. Optional EOR hinge fixture not required when fibre is used."
        if ok else
        "PARTIAL — fix fibre path (or EOR-verified hinges) and/or emit durable "
        "complete_gate_disclosures.json with honest found:false for NSP tables and "
        "§16.1.2 analogue."
    )
    return {
        "status": status,
        "design_status": status,
        "complete_allowed": ok,
        "reasons": reasons,
        "admin_notify": (not ok),
        "policy": COMPLETE_GATE_POLICY,
        "policy_date": COMPLETE_GATE_POLICY_DATE,
        "fibre": plast,
        "disclosures": disc,
        "nsp_acceptance_tables": {
            "found": nsp.get("found"),
            "prefer_fibre": nsp.get("prefer_fibre"),
            "hinge_params_verified": nsp.get("hinge_params_verified"),
        },
        "asce_16_1_2_drift_relief_analogue": {
            "found": (drift or {}).get("found"),
            "feedback_drift_loop": (drift or {}).get("feedback_drift_loop"),
            "is_anchor_instead": (drift or {}).get("is_anchor_instead"),
        },
        "hinge_eor": eor,
        "india_drift_check": disc.get("india_drift_limit"),
        "descending_branch": descending,
        "descending_branch_captured": descending["descending_branch_captured"],
        "descending_branch_status": descending["status"],
        "blocks_from_found_false_alone": False,
        "artefact_gate": art,
        "note": note,
    }


def admin_notify(
    cfg_or_job=None,
    job_dir: str | None = None,
    *,
    evidence=None,
    disclosures=None,
    status: dict | None = None,
) -> dict:
    """Admin-facing notify object. True when gate refuses COMPLETE (PARTIAL)."""
    st = status or design_status(
        cfg_or_job, job_dir=job_dir, evidence=evidence, disclosures=disclosures
    )
    return {
        "admin_notify": bool(st.get("admin_notify")),
        "design_status": st.get("status"),
        "complete_allowed": st.get("complete_allowed"),
        "reasons": list(st.get("reasons") or []),
        "policy": COMPLETE_GATE_POLICY,
        "message": (
            "NL India COMPLETE gate PARTIAL — Admin review: %s"
            % ("; ".join(st.get("reasons") or ["see design_status"])[:400])
            if st.get("admin_notify")
            else (
                "NL India COMPLETE gate OK — no Admin escalate required for "
                "NSP/§16.1.2 found:false disclosures"
            )
        ),
    }



def write_complete_gate_disclosures(
    out_dir: str,
    cfg_or_job=None,
    job_dir: str | None = None,
    filename: str = "complete_gate_disclosures.json",
    *,
    evidence=None,
) -> list[dict]:
    """Persist COMPLETE-gate honesty rows + design_status (found:false kept) for STATUS / review.

    Does not invent NSP acceptance tables or an ASCE §16.1.2 drift-relief analogue.
    Disclosed found:false no longer forces PARTIAL when fibre is preferred/used
    (Michael 2026-09-20 policy).
    """
    rows = complete_gate_disclosures(cfg_or_job, job_dir=job_dir)
    st = design_status(
        cfg_or_job, job_dir=job_dir, evidence=evidence, disclosures=rows
    )
    notify = admin_notify(status=st)
    os.makedirs(out_dir, exist_ok=True)
    path_out = os.path.join(out_dir, filename)
    payload = {
        "jurisdiction": JURISDICTION,
        "wave": "nl-complete-gate-fibre-disclose",
        "policy": COMPLETE_GATE_POLICY,
        "policy_date": COMPLETE_GATE_POLICY_DATE,
        "note": (
            "Honesty disclosures for COMPLETE gate. found:false means no India analogue "
            "was retrieved — do not invent IO/LS/CP or §16.1.2 drift relief. "
            "Disclosed found:false does not force PARTIAL when fibre preferred/used."
        ),
        "disclosures": rows,
        "descending_branch_captured": st["descending_branch_captured"],
        "descending_branch_status": st["descending_branch_status"],
        "descending_branch": st["descending_branch"],
        "complete_allowed": st["complete_allowed"],
        "design_status": st["status"],
        "admin_notify": notify["admin_notify"],
        "gate": st,
        "admin_notify_payload": notify,
    }
    with open(path_out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
        f.write("\n")
    return rows





# ---------------------------------------------------------------------------------------------------------------
# WP4.10 COMPLETE gate on ANALYSIS ARTEFACTS (never a verdict -- owner ruling D7)
# ---------------------------------------------------------------------------------------------------------------
def _sha256(path):
    import hashlib
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def summary_inputs(job_dir: str) -> dict:
    """sha256 of the analysis packages a summary reads (recorded by every summary; compared by the gate)."""
    out = {}
    for rel in ("pushover/pushover_package.json", "nlrha/nlrha_package.json", "nlrha/DBE/nlrha_package.json",
                "nlrha/MCE/nlrha_package.json", "ddm_results.json"):
        pth = os.path.join(job_dir, rel)
        if os.path.exists(pth):
            out[rel] = _sha256(pth)
    return out


def _package_has_links(job_dir) -> bool:
    """True when the HR package declares EBF links (member_schedule.csv role 'link')."""
    import csv
    p = os.path.join(job_dir, "design", "member_schedule.csv")
    if not os.path.exists(p):
        return False
    try:
        with open(p, newline="", encoding="utf-8") as f:
            return any((r.get("role") or "").strip() == "link" for r in csv.DictReader(f))
    except Exception:
        return False


def _nl17_package_checks(job_dir, what, pk, reasons, checks):
    """NL-17 (India): an analysis package counts toward COMPLETE only when
      a the IS specification values were collected from the corpus (`snl collect`: spec_values_collected);
      b its gravity is the HR engine's own seismic-weight load state (gravity_source 'hr_engine'), not the
        idealised equal nodal loads used when the HR engine is not importable;
      c the EBF links the HR package declares are modelled as nonlinear links (links > 0)."""
    key = what.replace(" ", "_").lower()
    ok_c = bool(pk.get("spec_values_collected"))
    checks[key + "_spec_values_collected"] = ok_c
    if not ok_c:
        reasons.append("%s ran without collected IS specification values (run `snl collect` first; "
                       "spec_values_collected is false)" % what)
    gs = pk.get("gravity_source")
    checks[key + "_gravity_source"] = gs
    if gs != "hr_engine":
        reasons.append("%s gravity is not the HR engine's load state (gravity_source=%r; set STELTIC_ENGINE_DIR)" % (what, gs))
    em = pk.get("elastic_members") or {}
    checks[key + "_elastic_members"] = em.get("n_elastic", 0)
    if em.get("flagged_elastic"):                       # NL-21: a gravity member past first yield must be fibre
        reasons.append("%s: %d elastic gravity member(s) exceed first yield (ratio > 1.0: %s) -- promote them to fibre "
                       "(snl run does this automatically; %s) and re-run" % (
                           what, len(em["flagged_elastic"]), ", ".join(str(t) for t in em["flagged_elastic"][:10]),
                           "nl_promote_fibre.json"))
    if _package_has_links(job_dir):
        n = int(pk.get("links") or 0)
        checks[key + "_links"] = n
        if n <= 0:
            reasons.append("%s: the HR package declares EBF links but the model has no nonlinear links" % what)


def artefact_gate(job_dir: str | None) -> dict:
    """Checks (all required for COMPLETE):
      1 pushover_package.json + nlrha_package.json (both levels) exist and prove fibre plasticity;
      2 every NLRHA record converged;
      3 elastic targets (IS 1893 DBE/MCE, no R) in NLRHA and NSP;
      4 mass = IS seismic weight (|sum m g - W| <= 1 %);
      5 non-vacuous response summaries (SFRS member rows exist);
      6 no spurious modes; participation sums <= 1;
      7 DDM: results exist, gravity transfer gate passed, every reported lambda_u is a detected limit point /
        plateau / ductility cap (NO_LIMIT_POINT runs are excluded; a gravity or wind NO_LIMIT_POINT below lambda 1
        blocks; NL-24: a SOLVER_FAILURE -- numerical stop with the structure still stiff -- blocks, any kind); IS 800 B-1.2 section check at lambda = 1 present -- a B-1.2 failure gives
        complete_with_capacity_shortfall;
      8 summaries (snl_summary.json) are FRESH: the package hashes they recorded match the files on disk;
      9 validate_nl_plan has no ERROR;
     10 (NL-17) pushover and both NLRHA levels: IS values collected, HR-engine gravity, EBF links modelled."""
    reasons, checks = [], {}
    if not job_dir or not os.path.isdir(job_dir):
        return dict(ok=False, reasons=["no job folder / analysis artefacts -- COMPLETE refused"], checks={}, capacity_shortfall=False)
    po = _read_json(os.path.join(job_dir, "pushover", "pushover_package.json"))
    nl = _read_json(os.path.join(job_dir, "nlrha", "nlrha_package.json"))
    checks["pushover_package"] = bool(po)
    checks["nlrha_package"] = bool(nl)
    if not po:
        reasons.append("pushover/pushover_package.json missing")
    if not nl:
        reasons.append("nlrha/nlrha_package.json missing")
    india = (po or {}).get("jurisdiction") == "india" or (nl or {}).get("jurisdiction") == "india"
    if po:
        if po.get("plasticity") != "fibre" or not po.get("fibre_eles"):
            reasons.append("pushover package does not prove fibre plasticity (plasticity=%r, fibre_eles=%r)" % (po.get("plasticity"), po.get("fibre_eles")))
        if india and ((po.get("hazard") or {}).get("R_in_target") is not False):
            reasons.append("pushover NSP target not stamped as the elastic IS spectrum (R_in_target must be False)")
        if india and not (po.get("mass_gate") or {}).get("ok"):
            reasons.append("pushover mass gate (sum m g = W within 1 %) not passed")
        if india:
            _nl17_package_checks(job_dir, "pushover", po, reasons, checks)
        dirs = po.get("directions") or {}
        if india and set(dirs) != {"X", "Y"}:
            reasons.append("pushover package must hold both directions X and Y (has %s)" % sorted(dirs))
        for d, dd in dirs.items():
            for lv, r in ((dd.get("response") or {}).items() if india else []):
                if not r.get("non_vacuous"):
                    reasons.append("pushover %s %s response has no member rows (vacuous)" % (d, lv))
    if nl and india:
        lvls = nl.get("levels") or {}
        if set(lvls) != {"DBE", "MCE"}:
            reasons.append("NLRHA must report both DBE and MCE (has %s)" % sorted(lvls))
        for lv, info in lvls.items():
            pkgp = os.path.join(job_dir, "nlrha", info.get("package") or os.path.join(lv, "nlrha_package.json"))
            lp = _read_json(pkgp)
            if not lp:
                reasons.append("NLRHA %s package missing (%s)" % (lv, pkgp)); continue
            if lp.get("plasticity") != "fibre" or not lp.get("fibre_eles"):
                reasons.append("NLRHA %s does not prove fibre plasticity" % lv)
            if "no R" not in str(lp.get("target_label") or ""):
                reasons.append("NLRHA %s target is not the IS elastic spectrum (label %r)" % (lv, lp.get("target_label")))
            rs = lp.get("response_summary") or {}
            n_suite = len(((lp.get("ground_motions") or {}).get("selected")) or [])
            if n_suite and (rs.get("n_records") or 0) < n_suite:
                reasons.append("NLRHA %s: only %s of the %d suite records analysed" % (lv, rs.get("n_records"), n_suite))
            if not rs.get("converged_all"):
                reasons.append("NLRHA %s: %s of %s records converged" % (lv, rs.get("n_converged"), rs.get("n_records")))
            if not (rs.get("non_vacuous") or {}).get("ok"):
                reasons.append("NLRHA %s response summary is vacuous (%s)" % (lv, (rs.get("non_vacuous") or {}).get("missing_kinds")))
            if not (lp.get("mass_gate") or {}).get("ok"):
                reasons.append("NLRHA %s mass gate not passed" % lv)
            _nl17_package_checks(job_dir, "NLRHA %s" % lv, lp, reasons, checks)
        mo = nl.get("modal") or {}
        if mo and not mo.get("spurious_ok", False):
            reasons.append("spurious modes present: %s" % mo.get("spurious_modes"))
        if mo and not mo.get("participation_sum_ok", False):
            reasons.append("modal participation sums exceed 1")
    # DDM
    ddm = _read_json(os.path.join(job_dir, "ddm_results.json"))
    shortfall = False
    if not ddm:
        reasons.append("ddm_results.json missing")
    else:
        g = (ddm.get("gravity_gate") or {})
        if not g.get("ok"):
            reasons.append("DDM gravity transfer gate (member forces at lambda=1 within 5 %% of member_schedule) not passed: %s"
                           % (g.get("summary") or "absent"))
        for r in ddm.get("runs") or []:
            stt = r.get("status")
            if stt is None:
                reasons.append("DDM run %s has no limit-point status (pre-WP4.9 results)" % r.get("label")); continue
            if stt == "SOLVER_FAILURE":                       # NL-24: a numerical stop blocks honestly, any kind
                reasons.append("DDM %s: SOLVER FAILURE (equilibrium iterations failed after the algorithm ladder and all "
                               "step cuts and the arc-length rescue; %s) at lambda %.3f -- a numerical stop, not a structural limit" % (
                                   r.get("label"), r.get("termination"), r.get("lambda_end") or 0))
                continue
            if stt == "NO_LIMIT_POINT" and r.get("kind") in ("gravity", "wind") and (r.get("lambda_end") or 0) < 1.0:
                reasons.append("DDM %s: NO_LIMIT_POINT and terminated below lambda 1 (%.3f)" % (r.get("label"), r.get("lambda_end") or 0))
        o_ = ddm.get("options") or {}
        if o_.get("n_combos_default") and (o_.get("n_combos_run") or 0) < o_["n_combos_default"]:
            reasons.append("DDM ran %s of the %s default combinations" % (o_.get("n_combos_run"), o_["n_combos_default"]))
        b12 = ddm.get("b12_check")
        if not b12:
            reasons.append("IS 800 B-1.2 section-capacity check at lambda = 1 missing")
        elif b12.get("ok") is False:
            shortfall = True
        if ddm.get("options", {}).get("time_limit") and float(ddm["options"]["time_limit"]) < 2400:
            reasons.append("DDM time limit %.0f s below the default 2400 s" % float(ddm["options"]["time_limit"]))
    # freshness
    summ = _read_json(os.path.join(job_dir, "snl_summary.json"))
    if not summ:
        reasons.append("snl_summary.json missing (regenerate summaries after every re-run)")
    else:
        rec = summ.get("inputs_sha256") or {}
        now = summary_inputs(job_dir)
        stale = [k for k in now if rec.get(k) != now[k]]
        if not rec:
            reasons.append("snl_summary.json records no input hashes (stale format)")
        elif stale:
            reasons.append("snl_summary.json is STALE for %s -- regenerate (`snl report`)" % ", ".join(stale))
    # nl_plan
    try:
        errs = [m for sev, m in validate_nl_plan(job_dir=job_dir) if sev == "ERROR"]
    except Exception:
        errs = []
    if errs:
        reasons.append("nl_plan ERROR: %s" % "; ".join(errs)[:200])
    return dict(ok=not reasons, reasons=reasons, checks=checks, capacity_shortfall=shortfall,
                inputs_sha256=summary_inputs(job_dir))


def write_complete_gate(job_dir: str) -> dict:
    """Evaluate the artefact gate for a finished job and write <job>/complete_gate.json (+ the disclosure file).
    Called only at the END of `nlrha run/report`, `pushover run`, `steltic_ddm run` and `snl report`."""
    st = design_status(job_dir=job_dir, evidence={"from_artifact": True})
    art = st["artefact_gate"]
    payload = dict(jurisdiction=JURISDICTION, status=st["status"], reasons=st["reasons"], checks=art.get("checks"),
                   inputs_sha256=art.get("inputs_sha256"),
                   statement="Gate on analysis artefacts only; IS 1893 provides no NL acceptance criteria (results informative).",
                   generated=__import__("time").strftime("%Y-%m-%dT%H:%M:%S"))
    with open(os.path.join(job_dir, "complete_gate.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, default=str)
    write_complete_gate_disclosures(job_dir, job_dir=job_dir, evidence={"from_artifact": True})
    return st
