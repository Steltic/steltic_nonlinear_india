"""collect.py -- read the IS specification values out of the IS corpus, BEFORE the analyses run (India).

    python -m snl collect <job folder> [--out hinge_params_collected.json]

India fork (owner rulings D3 / D6 / D7). The US step reads hinge backbones and acceptance criteria out of
AISC 342 / ASCE 41 / AISC 341. India has no foreign design basis and no NL acceptance criteria: IS 800:2007,
IS 1893 (Part 1):2016 and IS 18168:2023 tabulate no hinge backbone, and "IS 1893 (Part 1):2016 provides no
acceptance criteria for nonlinear analysis; results are for information". So what an India NL run
legitimately takes from the standards -- and what this step reads, checks and cites -- is:

  material              IS 2062 (Part 1):2025 Table 3: fu (Rm) and fy (ReH by thickness band) for the grade
  overstrength          IS 18168:2023 Table 1: Ry / Ru for the grade (reference -- capacity design; the NL
                        expected-strength factor stays an EOR input, nl_plan.material.expected_strength_factor)
  deformation_capacity  IS 800:2007 Section 12: the joint-rotation capacity of the system (0.02 / 0.04 rad) --
                        REFERENCE ONLY, never an acceptance limit
  spectrum              IS 1893 (Part 1):2016 Table 3 Z for the zone, 6.4.2 Sa/g for the soil type, Table 8 I
                        (the NL targets are DBE = (Z/2)·I·Sa/g and MCE = Z·I·Sa/g, never divided by R -- D6)
  damping               IS 1893 (Part 1):2016 7.2.4 (5 % of critical; the NL model's damping is a modelling input)

The hinge backbone groups of the parameter file (beam_flexure, column_flexure, brace_axial) are NOT collected:
they are modelling assumptions -- information / EOR inputs, never acceptance criteria -- and are labelled so
in the file (`india_status`). `verified` stays false for them; `spec_values_collected` says the IS values are in.

The machinery is the US third cut, unchanged in substance:
  * RETRIEVAL IS DETERMINISTIC. Collect knows which IS table / clause each group is read from (plan_for) and
    fetches it from the IS corpus itself, as exact lookups. No model chooses what to search.
  * THE ROW IS DECIDED FROM THE BUILDING. The grade from nl_plan / the package, the zone and soil type from
    seismic_calc.json / load_plan.json, the IS 800 clause from the system (row_for). No model chooses the row.
  * THE MODEL ONLY TRANSCRIBES. Per group, one short call with the passages and the named fields; it answers
    {value, quote} per field, reasoning effort LOW. Every quote must occur verbatim in the passages and every
    number in a value must be among the digits of its quote (check_field). Up to two retries naming exactly
    what was rejected; then the group is missing. No tools, no searching, no loop.
  * THE SOURCE IS BUILT BY THE PROGRAM from the passages' own document / section / page.
  * The same search more than REPEAT_LIMIT times is refused without a round trip (three strikes).

Every group is then validated (shape, ranges, ordering, a source naming a table / clause and a page, and a
cross-check against the IS constants the India engines use -- pushover/india_materials.py, nlrha/india_hazard.py)
and `hinge_params_collected.json` is written only when every needed group passed; otherwise
`hinge_params_collected.partial.json`, the missing fields named, and the hub's Run analyses stays closed.
collect_transcript.jsonl holds every prompt, answer and reasoning as it streams. Model MOCK (tests) takes the
values from the repository's IS constants instead of a provider, labelled as such.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import re
import sys
import time

from . import llm, rag
from .review import Emitter, _tool_title

OUT_NAME = "hinge_params_collected.json"
PARTIAL_NAME = "hinge_params_collected.partial.json"
EVIDENCE_NAME = "collect_evidence.json"
TRANSCRIPT_NAME = "collect_transcript.jsonl"    # every prompt, answer and reasoning, as it streams
MAX_TURNS = 80                     # a safety ceiling on the agent loop, not a search budget
MAX_SEARCHES = 60                  # a backstop against a runaway: the guard below is what actually stops one
REPEAT_LIMIT = 3                   # the same search this many times without moving on = the corpus does not hold it

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE = os.path.join(os.path.dirname(_HERE), "pushover", "hinge_params.json")

IS_NL_STATEMENT = ("IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; "
                   "results are for information.")
HINGE_STATUS = ("modelling assumption -- information / EOR input. IS 800:2007, IS 1893 (Part 1):2016 and "
                "IS 18168:2023 tabulate no hinge backbone (nlrha.india_authority.hinge_analogue_status: found:false); "
                "this is not an acceptance criterion.")
HINGE_GROUPS = ("beam_flexure", "column_flexure", "brace_axial")

# The groups a file can carry. `material`, `spectrum` and `damping` are always needed; `overstrength` when
# IS 18168 Table 1 lists the grade; `deformation_capacity` when IS 800 Section 12 names the system.
GROUP_ORDER = ("material", "overstrength", "deformation_capacity", "spectrum", "damping")
IS18168_GRADES = ("E250", "E275", "E300", "E350")
MPA_TO_KSI = 0.1450377


# ---------------------------------------------------------------- the building
def _json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                            # noqa: BLE001
        return default


def _grade(job: str, plan: dict, calc: dict) -> tuple[str, str]:
    """(grade, basis): nl_plan.material.grade, else the IS 2062 grade the package's member checks cite, else E250."""
    g = ((plan or {}).get("material") or {}).get("grade")
    if g:
        return str(g), "nl_plan.material.grade"
    seen: dict = {}
    for m in (calc or {}).get("members") or []:
        for mm in re.finditer(r"IS\s*2062\s*(E\s?\d{3})", str(m.get("cited") or "")):
            k = mm.group(1).replace(" ", "")
            seen[k] = seen.get(k, 0) + 1
    if seen:
        return max(seen, key=seen.get), "design/calc_package.json member citations (IS 2062 grade)"
    return "E250", "default E250 (neither nl_plan.material.grade nor the package names a grade)"


