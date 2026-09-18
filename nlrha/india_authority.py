"""India NL authority — LIVE RAG gates; never invent ASCE→IS mappings.

steltic_nonlinear_india is the India fork of USA steltic_nonlinear (ASCE 41 NSP +
ASCE 7-22 Ch.16 NLRHA + DDM). On this fork:

  * Design packages come from **steltic_india** (IS 800 / IS 808 / load_plan), not
    AISC-only forever. Point STELTIC_ENGINE_DIR at steltic_india/steel_engine.
  * Corpus: /workspace/engineering_rag_india only (stems IS_1893_Part_1_2016,
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

Reuse helpers from steltic_india (india_seismic, india_loads) when useful; do not
re-hardcode IS formulas here.
"""
from __future__ import annotations

import json
import os
from typing import Any

JURISDICTION = "india"
CORPUS_ROOT = "/workspace/engineering_rag_india"
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
        "note": "Dynamic analysis displacements shall not be scaled as in 7.7.3.",
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
}

# Explicit gaps — do NOT fabricate ASCE analogues.
ASCE_GAPS = [
    {
        "id": "asce_41_nsp",
        "found": False,
        "usa": "ASCE/SEI 41-23 NSP + AISC 342-22 component tables",
        "note": (
            "No IS 1893 / IS 800 pushover (NSP) procedure or steel hinge tables in the "
            "India corpus. Pushover engine remains scaffolding; hinge_params verified:false "
            "until an AHJ-accepted source is retrieved and cited."
        ),
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
            "India site hazard is zone factor Z / design spectrum from IS 1893 RAG "
            "(steltic_india load_plan / seis). USGS MCE_R path is USA scaffolding only."
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
