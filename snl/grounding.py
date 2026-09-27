"""grounding.py -- what provenance this project's component parameters actually have.

There are three states in the US module, and India adds a fourth, because on this fork the hinge backbones
can never be "verified" -- IS 800:2007, IS 1893 (Part 1):2016 and IS 18168:2023 tabulate none (owner rulings
D3 / D7; nlrha.india_authority.hinge_analogue_status found:false):

  verified    the printed values were read out of the converted standard and copied into the parameters
              file, with the table and page in `source`. Never true for an India hinge backbone.
  grounded    `snl revise` retrieved the IS clauses the reports cite and recorded the citations (and, if an
              AHJ-accepted source ever grounds a component group, that group); the backbone numbers in the
              file are untouched. Retrieval is not the check.
  collected   `snl collect` read the IS specification values the analyses rely on (IS 2062 fy / fu, IS 18168
              Ry / Ru, the IS 800 Section 12 joint-rotation capacity, IS 1893 Z / I / Sa/g / damping) out of
              the IS corpus and checked every one against the cell it came from. The backbones stay
              modelling assumptions (information / EOR inputs), never acceptance criteria.
  unverified  nobody has looked.

The record Revise leaves lives at the JOB ROOT, in revise_evidence.json, which the analysis run never writes
-- and it carries a fingerprint of the parameters it was taken against, so grounding recorded for one
parameter set can never be shown against another. The analysis run copies the input parameters over
pushover/hinge_params_used.json; pushover/cli.py re-applies the grounding from the evidence.
"""
from __future__ import annotations

import hashlib
import json
import os

VERIFIED, GROUNDED, COLLECTED, UNVERIFIED = "verified", "grounded", "collected", "unverified"
EVIDENCE = "revise_evidence.json"

# the keys that ARE the modelling parameters; `verified`, `source`, `grounding` and the readme are
# provenance about them, and a re-run rewriting those must not look like a different parameter set
_META = ("_README", "verified", "source", "grounding")


def fingerprint(prm: dict) -> str:
    """A stable hash of the modelling parameters themselves, ignoring provenance keys."""
    body = {k: v for k, v in (prm or {}).items() if k not in _META}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def job_root(where: str) -> str:
    """The project folder, given the job itself or one of its output folders (pushover/, nlrha/)."""
    where = os.path.abspath(where)
    if os.path.exists(os.path.join(where, EVIDENCE)):
        return where
    up = os.path.dirname(where)
    return up if os.path.exists(os.path.join(up, EVIDENCE)) else where


def evidence(where: str) -> dict | None:
    """The grounding Revise recorded for this project, or None. Never raises."""
    p = os.path.join(job_root(where), EVIDENCE)
    try:
        with open(p, encoding="utf-8") as f:
            ev = json.load(f)
    except (OSError, ValueError):
        return None
    return ev if isinstance(ev, dict) else None


def state(prm: dict, where: str) -> tuple[str, dict | None]:
    """-> (VERIFIED | GROUNDED | COLLECTED | UNVERIFIED, the evidence when it applies).

    Evidence taken against different parameters does not count: it is reported as the state the file has
    on its own, which is the honest answer -- the clauses were looked up for something else. On the India
    fork a revise record grounds the IS clauses (no IS hinge table exists to ground a group), so a record
    with grounded clauses and no grounded group is GROUNDED too."""
    prm = prm or {}
    if prm.get("verified"):
        return VERIFIED, None
    own = COLLECTED if spec_collected(prm) else UNVERIFIED
    ev = evidence(where)
    if not ev:
        return own, None
    groups = {k: v for k, v in (ev.get("groups") or {}).items() if v.get("grounded")}
    clauses = {k: v for k, v in (ev.get("clauses") or {}).items() if (v.get("grounded") if isinstance(v, dict) else v)}
    if not groups and not clauses:
        return own, None
    fp = (ev.get("params") or {}).get("fingerprint")
    if fp and fp != fingerprint(prm):
        return own, None                           # recorded against a different parameter set
    return GROUNDED, ev


def spec_collected(prm: dict | None) -> bool:
    """True when `snl collect` read every IS specification value this building needs (hinge_params_collected.json)."""
    return bool((prm or {}).get("spec_values_collected"))


def citations(ev: dict | None) -> list[str]:
    if not ev:
        return []
    out = []
    for k, v in (ev.get("groups") or {}).items():
        if v.get("grounded") and v.get("citation"):
            out.append("%s %s" % (k.replace("_", " "), v["citation"]))
    return out


def clause_citations(ev: dict | None) -> list[str]:
    if not ev:
        return []
    return ["%s %s" % (k, v.get("citation") or v) for k, v in (ev.get("clauses") or {}).items()
            if (v.get("grounded") if isinstance(v, dict) else v)]


# ---------------------------------------------------------------- how it reads in a report
MARK = 'data-provenance'


HINGE_NOTE = ("The hinge backbones in hinge_params_used.json are modelling assumptions (information / EOR input): "
              "IS 800:2007, IS 1893 (Part 1):2016 and IS 18168:2023 tabulate none, and they are not acceptance criteria. "
              "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information.")