def _soil_roman(soil) -> str:
    try:
        from nlrha import india_hazard as IH
        return IH.normalize_soil(soil)
    except Exception:                                            # noqa: BLE001
        s = str(soil or "").upper()
        return "III" if "III" in s or "SOFT" in s else "I" if re.search(r"\bI\b|ROCK|HARD", s) else "II"


def gather(job: str) -> dict:
    """What the step is told about the building, read from the HR package -- nothing invented."""
    job = os.path.abspath(job)
    calc = _json(os.path.join(job, "design", "calc_package.json"))
    if not isinstance(calc, dict):
        raise FileNotFoundError("design/calc_package.json")
    plan = _json(os.path.join(job, "nl_plan.json"), {}) or {}
    try:
        from nlrha import india_hazard as IH
        ind = IH.inputs_from_package(job)
    except Exception:                                            # noqa: BLE001
        ind = {}
    lp = (_json(os.path.join(job, "load_plan.json"), {}) or {}).get("seismic_summary") or {}
    system = str(lp.get("system") or calc.get("system") or "")
    grade, grade_basis = _grade(job, plan, calc)
    try:
        from pushover import india_materials as IM
        grade = IM.normalize_grade(grade)
        ref = IM.reference_rotation(system)
    except Exception:                                            # noqa: BLE001
        ref = {"refs": []}
    kinds = sorted({str((m.get("inputs") or {}).get("kind") or "").lower() for m in calc.get("members") or []} - {""})
    needed = ["material"]
    if grade in IS18168_GRADES:
        needed.append("overstrength")
    if ref.get("refs"):
        needed.append("deformation_capacity")
    needed += ["spectrum", "damping"]
    zone = ind.get("zone") or lp.get("zone")
    return {"job": job, "name": calc.get("building") or os.path.basename(job), "jurisdiction": "india",
            "system": system, "grade": grade, "grade_basis": grade_basis,
            "zone": str(zone).upper() if zone else None, "Z": ind.get("Z", lp.get("Z")), "I": ind.get("I", lp.get("I")),
            "R": ind.get("R", lp.get("R")), "soil": _soil_roman(ind.get("soil") or lp.get("soil")),
            "reference_rotation": ref, "member_kinds": kinds,
            "expected_strength_factor": ((plan.get("material") or {}).get("expected_strength_factor")),
            "needed": needed}


# ---------------------------------------------------------------- what is read from where
# The IS tables / clauses each group is read from. Collect fetches these itself, before any model is involved;
# the model only transcribes what came back. (document key, lookup type, id, context neighbours)
PLAN = {
    "material":     [("IS2062", "exact_table", "Table 3", 1)],
    "overstrength": [("IS18168", "exact_table", "Table 1", 1)],
    "spectrum":     [("IS1893", "exact_table", "Table 3", 1), ("IS1893", "exact_section", "6.4.2", 1),
                     ("IS1893", "exact_table", "Table 8", 1)],
    "damping":      [("IS1893", "exact_section", "7.2.4", 0)],
}


def _ref_row(facts: dict) -> tuple[str, str, dict]:
    """(document key, clause, row) of the system's joint-rotation reference (IS 800 Section 12; EBF: IS 18168)."""
    for r in (facts.get("reference_rotation") or {}).get("refs") or []:
        m = re.search(r"(IS\s*18168|IS\s*800)\S*\s+(\d+(?:\.\d+)+)", str(r.get("clause") or ""))
        if m:
            return ("IS18168" if "18168" in m.group(1) else "IS800"), m.group(2), r
    return "", "", {}


def plan_for(gid: str, facts: dict) -> list:
    if gid == "deformation_capacity":
        doc, clause, _r = _ref_row(facts)
        return [(doc, "exact_section", clause, 0)] if clause else []
    return PLAN.get(gid, [])


def prefetch(facts: dict, search) -> dict:
    """The passages for every needed group, up front. -> {group: [{"source","section","page","text"}, ...]}"""
    out: dict = {g: [] for g in facts["needed"]}
    for gid in facts["needed"]:
        for doc, how, q, nb in plan_for(gid, facts):
            res = search({"document": doc, "type": how, "query": q, "context_neighbors": nb, "top_k": 8,
                          "purpose": "IS values for %s" % gid}, raw=True)
            for h in (res.get("results") or [])[:6]:
                out[gid].append({"document": doc, "how": "%s %s" % (how, q), "source": h.get("source") or doc,
                                 "section": h.get("section") or "", "page": h.get("page") or "",
                                 "text": (h.get("text") or "")[:rag.EXACT_MAX_CHARS]})
    return out


def _quality_note(grade: str) -> str:
    return "the Rm and ReH values are the same for every quality (A, BR, B0, C) of a grade; read the first row of %s" % grade


