"""gate_reason.py -- the completeness gate in plain words (2026-10 check fixes, findings 1 and 3).

The gate (nlrha/india_authority.write_complete_gate -> complete_gate.json) gives a status and machine reasons. A public
page needs the same thing as a design engineer would say it: what stopped, in which combination, whether a capacity is
reported for it, whether its IS 800 B-1.2 check was made, and why that stop does or does not block COMPLETE. This module
builds that text from the stored results only (ddm_results.json read through the runaway guard, as the gate reads it;
the pushover package), for the four-analyses page, complete_gate.json and the site index.

Statuses (india_authority.design_status):
  complete                          every analysis complete
  complete_with_solver_stops        complete, with numerical stops that the method states instead of blocking: an
                                    earthquake combination (information only, no phi_s pass/fail) that passed lambda = 1
                                    and stopped at all three load-step sizes (dlam, dlam/2, dlam/4)
  complete_with_capacity_shortfall  complete, and the IS 800 B-1.2 section check at lambda = 1 is not satisfied
  partial                           something blocks COMPLETE (named in the text)
"""
from __future__ import annotations

import json
import math
import os
import re

STATUS_LABEL = {"complete": "COMPLETE", "complete_with_solver_stops": "COMPLETE WITH SOLVER STOPS",
                "complete_with_capacity_shortfall": "COMPLETE WITH A CAPACITY SHORTFALL", "partial": "PARTIAL"}
N_STEP_SIZES = 3                       # the retry ladder of the DDM sweep: dlam, dlam/2, dlam/4


