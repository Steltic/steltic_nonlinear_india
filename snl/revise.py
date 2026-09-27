"""Re-issue the nonlinear reports with the IS corpus behind them.

`snl run` does the OpenSees work and never queries anything, so every clause its reports cite is
marked UNVERIFIED. The Review tab does query -- live, against the IS corpus the user built on this PC from
their licensed BIS PDFs -- and writes review.md into the project folder. This step is the manual join
between the two: it re-asks the corpus for the IS clauses those reports depend on (IS 1893 (Part 1):2016
7.7.4, 7.11.1.1, 6.4.2 and the IS 800:2007 Section 12 joint-rotation clause of the building's system),
records every passage it got, and re-issues the documents that can be rebuilt from the job folder with
the citation in place of the placeholder wording.

India (owner rulings D3 / D7): there is no foreign design basis, and IS 800 / IS 1893 / IS 18168 tabulate
no hinge backbone (nlrha.india_authority.hinge_analogue_status: found:false). So the component groups
are NOT searched for a modelling-parameter table -- a table found in some other context would launder a
citation into the reports -- they are recorded as modelling assumptions (information / EOR inputs),
never acceptance criteria. What it will NOT do either: flip `verified`. Retrieval is not the check.
"""
from __future__ import annotations

import datetime
import json
import os
import re

from . import grounding as G, rag

# The component groups of the parameter file. The US module grounds each in an AISC 342 / ASCE 41 modelling-
# parameter table; India has no such table in any IS document, so `tries` is empty and the group is recorded
# as a modelling assumption with HINGE_NOTE. A future AHJ-accepted source would be cited in
# nl_plan.hinge_source (india_authority.hinge_eor_documented), not searched for here.
HINGE_NOTE = ("IS 800:2007, IS 1893 (Part 1):2016 and IS 18168:2023 tabulate no hinge backbone for this component "
              "(nlrha.india_authority.hinge_analogue_status: found:false). The backbone in the parameter file is a "
              "modelling assumption -- information / EOR input -- and never an acceptance criterion. "
              "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information.")
GROUPS = [
    ("beam_flexure", "beams in flexure", ("beam",), []),
    ("column_flexure", "columns in flexure", ("column",), []),
    ("brace_axial", "braces in axial compression and tension", ("brace",), []),
]
# A passage only grounds a BACKBONE if it is the modelling-parameter table for THAT component (kept for the
# day an IS-corpus document carries one; with `tries` empty nothing is searched).
_TABLE_RE = re.compile(r"modeling\s+parameters|modelling\s+parameters|acceptance\s+criteria|permissible\s+deformations", re.I)

# The IS clauses the India NLRHA / pushover reports and the four-analyses sheet cite. The joint-rotation clause
# of IS 800 Section 12 depends on the system and is added per job (system_clauses).
CLAUSES = [
    ("7.7.4", "IS1893", "time history method ground motion compatible with the design acceleration spectrum"),
    ("7.11.1.1", "IS1893", "storey drift shall not exceed 0.004 times the storey height"),
    ("6.4.2", "IS1893", "design horizontal seismic coefficient Ah zone factor Sa/g"),
]


def _system(job: str) -> str:
    """The lateral system as the HR package states it (load_plan.json seismic_summary, else cfg.py)."""
    try:
        lp = json.load(open(os.path.join(job, "load_plan.json"), encoding="utf-8")) or {}
        s = (lp.get("seismic_summary") or {}).get("system")
        if s:
            return str(s)
    except Exception:
        pass
    try:
        src = open(os.path.join(job, "cfg.py"), encoding="utf-8", errors="replace").read()
        m = re.search(r"['\"]?\bsystem['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", src)
        return m.group(1) if m else ""
    except Exception:
        return ""