# The fields each group is transcribed into: (field, what to read, kind). kind: number.
def fields_for(gid: str, facts: dict) -> list:
    g = facts.get("grade") or "E250"
    gs = g[0] + " " + g[1:]                      # the table prints "E 250"
    if gid == "material":
        return [("fu_MPa", "Table 3, the row of grade '%s': Tensile Strength Rm, Min, MPa (column 4)" % gs, "number"),
                ("fy_t16_MPa", "same row: Yield Stress ReH, Min, MPa, thickness <= 16 mm (column 5)", "number"),
                ("fy_t40_MPa", "same row: ReH, thickness > 16 to 40 mm (column 6)", "number"),
                ("fy_t100_MPa", "same row: ReH, thickness > 40 to 100 mm (column 7)", "number"),
                ("fy_tgt100_MPa", "same row: ReH, thickness > 100 mm (column 8); null with quote of the cell if it is '-'", "number")]
    if gid == "overstrength":
        return [("Ry", "Table 1, the row '%s (B0 or C)': Material Strength Uncertainty Factor Ry (column 3)" % g, "number"),
                ("Ru", "same row: Material Strength Uncertainty Factor Ru (column 4)", "number")]
    if gid == "deformation_capacity":
        _d, clause, r = _ref_row(facts)
        return [("rotation_rad", "clause %s: the %s, in radians, the frame should be shown to withstand ('0.04 radians' -> 0.04)"
                 % (clause, r.get("what") or "joint rotation"), "number")]
    if gid == "spectrum":
        soil = facts.get("soil") or "II"
        name = {"I": "Rocky or hard soil sites (Type I)", "II": "Medium stiff soil sites (Type II)", "III": "Soft soil sites (Type III)"}[soil]
        return [("Z", "Table 3 Seismic Zone Factor: Z in the column of zone %s" % (facts.get("zone") or "?"), "number"),
                ("Sa_plateau", "6.4.2 b) (response spectrum method), '%s': the constant Sa/g of the plateau" % name, "number"),
                ("Tc_s", "same soil, 6.4.2 b): the period in seconds where the plateau ends and Sa/g = c/T begins", "number"),
                ("Sa_c", "same soil, 6.4.2 b): the coefficient c of Sa/g = c/T ('1.36/T' -> 1.36)", "number"),
                ("Sa_floor", "same soil, 6.4.2 b): the constant Sa/g for T > 4.00 s", "number"),
                ("I_row_i", "Table 8 Importance Factor: I of row i) (important service and community buildings ...)", "number"),
                ("I_row_ii", "Table 8: I of row ii) (residential or commercial buildings with occupancy more than 200 persons)", "number"),
                ("I_row_iii", "Table 8: I of row iii) (all other buildings)", "number")]
    if gid == "damping":
        return [("damping_percent", "7.2.4 Damping Ratio: the value of damping, in percent of critical damping", "number")]
    return []


OPTIONAL = {"material": {"fy_tgt100_MPa"}}          # a '-' cell in IS 2062 Table 3 (E550 and up, t > 100 mm)


def row_for(gid: str, facts: dict) -> tuple[str, str]:
    """(variant, the row the model transcribes), decided from the building -- not by the model."""
    g = facts.get("grade") or "E250"
    if gid == "material":
        return "material", "IS 2062 (Part 1):2025 Table 3 'Mechanical Properties', grade %s (%s): Rm and ReH by thickness -- %s" % (
            g, facts.get("grade_basis") or "", _quality_note(g))
    if gid == "overstrength":
        return "overstrength", "IS 18168:2023 Table 1 'Material Strength Uncertainty Factors Ry and Ru', the row '%s (B0 or C)'" % g
    if gid == "deformation_capacity":
        doc, clause, r = _ref_row(facts)
        return "deformation_capacity", "%s %s: %s for the system '%s' (REFERENCE ONLY -- not an acceptance limit)" % (
            rag.TITLES.get(doc, doc), clause, r.get("what") or "joint rotation", facts.get("system") or "")
    if gid == "spectrum":
        return "spectrum", "IS 1893 (Part 1):2016 Table 3 (zone %s), 6.4.2 b) response spectrum method (soil type %s), Table 8 (importance factor rows)" % (
            facts.get("zone") or "?", facts.get("soil") or "?")
    if gid == "damping":
        return "damping", "IS 1893 (Part 1):2016 7.2.4 Damping Ratio"
    return gid, gid


# ---------------------------------------------------------------- transcription (the only thing the model does)
TRANSCRIBE = """You are transcribing values from PASSAGES of a converted Indian Standard (BIS) into named fields. This is copying, not engineering judgement, and nothing you remember about the standard counts.

For every field answer {"value": ..., "quote": "..."} where `quote` is the VERBATIM text from the passages the value was read from -- copy it exactly, converter artefacts included (a table row as it stands, e.g. "| ii)       | E 250               | A         | 410 ..."). The program that reads your answer rejects any value whose quote does not occur in the passages, and any number in a value that does not appear among the digits of its quote. A value you cannot quote: {"value": null, "quote": null, "why": "what is missing"}.

How the converted text reads:
- Tables are Markdown rows: "| (1) | (2) | ... |" gives the column numbers; the header rows above name them. Read the column the field names, in the row the TABLE AND ROW line names, and quote that row.
- A cell "-" or "--" means no value is specified: answer null for that field, quoting the row.
- Where a clause states a value in words ("0.04 radians", "5 percent of critical damping"), the value is the number and the quote is the sentence.
- Where a table appears twice (a base page and an amended restatement), both copies say the same; quote either.

Reply with ONE JSON object -- field name -> {"value", "quote"} -- and nothing else."""


def _ask_message(gid: str, variant: str, row: str, fields: list, passages: list, retry_note: str = "") -> str:
    lines = ["GROUP: %s" % gid, "TABLE AND ROW: %s" % row, "", "FIELDS (name: what to read):"]
    for f, what, kind in fields:
        lines.append("  %s: %s" % (f, what))
    lines += ["", "PASSAGES:"]
    for p in passages:
        lines.append("[%s %s p. %s]" % (p["source"], p["section"], p["page"]))
        lines.append(p["text"])
        lines.append("")
    if retry_note:
        lines += ["YOUR LAST ANSWER WAS NOT ACCEPTED -- these fields again:", retry_note, ""]
    lines.append("Transcribe the fields now. JSON only.")
    return "\n".join(lines)


_NUM = re.compile(r"\d+(?:\.\d+)?")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def _digit_groups(s: str) -> set:
    """Every number-like token in a quote, as bare digits: '0 . 5 5' -> '055', '0 07' -> '007', '5 5' -> '55'."""
    t = re.sub(r"[^0-9.\s]", " ", s or "")
    groups = set()
    for tok in re.findall(r"[0-9][0-9.\s]*", t):
        d = re.sub(r"[^0-9]", "", tok)
        if d:
            groups.add(d)
            parts = tok.split()
            for i in range(len(parts)):
                acc = ""
                for j in range(i, min(len(parts), i + 4)):
                    acc += re.sub(r"[^0-9]", "", parts[j])
                    if acc:
                        groups.add(acc)
    return groups


