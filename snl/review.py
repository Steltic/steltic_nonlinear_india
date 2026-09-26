"""review.py -- the Review step: the model reads what the run measured and writes the engineer's review.

    python -m snl review <job folder> [--focus "..."] [--no-standards] [--max-searches 8]

Inputs are what a finished run left in the job folder (snl_summary.json, snl_run.json, nlrha/nlrha_package.json,
pushover/pushover_package.json, ddm_results.json, design/calc_package.json, seismic_calc.json, the design-criteria
draft, any feedback loops) -- gathered here into one bounded evidence document, every number from a file, nothing
invented. The model (the hub's connection, via STELTIC_LLM_*) grounds the clauses it cites through the IS corpus
(snl/rag.py, RAG_API_URL -> engineering_rag_india) and writes review.md / review.html / review_transcript.json
beside the analyses. India (D3 / D7): IS documents only, and no pass/fail verdict -- IS 1893 (Part 1):2016
provides no acceptance criteria for nonlinear analysis; results are for information.

While it works it prints one JSON event per line in the vocabulary the Steltic hub relays -- reasoning,
token, tool, tool_result, milestone, status, usage -- so the hub shows the model's text on the run line, its
reasoning in the separate box, and one line per standards search, exactly as it does for HR Steel and CFS.
Plain lines are the log. Model MOCK writes the review from the evidence alone, offline, with the same searches.
"""
from __future__ import annotations
import datetime, html, json, os, re, sys, time

from . import llm, rag

MAX_TURNS = 14
TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_engineering_standards",
        "description": ("Search the licensed IS corpus (IS 1893 (Part 1):2016, IS 800:2007, IS 18168:2023, IS 2062 (Part 1):2025, "
                        "IS 808:2021, IS 875) for the clause, table or equation you are about to cite. ONE thing per call. Give the exact "
                        "id in `clause` when you know it (7.11.1.1, 7.7.4, 12.11.1, Table 3): the server does an exact section/table "
                        "lookup first, then full text. `query` in the standard's own words, short. Search only documents the corpus holds "
                        "(see DOCUMENTS IN THE CORPUS); a miss is escalated for you (filters dropped, exact id, other IS documents) and the "
                        "result says which document answered. Cite only what a passage supports; a clause the search cannot find is "
                        "cited from memory and marked (UNVERIFIED). There is no foreign design basis: do not cite ASCE / AISC as authority."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you are looking for, in the standard's own words"},
                "document": {"type": "string", "enum": list(rag.DOCUMENTS), "description": "; ".join("%s = %s" % (k, d) for k, (_c, d) in rag.DOCUMENTS.items())},
                "clause": {"type": "string", "description": "Exact clause / table id when known, e.g. 7.11.1.1, 7.7.4, 12.11.1, Table 3"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            "required": ["query", "document"],
        },
    },
}]

IS_NL_STATEMENT = ("IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; "
                   "results are for information.")

SYSTEM = """You are the independent structural reviewer for a steel building designed to IS 800:2007 and IS 1893 (Part 1):2016 by HR Steel (steltic_india) and run through the three nonlinear analyses of steltic_nonlinear_india: a pushover (nonlinear static; target displacement against the IS 1893 elastic spectrum), the nonlinear response-history analysis (IS 1893 7.7.4) at the elastic DBE = (Z/2)·I·Sa/g and MCE = Z·I·Sa/g (never divided by R), and the DDM system-capacity (GMNIA) check. You are handed the run's measured results as an EVIDENCE document.

IS standards only: there is no foreign design basis. IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information. So the review reports response quantities and margins against IS reference values and gives NO pass/fail verdict for a nonlinear result: never write ACCEPTABLE, NOT ACCEPTABLE, PASS or FAIL for the pushover or the NLRHA, and never import ASCE 7 Chapter 16, ASCE 41 or AISC 341 / 342 / 358 limits (drift x 2, IO / LS / CP, unacceptable-response counts, Risk Category) as India criteria.

Write the review as Markdown with these sections, in this order:
1. **Summary** -- one paragraph that starts with the sentence "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information." and then says what the analyses show and how the response compares with the IS reference values.
2. **What the run measured** -- the numbers that matter, each attributed to its analysis and hazard level.
3. **Response-history results (DBE and MCE)** -- per level: suite mean and peak storey drift (with, for comparison only, IS 1893 7.11.1.1's 0.004 h, which limits the LINEAR analysis under VB), base shear against VB and the elastic Sa(T1)·W, ductility demand, member chord rotations against the IS 800 Section 12 joint-rotation capacity for the system (0.02 / 0.04 rad, reference only), column axial force against IS 800 7.1.2 Pd (information), records that did not converge.
4. **Pushover** -- capacity curve, Vmax / VB, mechanism, target displacement at IS-DBE and IS-MCE and whether it was reached, the descending branch.
5. **DDM system capacity** -- governing combination (IS 800 Table 4 / the package's load_plan), lambda_u, the IS 800 B-1.2 section check at lambda = 1, the gravity transfer gate.
6. **Design basis and the design criteria draft** -- consistency between the linear design (zone, Z, I, R, soil type, VB, W, Ta) and what the nonlinear analyses used; gaps to close in the design-criteria document.
7. **What to change, and why** -- ranked; each item names the member group or parameter, the measured quantity that motivates it, and the IS clause that bears on it. If nothing should change, say so and why.
8. **Open items and verification** -- modelling assumptions (hinge backbones are in no IS document: information / EOR inputs, never acceptance criteria), unverified parameters, found:false disclosures, records retried, anything flagged in the evidence.

Rules:
- Every number comes from the EVIDENCE. Never invent a value; when the evidence lacks one, say "not in the run".
- Before you cite a clause, table or equation, look it up with search_engineering_standards (at most the number of searches you are told) and cite it as [IS 1893 (Part 1):2016 cl. 7.11.1.1, p. 22] with the page the passage gives. A clause you could not find: cite it from memory and append (UNVERIFIED).
- Ratios and percentages are written with their basis (e.g. "MCE suite mean drift 1.46% of h; 0.004 h = 0.40% is the linear-analysis limit of IS 1893 7.11.1.1, shown for comparison only").
- Units are SI (kN, mm, MPa, rad) as the evidence gives them.
- Be specific and short. No preamble, no closing pleasantries. Write in English.

How to search (the retrieval policy the design agents follow):
- One clause, table or equation per call. Put its exact id in `clause` (7.11.1.1, 7.7.4, 6.4.2, 12.8.1, Table 3); the server tries an exact section / table lookup first, then full text. `query` is short and in the standard's own words ("storey drift 0.004 times the storey height"), not a sentence of your own.
- Search only the documents listed under DOCUMENTS IN THE CORPUS. A document listed as ABSENT is not in the IS corpus on this PC: do not search it (such a call is answered with a corpus-gap note, is not counted, and is wasted); cite it from memory, marked (UNVERIFIED), and say in section 8 that it was unavailable.
- A miss is escalated for you: the clause filter dropped, the id as an exact lookup, then every other IS document. When the result says it was answered by another document, cite THAT document, not the one you asked for.
- NO PASSAGES after the ladder means the wording is not in the indexed text: re-word once in the standard's own terms or ask for the parent clause, then cite from memory, (UNVERIFIED). Never invent a clause number, table id or page.
"""


