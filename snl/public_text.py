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


def has_internal_words(text):
    """True when `text` still carries a ticket id or 'EOR' (used by the tests and the build check)."""
    t = str(text or "")
    return bool(_TICKET.search(t)) or bool(re.search(r"\bEOR\b", t))