def _numbers_in(value) -> list:
    return [re.sub(r"[^0-9]", "", n) for n in _NUM.findall(str(value))]


def check_field(kind: str, value, quote: str, passages_norm: str) -> str:
    """'' when the value is backed by the quote and the quote by the passages; else the reason."""
    if value is None:
        return "not read"
    if not quote or not isinstance(quote, str):
        return "no quote"
    if _norm(quote) not in passages_norm:
        return "the quote does not occur in the passages"
    if kind == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        return "must be a number"
    groups = _digit_groups(quote)
    for d in _numbers_in(value):
        if d and d.lstrip("0") and d not in groups and d.lstrip("0") not in {g.lstrip("0") for g in groups}:
            return "the number %s is not in the quote" % d
    return ""


def transcribe(gid: str, facts: dict, passages: list, conn: dict, em, trace) -> tuple[dict, dict]:
    """One group. -> (fields {name: value}, problems {name: why}). At most 3 model calls, no tools."""
    variant, row = row_for(gid, facts)
    fields = fields_for(gid, facts)
    optional = OPTIONAL.get(gid, set())
    if not passages:
        return {}, {f: "no passage was returned for this table / clause (%s)" % ", ".join("%s %s" % (d, q) for d, h, q, n in plan_for(gid, facts))
                    for f, _w, _k in fields if f not in optional}
    passages_norm = _norm("\n".join(p["text"] for p in passages))
    got: dict = {}
    probs: dict = {}
    retry_note = ""
    # transcription is copying: a reasoning model at "high" deliberates for pages over it
    tconn = dict(conn, reasoning="low", max_tokens=min(int(conn.get("max_tokens") or 4000), 6000))
    for attempt in range(3):
        msg = _ask_message(gid, variant, row, fields, passages, retry_note)
        trace({"type": "prompt", "group": gid, "attempt": attempt + 1, "chars": len(msg)})
        messages = [{"role": "system", "content": TRANSCRIBE}, {"role": "user", "content": msg}]

        def on_piece(kind, text):
            em.event(type=kind, text=text)
        out = llm.chat_with_retry(tconn, messages, None, on_piece)
        if out.get("usage"):
            em.usage(out["usage"])
        trace({"type": "answer", "group": gid, "attempt": attempt + 1, "reasoning": out.get("reasoning", "")[:20000],
               "content": (out.get("content") or "")[:20000]})
        ans = _parse_json(out.get("content") or "")
        if not isinstance(ans, dict):
            retry_note = "your reply was not a JSON object"
            continue
        probs = {}
        rejected = {}                       # the model quoted something and the check refused it
        for f, what, kind in fields:
            a = ans.get(f)
            if not isinstance(a, dict):
                if f not in optional:
                    probs[f] = "missing from the reply"
                    rejected[f] = probs[f]
                continue
            why = check_field(kind, a.get("value"), a.get("quote"), passages_norm)
            if why == "not read" and f in optional:
                continue                                         # a '-' cell: no value is specified
            if why:
                probs[f] = why + ((" -- " + str(a.get("why"))) if a.get("why") else "")
                if why != "not read":
                    rejected[f] = probs[f]
            else:
                got[f] = a["value"]
                got.setdefault("_quotes", {})[f] = a.get("quote")
        if not probs:
            break
        if not rejected and attempt >= 1:
            break                           # asked twice, both times "not in the passages": it is not
        if rejected:
            retry_note = "\n".join("  %s: %s" % (f, w) for f, w in rejected.items()) + \
                "\n(copy the quote EXACTLY from the passage; a number that is not in the quote cannot be used)"
        else:
            # every remaining field was reported absent: one more look, with the size of what was handed
            # over, in case the row sits further down the table than the first reading went
            retry_note = "\n".join("  %s: %s" % (f, w) for f, w in probs.items()) + \
                "\n(the passages above run %d characters; the rows of a long table (IS 2062 Table 3 runs past 30,000 characters, printed twice) come far below its header -- read to the end before answering that a cell is absent)" % sum(len(p["text"]) for p in passages)
    return got, probs


def _source(gid: str, facts: dict, passages: list) -> str:
    variant, row = row_for(gid, facts)
    pages = sorted({str(p["page"]) for p in passages if p.get("page") not in (None, "")}, key=lambda x: (len(x), x))
    ids = []
    for doc, how, q, nb in plan_for(gid, facts):
        ids.append("%s %s%s" % (rag.TITLES.get(doc, doc), "" if q.startswith("Table") else "cl. ", q))
    span = "-".join(pages[:1] + pages[-1:]) if len(pages) > 1 else (pages[0] if pages else "?")
    return "%s, p. %s" % ("; ".join(ids), span)


def assemble(gid: str, facts: dict, got: dict, passages: list) -> dict:
    """The group as the file carries it: the transcribed values, the quotes, a source built from the passages'
    own document / section / page (not from the model), and what the value is for on this fork."""
    variant, row = row_for(gid, facts)
    quotes = got.pop("_quotes", {})
    g = dict(got)
    docs = sorted({p["source"] for p in passages if p.get("source")})
    g["source"] = _source(gid, facts, passages)
    g["quotes"] = quotes
    g["basis"] = row + " -- transcribed by `snl collect` from the converted %s; every value carries the cell it was read from in `quotes`." % ", ".join(docs)
    if gid == "material":
        g["grade"] = facts.get("grade")
        g["grade_basis"] = facts.get("grade_basis")
    elif gid == "overstrength":
        g["use"] = ("reference: IS 18168 Ry / Ru are capacity-design factors. The NL expected-strength factor is an EOR "
                    "input (nl_plan.material.expected_strength_factor, default 1.0 = nominal), not taken from here.")
    elif gid == "deformation_capacity":
        _d, clause, r = _ref_row(facts)
        g.update(clause=clause, what=r.get("what"), system=facts.get("system"),
                 use="REFERENCE ONLY (D7): reported beside the measured chord rotations; not an acceptance limit.")
    elif gid == "spectrum":
        g.update(zone=facts.get("zone"), soil=facts.get("soil"), I_package=facts.get("I"),
                 use="NL targets: DBE = (Z/2)·I·Sa/g, MCE = Z·I·Sa/g, never divided by R (D6).")
    elif gid == "damping":
        if isinstance(g.get("damping_percent"), (int, float)):
            g["damping_ratio"] = round(g["damping_percent"] / 100.0, 4)
        g["use"] = ("IS 1893 7.2.4: 5 % for estimating Ah (all methods). The NLRHA's inherent damping is a modelling "
                    "input (nlrha numerics); this value is recorded as the IS reference.")
    return g