def _collected_line(prm: dict) -> str:
    ic = (prm or {}).get("india_collect") or {}
    if not spec_collected(prm):
        return ""
    src = "; ".join("%s: %s" % (g, (r or {}).get("source") or "") for g, r in (ic.get("groups") or {}).items())
    return " IS specification values collected by <code>snl collect</code>%s: %s." % (
        (" on " + _esc(str(ic.get("asked")))) if ic.get("asked") else "", _esc(src or "see hinge_params_collected.json"))


def block_html(st: str, ev: dict | None, prm: dict | None = None) -> str:
    """The provenance block a supplement carries, marked so Revise can replace it in place."""
    prm = prm or {}
    if st == VERIFIED:
        return ('<div class="note" %s="verified">COMPONENT PARAMETERS VERIFIED — %s</div>'
                % (MARK, _esc(str(prm.get("source") or "reconciled against the printed tables."))))
    if st == GROUNDED:
        cites = "; ".join(citations(ev) + clause_citations(ev)) or "the IS corpus on this PC"
        asked = _esc(str((ev or {}).get("asked") or ""))
        return ('<div class="note" %s="grounded"><b>IS CLAUSES RETRIEVED — HINGE BACKBONES ARE MODELLING ASSUMPTIONS.</b> '
                'The IS clauses these results are reported against were retrieved from the IS corpus on this PC%s and '
                'are cited here: %s.%s %s Retrieval log: revise_evidence.json.</div>'
                % (MARK, (" on " + asked) if asked else "", _esc(cites), _collected_line(prm), _esc(HINGE_NOTE)))
    if st == COLLECTED:
        return ('<div class="note" %s="collected"><b>IS SPECIFICATION VALUES COLLECTED — HINGE BACKBONES ARE MODELLING '
                'ASSUMPTIONS.</b>%s %s</div>' % (MARK, _collected_line(prm), _esc(HINGE_NOTE)))
    return ('<div class="banner" %s="unverified">UNVERIFIED MODELLING PARAMETERS — hinge_params.json has '
            'verified=false and no IS specification value or clause has been read for it: run Collect specification '
            'values before the analyses, and Review, then Revise, after them. %s Source note: %s</div>'
            % (MARK, _esc(HINGE_NOTE), _esc(str(prm.get("source") or ""))))


def summary(st: str, ev: dict | None, prm: dict | None = None, width: int = 110) -> str:
    """One line, for a table cell or the .docx."""
    prm = prm or {}
    if st == VERIFIED:
        return "verified · " + str(prm.get("source") or "")[:width]
    if st == GROUNDED:
        return ("IS clauses retrieved (" + ("; ".join(citations(ev) + clause_citations(ev)) or "corpus")[:width]
                + ") · hinge backbones are modelling assumptions")
    if st == COLLECTED:
        return "IS specification values collected · hinge backbones are modelling assumptions"
    return "UNVERIFIED placeholders (hinge backbones: modelling assumptions)"


_DISCLOSURE = "Cyclic deterioration"


def _carried_disclosure(block: str) -> str:
    """Any non-provenance disclosure inside a block being replaced, preserved as a note of its own."""
    i = block.find(_DISCLOSURE)
    if i < 0:
        return ""
    tail = block[i:]
    tail = tail[:tail.rfind("</div>")] if "</div>" in tail else tail
    return '<div class="note">%s</div>' % tail.strip()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- patching a report already written
PATCHED, UNCHANGED, ABSENT = "patched", "unchanged", "absent"


def patch(path: str, st: str, ev: dict | None, prm: dict | None = None) -> str:
    """Replace the provenance block in a supplement that is already on disk.

    -> PATCHED (rewritten) | UNCHANGED (already says this) | ABSENT (no block to replace).
    Running Revise twice is not an error, and must not be reported as one.

    This is what lets Revise finish the job. The supplements are written from live analysis objects
    during the run, so they cannot be re-rendered without re-running -- and re-running is exactly
    what erases the grounding. Only the provenance block is touched; not one number moves.
    """
    import re
    try:
        with open(path, encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return ABSENT
    new = block_html(st, ev, prm)
    # the marked form this module writes, and the legacy unmarked banner that predates it (the US-scaffolding
    # supplements still write that one)
    pats = [re.compile(r'<div class="(?:banner|note)" %s="[a-z]+">.*?</div>' % MARK, re.S),
            re.compile(r'<div class="banner">UNVERIFIED (?:MODELLING|COMPONENT) PARAMETERS.*?</div>', re.S)]
    for p in pats:
        m = p.search(html)
        if m:
            # The legacy NLRHA banner carried a SECOND disclosure -- cyclic deterioration is off, though
            # 16.3.1 asks for it. That is a modelling disclosure, not provenance, and replacing the block
            # must not quietly delete it.
            keep = _carried_disclosure(m.group(0))
            out = p.sub(lambda _m: new + keep, html, count=1)
            if out == html:
                return UNCHANGED
            with open(path, "w", encoding="utf-8") as f:
                f.write(out)
            return PATCHED
    return ABSENT
