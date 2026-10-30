"""public_text.py -- what a public NL page may say (2026-10 check fixes, findings 3, 5 and 6 of the second-wave review).

The published pages (four-analyses sheet, pushover / NLRHA / DDM reports, the site index) are read by design engineers
who do not know this project's ticket numbers, file names or abbreviations. Three kinds of text never belong there:
  * internal ticket ids -- "(NL-21)", "(NL-24 / NL-36)", "NL-31": the method is described in words instead;
  * "EOR" -- written out as "design engineer";
  * build-machine words -- JSON file names and keys ("hinge_params_used.json", "nl_plan.gm_selection.sf_bounds").

New reports are written without them (the generators were changed). Reports stored before this change are cleaned by
`scrub_html` when `snl report` refreshes them: literal replacements of the stored phrases, then the ticket-id pattern.
Report-only and idempotent: a second pass changes nothing.
"""
from __future__ import annotations

import html as _html
import re

# a ticket id in brackets, alone or as a list: " (NL-21)", " (NL-24 / NL-36)"
_TICKETS_IN_BRACKETS = re.compile(r" ?\((?:NL-\d+)(?:\s*(?:/|,|and)\s*NL-\d+)*\)")
_TICKET = re.compile(r"\bNL-\d+\b")

HINGE_NOTE_OLD = ("The hinge backbones in hinge_params_used.json are modelling assumptions (information / EOR input): "
                  "IS 800:2007, IS 1893 (Part 1):2016 and IS 18168:2023 tabulate none, and they are not acceptance criteria. "
                  "IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for information.")
HINGE_NOTE = ("The hinge backbones used in these analyses are modelling assumptions (information / design engineer's "
              "input): IS 800:2007, IS 1893 (Part 1):2016 and IS 18168:2023 tabulate none, and they are not acceptance "
              "criteria. IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; results are for "
              "information.")

SF_BOUNDS_OLD = "the engineer may set nl_plan.gm_selection.sf_bounds"
SF_BOUNDS_NEW = "the design engineer may set them"

# (old, new) phrases of stored report HTML; the old HINGE_NOTE in both its escaped and its raw form
_LITERAL = [
    (_html.escape(HINGE_NOTE_OLD, quote=False), _html.escape(HINGE_NOTE, quote=False)),
    (HINGE_NOTE_OLD, HINGE_NOTE),
    ("information / EOR input", "information / design engineer's input"),
    ("information, EOR input", "information, design engineer's input"),
    (SF_BOUNDS_OLD, SF_BOUNDS_NEW),
    ("Modelling disclosures (NL-21)", "Modelling disclosures"),
    ("IS specification values collected by <code>snl collect</code>", "IS specification values collected from the IS corpus"),
]


def scrub(text):
    """Plain text for a public page: no ticket ids, no 'EOR'. None stays None."""
    if text is None:
        return None
    s = str(text)
    for old, new in _LITERAL:
        s = s.replace(old, new)
    s = _TICKETS_IN_BRACKETS.sub("", s)
    s = s.replace("EOR to confirm", "design engineer to confirm").replace("EOR input", "design engineer's input")
    return s


def scrub_html(h):
    """The same for a stored report page. Only bracketed ticket ids are removed by pattern (a bare 'NL-36' inside a
    sentence would leave a broken sentence, so those are fixed in the generators and listed in `_LITERAL`). Base64
    images hold no brackets or spaces, so the pattern cannot touch them."""
    if not h:
        return h
    for old, new in _LITERAL:
        h = h.replace(old, new)
    return _TICKETS_IN_BRACKETS.sub("", h)


# ---------------------------------------------------------------- third wave (P10): keys and solver words in words
# HR schedule role keys (a key with an underscore never belongs on a page; floor / roof / brace / link read as English)
ROLE_WORDS = {"lateral_col": "lateral column", "gravity_col": "gravity column", "col": "column", "floor": "floor beam",
              "roof": "roof beam", "link": "EBF link", "brace": "brace", "beam": "beam", "eave_strut": "eave strut",
              "crane_girder": "crane girder", "end_post": "end-wall post", "wind_post": "wind post"}