def system_clauses(job: str) -> list:
    """[(clause, document, query)] -- the IS joint-rotation reference for this building's system (reference only)."""
    try:
        from pushover import india_materials as IM
        ref = IM.reference_rotation(_system(job))
    except Exception:
        return []
    out = []
    for r in ref.get("refs") or []:
        m = re.search(r"(IS\s*18168|IS\s*800)\S*\s+(\d+(?:\.\d+)+)", str(r.get("clause") or ""))
        if m:
            out.append((m.group(2), "IS18168" if "18168" in m.group(1) else "IS800",
                        "%s %s rad" % (r.get("what") or "joint rotation", r.get("value"))))
    return out[:1]


def _cite(hit: dict, doc_key: str) -> str:
    sec = (hit.get("section") or "").strip()
    page = hit.get("page")
    bits = rag.TITLES.get(doc_key, doc_key)
    if sec:
        bits += " cl. " + sec
    if page not in (None, ""):
        bits += ", p. " + str(page)
    return "[%s]" % bits


def _relevant_hit(res: dict, words: tuple) -> dict | None:
    """The first hit that is the modelling-parameter table for this component -- or None.

    `rag.search` climbs a ladder whose last rung drops the document filter, and bm25 will happily
    hand back a neighbouring clause that shares vocabulary. Grounding a beam backbone in a gusset
    clause would be a citation nobody could check, so both tests have to pass.
    """
    if not res.get("ok"):
        return None
    for h in res.get("results") or []:
        text = "%s %s" % (h.get("title") or "", h.get("text") or "")
        if not text.strip():
            continue
        if not _TABLE_RE.search(text):
            continue
        if not any(w in text.lower() for w in words):
            continue
        return h
    return None


def _first_real_hit(res: dict, doc_key: str = "") -> dict | None:
    """The first hit that actually came from the document we asked for.

    `rag.search` climbs a ladder and its last rung drops the document filter, so a hit can come from
    a neighbouring standard. Citing an IS 1893 clause from an IS 800 passage would be worse than not
    grounding it at all, so the source has to match what was asked. (The US version's docstring says
    this but returned the first hit of any source; here the source is checked.)
    """
    if not res.get("ok"):
        return None
    want = rag.STEMS.get(doc_key or "", "")
    for h in res.get("results") or []:
        if not h.get("text"):
            continue
        src = str(h.get("source") or "")
        if want and src and rag.resolve(src) not in (None, doc_key) and not src.startswith(want):
            continue
        return h
    return None


def probe(log=print, extra_clauses=()) -> dict:
    """Ask the corpus for everything the reports lean on. -> the evidence record."""
    ev = {"asked": datetime.datetime.now().isoformat(timespec="seconds"),
          "rag_url": rag.url(), "groups": {}, "clauses": {}}
    if not rag.configured():
        ev["note"] = ("no standards server (RAG_API_URL is empty) -- start the hub's IS corpus module "
                      "from the hub's Modules page, or run this from the hub")
        return ev
    st = rag.status(force=True)
    cm = rag.corpus_map(st)
    ev["corpus"] = {"present": sorted(cm.get("present") or []), "absent": sorted(cm.get("absent") or [])}
    for gid, what, words, tries in GROUPS:
        rec = {"what": what, "grounded": False, "attempts": []}
        if not tries:
            rec.update(status="modelling assumption", note=HINGE_NOTE)
        for doc_key, query, chapter in tries:
            if doc_key in (cm.get("absent") or []):
                rec["attempts"].append({"document": doc_key, "skipped": "not converted on this PC"})
                continue
            res = rag.search(query, doc_key, top_k=6, chapter=chapter)
            hit = _relevant_hit(res, words)
            rec["attempts"].append({"document": doc_key, "query": query, "hits": len(res.get("results") or []),
                                    "relevant": bool(hit), "note": res.get("note") or "", "via": res.get("via") or ""})
            if hit:
                rec.update(grounded=True, document=doc_key, citation=_cite(hit, doc_key),
                           section=hit.get("section") or "", page=hit.get("page"),
                           passage=(hit.get("text") or "")[:1200])
                break
        ev["groups"][gid] = rec
        log("   %-16s %s" % (gid, rec.get("citation") if rec["grounded"]
                              else ("modelling assumption (information / EOR input) -- no IS hinge table" if not tries
                                    else "no modelling-parameter table for this component in the corpus")))
    for cid, doc_key, query in list(CLAUSES) + list(extra_clauses):
        res = rag.search(query, doc_key, top_k=3, clause=cid)
        hit = _first_real_hit(res, doc_key)
        ev["clauses"][cid] = ({"grounded": True, "citation": _cite(hit, doc_key), "page": hit.get("page"),
                               "passage": (hit.get("text") or "")[:800]} if hit else
                              {"grounded": False, "note": res.get("note") or "no passages"})
        log("   %-16s %s" % (cid, ev["clauses"][cid].get("citation") or "NOT FOUND in the corpus"))
    return ev