# ---------------------------------------------------------------- validation
_ID_PAGE = re.compile(r"(Table|Tbl\.?|cl\.?|Clause|Sec(?:tion)?\.?|§)\s*[A-Z]?\d+(?:[.\-]\d+)*[a-z]?", re.I)
_PAGE = re.compile(r"\b(p\.?|pp\.?|page|pdf|printed)\s*\d+", re.I)


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _source_ok(g: dict) -> bool:
    s = str(g.get("source") or "")
    return bool(_ID_PAGE.search(s)) and bool(_PAGE.search(s))


def _ordered_desc(*vals) -> bool:
    vals = [v for v in vals if _num(v)]
    return all(a >= b for a, b in zip(vals, vals[1:]))


def validate(groups: dict, needed: list, facts: dict | None = None) -> tuple[bool, dict]:
    """-> (every needed group passed, {group: [problems]}). An empty list means the group passed.

    Besides shape and ranges, every value is checked against the IS constant the India engines use
    (pushover/india_materials.py, nlrha/india_hazard.py): the analyses run on those constants, so a value the
    corpus prints differently means one of them is wrong, and the gate stays closed until someone looks."""
    facts = facts or {}
    probs: dict = {}
    try:
        from pushover import india_materials as IM
    except Exception:                                            # noqa: BLE001
        IM = None
    try:
        from nlrha import india_hazard as IH
    except Exception:                                            # noqa: BLE001
        IH = None
    for gid in needed:
        g = groups.get(gid)
        p: list = []
        if not isinstance(g, dict):
            probs[gid] = ["group missing"]
            continue
        if not _source_ok(g):
            p.append("source must name a table / clause id AND a printed page")
        if gid == "material":
            for k in ("fu_MPa", "fy_t16_MPa", "fy_t40_MPa", "fy_t100_MPa"):
                if not (_num(g.get(k)) and 150 <= g[k] <= 1000):
                    p.append("%s outside 150-1000 MPa" % k)
            if not _ordered_desc(g.get("fy_t16_MPa"), g.get("fy_t40_MPa"), g.get("fy_t100_MPa"), g.get("fy_tgt100_MPa")):
                p.append("ReH must not rise with thickness")
            if _num(g.get("fu_MPa")) and _num(g.get("fy_t16_MPa")) and g["fu_MPa"] <= g["fy_t16_MPa"]:
                p.append("fu <= fy")
            if IM and facts.get("grade") in getattr(IM, "IS2062_TABLE3_REH", {}):
                rep = IM.IS2062_TABLE3_REH[facts["grade"]]
                for k, v in zip(("fy_t16_MPa", "fy_t40_MPa", "fy_t100_MPa", "fy_tgt100_MPa"), rep):
                    if v is not None and _num(g.get(k)) and abs(g[k] - v) > 0.5:
                        p.append("%s = %s differs from pushover/india_materials.py IS2062_TABLE3_REH %s (%s)" % (k, g[k], facts["grade"], v))
        elif gid == "overstrength":
            for k in ("Ry", "Ru"):
                if not (_num(g.get(k)) and 1.0 <= g[k] <= 2.0):
                    p.append("%s outside 1.0-2.0" % k)
            ref = (getattr(IM, "IS18168_RY", {}) or {}).get(facts.get("grade")) if IM else None
            if ref is not None and _num(g.get("Ry")) and abs(g["Ry"] - ref) > 1e-6:
                p.append("Ry = %s differs from pushover/india_materials.py IS18168_RY %s (%s)" % (g["Ry"], facts.get("grade"), ref))
        elif gid == "deformation_capacity":
            if not (_num(g.get("rotation_rad")) and 0 < g["rotation_rad"] <= 0.1):
                p.append("rotation_rad outside (0, 0.1] rad")
            ref = ((facts.get("reference_rotation") or {}).get("refs") or [{}])[0].get("value")
            if ref is not None and _num(g.get("rotation_rad")) and abs(g["rotation_rad"] - ref) > 1e-9:
                p.append("rotation_rad = %s differs from pushover/india_materials.py reference_rotation (%s)" % (g["rotation_rad"], ref))
        elif gid == "spectrum":
            if not (_num(g.get("Z")) and g["Z"] in (0.10, 0.16, 0.24, 0.36)):
                p.append("Z not one of the Table 3 values 0.10 / 0.16 / 0.24 / 0.36")
            if IH and facts.get("zone") in getattr(IH, "ZONE_FACTOR_Z", {}) and _num(g.get("Z")) and abs(g["Z"] - IH.ZONE_FACTOR_Z[facts["zone"]]) > 1e-9:
                p.append("Z = %s differs from nlrha/india_hazard.py ZONE_FACTOR_Z[%s] (%s)" % (g["Z"], facts["zone"], IH.ZONE_FACTOR_Z[facts["zone"]]))
            if _num(facts.get("Z")) and _num(g.get("Z")) and abs(g["Z"] - facts["Z"]) > 1e-9:
                p.append("Z = %s differs from the package's seismic_calc.json Z (%s)" % (g["Z"], facts["Z"]))
            for k in ("Sa_plateau", "Tc_s", "Sa_c", "Sa_floor"):
                if not (_num(g.get(k)) and g[k] > 0):
                    p.append(k)
            if all(_num(g.get(k)) for k in ("Sa_plateau", "Tc_s", "Sa_c")) and g["Tc_s"] > 0 and abs(g["Sa_c"] / g["Tc_s"] - g["Sa_plateau"]) > 0.05 * g["Sa_plateau"]:
                p.append("c / Tc = %.3f does not meet the plateau %.3f" % (g["Sa_c"] / g["Tc_s"], g["Sa_plateau"]))
            if IH and all(_num(g.get(k)) for k in ("Sa_c", "Tc_s")):
                try:
                    T = min(4.0, max(g["Tc_s"] * 1.5, 1.0))
                    rep = IH.sa_over_g(T, facts.get("soil") or "II")
                    if abs(rep - g["Sa_c"] / T) > 0.01 * rep:
                        p.append("Sa/g(%.2f s) = %.3f from the corpus differs from nlrha/india_hazard.sa_over_g (%.3f)" % (T, g["Sa_c"] / T, rep))
                except Exception:                                # noqa: BLE001
                    pass
            rows = [g.get(k) for k in ("I_row_i", "I_row_ii", "I_row_iii")]
            if not all(_num(x) and 1.0 <= x <= 2.0 for x in rows):
                p.append("Table 8 importance factors outside 1.0-2.0")
            elif _num(facts.get("I")) and facts["I"] not in rows and facts["I"] < min(rows):
                p.append("the package's I = %s is below every Table 8 row %s" % (facts["I"], rows))
        elif gid == "damping":
            if not (_num(g.get("damping_percent")) and 0 < g["damping_percent"] <= 20):
                p.append("damping_percent outside (0, 20]")
        probs[gid] = p
    return all(not v for v in probs.values()), probs