# DDM sweep statuses (steltic_ddm/solver.limit_status) and terminations (solver.sweep `term`)
STATUS_WORDS = {"NO_LIMIT_POINT": "no limit point", "LIMIT_POINT": "limit point", "PLASTIC_PLATEAU": "plastic plateau",
                "DUCTILITY_CAP": "ductility cap", "SOLVER_FAILURE": "numerical stop"}
TERM_WORDS = {"time_limit": "time limit", "post_peak_budget": "post-peak step budget", "post_peak_drop": "post-peak drop",
              "step_exhausted": "smallest step reached", "too_many_failures": "repeated failed steps",
              "ductility_cap": "ductility cap", "max_steps": "step budget", "disp_cap": "displacement cap",
              "runaway": "numerical runaway"}
_KEYED = re.compile(r"\b(" + "|".join(sorted((k for k in list(ROLE_WORDS) + list(TERM_WORDS) if "_" in k), key=len,
                                              reverse=True)) + r")\b")
_STATUS = re.compile(r"\b(" + "|".join(sorted(STATUS_WORDS, key=len, reverse=True)) + r")\b")
# corpus group keys of the collected IS values: material@E350, tube_material@YST310, deformation_capacity@IS 800:12.8
_GROUP_KEY = re.compile(r"\b([a-z]+(?:_[a-z]+)+|material|overstrength|spectrum|damping)@([A-Za-z0-9 .]+?)(?=:|;|,|\)|$)")
_GROUP_PLAIN = re.compile(r"\b(deformation_capacity|tube_material)\b")


def role_words(role) -> str:
    """'lateral_col' -> 'lateral column' (unknown keys: underscores to spaces)."""
    r = str(role or "")
    return ROLE_WORDS.get(r, r.replace("_", " "))


def status_words(s) -> str:
    """'NO_LIMIT_POINT' -> 'no limit point'; a termination 'time_limit' -> 'time limit'; anything else unchanged."""
    t = str(s or "")
    return STATUS_WORDS.get(t) or TERM_WORDS.get(t) or t


def group_words(g) -> str:
    """Corpus group key -> words: 'material@E350' -> 'material (E350)', 'deformation_capacity' -> 'deformation capacity'."""
    s = str(g or "")
    if "@" in s:
        a, b = s.split("@", 1)
        return "%s (%s)" % (a.replace("_", " "), b.replace(":", " "))
    return s.replace("_", " ")


def words(text):
    """Keys and solver tokens in a public TEXT in words (idempotent): role keys with an underscore, sweep statuses,
    terminations, corpus group keys. Leaves anything else alone."""
    if text is None:
        return None
    s = str(text)
    s = _GROUP_KEY.sub(lambda m: "%s (%s)" % (m.group(1).replace("_", " "), m.group(2).strip()), s)
    s = _GROUP_PLAIN.sub(lambda m: m.group(1).replace("_", " "), s)
    s = _STATUS.sub(lambda m: STATUS_WORDS[m.group(1)], s)
    s = _KEYED.sub(lambda m: ROLE_WORDS.get(m.group(1)) or TERM_WORDS.get(m.group(1)), s)
    return s


_SCRIPT_OR_STYLE = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>)", re.S | re.I)


def words_html(h):
    """`words` on the text of a page, outside <script> and <style> (a viewer's data keys drive its code and colours)."""
    if not h:
        return h
    parts = _SCRIPT_OR_STYLE.split(h)
    return "".join(p if (i % 2 == 1) else words(p) for i, p in enumerate(parts))


def has_internal_words(text):
    """True when `text` still carries a ticket id or 'EOR' (used by the tests and the build check)."""
    t = str(text or "")
    return bool(_TICKET.search(t)) or bool(re.search(r"\bEOR\b", t))