def _j(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                                  # noqa: BLE001
        return None


def _floor3(x):
    return None if x is None else math.floor(float(x) * 1000.0 + 1e-9) / 1000.0


def _ceil3(x):
    return None if x is None else math.ceil(float(x) * 1000.0 - 1e-9) / 1000.0


def _ddm(job):
    """ddm_results.json read through the runaway guard, as the gate and the site index read it."""
    ddm = _j(os.path.join(job, "ddm_results.json"))
    if not ddm or not ddm.get("runs"):
        return ddm
    try:
        from steltic_ddm.cli import reclassify_stored_run
        dl = (ddm.get("options") or {}).get("dlam") or 0.05
        for r in ddm["runs"]:
            reclassify_stored_run(r, dl)
    except Exception:                                                  # noqa: BLE001
        pass
    return ddm


def _runaway_words(r):
    """'a step returned λ = -787.9 after λ = 1.318' from the guard's criterion, else a general phrase."""
    crit = str((r.get("runaway") or {}).get("criterion") or "")
    m = re.search(r"lambda (-?\d+(?:\.\d+)?) after (-?\d+(?:\.\d+)?)", crit)
    if m:
        return ("a numerical runaway: the next step returned λ = %s after λ = %s, which is not physically possible, so the "
                "step was discarded" % (format(float(m.group(1)), ".1f"), m.group(2)))
    return "a numerical runaway: a step went outside the plausibility bounds of the method and was discarded"


def _step_sizes(r):
    rt = [x for x in (r.get("retries") or []) if isinstance(x, dict) and x.get("dlam")]
    return [float(x["dlam"]) for x in rt]


def _b12_words(r):
    b = r.get("b12") or {}
    if not b:
        return "its IS 800 B-1.2 check at λ = 1 was not made"
    dcs = [g.get("dc_max") for g in b.get("groups") or [] if g.get("dc_max") is not None]
    if b.get("reached_lambda_1") and b.get("ok") is True:
        return "λ = 1 was passed before the stop, so its IS 800 B-1.2 check at λ = 1 was made and is satisfied%s" % (
            (" (largest ratio %.3f)" % _ceil3(max(dcs))) if dcs else "")
    if b.get("reached_lambda_1") and b.get("ok") is False:
        return "λ = 1 was passed before the stop; its IS 800 B-1.2 check at λ = 1 is NOT satisfied%s" % (
            (" (largest ratio %.3f)" % _ceil3(max(dcs))) if dcs else "")
    return "it stopped before λ = 1, so its IS 800 B-1.2 check at λ = 1 could not be made"


def stop_items(job, ddm=None):
    """One plain sentence per DDM sweep that stopped numerically, saying why it does or does not block COMPLETE."""
    from nlrha.india_authority import ddm_solver_stop_disclosable
    ddm = ddm if ddm is not None else _ddm(job)
    out = []
    n = len((ddm or {}).get("runs") or [])
    for r in (ddm or {}).get("runs") or []:
        if r.get("status") != "SOLVER_FAILURE":
            continue
        lam = _floor3(r.get("lambda_end") or 0.0)
        runaway = bool(r.get("runaway") or r.get("termination") == "runaway")
        what = _runaway_words(r) if runaway else "the equilibrium iterations failed"
        sizes = _step_sizes(r)
        tried = ("load-step sizes tried: Δλ %s" % ", ".join("%g" % s for s in sizes)) if sizes else "no smaller load step tried"
        head = "DDM %s stopped numerically at λ = %.3f (%s; %s). No capacity is reported for this combination; %s." % (
            r.get("label"), lam, what, tried, _b12_words(r))
        if ddm_solver_stop_disclosable(r):
            why = ("The stop is stated, not blocking: it is an earthquake combination, which this advanced analysis "
                   "reports for information only (no φs pass/fail), it passed λ = 1, and it stopped at all %d load-step "
                   "sizes the method uses." % N_STEP_SIZES)
        elif r.get("kind") in ("gravity", "wind"):
            why = "It blocks COMPLETE: a gravity or wind combination must end at a structural limit, not a numerical stop."
        elif float(r.get("lambda_end") or 0.0) < 1.0:
            why = "It blocks COMPLETE: it stopped before λ = 1."
        else:
            done = len(sizes)
            why = ("It blocks COMPLETE: the method re-runs a stopped sweep with smaller load steps (Δλ, Δλ/2, Δλ/4) "
                   "before it may state the stop instead%s." % (
                       (", and %d of the %d sizes have been run" % (done, N_STEP_SIZES)) if done < N_STEP_SIZES else
                       (" and %s" % ("the stop here is a numerical runaway, not a failure to converge" if runaway else
                                    "this combination does not qualify"))))
        out.append(dict(label=r.get("label"), blocking=not ddm_solver_stop_disclosable(r), text=head + " " + why,
                        lambda_end=lam, runaway=runaway, step_sizes=sizes, n_runs=n))
    return out


def pushover_items(job):
    """One sentence per pushover target the curve did not reach (values printed at that target are curve-end values)."""
    po = _j(os.path.join(job, "pushover", "pushover_package.json")) or {}
    out = []
    for d, dd in sorted((po.get("directions") or {}).items()):
        cap = dd.get("capacity") or {}
        for lv, n in (dd.get("nsp") or {}).items():
            if n.get("reached_target") is False:
                r = (dd.get("response") or {}).get(lv) or {}
                end = r.get("roof_disp_mm")
                if end is None and cap.get("u_end_in") is not None:
                    end = float(cap["u_end_in"]) * 25.4
                txt = ("Pushover %s: the curve ended in a numerical stop at %.0f mm, before the %s target of %.1f mm; the "
                       "response shown for %s is the value at the curve end, not at the target." % (
                           d, end, lv, n["target_disp_mm"], lv)) if (end is not None and n.get("target_disp_mm")) else (
                       "Pushover %s: the curve ended in a numerical stop before the %s target; the response shown for %s is "
                       "the value at the curve end, not at the target." % (d, lv, lv))
                out.append(dict(direction=d, level=lv, target_mm=n.get("target_disp_mm"), end_mm=end, text=txt))
    return out


def review_items(job):
    try:
        from pushover import review as RV
    except Exception:                                                  # noqa: BLE001
        return []
    return [dict(direction=d, text=(e.get("summary") or "Pushover %s under review." % d))
            for d, e in sorted(RV.directions_under_review(job).items())]


def gate_reason(job, gate=None):
    """{'status', 'label', 'text', 'items'}: the gate in plain words. `gate` is complete_gate.json (read when None)."""
    gate = gate if gate is not None else (_j(os.path.join(job, "complete_gate.json")) or {})
    status = gate.get("status")
    label = STATUS_LABEL.get(status, str(status or "not run").upper().replace("_", " "))
    ddm = _ddm(job)
    stops = stop_items(job, ddm)
    po = pushover_items(job)
    rv = review_items(job)
    parts = []
    if status == "complete":
        parts.append("All four analyses are complete and every check of the completeness gate is met.")
    elif status == "complete_with_solver_stops":
        parts.append("All four analyses are complete; %s stated rather than blocking:" % (
            "one numerical stop is" if sum(1 for s in stops if not s["blocking"]) == 1 else "the numerical stops below are"))
    elif status == "complete_with_capacity_shortfall":
        b12 = (ddm or {}).get("b12_check") or {}
        worst = None
        for c in b12.get("combos") or []:
            for g in c.get("groups") or []:
                if worst is None or (g.get("dc_max") or 0) > worst[0]:
                    worst = (g.get("dc_max") or 0, g, c.get("combo"))
        parts.append("All four analyses are complete, but the IS 800 Annex B-1.2 section check at λ = 1 is not satisfied%s." % (
            (": %s %s, ratio %.3f under %s" % (str(worst[1].get("role") or "").replace("_", " "), worst[1].get("section"),
                                               _ceil3(worst[0]), worst[2])) if worst and worst[0] > 1.0 else ""))
    elif status == "partial":
        blocking = [s for s in stops if s["blocking"]]
        if blocking:
            parts.append("%s of the %d DDM combinations stopped numerically, and that blocks a COMPLETE status:" % (
                "One" if len(blocking) == 1 else str(len(blocking)), blocking[0]["n_runs"]))
        else:
            parts.append("The completeness gate is not met (%s)." % "; ".join(
                str(x) for x in (gate.get("reasons") or [])[:3]))
    else:
        parts.append("Completeness gate: %s." % label)
    parts += [s["text"] for s in stops if (status != "complete" or not s["blocking"])]
    parts += [p["text"] for p in po]
    parts += [x["text"] for x in rv]
    from .public_text import scrub
    text = scrub(" ".join(parts))
    return dict(status=status, label=label, text=text, items=dict(ddm_stops=stops, pushover_targets=po, under_review=rv))


def notes(job, chk=None):
    """Short plain notes for complete_gate.json `notes` (no ticket ids)."""
    out = []
    stops = stop_items(job)
    if stops:
        nb = sum(1 for s in stops if s["blocking"])
        nr = sum(1 for s in stops if s["runaway"])
        out.append("DDM: %d sweep%s stopped numerically%s; %s. No capacity is reported for %s." % (
            len(stops), "" if len(stops) == 1 else "s",
            ((" (a numerical runaway)" if len(stops) == 1 else " (%d of them a numerical runaway)" % nr) if nr else ""),
            ("%d stated (earthquake combination past λ = 1, stopped at every load-step size), %d blocking COMPLETE"
             % (len(stops) - nb, nb)) if (nb and nb < len(stops)) else (
                "it blocks COMPLETE" if nb == 1 and len(stops) == 1 else ("they block COMPLETE" if nb else
                ("stated, not blocking (earthquake combination past λ = 1, stopped at every load-step size)"
                 if len(stops) == 1 else "stated, not blocking (earthquake combinations past λ = 1, stopped at every "
                                         "load-step size)"))),
            "it" if len(stops) == 1 else "them"))
    out += [p["text"] for p in pushover_items(job)]
    out += [x["text"] for x in review_items(job)]
    return out