# ---------------------------------------------------------------- assembling the file
def _merge(template: dict, groups: dict, facts: dict, ok: bool) -> dict:
    """The template (hinge backbones, procedure constants, numerics) with the collected IS values added. The
    backbone groups keep the repository values and are labelled as modelling assumptions."""
    out = json.loads(json.dumps(template))
    for hg in HINGE_GROUPS:
        if isinstance(out.get(hg), dict):
            out[hg]["india_status"] = HINGE_STATUS
    mat = groups.get("material") or {}
    if _num(mat.get("fy_t16_MPa")):
        f = facts.get("expected_strength_factor")
        out["material"] = dict(out.get("material") or {},
                               Fy_ksi=round(mat["fy_t16_MPa"] * MPA_TO_KSI, 3),
                               Ry_expected=float(f) if f is not None else 1.0,
                               grade=facts.get("grade"), fy_MPa_t16=mat["fy_t16_MPa"], fu_MPa=mat.get("fu_MPa"),
                               source=mat.get("source"),
                               note=("IS 2062 (Part 1):2025 Table 3 ReH (t <= 16 mm) of %s, in ksi for the hinge path (the fibre path "
                                     "reads fy per section and thickness band from pushover/india_materials.py). Ry_expected is the "
                                     "EOR expected-strength factor (nl_plan.material.expected_strength_factor, default 1.0 = nominal); "
                                     "IS 18168 Ry is recorded under india_spec.overstrength as reference." % facts.get("grade")))
    out["india_spec"] = {g: groups[g] for g in GROUP_ORDER if isinstance(groups.get(g), dict)}
    out["verified"] = False                      # the hinge backbones: modelling assumptions, never read from an IS table
    out["spec_values_collected"] = bool(ok)
    return out


def _parse_json(text: str) -> dict | None:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(t[i:j + 1])
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def _readme(facts: dict, ok: bool, probs: dict, conn: dict, n_searches: int) -> list:
    when = datetime.datetime.now().isoformat(timespec="seconds")
    lines = ["RUN-SPECIFIC parameter file for %s, IS specification values collected from the IS corpus on this PC %s by `snl collect`." % (facts["name"], when),
             "Model: %s. Standards searches: %d. Retrieval log: %s. Every india_spec group's `source` names the IS table / clause and page it was read from." % (conn.get("model") or "MOCK", n_searches, EVIDENCE_NAME),
             "IS groups this building needs: %s." % ", ".join(facts["needed"])]
    if ok:
        lines.append("spec_values_collected=true: every needed IS value was read from a retrieved passage, checked against the cell it came from and against the IS constants the engines use.")
    else:
        lines.append("spec_values_collected=false: " + "; ".join("%s (%s)" % (g, ", ".join(p)) for g, p in probs.items() if p))
    lines.append("verified=false, and it stays so: the hinge backbones (beam_flexure, column_flexure, brace_axial) are modelling "
                 "assumptions -- information / EOR inputs; IS 800 / IS 1893 / IS 18168 tabulate none. They are not acceptance criteria.")
    lines.append(IS_NL_STATEMENT)
    return lines