def annotate_params(job: str, ev: dict, log=print) -> dict | None:
    """Write the grounding into the params file the run actually used.

    -> {"path", "fingerprint"}, or None. The fingerprint is of the modelling parameters alone, so the
    record survives the analysis run copying a byte-identical params file over this one -- and stops a
    grounding recorded for one parameter set being shown against another."""
    path = next((p for p in (os.path.join(job, "pushover", "hinge_params_used.json"),
                             os.path.join(job, "hinge_params_base.json")) if os.path.exists(p)), None)
    if not path:
        log("!! no hinge_params_used.json in this project -- run the analyses first")
        return None
    try:
        prm = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        log("!! could not read %s: %s" % (path, e))
        return None
    grounded = {g: r for g, r in ev.get("groups", {}).items() if r.get("grounded")}
    prm["grounding"] = {"asked": ev.get("asked"), "groups": {g: {k: r.get(k) for k in ("document", "citation", "section", "page")}
                                                             for g, r in grounded.items()},
                        "clauses": {c: r.get("citation") for c, r in ev.get("clauses", {}).items() if r.get("grounded")},
                        "evidence": "revise_evidence.json"}
    if grounded:
        cites = "; ".join(r["citation"] for r in grounded.values())
        prm["source"] = ("cited from the corpus on this PC %s -- %s. The numeric backbone values in "
                         "this file were NOT read out of those tables; `verified` stays "
                         "false until they are." % (ev.get("asked") or "", cites))
    assumed = [g for g, r in ev.get("groups", {}).items() if r.get("status") == "modelling assumption"]
    if assumed:
        prm["grounding"]["modelling_assumptions"] = {"groups": assumed, "note": HINGE_NOTE}
    json.dump(prm, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(">> params annotated: %s (%d of %d groups grounded)" % (path, len(grounded), len(GROUPS)))
    return {"path": path, "fingerprint": G.fingerprint(prm)}


def run(job: str, log=print) -> dict:
    """The whole step. Requires the Review tab to have run on this project."""
    job = os.path.abspath(job)
    review = os.path.join(job, "review.md")
    if not os.path.exists(review):
        raise SystemExit("no review.md in %s -- run the Review tab on this project first; it reads what the "
                         "analyses measured, looks the governing clauses up in the corpus and writes review.md, "
                         "review.html and review_transcript.json into the project folder." % job)
    if not os.path.getsize(review):
        raise SystemExit("review.md in %s is empty -- re-run the Review tab." % job)
    log(">> review found: %s (%d bytes)" % (review, os.path.getsize(review)))
    log(">> asking the corpus for the clauses the reports lean on")
    ev = probe(log=log, extra_clauses=system_clauses(job))
    ev["review_md"] = {"path": review, "bytes": os.path.getsize(review)}
    prm_rec = annotate_params(job, ev, log=log)
    if prm_rec:
        ev["params"] = prm_rec                     # written into the evidence, which the run never touches
    out = os.path.join(job, "revise_evidence.json")
    json.dump(ev, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    log(">> evidence: %s" % out)

    # The supplements are rendered during the analysis run from live OpenSees objects, so they cannot be
    # re-rendered here -- and re-running the analyses is what ERASES this grounding (pushover/cli.py copies
    # the input params over hinge_params_used.json). So the provenance block in each report is replaced
    # where it stands. Only that block moves; not one number is touched. India: the pushover report and
    # the NLRHA index plus its DBE / MCE level pages.
    prm = {}
    if prm_rec:
        try:
            prm = json.load(open(prm_rec["path"], encoding="utf-8"))
        except Exception:
            prm = {}
    st, gev = G.state(prm, job)
    patched = []
    reports = ["pushover/pushover_report.html", "nlrha/nlrha_report.html"]
    reports += ["nlrha/%s/nlrha_report.html" % lv for lv in ("DBE", "MCE")]
    for rel in reports:
        fp = os.path.join(job, *rel.split("/"))
        if not os.path.exists(fp):
            continue
        res = G.patch(fp, st, gev, prm)
        if res == G.PATCHED:
            patched.append(fp)
        elif res == G.UNCHANGED:
            log("   already current: %s" % rel)
        else:
            log("!! %s carries no provenance block (written by an older build) -- re-run the analyses "
                "once to pick up the new report, or read the citation in revise_evidence.json" % rel)
    pk_rels = ["pushover/pushover_package.json", "nlrha/nlrha_package.json"]
    pk_rels += ["nlrha/%s/nlrha_package.json" % lv for lv in ("DBE", "MCE")]
    for pk_rel in pk_rels:
        pk_path = os.path.join(job, *pk_rel.split("/"))
        if not os.path.exists(pk_path):
            continue
        try:                                        # the four-analyses sheet reads provenance from here
            pk = json.load(open(pk_path, encoding="utf-8"))
            pk["params_state"] = st
            pk["params_grounding"] = (gev or {}).get("groups") or {}
            pk["params_clauses"] = {c: r.get("citation") for c, r in ((gev or {}).get("clauses") or {}).items()
                                    if isinstance(r, dict) and r.get("grounded")}
            json.dump(pk, open(pk_path, "w", encoding="utf-8"), indent=1, default=str)
            patched.append(pk_path)
        except Exception as e:
            log("!! could not update %s: %s" % (pk_rel, e))

    rebuilt, failed = list(patched), []
    try:                                   # the design-criteria document reads the params file
        from nlrha import design_criteria as DC
        made = DC.write(job)
        rebuilt += [p for p in (made if isinstance(made, (list, tuple)) else [made]) if p]
    except Exception as e:
        failed.append("design criteria: %r" % (e,))
    try:                                   # the four-analyses sheet reads the packages
        from . import compare
        rebuilt.append(compare.build(job))
    except Exception as e:
        failed.append("four analyses: %r" % (e,))
    for p in rebuilt:
        log(">> re-issued: %s" % p)
    for f in failed:
        log("!! not re-issued -- %s" % f)
    n = sum(1 for r in ev.get("groups", {}).values() if r.get("grounded"))
    c = sum(1 for r in ev.get("clauses", {}).values() if r.get("grounded"))
    nc = len(ev.get("clauses", {}))
    log(">> grounded %d of %d IS clauses; %d component groups are modelling assumptions (no IS hinge table)"
        % (c, nc, sum(1 for r in ev.get("groups", {}).values() if r.get("status") == "modelling assumption")))
    if c < nc:
        log("   what the corpus could not answer stays marked in the reports -- that is the point of the mark")
    if st == G.GROUNDED:
        log("   every document in this project now carries the citation. Do NOT re-run the analyses to "
            "\"pick it up\" -- a run copies the input parameters over pushover/hinge_params_used.json, and "
            "the grounding is re-applied from revise_evidence.json on the next run rather than lost.")
    log("   `verified` stays false: the hinge backbones are modelling assumptions (information / EOR input) -- "
        "IS 800 / IS 1893 / IS 18168 tabulate none -- and a retrieved clause is not a check of any number.")
    return {"evidence": out, "rebuilt": rebuilt, "failed": failed, "groups_grounded": n, "clauses_grounded": c}
