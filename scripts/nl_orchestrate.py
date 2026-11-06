#!/usr/bin/env python3
"""nl_orchestrate.py -- resumable full re-runs of the nonlinear analyses (third wave, P2 / stage 2).

A queue file lists the steps of every building; each call of `next` runs steps until its own time budget is spent,
then stops cleanly, so the whole re-run proceeds in background commands of under 2 h each. Every analysis runs under
the box-wide `heavy` slot runner. A step that is not finished when its chunk ends (exit 75, snl/checkpoint.py) stays
in the queue and resumes from its checkpoint in the next chunk:

  * gravity  -- the HR gravity states recorded with the engine in the queue (STELTIC_ENGINE_DIR);
  * pushover -- one step (both directions, one package), `--checkpoint-dir`: journaled replay, a finished direction
                is kept;
  * NLRHA    -- one step (DBE and MCE), `--record-cache` and `--parallel 1`: finished records are kept, and a chunk
                stops before a record that would not fit (the longest record so far);
  * DDM      -- one step per job, `--checkpoint-dir`: every (combination, imperfection) sweep journaled, finished
                sweeps kept;
  * report   -- `snl report`, after the analyses of the job.

    python scripts/nl_orchestrate.py plan   --queue Q.json --jobs <job> [<job> ...] [--analyses pushover nlrha ddm]
                                            [--engine <steel_engine>] [--python <py>] [--heavy <heavy>]
                                            [--speed-factor F] [--job-args "JOB:KIND=ARGS" ...]
    python scripts/nl_orchestrate.py next   --queue Q.json [--budget 6900] [--max-steps N] [--dry-run]
    python scripts/nl_orchestrate.py status --queue Q.json
    python scripts/nl_orchestrate.py unstall --queue Q.json (--step <id> | --job <job name>)
    python scripts/nl_orchestrate.py refresh --queue Q.json [--engine <steel_engine>] [--include-code] [--dry-run]
    python scripts/nl_orchestrate.py sync   --from <gold jobs root> --to <work jobs root> [--jobs NAME ...] [--dry-run]

Stage 2: a finished step keeps the fingerprint of what it read (fingerprint()); `refresh` compares it with the files
now on disk and puts back the steps whose inputs changed, with everything after them. `sync` brings the HR files of
the gold into the work tree and leaves the NL outputs there alone. Each chunk records the peak memory of its analysis.

Files next to the queue: Q.json.runtime.log (one line per chunk: start, end, step, exit code, seconds, peak memory)
and Q.json.lock (one `next` at a time). The analysis commands are the October re-run commands (tools/step.sh,
run_ddm.sh) with the checkpoint options added; nothing here changes an analysis.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

EXIT_RESUME = 75
EXIT_NO_PROGRESS = 76               # review M3: the step cannot advance in chunks (snl/checkpoint.py NoProgress)
MARGIN_S = 300.0                    # a chunk ends this long before the budget (the journal save, the report)
MIN_CHUNK_S = 600.0                 # no step is started with less than this left
NO_GAIN_LIMIT = 3                   # re-check M3: stalled after this many FULL chunks in a row that kept nothing new
FULL_SHARE = 0.9                    # a chunk is "full" when it had at least this share of the queue's full chunk
# No cap on the number of chunks (re-check M3 e): a count of chunks is not a measure of progress. A step that keeps
# gaining (finished pieces, live calls, cached records) is advancing however long it takes -- the IN_Ex19 DDM alone
# needs about 67 000 s of sweeps, 11 or more full chunks before any replay overhead, so the first version's cap of 24
# was close -- and one that stops gaining is caught by NO_GAIN_LIMIT and exit 76 instead.
DEFAULT_PY = "/home/claude/venv312/bin/python"
DEFAULT_HEAVY = "/home/claude/bin/heavy"
NL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS_KINDS = ("pushover", "nlrha", "ddm")
# Stage 2, `sync`: files and folders the NL writes into a job (at any depth: a unit's own outputs too). `sync` never
# copies, replaces or removes them. Taken from the October NL golds against the HR golds, plus the stage-2 files.
NL_OUTPUTS = ("pushover", "nlrha", "nl_checkpoints", "nlrha_probe", "pushover_proof", "ddm_*", "_ddm_before_*",
              "model_gmnia.py", "four_analyses.html", "snl_*", "complete_gate*", "design_criteria_16_1_4.*",
              "nl_hr_gravity.json", "steltic_viewer_bundle.html", "pushover_review.json", "nl_orchestrate_*",
              ".nl_orchestrate_*", "nl_promote_fibre.json", "nl_plan.json", "hinge_params*.json", "collect_*",
              ".batch_step_*", "batch.log", "batch_done.json", "merge_report.log", "retrieval_log.md", "*.pre_ddm.bak",
              ".nl_sync.json", "stage2_*.log", "*.before_refresh_*")
SYNC_SKIP = ("__pycache__", "*.pyc")          # neither copied nor removed
GRAVITY_META = ("engine_sha", "engine", "inputs_sha256", "source", "note", "dp_note", "job")


def _ck():
    """snl.checkpoint of this checkout (the orchestrator runs as a script)."""
    if NL_ROOT not in sys.path:
        sys.path.insert(0, NL_ROOT)
    from snl import checkpoint as CK
    return CK


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def load(q):
    """The queue; its backup (<q>.bak, the previous save) when the file itself is unreadable -- a power cut on NTFS can
    leave a just-written file zero-filled (review M7)."""
    try:
        return json.load(open(q, encoding="utf-8"))
    except (OSError, ValueError) as ex:
        bak = q + ".bak"
        if os.path.exists(bak):
            print("!! %s unreadable (%s): continuing from its backup %s" % (q, type(ex).__name__, bak), flush=True)
            return json.load(open(bak, encoding="utf-8"))
        raise


def _replace(src, dst, tries=6):
    """os.replace, retried: on Windows an antivirus or the indexer can hold the file for a moment."""
    for i in range(tries):
        try:
            return os.replace(src, dst)
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.5)


def save(q, d):
    """Write the queue durably: a temp file flushed to disk, the previous queue kept as <q>.bak, then the swap
    (review M7)."""
    tmp = q + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(q):
        try:
            json.load(open(q, encoding="utf-8"))                 # only a readable queue becomes the backup
            shutil.copyfile(q, q + ".bak")
        except (OSError, ValueError):
            pass
    _replace(tmp, q)


def _job_steps(job, analyses, py):
    """The steps of one job (ids '<job name>/<what>'); `after` orders them."""
    name = os.path.basename(os.path.normpath(job)) if "units" not in job else \
        "/".join(os.path.normpath(job).split(os.sep)[-3:])
    ck = os.path.join(job, "nl_checkpoints")
    prm = os.path.join(job, "hinge_params_collected.json")
    pa = ["--params", prm] if os.path.exists(prm) else []
    steps = [dict(id=name + "/gravity", job=job, kind="gravity", after=[],
                  cmd=[py, "-m", "snl.hr_gravity", job])]
    last = [name + "/gravity"]
    if "pushover" in analyses:
        sid = name + "/pushover"                       # both directions in one package: the journal keeps a finished one
        steps.append(dict(id=sid, job=job, kind="pushover", after=list(last),
                          cmd=[py, "-m", "pushover", "run", job] + pa + ["--plasticity", "fibre", "--member-nseg", "4",
                               "--dirs", "X", "Y", "--checkpoint-dir", os.path.join(ck, "pushover")]))
        last = [sid]
    if "nlrha" in analyses:
        sid = name + "/nlrha"
        steps.append(dict(id=sid, job=job, kind="nlrha", after=list(last),
                          cmd=[py, "-m", "nlrha", "run", job] + pa + ["--plasticity", "fibre", "--member-nseg", "4",
                               "--dt", "0.01", "--integrator", "hht", "--n", "11", "--parallel", "1",
                               "--record-cache", os.path.join(ck, "nlrha")]))
        last = [sid]
    if "ddm" in analyses:
        sid = name + "/ddm"
        steps.append(dict(id=sid, job=job, kind="ddm", after=list(last),
                          cmd=[py, "-m", "steltic_ddm", "run", job, "--workers", "1",
                               "--checkpoint-dir", os.path.join(ck, "ddm")]))
        last = [sid]
    steps.append(dict(id=name + "/report", job=job, kind="report", after=list(last), cmd=[py, "-m", "snl", "report", job]))
    for s in steps:
        s.update(state="pending", chunks=[])
    return steps


def _merge_args(cmd, extra):
    """The command with the options of `extra` put in: an option already in the command is replaced (the option and
    its values, up to the next '--' token), anything else is added at the end."""
    flags = {t for t in extra if t.startswith("--")}
    out, skip = [], False
    for t in cmd:
        if t.startswith("--"):
            skip = t in flags
        if not skip:
            out.append(t)
    return out + list(extra)


def apply_job_args(steps, specs):
    """Stage 2, `plan --job-args "JOB:KIND=ARGS"`: per-job options of one analysis -- JOB a step's job name (the part
    of its id before the last '/') or the job folder's name, KIND gravity / pushover / nlrha / ddm / report, both
    with '*' wildcards; ARGS shell words merged into the command (_merge_args). A spec that matches no step is an
    error, so a typing slip is not silently ignored."""
    for spec in specs or ():
        if ":" not in spec or "=" not in spec.split(":", 1)[1]:
            raise SystemExit("--job-args %r: expected JOB:KIND=ARGS" % spec)
        pat, rest = spec.split(":", 1)
        kind, argstr = rest.split("=", 1)
        extra = shlex.split(argstr)
        hit = 0
        for st in steps:
            name = st["id"].rsplit("/", 1)[0]
            if (fnmatch.fnmatchcase(name, pat) or fnmatch.fnmatchcase(os.path.basename(st["job"]), pat)) \
                    and fnmatch.fnmatchcase(st["kind"], kind):
                st["cmd"] = _merge_args(st["cmd"], extra)
                st.setdefault("job_args", []).append(argstr)
                hit += 1
        if not hit:
            raise SystemExit("--job-args %r matches no step" % spec)
    return steps


def plan(args):
    if os.path.exists(args.queue) and not args.force:
        raise SystemExit("queue %s exists (use --force to rewrite it)" % args.queue)
    steps = []
    for j in args.jobs:
        steps += _job_steps(os.path.abspath(j), set(args.analyses), args.python)
    apply_job_args(steps, getattr(args, "job_args", None))
    sf = getattr(args, "speed_factor", None)
    if sf is None:
        sf = float(os.environ.get("SNL_SPEED_FACTOR") or 1.0)
    d = dict(version=1, created=_now(), nl_root=NL_ROOT, heavy=args.heavy, python=args.python,
             env=dict(STELTIC_ENGINE_DIR=os.path.abspath(args.engine) if args.engine else os.environ.get("STELTIC_ENGINE_DIR", ""),
                      MPLBACKEND="Agg", RAG_API_URL="", PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0",
                      SNL_SPEED_FACTOR="%g" % float(sf)),
             steps=steps)
    save(args.queue, d)
    print("planned %d steps for %d job(s) -> %s" % (len(steps), len(args.jobs), args.queue))
    if any(st["kind"] == "ddm" for st in steps):
        print("DDM sweep time limit: 2400 s on the reference machine x speed factor %g = %.0f s" % (float(sf), 2400.0 * float(sf)))
    return d


def _engine_dir(d):
    return (d.get("env") or {}).get("STELTIC_ENGINE_DIR") or None


def gravity_digest(job):
    """sha256 (16 hex) of the HR gravity record's content (the states, the column load reduction, the roof share), its
    provenance fields left out; None without a record."""
    try:
        g = json.load(open(os.path.join(job, "nl_hr_gravity.json"), encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        return None
    g = {k: v for k, v in g.items() if k not in GRAVITY_META}
    return hashlib.sha256(json.dumps(g, sort_keys=True, default=str).encode()).hexdigest()[:16]


def fingerprint(d, s):
    """Stage 2: what a step read, taken when it finishes -- the job's input files (snl.checkpoint.hr_digest: the HR
    model, cfg, load plan, IS 1893 calculation, design of record, design/*, the NL plan and hinge parameters), the HR
    engine, the analysis code, and for an analysis or report step the HR gravity states it used and the section
    tables."""
    CK = _ck()
    eng = _engine_dir(d)
    from snl.hr_gravity import engine_fingerprint
    fp = dict(inputs=CK.hr_digest(s["job"]), engine=engine_fingerprint(eng) if eng else None, code=CK.code_key())
    if s["kind"] != "gravity":
        fp.update(gravity=gravity_digest(s["job"]), tables=CK.section_tables_key(eng or ""))
    return fp


def _dependents(d, sid):
    """Every step that runs after `sid` through `after` (transitively)."""
    out, todo = [], [sid]
    while todo:
        cur = todo.pop()
        for x in d["steps"]:
            if cur in (x.get("after") or []) and x["id"] not in out:
                out.append(x["id"]); todo.append(x["id"])
    return out


def _reset(s, state, reason, now=None):
    s.setdefault("refresh_history", []).append(dict(time=now or _now(), from_state=s["state"], to=state, reason=reason,
                                                    fingerprint=s.get("fingerprint")))
    s["state"] = state
    s["refresh_reason"] = reason
    s.pop("stalled_reason", None)
    s["no_gain_full_chunks"] = 0
    if state == "pending":
        for k in ("promotion_rounds", "promoted", "note_promotion", "started_fingerprint"):   # review M2, M5
            s.pop(k, None)


# Review M1: what each step writes into its job folder. When a step goes back to pending these are set aside, so a
# failed re-run can never leave the earlier inputs' results in place (shipped in the zip, read by a report or the gate).
STEP_OUTPUTS = {"gravity": ("nl_hr_gravity.json",),
                "pushover": ("pushover",),
                "nlrha": ("nlrha",),
                "ddm": ("ddm_results.json", "ddm_report.html", "ddm_viewer_3d.html", "model_gmnia.py"),
                "report": ("complete_gate.json", "complete_gate_disclosures.json", "four_analyses.html",
                           "snl_summary.json", "snl_run.json", "design_criteria_16_1_4.docx",
                           "design_criteria_16_1_4.html", "steltic_viewer_bundle.html")}


def _aside(path, stamp):
    to, n = path + ".before_refresh_" + stamp, 1
    while os.path.exists(to):
        n += 1
        to = "%s.before_refresh_%s_%d" % (path, stamp, n)
    _replace(path, to)
    return to


def set_aside_outputs(s, stamp):
    """Move a step's outputs and its journals / record cache aside (renamed *.before_refresh_<stamp>, never deleted);
    for the DDM also take its block out of design/calc_package.json. Returns what was moved."""
    moved = []
    ck = _opt(s["cmd"], "--checkpoint-dir") or _opt(s["cmd"], "--record-cache")
    # the journals / record cache: a fresh journal starts its counters at zero, which next to the old ones would read
    # as lost progress
    for p in ([ck] if ck else []) + [os.path.join(s["job"], x) for x in STEP_OUTPUTS.get(s["kind"], ())]:
        if os.path.exists(p):
            moved.append(_aside(p, stamp))
    if s["kind"] == "ddm":
        cp = os.path.join(s["job"], "design", "calc_package.json")
        try:
            pkg = json.load(open(cp, encoding="utf-8"))
            if isinstance(pkg, dict) and "ddm_analysis" in pkg:
                pkg.pop("ddm_analysis")
                tmp = cp + ".nl_sync_tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(json.dumps(pkg, indent=1))
                _replace(tmp, cp)
                moved.append(cp + " (ddm_analysis block removed)")
        except (OSError, ValueError):
            pass
    if ck:
        s["set_aside"] = next((m for m in moved if m.startswith(ck)), s.get("set_aside"))
    return moved


def refresh(args):
    """Stage 2: compare each finished (or started) step's fingerprint with the files now on disk and put back what is
    stale. A change of the job's input files resets the step and every step after it; an HR engine change alone resets
    the gravity step, resets the DDM (it reads the engine's load combinations directly) and sets the pushover, NLRHA
    and report steps to `recheck`: after the gravity step has run again they are done again when the gravity states
    and the section tables are unchanged, else pending (reconcile_rechecks). A change of the gravity states or the
    section tables under a finished analysis resets it. An analysis-code change is reported only, unless
    --include-code. A step without a fingerprint (finished before stage 2) is reset."""
    d = load(args.queue)
    if getattr(args, "engine", None):
        d.setdefault("env", {})["STELTIC_ENGINE_DIR"] = os.path.abspath(args.engine)
    by_id = {s["id"]: s for s in d["steps"]}
    plan_ = {}                                                   # step id -> (new state, reason)

    def mark(sid, state, reason):
        old = plan_.get(sid)
        if old is None or (old[0] == "recheck" and state == "pending"):
            plan_[sid] = (state, reason)
    for s in d["steps"]:
        # a finished step: what it read; a started one (resume / stalled / failed): what its first chunk began with;
        # a step that has not run since it was planned or reset has nothing to compare
        old = s.get("fingerprint") if s["state"] in ("done", "recheck") else s.get("started_fingerprint")
        if old is None:
            if s["state"] == "done":
                mark(s["id"], "pending", "finished without a fingerprint (before stage 2)")
                for x in _dependents(d, s["id"]):
                    mark(x, "pending", "after %s, which is reset" % s["id"])
            continue
        new = fingerprint(d, s)
        why = [k for k in ("inputs", "gravity", "tables") if k in new and old.get(k) != new.get(k)]
        if why:
            words = {"inputs": "the job's input files changed", "gravity": "the HR gravity states changed",
                     "tables": "the section tables changed"}
            r = "; ".join(words[w] for w in why)
            mark(s["id"], "pending", r)
            for x in _dependents(d, s["id"]):
                mark(x, "pending", "after %s (%s)" % (s["id"], r))
            continue
        if old.get("engine") != new.get("engine") and s["kind"] == "gravity":
            r = "the HR engine changed (%s -> %s)" % (old.get("engine"), new.get("engine"))
            mark(s["id"], "pending", r)
            for x in _dependents(d, s["id"]):
                kind = by_id[x]["kind"]
                if kind == "ddm":
                    mark(x, "pending", r + "; the DDM reads the engine's load combinations directly")
                elif by_id[x]["state"] == "done" or by_id[x]["chunks"]:
                    mark(x, "recheck", r + "; done again if the gravity states and section tables are unchanged")
            continue
        if old.get("code") != new.get("code"):
            if getattr(args, "include_code", False):
                mark(s["id"], "pending", "the analysis code changed (--include-code)")
                for x in _dependents(d, s["id"]):
                    mark(x, "pending", "after %s (the analysis code changed)" % s["id"])
            else:
                s["code_changed"] = "the analysis code changed since this step ran (%s -> %s); kept (refresh " \
                                    "--include-code to run it again)" % (old.get("code"), new.get("code"))
    stamp = time.strftime("%Y%m%d%H%M%S")
    for sid, (state, reason) in plan_.items():
        s = by_id[sid]
        print("%-52s %-8s -> %-8s %s" % (sid, s["state"], state, reason))
        if not getattr(args, "dry_run", False):
            _reset(s, state, reason)
            if state == "pending":
                s.pop("fingerprint", None)
                for m in set_aside_outputs(s, stamp):                # review M1: outputs too, not only journals
                    print("    set aside: %s" % m)
    if not plan_:
        print("refresh: every step is current")
    if not getattr(args, "dry_run", False):
        save(args.queue, d)
    return plan_


def reconcile_rechecks(d, job):
    """After the gravity step of `job` has run again (refresh after an engine change): each `recheck` step of the job
    is done again when its job inputs, gravity states and section tables are those it ran with, else pending; the
    report step is done again only when nothing before it went back to pending."""
    went_pending = False
    for s in d["steps"]:
        if s["job"] != job or s["state"] != "recheck" or s["kind"] == "report":
            continue
        old = s.get("fingerprint") or {}
        new = fingerprint(d, s)
        same = all(old.get(k) == new.get(k) for k in ("inputs", "gravity", "tables"))
        if same and old:
            s["state"] = "done"
            s["fingerprint"] = dict(old, engine=new.get("engine"))
            s["recheck_note"] = ("rechecked %s after the engine change: the gravity states and section tables are "
                                 "unchanged, the result stands" % _now())
        else:
            _reset(s, "pending", "rechecked after the engine change: the gravity states or section tables changed")
            s.pop("fingerprint", None)
            set_aside_outputs(s, time.strftime("%Y%m%d%H%M%S"))  # review M1 / M5: no old output, a fresh start print
            s["recheck_note"] = "rechecked %s: the gravity states or section tables changed -- runs again" % _now()
            went_pending = True
    went_pending = went_pending or any(s["job"] == job and s["kind"] not in ("report", "gravity") and s["state"] != "done"
                                       for s in d["steps"])
    for s in d["steps"]:
        if s["job"] == job and s["state"] == "recheck" and s["kind"] == "report":
            if went_pending:
                _reset(s, "pending", "an analysis of the job runs again")
                set_aside_outputs(s, time.strftime("%Y%m%d%H%M%S"))
            else:
                s["state"] = "done"


def _ready(d, s):
    done = {x["id"] for x in d["steps"] if x["state"] == "done"}
    return s["state"] in ("pending", "resume") and all(a in done for a in s.get("after") or [])


def _log(q, line):
    with open(q + ".runtime.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _opt(cmd, flag):
    return cmd[cmd.index(flag) + 1] if flag in cmd and cmd.index(flag) + 1 < len(cmd) else None


def progress_of(s):
    """Re-check M3: what a step has kept so far, in MONOTONE counters -- finished pieces and live calls of its journals
    (pushover / DDM; a live restart or a shorter journal after it still adds live calls), or cached records (NLRHA).
    None for a step without either."""
    import glob
    import pickle
    ck = _opt(s["cmd"], "--checkpoint-dir") or _opt(s["cmd"], "--record-cache")
    if not ck:
        return None
    if not os.path.isdir(ck):
        return dict(done=0, live=0, records=0)
    if s["kind"] == "nlrha":
        return dict(done=0, live=0, records=len(glob.glob(os.path.join(ck, "*.pkl"))))
    done = live = 0
    for p in glob.glob(os.path.join(ck, "*.ckpt")):
        try:
            j = pickle.load(open(p, "rb"))
        except Exception:                                        # noqa: BLE001
            continue
        done += len(j.get("done") or {})
        live += int(j.get("live_calls") or 0)
    return dict(done=done, live=live, records=0)


def gained(before, after):
    """Any counter went up."""
    if before is None or after is None:
        return True
    return any(after.get(k, 0) > before.get(k, 0) for k in ("done", "live", "records"))


def _last_line(logp, word):
    try:
        lines = [x.strip() for x in open(logp, encoding="utf-8", errors="replace") if word in x]
        return lines[-1] if lines else None
    except OSError:
        return None


def run_step(q, d, s, remaining, full_chunk=None, dry=False, runner=None):
    """One chunk of step `s` with `remaining` seconds left in this call; `full_chunk` is the queue's full chunk (the
    `next` budget less the margin). Returns the exit code. The command runs inside the heavy slot through `_exec`, which
    fixes the chunk's deadline when the slot is granted (the wait for a slot is not analysis time) and applies the
    timeout; the command gets --chunk-seconds (what is left in this call) and $SNL_FULL_CHUNK (the full chunk), and
    judges "cannot advance in chunks" (exit 76) against the full chunk only (re-check M3 b).
    Stalled (not run again until `unstall`): exit 76, or NO_GAIN_LIMIT full chunks in a row that kept nothing new
    (progress_of). A part-chunk never counts as no progress."""
    chunk = remaining - MARGIN_S
    full_chunk = float(full_chunk if full_chunk is not None else chunk)
    deadline = time.time() + chunk
    env = dict(os.environ, **{k: v for k, v in (d.get("env") or {}).items() if v is not None})
    env["PYTHONPATH"] = d.get("nl_root", NL_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["SNL_FULL_CHUNK"] = "%.0f" % full_chunk
    cmd = list(s["cmd"])
    if s["kind"] in ("pushover", "ddm", "nlrha"):
        cmd += ["--chunk-seconds", "%.0f" % chunk]
    stamp = os.path.join(s["job"], ".nl_orchestrate_%s.stamp" % s["id"].split("/")[-1])
    full = [d.get("heavy") or DEFAULT_HEAVY, d.get("python") or DEFAULT_PY, os.path.abspath(__file__), "_exec",
            "--deadline", "%.0f" % deadline, "--chunk", "%.0f" % chunk, "--stamp", stamp, "--"] + cmd
    t0 = time.time()
    print("[%s] %s: %s" % (_now(), s["id"], " ".join(shlex.quote(c) for c in full)), flush=True)
    if dry:
        return 0
    logp = os.path.join(s["job"], "nl_orchestrate_%s.log" % s["id"].split("/")[-1])
    before = progress_of(s)
    if "started_fingerprint" not in s:
        try:
            s["started_fingerprint"] = fingerprint(d, s)         # stage 2: what a partly-run step began with
        except Exception as ex:                                   # noqa: BLE001
            s["started_fingerprint"] = dict(error=type(ex).__name__)
    try:
        os.remove(stamp)
    except OSError:
        pass
    with open(logp, "a", encoding="utf-8") as lf:
        lf.write("\n==== %s chunk start %s\n" % (s["id"], _now())); lf.flush()
        rc = (runner or subprocess.call)(full, stdout=lf, stderr=subprocess.STDOUT, env=env, cwd=d.get("nl_root", NL_ROOT))
    sec = time.time() - t0
    try:
        st = json.load(open(stamp, encoding="utf-8"))
        had = float(st["deadline"]) - float(st["slot_start"])          # analysis time this chunk really had
    except Exception:                                                  # noqa: BLE001
        had, st = None, {}
    peak = st.get("peak_rss_mb") if isinstance(st, dict) else None    # stage 2: the analysis's peak memory
    cpu = st.get("cpu_s") if isinstance(st, dict) else None           # ... and its CPU time
    after = progress_of(s)
    is_full = (had if had is not None else chunk) >= FULL_SHARE * full_chunk
    ch = dict(start=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)), end=_now(), rc=rc, seconds=round(sec),
              progress=after, had_s=round(had) if had is not None else None, full=bool(is_full), peak_rss_mb=peak,
              cpu_s=cpu)
    s["chunks"].append(ch)
    s.pop("stalled_reason", None)
    if rc == 0:
        s["state"] = "done"
        try:
            s["fingerprint"] = fingerprint(d, s)                 # stage 2: what the finished step read
        except Exception as ex:                                   # noqa: BLE001 -- never lose the finished state
            s["fingerprint"] = dict(error="%s: %s" % (type(ex).__name__, ex))
        s.pop("code_changed", None)
        if s["kind"] == "gravity":
            reconcile_rechecks(d, s["job"])
    elif rc == EXIT_NO_PROGRESS:
        s["state"] = "stalled"
        s["stalled_reason"] = _last_line(logp, "NO PROGRESS") or "the step cannot advance in chunks (exit 76)"
    elif rc in (EXIT_RESUME, 124):
        s["state"] = "resume"
        if rc == 124:
            s["note_timeout"] = "killed at the chunk timeout: resumes from the last journal save (5 min)"
        if gained(before, after):
            s["no_gain_full_chunks"] = 0
        elif is_full:
            s["no_gain_full_chunks"] = int(s.get("no_gain_full_chunks") or 0) + 1
            if s["no_gain_full_chunks"] >= NO_GAIN_LIMIT:
                s["state"] = "stalled"
                s["stalled_reason"] = ("%d full chunks in a row kept nothing new (no finished piece, no live call, no "
                                       "cached record: %s)" % (s["no_gain_full_chunks"], after))
    else:
        s["state"] = "failed"
    _log(q, "%s  %s  %-48s rc=%s seconds=%.0f cpu=%s peak_rss=%s state=%s%s" % (
        ch["start"], ch["end"], s["id"], rc, sec, ("%.0f" % cpu) if cpu is not None else "n/a",
        ("%.0fMB" % peak) if peak is not None else "n/a", s["state"],
        (" (%s)" % s["stalled_reason"]) if s.get("stalled_reason") else ""))
    save(q, d)
    return rc


def _exec(a):
    """Inside the heavy slot: the chunk's deadline from now (never past the outer deadline), stamped for run_step, and
    the command run under it with a timeout (exit 124 when it is killed)."""
    import resource
    t0 = time.time()
    dl = min(float(a.deadline), t0 + float(a.chunk))
    with open(a.stamp, "w", encoding="utf-8") as f:
        json.dump(dict(slot_start=t0, deadline=dl), f)
    env = dict(os.environ, SNL_DEADLINE="%.0f" % dl)
    u0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        rc = subprocess.call(a.command, env=env, timeout=max(1.0, dl - t0 + MARGIN_S / 2))
    except subprocess.TimeoutExpired:
        rc = 124
    # stage 2: the peak resident memory of the analysis and the processes it waited for (Linux: kB; a killed command
    # is waited for too), and their CPU time beside the wall time (a pause of the machine shows as wall >> CPU)
    u = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak = u.ru_maxrss / 1024.0
    with open(a.stamp, "w", encoding="utf-8") as f:
        json.dump(dict(slot_start=t0, deadline=dl, end=time.time(), rc=rc, peak_rss_mb=round(peak, 1),
                       cpu_s=round(u.ru_utime + u.ru_stime - u0.ru_utime - u0.ru_stime, 1)), f)
    return rc


def next_steps(args, runner=None):
    """Run ready steps until the budget is spent (or --max-steps chunks). Re-check M3 a: a step that ends 'resume'
    (exit 75 / 124) is NOT run again in the same call -- what is left would be a part-chunk that mostly replays -- the
    call moves on to other ready steps; the next call gives it a full chunk."""
    lockf = open(args.queue + ".lock", "w")
    try:
        import fcntl                                  # POSIX only: `next` runs on the box, never on Windows (review B1)
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("another `next` is running on %s" % args.queue)
    t_end = time.time() + args.budget
    full_chunk = args.budget - MARGIN_S
    n = 0
    d_dry = None
    deferred = set()
    while True:
        d = d_dry if (args.dry_run and d_dry is not None) else load(args.queue)
        ready = [s for s in d["steps"] if _ready(d, s) and s["id"] not in deferred]
        if not ready:
            if args.dry_run:
                print("dry run: %d step(s) listed in order; the queue file is unchanged" % n)
                return 0
            left = [s["id"] for s in d["steps"] if s["state"] != "done"]
            print("nothing ready; not done: %s" % (", ".join(left) or "none -- the queue is complete"))
            return 0
        remaining = t_end - time.time()
        if remaining < MIN_CHUNK_S + MARGIN_S or (args.max_steps and n >= args.max_steps):
            print("budget spent (%.0f s left) after %d chunk(s); next: %s" % (remaining, n, ready[0]["id"]))
            return 0
        s = ready[0]
        rc = run_step(args.queue, d, s, remaining, full_chunk=full_chunk, dry=args.dry_run, runner=runner)
        n += 1
        if rc in (EXIT_RESUME, 124):
            deferred.add(s["id"])
        if args.dry_run:                               # print the commands in order, change nothing on disk
            d_dry = d if n == 1 else d_dry
            s["state"] = "done"
            continue
        if rc not in (0, EXIT_RESUME, 124) and args.stop_on_failure:
            print("step %s failed (rc %s); stopping" % (s["id"], rc))
            return rc


def unstall(args):
    """Re-check M3 f: put stalled steps back in the queue -- one step (--step ID) or every stalled step of a job
    (--job NAME, the part of the step id before the last '/')."""
    d = load(args.queue)
    hit = []
    for s in d["steps"]:
        if s["state"] != "stalled":
            continue
        if (args.step and s["id"] == args.step) or (args.job and s["id"].rsplit("/", 1)[0] == args.job):
            s["state"] = "resume" if s["chunks"] else "pending"
            s.pop("stalled_reason", None)
            s["no_gain_full_chunks"] = 0
            hit.append(s["id"])
    save(args.queue, d)
    print("unstalled: %s" % (", ".join(hit) or "nothing (no stalled step matched)"))
    return 0


def status(args):
    d = load(args.queue)
    print("%-52s %-8s %6s %8s %8s" % ("step", "state", "chunks", "seconds", "peak MB"))
    for s in d["steps"]:
        pk = [c.get("peak_rss_mb") for c in s["chunks"] if c.get("peak_rss_mb") is not None]
        print("%-52s %-8s %6d %8d %8s" % (s["id"], s["state"], len(s["chunks"]), sum(c["seconds"] for c in s["chunks"]),
                                          ("%.0f" % max(pk)) if pk else "-"))
        for k, w in (("stalled_reason", "stalled"), ("refresh_reason", "refresh"), ("code_changed", "note"),
                     ("recheck_note", "recheck")):
            if s.get(k) and (k != "refresh_reason" or s["state"] != "done"):
                print("    %s: %s" % (w, s[k]))
    return d


def _is_nl(rel):
    """A path (relative to a job folder) that is an NL output or inside one, at any depth."""
    return any(fnmatch.fnmatchcase(part, pat) for part in rel.replace(os.sep, "/").split("/") for pat in NL_OUTPUTS)


def _skipped(rel):
    return any(fnmatch.fnmatchcase(part, pat) for part in rel.replace(os.sep, "/").split("/") for pat in SYNC_SKIP)


def _hr_files(root, inputs=()):
    """Relative paths of the HR files under one job folder (NL outputs and SYNC_SKIP left out; links not followed).
    `inputs`: file names (at any depth) taken although they match NL_OUTPUTS -- the NL inputs a gold bundle carries
    (the PC runner: hinge_params_collected.json, nl_plan.json)."""
    out = []
    for r, dirs, files in os.walk(root):
        rel_r = os.path.relpath(r, root)
        dirs[:] = sorted(x for x in dirs if not _is_nl(os.path.normpath(os.path.join(rel_r, x)))
                         and not _skipped(os.path.normpath(os.path.join(rel_r, x))))
        for f in sorted(files):
            rel = os.path.normpath(os.path.join(rel_r, f))
            if (not _is_nl(rel) or f in inputs) and not _skipped(rel) and not os.path.islink(os.path.join(r, f)):
                out.append(rel)
    return out


def _nl_written(rel):
    """The NL_WRITES_IN_DESIGN name a path (relative to the folder sync walks) stands for: the building's own
    design/calc_package.json or a nested unit's (unitC_gym/design/..., units/stem/design/...) -- review M9."""
    CK = _ck()
    r = rel.replace(os.sep, "/")
    for f, _ in CK.NL_WRITES_IN_DESIGN:
        if r == f or r.endswith("/" + f):
            return f
    return None


def _same(rel, a, b):
    """The same HR content: byte equality, except a file the NL writes a block into (design/calc_package.json, the
    building's or a unit's), which is compared without that block (snl.checkpoint.hr_content)."""
    CK = _ck()
    f = _nl_written(rel)
    if f:
        return CK.hr_content(None, f, a) == CK.hr_content(None, f, b)
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    import filecmp
    return filecmp.cmp(a, b, shallow=False)


def sync(args):
    """Stage 2: bring the HR files of the gold (`--from`, a folder of job folders; read only) into the work tree
    (`--to`). Per job: HR files new or changed at the source are copied (with their times); a file is removed only
    when the previous sync of the job brought it in (its .nl_sync.json lists it) and the source no longer has it, so
    an NL file under a name NL_OUTPUTS does not know (a log, a 'before' copy) is never removed; NL outputs
    (NL_OUTPUTS, at any depth) are never copied, replaced or removed. When
    design/calc_package.json changes at the source the NL's DDM block in the work copy goes with it (the DDM writes it
    again) and so does the stale backup beside it. A job folder only in the work tree is left alone. Each synced job
    gets .nl_sync.json (source, time, what changed, the input digest). `refresh` then finds the stale steps."""
    CK = _ck()
    src_root, dst_root = os.path.abspath(args.src), os.path.abspath(args.dst)
    try:
        nested = os.path.commonpath([src_root, dst_root]) in (src_root, dst_root)
    except ValueError:                                           # Windows: two drives can never contain each other
        nested = False
    if nested:
        raise SystemExit("sync: --from and --to must not contain each other")
    names = sorted(x for x in os.listdir(src_root) if os.path.isdir(os.path.join(src_root, x)) and not _skipped(x))
    if args.jobs:
        missing = [j for j in args.jobs if j not in names]
        if missing:
            raise SystemExit("sync: not in %s: %s" % (src_root, ", ".join(missing)))
        names = [x for x in names if x in args.jobs]
    dry = bool(getattr(args, "dry_run", False))
    summary = {}
    for name in names:
        src, dst = os.path.join(src_root, name), os.path.join(dst_root, name)
        inputs = tuple(getattr(args, "inputs", None) or ())
        s_files, d_files = _hr_files(src, inputs), (_hr_files(dst, inputs) if os.path.isdir(dst) else [])
        added = [r for r in s_files if r not in set(d_files)]
        changed = [r for r in s_files if r in set(d_files) and not _same(r, os.path.join(src, r), os.path.join(dst, r))]
        try:
            prev = set(json.load(open(os.path.join(dst, ".nl_sync.json"), encoding="utf-8")).get("files") or [])
        except Exception:                                        # noqa: BLE001 -- no earlier sync of this job
            prev = None
        gone = [r for r in d_files if r not in set(s_files)]
        removed = [r for r in gone if prev is not None and r in prev]
        kept = [r for r in gone if r not in set(removed)]
        if kept:
            print("kept     %s: %d file(s) not at the source and not brought in by a sync (%s%s)" % (
                name, len(kept), ", ".join(kept[:5]), ", ..." if len(kept) > 5 else ""))
        extra = []
        for r in changed:
            if _nl_written(r):
                for suf in CK.NL_BACKUP_SUFFIXES:
                    if os.path.exists(os.path.join(dst, r + suf)):
                        extra.append(r + suf)
        summary[name] = dict(added=added, changed=changed, removed=removed + extra)
        quiet = bool(getattr(args, "quiet", False))
        for r in added + changed:
            if not quiet:
                print("%-8s %s/%s" % ("add" if r in added else "update", name, r))
            if not dry:
                os.makedirs(os.path.dirname(os.path.join(dst, r)), exist_ok=True)
                tmp = os.path.join(dst, r) + ".nl_sync_tmp"
                shutil.copy2(os.path.join(src, r), tmp)
                os.replace(tmp, os.path.join(dst, r))
        for r in removed + extra:                                # removals are always listed
            print("%-8s %s/%s" % ("remove", name, r))
            if not dry:
                os.remove(os.path.join(dst, r))
        if not dry and (added or changed or removed or extra or not os.path.exists(os.path.join(dst, ".nl_sync.json"))):
            os.makedirs(dst, exist_ok=True)
            json.dump(dict(source=src, time=_now(), added=added, changed=changed, removed=removed + extra,
                           inputs=CK.hr_digest(dst), files=s_files),
                      open(os.path.join(dst, ".nl_sync.json"), "w", encoding="utf-8"), indent=1)
        print("%s: %d added, %d updated, %d removed%s" % (name, len(added), len(changed), len(removed) + len(extra),
                                                         " (dry run)" if dry else ""))
    others = sorted(x for x in (os.listdir(dst_root) if os.path.isdir(dst_root) else [])
                    if os.path.isdir(os.path.join(dst_root, x)) and x not in names and not args.jobs)
    if others:
        print("left alone (not in the source): %s" % ", ".join(others))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nl_orchestrate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--queue", required=True); p.add_argument("--jobs", nargs="+", required=True)
    p.add_argument("--analyses", nargs="+", default=["pushover", "nlrha", "ddm"], choices=["pushover", "nlrha", "ddm"])
    p.add_argument("--engine"); p.add_argument("--python", default=DEFAULT_PY); p.add_argument("--heavy", default=DEFAULT_HEAVY)
    p.add_argument("--force", action="store_true")
    p.add_argument("--speed-factor", type=float, default=None,
                   help="this machine against the reference machine for the DDM time limit (the owner's PC 1.0, the "
                        "2-core box 1.6); default $SNL_SPEED_FACTOR or 1.0")
    p.add_argument("--job-args", nargs="+", default=[], metavar="JOB:KIND=ARGS",
                   help="per-job options, e.g. 'IN_Ex19*:pushover=--dirs Y --tail none' (JOB and KIND take * wildcards)")
    n = sub.add_parser("next"); n.add_argument("--queue", required=True)
    n.add_argument("--budget", type=float, default=6900.0, help="seconds this call may take (default 6 900: under 2 h)")
    n.add_argument("--max-steps", type=int, default=0); n.add_argument("--dry-run", action="store_true")
    n.add_argument("--stop-on-failure", action="store_true")
    s = sub.add_parser("status"); s.add_argument("--queue", required=True)
    u = sub.add_parser("unstall"); u.add_argument("--queue", required=True)
    g = u.add_mutually_exclusive_group(required=True); g.add_argument("--step"); g.add_argument("--job")
    rf = sub.add_parser("refresh"); rf.add_argument("--queue", required=True); rf.add_argument("--engine")
    rf.add_argument("--include-code", action="store_true"); rf.add_argument("--dry-run", action="store_true")
    sy = sub.add_parser("sync"); sy.add_argument("--from", dest="src", required=True); sy.add_argument("--to", dest="dst", required=True)
    sy.add_argument("--jobs", nargs="+", default=[]); sy.add_argument("--dry-run", action="store_true")
    x = sub.add_parser("_exec", help="internal: one chunk inside the heavy slot")
    x.add_argument("--deadline", required=True); x.add_argument("--chunk", required=True); x.add_argument("--stamp", required=True)
    x.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if a.cmd == "_exec":
        a.command = a.command[1:] if a.command[:1] == ["--"] else a.command
        return _exec(a)
    r = {"plan": plan, "next": next_steps, "status": status, "unstall": unstall, "refresh": refresh, "sync": sync}[a.cmd](a)
    return r if isinstance(r, int) else 0          # plan / status / refresh / sync return data (for callers); exit 0


if __name__ == "__main__":
    sys.exit(main() or 0)