# ---------------------------------------------------------------- evidence
def _json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        s = open(path, encoding="utf-8").read()
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return json.loads(re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s))
    except Exception:                                            # noqa: BLE001
        return default


def _text_of_html(path, limit=6000):
    if not os.path.exists(path):
        return ""
    h = open(path, encoding="utf-8", errors="replace").read()
    t = re.sub(r"<style.*?</style>|<script.*?</script>", "", h, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()[:limit]


def _r(v, n=4):
    if isinstance(v, float):
        return round(v, n)
    if isinstance(v, dict):
        return {k: _r(x, n) for k, x in v.items()}
    if isinstance(v, list):
        return [_r(x, n) for x in v]
    return v


def _scal(d, keys=None, n=4):
    """The scalar fields of a dict (numbers, strings, booleans, None), rounded -- lists and blocks left out."""
    if not isinstance(d, dict):
        return None
    return {k: _r(v, n) for k, v in d.items() if (keys is None or k in keys) and (v is None or isinstance(v, (int, float, str, bool)))}


def _pct100(x, n=3):
    return _r(100 * x, n) if isinstance(x, (int, float)) else None


def _level(job: str, lv: str, d: dict) -> dict:
    """One NLRHA hazard level: the index row plus the per-level response summary, bounded."""
    out = {k: _r(d.get(k)) for k in ("target_label", "n_records", "n_converged")}
    out["max_mean_drift_pct"] = _pct100(d.get("max_mean_drift"))
    out["max_peak_drift_pct"] = _pct100(d.get("max_peak_drift"))
    out["base_shear"] = _scal(d.get("base_shear"))
    out["ductility"] = _r(d.get("ductility"))
    sf = [x for x in (d.get("scale_factors") or []) if isinstance(x, (int, float))]
    out["sf_range"] = [_r(min(sf), 3), _r(max(sf), 3)] if sf else None
    rel = d.get("package")
    lp = _json(os.path.join(job, "nlrha", rel)) if rel else None
    rs = (lp or {}).get("response_summary") or {}
    if rs:
        out["story"] = [{"story": s.get("story"), "h_mm": _r(s.get("h_mm"), 0), "mean_X_pct": _pct100(s.get("mean_X")), "mean_Y_pct": _pct100(s.get("mean_Y")),
                         "max_X_pct": _pct100(s.get("max_X")), "max_Y_pct": _pct100(s.get("max_Y"))} for s in rs.get("story") or []]
        out["records"] = [{"label": p.get("label"), "sf": _r(p.get("sf"), 3), "converged": p.get("converged"), "reason": p.get("reason"),
                           "max_drift_X_pct": _pct100(p.get("max_drift_X")), "max_drift_Y_pct": _pct100(p.get("max_drift_Y")),
                           "residual_max_pct": _pct100(p.get("residual_max")), "base_shear_kN": _r(p.get("base_shear_kN"), 0),
                           "retry": bool(p.get("retry"))} for p in rs.get("per_record") or []]
        out["reference_rotation"] = rs.get("reference_rotation")
        out["member_groups_worst"] = sorted([_scal(g) for g in rs.get("member_groups") or []],
                                            key=lambda g: -((g or {}).get("chord_rot_max_rad") or 0))[:12]
        out["brace_groups_worst"] = sorted([_scal(g) for g in rs.get("brace_groups") or []],
                                           key=lambda g: -((g or {}).get("mu_tension_max") or 0))[:8]
        out["column_axial_vs_Pd_worst"] = sorted([_scal(c, ("section", "z_mm", "P_mean_kN", "P_max_kN", "Pd_kN", "ratio_max", "cite"))
                                                  for c in rs.get("force_controlled_columns") or []],
                                                 key=lambda c: -((c or {}).get("ratio_max") or 0))[:8]
        out["non_vacuous"] = _scal(rs.get("non_vacuous"))
    if lp:
        out["plasticity"] = lp.get("plasticity")
        out["materials"] = (lp.get("materials") or [])[:6] if isinstance(lp.get("materials"), list) else lp.get("materials")
    return out


def gather(job: str) -> dict:
    """Everything the reviewer may cite, bounded (a few tens of kB), every number from a file in the job folder.

    India package shapes (steltic_nonlinear_india): nlrha/nlrha_package.json is the index of the DBE / MCE levels
    (nlrha/<LEVEL>/nlrha_package.json holds each level's response summary), the pushover and DDM packages carry
    response quantities only (verdict None, D7), the linear design basis is seismic_calc.json / load_plan.json."""
    job = os.path.abspath(job)
    ev: dict = {"job": os.path.basename(job), "jurisdiction": "india", "statement": IS_NL_STATEMENT, "files": {}}
    for rel in ("snl_summary.json", "snl_run.json", "nlrha/nlrha_package.json", "pushover/pushover_package.json", "ddm_results.json",
                "design/calc_package.json", "seismic_calc.json", "load_plan.json", "nl_plan.json", "hinge_params_collected.json",
                "complete_gate.json", "design_criteria_16_1_4.html", "four_analyses.html", "report.html"):
        ev["files"][rel] = os.path.exists(os.path.join(job, rel))
    summ = _json(os.path.join(job, "snl_summary.json"), {}) or {}
    ev["summary"] = _r({k: v for k, v in summ.items() if k != "inputs_sha256"})
    run = _json(os.path.join(job, "snl_run.json"), {}) or {}
    ev["run"] = {"started": run.get("started"), "finished": run.get("finished"),
                 "steps": {k: {"returncode": v.get("returncode"), "seconds": v.get("seconds"), "skipped": v.get("skipped")}
                           for k, v in (run.get("steps") or {}).items() if isinstance(v, dict)}}
    # response history: the DBE / MCE index and each level's response summary
    nl = _json(os.path.join(job, "nlrha", "nlrha_package.json"))
    if nl:
        ev["nlrha"] = {"statement": nl.get("statement"), "verdict": nl.get("verdict"), "hazard": _r(nl.get("hazard")),
                       "plasticity": nl.get("plasticity"), "gm_basis": nl.get("gm_basis"),
                       "damping": (nl.get("numerics") or {}).get("damping") if isinstance(nl.get("numerics"), dict) else None,
                       "modal": _scal(nl.get("modal")),
                       "levels": {lv: _level(job, lv, d) for lv, d in (nl.get("levels") or {}).items() if isinstance(d, dict)}}
    # pushover
    po = _json(os.path.join(job, "pushover", "pushover_package.json"))
    if po:
        d = {}
        for k, x in (po.get("directions") or {}).items():
            d[k] = {"T1": _r(x.get("T1")), "meff_frac": _r(x.get("meff_frac")), "stop_reason": x.get("stop_reason"),
                    "tail": {kk: (x.get("tail") or {}).get(kk) for kk in ("status", "captured", "message")},
                    "capacity": _scal(x.get("capacity")),
                    "nsp": {lvl: _scal(v, ("Te", "Sa", "C0", "C1", "C2", "target_disp_mm", "reached_target", "nsp_permitted"))
                            for lvl, v in (x.get("nsp") or {}).items() if isinstance(v, dict)},
                    "response": {lvl: _scal(v) for lvl, v in (x.get("response") or {}).items() if isinstance(v, dict)}}
        ev["pushover"] = {"statement": po.get("statement"), "verdict": po.get("verdict"), "params_verified": po.get("params_verified"),
                          "brace_backbone_note": po.get("brace_backbone_note"), "plasticity": po.get("plasticity"),
                          "basis": _scal(po.get("basis")), "hazard": po.get("hazard"), "reference_rotation": po.get("reference_rotation"),
                          "materials": (po.get("materials") or [])[:6] if isinstance(po.get("materials"), list) else po.get("materials"),
                          "directions": d}
    # DDM
    dd = _json(os.path.join(job, "ddm_results.json"))
    if dd:
        runs = []
        for r in dd.get("runs") or []:
            row = _scal(r, ("label", "status", "lambda_u", "lambda_end", "check", "termination", "imp"))
            cls = r.get("cls") or {}
            if isinstance(cls, dict):
                row.update({"mechanism": (cls.get("mechanism") or "")[:160], "mechanism_class": cls.get("cls")})
            runs.append(row)
        ev["ddm"] = {"status": dd.get("status"), "runs": runs,
                     "b12_check": _scal(dd.get("b12_check")), "gravity_gate": _scal(dd.get("gravity_gate")),
                     "gate": _scal(dd.get("gate")),
                     "options": {k: v for k, v in (dd.get("options") or {}).items() if isinstance(v, (int, float, str, bool))}}
    # the linear design
    cp = _json(os.path.join(job, "design", "calc_package.json"), {}) or {}
    members = [m for m in (cp.get("members") or []) if isinstance(m, dict) and isinstance(m.get("DC"), (int, float))]
    sc = _json(os.path.join(job, "seismic_calc.json"), {}) or {}
    lp = (_json(os.path.join(job, "load_plan.json"), {}) or {}).get("seismic_summary") or {}
    ev["design"] = {"building": cp.get("building"), "code": cp.get("code"),
                    "worst_members": [{"id": m.get("id"), "section": (m.get("inputs") or {}).get("section"), "DC": _r(m.get("DC")),
                                       "limit_state": m.get("limit_state"), "combo": (m.get("inputs") or {}).get("governing_combo")}
                                      for m in sorted(members, key=lambda m: -m["DC"])[:10]],
                    "n_members_checked": len(members),
                    "seismic": {"zone": lp.get("zone"), "Z": sc.get("Z", lp.get("Z")), "I": sc.get("I", lp.get("I")), "R": sc.get("R", lp.get("R")),
                                "soil": lp.get("soil"), "system": lp.get("system"), "Ta_s": _r(sc.get("Ta_s", lp.get("Ta_s"))),
                                "Sa_g": sc.get("Sa_g"), "Ah": _r(sc.get("Ah")), "VB_kN": _r(sc.get("VB_kN"), 1),
                                "W_kN": _r(sum(sc["W_kN"]) if isinstance(sc.get("W_kN"), list) else sc.get("W_kN", lp.get("W_kN")), 1),
                                "drift_limit_ratio": lp.get("drift_limit_ratio"), "cite": lp.get("cite")}}
    # the design-criteria draft, the four-analyses sheet, the COMPLETE gate's disclosures
    ev["design_criteria_draft"] = _text_of_html(os.path.join(job, "design_criteria_16_1_4.html"), 5000)
    ev["four_analyses"] = _text_of_html(os.path.join(job, "four_analyses.html"), 2500)
    gate = _json(os.path.join(job, "complete_gate.json"))
    if isinstance(gate, dict):
        ev["complete_gate"] = {"status": gate.get("status") or gate.get("design_status"),
                               "disclosures": [_scal(x, ("id", "found", "note", "status")) for x in (gate.get("disclosures") or []) if isinstance(x, dict)][:12]}
    # feedback loops already run
    fb = os.path.join(job, "feedback")
    loops = []
    if os.path.isdir(fb):
        for d in sorted(os.listdir(fb)):
            st = _json(os.path.join(fb, d, "state.json"))
            if st:
                loops.append({"id": d, "kind": st.get("kind"), "status": st.get("status"), "passed": st.get("passed"), "title": st.get("title"),
                              "verdict": ((st.get("comparison") or {}).get("verdict_text") or "")[:300], "promoted_at": st.get("promoted_at")})
    ev["feedback_loops"] = loops
    return ev


# ---------------------------------------------------------------- events
class Emitter:
    """One JSON event per line on stdout (what the hub relays), plain lines for the log."""
    def __init__(self, out=None):
        self.out = out or sys.stdout
        self.cum_in = self.cum_out = 0

    def event(self, **ev):
        self.out.write(json.dumps(ev, ensure_ascii=False) + "\n"); self.out.flush()

    def log(self, text):
        self.out.write(str(text).replace("\n", " ") + "\n"); self.out.flush()

    def usage(self, u):
        if not isinstance(u, dict):
            return
        i, o = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
        self.cum_in += i; self.cum_out += o
        self.event(type="usage", last_in=i, last_out=o, cum_in=self.cum_in, cum_out=self.cum_out)


# ---------------------------------------------------------------- the review
def _evidence_message(ev: dict, focus: str) -> str:
    txt = json.dumps(ev, indent=None, ensure_ascii=False, default=str)
    return ("EVIDENCE (the run's measured results, JSON):\n" + txt + "\n\n"
            + ("FOCUS (the engineer's question -- address it first, in the Summary and in section 7):\n" + focus.strip() + "\n\n" if focus and focus.strip() else "")
            + "Write the review now.")


def _tool_title(args: dict) -> str:
    q = (args.get("query") or "").strip()
    return "%s%s: %s" % (args.get("document") or "?", (" " + args["clause"]) if args.get("clause") else "", q[:90])


def run(job: str, focus: str = "", use_standards: bool = True, max_searches: int = 8, emit: Emitter | None = None, conn: dict | None = None) -> dict:
    """The whole step. Returns {"ok", "review_md", "paths", "searches", "usage"}."""
    em = emit or Emitter()
    job = os.path.abspath(job)
    conn = conn or llm.connection()
    t0 = time.time()
    em.event(type="status", text="reading what the run measured")
    ev = gather(job)
    have = [k for k in ("nlrha", "pushover", "ddm") if k in ev]
    if not have and not ev.get("summary"):
        em.event(type="error", text="nothing to review: no snl_summary.json, nlrha/, pushover/ or ddm_results.json in %s -- run the analyses first" % job)
        return {"ok": False, "review_md": "", "paths": {}, "searches": [], "usage": {}}
    em.event(type="milestone", text="evidence: %s%s" % (", ".join(have) or "summary only", "" if use_standards and rag.configured() else
                                                         (" -- standards search off" if not use_standards else " -- no standards server (RAG_API_URL empty): clauses will be cited from memory, marked UNVERIFIED")))
    em.log("evidence gathered from %s: %d kB, analyses: %s" % (os.path.basename(job), len(json.dumps(ev, default=str)) // 1000, ", ".join(have) or "none"))
    searches: list = []
    budget = max(0, int(max_searches)) if (use_standards and rag.configured()) else 0   # no server: no tool offered, the review says so
    corpus_line = ""
    if budget:
        # what the corpus actually holds, before the first search: the model is told, and a search for a
        # document that is not here is answered as a gap without spending the budget
        st = rag.status(force=True)
        cm = rag.corpus_map(st)
        corpus_line = rag.describe_corpus(cm)
        if not st.get("ok") and st.get("note"):
            em.event(type="warning", text="standards server: %s -- searches may fail; clauses then come from memory, marked UNVERIFIED" % st["note"])
        em.event(type="milestone", text="standards corpus -- " + corpus_line)
        if cm.get("known") and cm.get("absent"):
            em.log("standards corpus: %s absent on this PC -- the model is told not to search %s; install / update the IS corpus module (engineering_rag_india) or convert on its Convert tab (stems %s), then Rebuild index"
                   % (", ".join(rag.TITLES[k] for k in cm["absent"]), "them" if len(cm["absent"]) > 1 else "it", ", ".join(rag.STEMS[k] for k in cm["absent"])))
    spent = {"n": 0}                                             # searches that reached a document the corpus holds

    def do_search(args: dict) -> str:
        n = len(searches) + 1
        em.event(type="tool", name="search_engineering_standards", step=n, title=_tool_title(args))
        if spent["n"] >= budget:
            res = {"ok": False, "results": [], "counted": False, "via": "", "note": "search budget of %d used up -- cite the remaining clauses from memory, marked UNVERIFIED" % budget, "ms": 0}
        else:
            res = rag.search(args.get("query") or "", args.get("document") or "IS1893", int(args.get("top_k") or 5), args.get("clause") or "", args.get("chapter") or "")
            if res.get("counted", True):
                spent["n"] += 1
        searches.append({"n": n, "args": args, "hits": len(res.get("results") or []), "note": res.get("note"), "ms": res.get("ms"),
                         "via": res.get("via"), "counted": bool(res.get("counted", True)), "missing_document": res.get("missing_document"),
                         "attempts": res.get("attempts"),
                         "results": [{k: h.get(k) for k in ("source", "section", "title", "page", "score")} for h in (res.get("results") or [])],
                         "passages": [h.get("text") for h in (res.get("results") or [])]})
        nres = len(res.get("results") or [])
        summ = "%d passage(s)" % nres
        if res.get("via") and res["via"] not in ("", "as-asked"):
            summ += " via " + str(res["via"]).split(" (")[0]
        if res.get("missing_document"):
            summ += " -- %s is not in the corpus (not counted)" % res["missing_document"]
        elif res.get("note") and (not nres or res.get("via") == "any-document"):
            summ += (" -- " + str(res["note"]))[:160]
        em.event(type="tool_result", step=n, summary=summ, ms=res.get("ms") or 0)
        return rag.render(res)

    if conn.get("mock"):
        em.event(type="status", text="model MOCK: writing the review from the evidence alone")
        md = mock_review(ev, focus, do_search if budget else None)
        usage = {}
    else:
        em.event(type="status", text="asking %s (up to %d standards searches)" % (conn["model"], budget))
        sys_msg = SYSTEM
        if budget:
            sys_msg += "\nDOCUMENTS IN THE CORPUS -- " + corpus_line + "\nYou may make at most %d searches (a search for an ABSENT document is not counted, and is wasted)." % budget
        else:
            sys_msg += "\nThe standards search is unavailable for this run: cite from memory and mark every clause (UNVERIFIED)."
        messages = [{"role": "system", "content": sys_msg},
                    {"role": "user", "content": _evidence_message(ev, focus)}]
        md = ""
        usage = {}
        for turn in range(MAX_TURNS):
            def on_piece(kind, text):
                em.event(type=kind, text=text)
            try:
                out = llm.chat_with_retry(conn, messages, TOOLS if budget else None, on_piece)
            except llm.LLMError as e:
                em.event(type="error", text=str(e))
                return {"ok": False, "review_md": "", "paths": {}, "searches": searches, "usage": usage}
            if out.get("usage"):
                em.usage(out["usage"]); usage = out["usage"]
            if out["tool_calls"]:
                messages.append({"role": "assistant", "content": out["content"] or None, "tool_calls": out["tool_calls"]})
                for tc in out["tool_calls"]:
                    try:
                        args = json.loads(tc["function"]["arguments"] or "{}")
                    except ValueError:
                        args = {"query": tc["function"]["arguments"], "document": "IS1893"}
                    if tc["function"]["name"] != "search_engineering_standards":
                        result = "unknown tool %s" % tc["function"]["name"]
                    else:
                        result = do_search(args if isinstance(args, dict) else {})
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                continue
            md = (out["content"] or "").strip()
            if md:
                break
            messages.append({"role": "assistant", "content": ""})
            messages.append({"role": "user", "content": "Your reply was empty. Write the review now, in the eight sections."})
        if not md:
            em.event(type="error", text="the model did not produce the review after %d turns" % MAX_TURNS)
            return {"ok": False, "review_md": "", "paths": {}, "searches": searches, "usage": usage}
    paths = write_outputs(job, md, ev, searches, conn, focus, time.time() - t0)
    em.event(type="milestone", text="review written: review.md, review.html (%d standards searches, %d s)" % (len(searches), int(time.time() - t0)))
    em.log(">> review: " + paths["md"])
    return {"ok": True, "review_md": md, "paths": paths, "searches": searches, "usage": usage}


# ---------------------------------------------------------------- MOCK: the review from the evidence alone
def _pct(x, n=2):
    return "%.*f%%" % (n, 100 * x) if isinstance(x, (int, float)) else "not in the run"


def _f(x, n=2):
    return ("%.*f" % (n, x)) if isinstance(x, (int, float)) else "not in the run"


_DOC_TITLE = {"IS1893": "IS 1893 (Part 1):2016", "IS800": "IS 800:2007", "IS18168": "IS 18168:2023", "IS2062": "IS 2062 (Part 1):2025"}


def _ref_clause(ev: dict) -> tuple:
    """(document key, clause, words) of the IS joint-rotation reference for this system, from the evidence."""
    nl = ev.get("nlrha") or {}
    refs = []
    for lv in (nl.get("levels") or {}).values():
        refs = ((lv or {}).get("reference_rotation") or {}).get("refs") or refs
    refs = refs or ((ev.get("pushover") or {}).get("reference_rotation") or {}).get("refs") or []
    for r in refs:
        m = re.search(r"(IS\s*18168|IS\s*800)[^0-9]*(?:\d{4}\s+)?(\d+(?:\.\d+)+)", str(r.get("clause") or ""))
        if m:
            return ("IS18168" if "18168" in m.group(1) else "IS800"), m.group(2), str(r.get("what") or "joint rotation")
    return "IS800", "12.11.1", "joint rotation"


def mock_review(ev: dict, focus: str = "", search=None) -> str:
    """A deterministic review from the evidence (model MOCK). The searches still run, so the offline
    pipeline exercises the standards server the way a real run does. India: response quantities and IS
    reference values only, no verdict (D7)."""
    nl, po, dd, de = ev.get("nlrha") or {}, ev.get("pushover") or {}, ev.get("ddm") or {}, ev.get("design") or {}
    rdoc, rcl, rwhat = _ref_clause(ev)
    asks = (("7.11.1.1", {"query": "storey drift shall not exceed 0.004 times the storey height", "document": "IS1893", "clause": "7.11.1.1"}),
            ("7.7.4", {"query": "time history method ground motion compatible with the design acceleration spectrum", "document": "IS1893", "clause": "7.7.4"}),
            (rcl, {"query": "inelastic deformation corresponding to a joint rotation radians", "document": rdoc, "clause": rcl}))
    cite = {}
    for key, args in asks:
        title = _DOC_TITLE.get(args["document"], args["document"])
        if search:
            txt = search(args)
            m = re.search(r"\[1\] (\S+) (\S+)(?: p\. (\S+))?", txt)
            grounded = "NO PASSAGES" not in txt and "CORPUS GAP" not in txt and "(answered by: any-document" not in txt
            cite[key] = ("[%s cl. %s%s]" % (title, key, (", p. " + m.group(3)) if m and m.group(3) else "")) if grounded else "[%s cl. %s] (UNVERIFIED)" % (title, key)
        else:
            cite[key] = "[%s cl. %s] (UNVERIFIED)" % (title, key)
    levels = nl.get("levels") or {}
    lines = ["# Review of %s — nonlinear analyses (model MOCK)" % ev.get("job"), ""]
    if focus.strip():
        lines += ["**Focus asked:** " + focus.strip(), ""]
    lines += ["## 1. Summary", "", IS_NL_STATEMENT]
    for lv, d in levels.items():
        bs = d.get("base_shear") or {}
        lines.append("NLRHA %s (%s): %s of %s records converged; suite mean storey drift up to %s%% of h, peak %s%%; mean base shear %s × VB."
                     % (lv, d.get("target_label") or "", d.get("n_converged"), d.get("n_records"), _f(d.get("max_mean_drift_pct"), 3),
                        _f(d.get("max_peak_drift_pct"), 3), _f(bs.get("mean_over_VB"))))
    if not levels:
        lines.append("NLRHA: not in the run.")
    for k, x in (po.get("directions") or {}).items():
        cap = x.get("capacity") or {}
        lines.append("Pushover %s: Vmax %s kN = %s × VB; stop: %s." % (k, _f(cap.get("Vmax_kN"), 0), _f(cap.get("Vmax_over_VB")), x.get("stop_reason")))
    if dd.get("runs"):
        lams = [r for r in dd["runs"] if isinstance(r.get("lambda_u"), (int, float))]
        gov = min(lams, key=lambda r: r["lambda_u"]) if lams else None
        lines.append("DDM: %s runs; lowest λu %s (%s); IS 800 B-1.2 check %s." % (len(dd["runs"]), _f((gov or {}).get("lambda_u"), 3),
                     (gov or {}).get("label") or "no limit point", "satisfied" if (dd.get("b12_check") or {}).get("ok") else "not satisfied / not run"))
    lines += ["", "## 2. What the run measured", ""]
    s = de.get("seismic") or {}
    lines.append("- Linear design: zone %s, Z = %s, I = %s, R = %s, soil %s; VB = %s kN, W = %s kN; governing member D/C %s."
                 % (s.get("zone"), s.get("Z"), s.get("I"), s.get("R"), s.get("soil"), _f(s.get("VB_kN"), 1), _f(s.get("W_kN"), 1),
                    _f((de.get("worst_members") or [{}])[0].get("DC"))))
    for lv, d in levels.items():
        for r in d.get("story") or []:
            lines.append("- %s storey %s: mean drift X %s%% / Y %s%%, record max X %s%% / Y %s%%." % (
                lv, r.get("story"), _f(r.get("mean_X_pct"), 3), _f(r.get("mean_Y_pct"), 3), _f(r.get("max_X_pct"), 3), _f(r.get("max_Y_pct"), 3)))
    lines += ["", "## 3. Response-history results (DBE and MCE)", ""]
    for lv, d in levels.items():
        lines.append("- %s: suite mean storey drift up to %s%% of h. For comparison only, IS 1893 limits the drift of the LINEAR analysis under VB to 0.004 h (0.40%%) %s; it is not a nonlinear acceptance criterion."
                     % (lv, _f(d.get("max_mean_drift_pct"), 3), cite["7.11.1.1"]))
        mg = (d.get("member_groups_worst") or [None])[0]
        if mg:
            lines.append("- %s: largest member chord rotation %s rad (%s %s), %s × the IS reference %s of %s rad %s (reference only)."
                         % (lv, _f(mg.get("chord_rot_max_rad"), 5), mg.get("kind"), mg.get("section"), _f(mg.get("ratio_to_reference"), 3), rwhat,
                            _f(((d.get("reference_rotation") or {}).get("value")), 2), cite[rcl]))
        bad = [r.get("label") for r in d.get("records") or [] if r.get("converged") is False]
        if bad:
            lines.append("- %s: records not converged: %s." % (lv, ", ".join(str(b) for b in bad)))
    if levels:
        lines.append("- Ground motions scaled to the IS 1893 elastic target, preferably compatible with the design spectrum %s." % cite["7.7.4"])
    else:
        lines.append("Not in the run.")
    lines += ["", "## 4. Pushover", ""]
    for k, x in (po.get("directions") or {}).items():
        t = x.get("tail") or {}
        for lvl, n in (x.get("nsp") or {}).items():
            lines.append("- %s %s: Te %s s, Sa %s g (elastic, no R), target %s mm, reached %s." % (k, lvl, _f(n.get("Te"), 3), _f(n.get("Sa"), 3),
                                                                                              _f(n.get("target_disp_mm"), 1), n.get("reached_target")))
        lines.append("- %s: T1 %s s; descending branch %s." % (k, _f(x.get("T1"), 3), t.get("status")))
    if not po:
        lines.append("Not in the run.")
    lines += ["", "## 5. DDM system capacity", ""]
    for r in (dd.get("runs") or [])[:12]:
        lines.append("- %s: %s, λu %s%s." % (r.get("label"), r.get("status"), _f(r.get("lambda_u"), 3), ("; " + r["mechanism"]) if r.get("mechanism") else ""))
    if not dd:
        lines.append("Not in the run.")
    lines += ["", "## 6. Design basis and the design criteria draft", ""]
    lines.append("- Linear basis: %s." % (", ".join("%s = %s" % kv for kv in s.items() if kv[1] is not None) or "not in the run"))
    lines.append("- Design-criteria draft %s." % ("present" if ev.get("design_criteria_draft") else "not in the run"))
    lines += ["", "## 7. What to change, and why", ""]
    lines.append("The analyses give response quantities, not a verdict (IS 1893 provides no nonlinear acceptance criteria). Where a member group's "
                 "chord rotation is far below the IS 800 Section 12 reference, a resize loop in the Feedback tab quantifies a lighter design; "
                 "where it approaches it, the engineer of record decides whether to stiffen or strengthen that group.")
    lines += ["", "## 8. Open items and verification", ""]
    if po and not po.get("params_verified"):
        lines.append("- Hinge backbones (pushover and NLRHA) are modelling assumptions — information / EOR inputs; IS 800 and IS 1893 tabulate none. They are not acceptance criteria.")
    for x in ((ev.get("complete_gate") or {}).get("disclosures") or []):
        if x and x.get("found") is False:
            lines.append("- Disclosed found:false — %s." % (x.get("id") or x.get("note")))
    for lv, d in levels.items():
        for r in d.get("records") or []:
            if r.get("retry"):
                lines.append("- %s record %s was re-run at a finer step (%s)." % (lv, r.get("label"), "converged" if r.get("converged") else "still non-converged"))
    lines.append("- This review was written offline (model MOCK) from the evidence; clauses marked UNVERIFIED were not read from the corpus.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- outputs
_CSS = """body{font:15px/1.5 -apple-system,'Segoe UI',system-ui,sans-serif;color:#1d1d1b;max-width:900px;margin:32px auto;padding:0 20px;background:#fbfaf7}
h1{font-size:24px;border-bottom:2px solid #7b93e8;padding-bottom:6px}h2{font-size:18px;margin-top:28px;color:#1a3d7c}
code{background:#f1ede6;padding:1px 4px;border-radius:3px;font-size:13px}pre{background:#f1ede6;padding:10px;overflow:auto}
table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #d9d2c6;padding:4px 8px;font-size:13.5px}th{background:#f1ede6}
.meta{color:#6b655c;font-size:12.5px;margin-bottom:18px}.disc{margin-top:36px;padding:10px 12px;border:1px solid #e0b341;background:#fff8e6;font-size:12.5px}
.src{font-size:12px;color:#6b655c}"""


def _md_to_html(md: str) -> str:
    """Enough Markdown for a review: headings, lists, bold/italic/code, paragraphs, pipe tables."""
    out, para, inlist, intable = [], [], False, False

    def inline(t):
        t = html.escape(t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
        return t

    def flush():
        nonlocal para, inlist, intable
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>"); para = []
        if inlist:
            out.append("</ul>"); inlist = False
        if intable:
            out.append("</table>"); intable = False
    for line in md.splitlines():
        s = line.rstrip()
        if not s.strip():
            flush(); continue
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            flush(); out.append("<h%d>%s</h%d>" % (len(m.group(1)), inline(m.group(2)), len(m.group(1)))); continue
        if s.lstrip().startswith("|"):
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            if not intable:
                if para or inlist:
                    flush()
                out.append("<table>"); intable = True
                out.append("<tr>" + "".join("<th>%s</th>" % inline(c) for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in cells) + "</tr>")
            continue
        m = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.*)", s)
        if m:
            if intable or para:
                flush()
            if not inlist:
                out.append("<ul>"); inlist = True
            out.append("<li>" + inline(m.group(1)) + "</li>"); continue
        if inlist or intable:
            flush()
        para.append(s.strip())
    flush()
    return "\n".join(out)


def write_outputs(job: str, md: str, ev: dict, searches: list, conn: dict, focus: str, seconds: float) -> dict:
    md_path = os.path.join(job, "review.md")
    open(md_path, "w", encoding="utf-8").write(md if md.endswith("\n") else md + "\n")
    date = datetime.date.today().isoformat()
    model = "MOCK (offline)" if conn.get("mock") else conn.get("model")
    doc = ("<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>Review — %s</title><style>%s</style></head><body>"
           "<div class=\"meta\">steltic_nonlinear_india · Review of <b>%s</b> · %s · model %s · %d standards searches · %d s</div>%s"
           "<div class=\"disc\">Written by a language model from the run's measured results (see review_transcript.json for the evidence and every passage it read). "
           "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information. "
           "Not for construction. Every statement requires review by the engineer of record; a clause marked UNVERIFIED was cited from the model's memory, not from the IS corpus.</div>"
           "<p class=\"src\">Files: review.md · review_transcript.json · four_analyses.html · nlrha/nlrha_report.html (DBE / MCE) · pushover/pushover_report.html · ddm_report.html · design_criteria_16_1_4.html</p>"
           "</body></html>") % (html.escape(ev.get("job") or ""), _CSS, html.escape(ev.get("job") or ""), date, html.escape(str(model)), len(searches), int(seconds), _md_to_html(md))
    html_path = os.path.join(job, "review.html")
    open(html_path, "w", encoding="utf-8").write(doc)
    tr_path = os.path.join(job, "review_transcript.json")
    json.dump({"job": ev.get("job"), "date": date, "model": model, "focus": focus, "seconds": round(seconds, 1), "searches": searches, "evidence": ev},
              open(tr_path, "w", encoding="utf-8"), indent=1, default=str)
    return {"md": md_path, "html": html_path, "transcript": tr_path}


# ---------------------------------------------------------------- CLI
def cmd_review(a) -> int:
    em = Emitter()
    r = run(a.job, focus=a.focus or "", use_standards=not a.no_standards, max_searches=a.max_searches, emit=em)
    return 0 if r["ok"] else 1