def write_evidence(job: str, facts: dict, searches: list, probs: dict, ok: bool, conn: dict, out_path: str) -> str:
    ev = {"asked": datetime.datetime.now().isoformat(timespec="seconds"), "rag_url": rag.url(),
          "model": conn.get("model") or "MOCK", "building": facts, "needed": facts["needed"],
          "verified": ok, "spec_values_collected": ok, "problems": {g: p for g, p in probs.items() if p}, "written": out_path,
          "refused": [x for x in searches if x.get("via") == "refused"], "searches": searches}
    p = os.path.join(job, EVIDENCE_NAME)
    json.dump(ev, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    # the design-criteria document reads retrieval_log.md for its "standards consulted" section
    md = ["# Standards consulted -- IS specification values (snl collect, %s)" % ev["asked"], ""]
    for s in searches:
        a = s.get("args") or {}
        md.append("- **%s** %s `%s` -> %d passage(s)%s" % (a.get("document") or "?", a.get("type") or "", (a.get("query") or "")[:90],
                                                          s.get("hits") or 0, (" via " + s["via"]) if s.get("via") and s["via"] != "as-asked" else ""))
        for r in (s.get("results") or [])[:3]:
            md.append("    - %s %s p. %s" % (r.get("source") or "", r.get("section") or "", r.get("page") or "?"))
    open(os.path.join(job, "retrieval_log.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    return p


# ---------------------------------------------------------------- the step
def run(job: str, out_name: str = OUT_NAME, emit: Emitter | None = None, conn: dict | None = None) -> dict:
    em = emit or Emitter()
    job = os.path.abspath(job)
    conn = conn or llm.connection()
    t0 = time.time()
    em.event(type="status", text="reading the design package")
    try:
        facts = gather(job)
    except Exception as e:                                       # noqa: BLE001
        em.event(type="error", text="no design package in %s -- run HR Steel (IS 800) on this project first (%s)" % (job, e))
        return {"ok": False, "verified": False, "path": "", "missing": ["design package"], "searches": [], "usage": {}}
    template = json.load(open(_TEMPLATE, encoding="utf-8"))
    em.event(type="milestone", text="%s: %s, grade %s, zone %s, soil type %s; IS groups to collect: %s (hinge backbones: modelling assumptions, not collected)" % (
        facts["name"], facts["system"] or "system not stated", facts["grade"], facts["zone"] or "?", facts["soil"] or "?",
        ", ".join(facts["needed"])))

    searching = rag.configured()
    searches: list = []
    if searching:
        st = rag.status(force=True)
        cm = rag.corpus_map(st)
        em.event(type="milestone", text="standards corpus -- " + rag.describe_corpus(cm))
        if cm.get("known") and cm.get("absent"):
            em.log("standards corpus: %s absent on this PC -- a group whose table lives there cannot be collected"
                   % ", ".join(rag.TITLES[k] for k in cm["absent"]))
    else:
        em.event(type="error", text="no standards server (RAG_API_URL is empty): nothing can be collected -- start the IS corpus module (engineering_rag_india) from the hub's Modules page")
        return {"ok": False, "verified": False, "path": "", "missing": facts["needed"], "searches": [], "usage": {}}

    repeats: dict = {}                                       # normalised search -> times it was sent
    refused: list = []                                       # searches the guard closed, for the record

    def _key(args: dict) -> tuple:
        q = re.sub(r"[^0-9a-z./ -]", " ", (args.get("query") or "").lower())
        return ((args.get("document") or args.get("doc") or "IS1893").upper(), (args.get("type") or "").lower(),
                " ".join(q.split()), (args.get("clause") or "").upper(), (args.get("chapter") or "").upper())

    def do_search(args: dict, raw: bool = False):
        n = len(searches) + 1
        em.event(type="tool", name="search_engineering_standards", step=n, title=_tool_title(args))
        # The same search again is a loop, not a lookup. Three times is the limit: after that the corpus is
        # declared not to hold it and the search is refused without a round trip.
        k = _key(args)
        repeats[k] = repeats.get(k, 0) + 1
        if repeats[k] > REPEAT_LIMIT or len(searches) >= MAX_SEARCHES:
            why = ("ABSENT -- this exact search has been made %d times and returned the same passages each time. The "
                   "corpus does not hold what you are looking for in a form this search can find. Do NOT send it again: "
                   "put the group under \"missing\" with what you did find, and move on."
                   % (repeats[k] - 1)) if repeats[k] > REPEAT_LIMIT else \
                  ("ABSENT -- %d searches is the ceiling for this step. Write the file now with what you have; a group "
                   "you could not source goes under \"missing\"." % MAX_SEARCHES)
            refused.append({"n": n, "args": args, "why": why[:80]})
            em.event(type="tool_result", step=n, summary="refused: " + why[:90], ms=0)
            searches.append({"n": n, "args": args, "hits": 0, "note": why, "ms": 0, "via": "refused", "results": [], "passages": []})
            return {"ok": False, "results": [], "note": why, "via": "refused"} if raw else "NO PASSAGES. " + why
        res = rag.search(args.get("query") or "", args.get("document") or args.get("doc") or "IS1893",
                         int(args.get("top_k") or 5), args.get("clause") or "", args.get("chapter") or "",
                         qtype=args.get("type") or "", want_commentary=bool(args.get("want_commentary")),
                         neighbors=args.get("context_neighbors"))
        searches.append({"n": n, "args": args, "hits": len(res.get("results") or []), "note": res.get("note"),
                         "ms": res.get("ms"), "via": res.get("via"), "missing_document": res.get("missing_document"),
                         "results": [{k: h.get(k) for k in ("source", "section", "title", "page", "score")} for h in (res.get("results") or [])],
                         "passages": [h.get("text") for h in (res.get("results") or [])]})
        nres = len(res.get("results") or [])
        summ = "%d passage(s)" % nres + ((" via " + str(res["via"]).split(" (")[0]) if res.get("via") not in ("", "as-asked", None) else "")
        if repeats[k] == REPEAT_LIMIT:
            summ += " -- asked %d times now; one more and it is declared absent" % REPEAT_LIMIT
        em.event(type="tool_result", step=n, summary=summ, ms=res.get("ms") or 0)
        return res if raw else rag.render(res)

    usage: dict = {}
    # the trace, written as it happens -- a cancelled run still leaves it on disk
    trace_path = os.path.join(job, TRANSCRIPT_NAME)
    tf = open(trace_path, "w", encoding="utf-8")

    def trace(rec: dict):
        rec = dict(rec, t=time.time())
        tf.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n"); tf.flush()

    em.event(type="status", text="fetching the IS tables and clauses each group is read from")
    fetched = prefetch(facts, do_search)
    trace({"type": "prefetch", "groups": {g: [(p["how"], p["section"], p["page"], len(p["text"])) for p in ps] for g, ps in fetched.items()}})
    em.event(type="milestone", text="tables fetched -- %s" % "; ".join(
        "%s: %d passage(s)" % (g, len(ps)) for g, ps in fetched.items()))

    groups: dict = {}
    tprobs: dict = {}
    if conn.get("mock"):
        em.event(type="status", text="model MOCK: taking the values from the repository's IS constants (not transcribed)")
        groups = mock_collect(facts, fetched)
    else:
        em.event(type="status", text="asking %s to transcribe each group from its table (reasoning low, no searching)" % conn["model"])
        for gid in facts["needed"]:
            em.event(type="milestone", text="transcribing %s -- %s" % (gid, row_for(gid, facts)[1]))
            try:
                got, probs = transcribe(gid, facts, fetched.get(gid) or [], conn, em, trace)
            except llm.LLMError as e:
                em.event(type="error", text=str(e))
                tf.close()
                return {"ok": False, "verified": False, "path": "", "missing": facts["needed"], "searches": searches, "usage": usage}
            trace({"type": "group", "group": gid, "fields": {k: v for k, v in got.items() if k != "_quotes"}, "problems": probs})
            if probs:
                tprobs[gid] = probs
                em.log("   %-21s NOT READ: %s" % (gid, "; ".join("%s (%s)" % (f, w) for f, w in probs.items())))
            if got:
                groups[gid] = assemble(gid, facts, got, fetched.get(gid) or [])
    tf.close()

    ok, probs = validate(groups, facts["needed"], facts)
    for g, tp in tprobs.items():
        probs[g] = (probs.get(g) or []) + ["%s: %s" % (f, w) for f, w in tp.items()]
    ok = all(not v for v in probs.values())
    missing = [g for g, p in probs.items() if p]
    params = _merge(template, groups, facts, ok)
    asked = datetime.datetime.now().isoformat(timespec="seconds")
    params["india_collect"] = {"asked": asked, "complete": bool(ok), "needed": facts["needed"],
                               "groups": {g: {"source": (groups.get(g) or {}).get("source") or "MISSING"} for g in facts["needed"]},
                               "statement": IS_NL_STATEMENT}
    params["source"] = ("IS specification values collected from the IS corpus on this PC by `snl collect` %s -- " % asked
                        + "; ".join("%s: %s" % (g, (groups.get(g) or {}).get("source") or "MISSING") for g in facts["needed"])
                        + ". Hinge backbones: modelling assumptions (information / EOR input), not read from any IS table.")
    params["_README"] = _readme(facts, ok, probs, conn, len(searches))
    out_path = os.path.join(job, out_name if ok else PARTIAL_NAME)
    json.dump(params, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    write_evidence(job, facts, searches, probs, ok, conn, out_path)
    for g in facts["needed"]:
        em.log("   %-21s %s" % (g, ("ok -- " + str((groups.get(g) or {}).get("source") or ""))[:140] if not probs.get(g)
                                else "NOT COLLECTED -- " + "; ".join(probs[g])))
    if ok:
        em.event(type="milestone", text="collected: %s (%d IS groups, %d standards searches, %d s) -- Run analyses is now open"
                 % (os.path.basename(out_path), len(facts["needed"]), len(searches), int(time.time() - t0)))
    else:
        em.event(type="error", text="not every IS value could be read from the corpus: %s. Written as %s; Run analyses stays closed until every group is collected."
                 % (", ".join(missing), PARTIAL_NAME))
    em.log(">> params: " + out_path)
    return {"ok": ok, "verified": ok, "path": out_path, "missing": missing, "searches": searches, "usage": usage}


# ---------------------------------------------------------------- MOCK
def mock_collect(facts: dict, fetched: dict | None = None) -> dict:
    """Offline: the repository's IS constants, labelled as such (NOT transcribed from the corpus). The pre-fetch
    already made the searches; the source keeps the page the fetched passage gave, when one came back."""
    from pushover import india_materials as IM
    from nlrha import india_hazard as IH
    fetched = fetched or {}
    out: dict = {}

    def src(gid):
        return "MOCK (values from the repository's IS constants, not transcribed) -- " + _source(gid, facts, fetched.get(gid) or [])
    g = facts.get("grade") or "E250"
    for gid in facts["needed"]:
        if gid == "material":
            rep = IM.IS2062_TABLE3_REH.get(g)
            fu = {"E235": 360, "E250": 410, "E275": 430, "E300": 440, "E350": 490, "E410": 540, "E450": 570,
                  "E500": 580, "E550": 650, "E600": 700, "E650": 750}.get(g)
            if not rep or not fu:
                continue
            out[gid] = {"fu_MPa": float(fu), "fy_t16_MPa": float(rep[0]), "fy_t40_MPa": float(rep[1]), "fy_t100_MPa": float(rep[2])}
            if rep[3] is not None:
                out[gid]["fy_tgt100_MPa"] = float(rep[3])
        elif gid == "overstrength":
            ry = IM.IS18168_RY.get(g)
            if ry is None:
                continue
            out[gid] = {"Ry": ry, "Ru": {"E250": 1.2, "E275": 1.2, "E300": 1.1, "E350": 1.1}.get(g)}
        elif gid == "deformation_capacity":
            v = ((facts.get("reference_rotation") or {}).get("refs") or [{}])[0].get("value")
            if v is None:
                continue
            out[gid] = {"rotation_rad": v}
        elif gid == "spectrum":
            soil = facts.get("soil") or "II"
            tc, c, floor = {"I": (0.40, 1.00, 0.25), "II": (0.55, 1.36, 0.34), "III": (0.67, 1.67, 0.42)}[soil]
            out[gid] = {"Z": IH.ZONE_FACTOR_Z.get(facts.get("zone") or "", facts.get("Z")), "Sa_plateau": 2.5, "Tc_s": tc,
                        "Sa_c": c, "Sa_floor": floor, "I_row_i": 1.5, "I_row_ii": 1.2, "I_row_iii": 1.0}
        elif gid == "damping":
            out[gid] = {"damping_percent": 5}
        else:
            continue
        a = assemble(gid, facts, dict(out[gid]), fetched.get(gid) or [])
        a["source"] = src(gid)
        out[gid] = a
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="snl collect")
    ap.add_argument("job")
    ap.add_argument("--out", default=OUT_NAME, help="file name written into the job folder (default %s)" % OUT_NAME)
    a = ap.parse_args(argv)
    r = run(a.job, out_name=a.out, emit=Emitter())
    return 0 if r["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
