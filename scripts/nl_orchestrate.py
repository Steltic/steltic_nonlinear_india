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
    python scripts/nl_orchestrate.py next   --queue Q.json [--budget 6900] [--max-steps N] [--dry-run]
    python scripts/nl_orchestrate.py status --queue Q.json
    python scripts/nl_orchestrate.py unstall --queue Q.json (--step <id> | --job <job name>)

Files next to the queue: Q.json.runtime.log (one line per chunk: start, end, step, exit code, seconds) and
Q.json.lock (one `next` at a time). The analysis commands are the October re-run commands (tools/step.sh,
run_ddm.sh) with the checkpoint options added; nothing here changes an analysis.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
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


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def load(q):
    return json.load(open(q, encoding="utf-8"))


def save(q, d):
    tmp = q + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, q)


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


def plan(args):
    if os.path.exists(args.queue) and not args.force:
        raise SystemExit("queue %s exists (use --force to rewrite it)" % args.queue)
    steps = []
    for j in args.jobs:
        steps += _job_steps(os.path.abspath(j), set(args.analyses), args.python)
    d = dict(version=1, created=_now(), nl_root=NL_ROOT, heavy=args.heavy, python=args.python,
             env=dict(STELTIC_ENGINE_DIR=os.path.abspath(args.engine) if args.engine else os.environ.get("STELTIC_ENGINE_DIR", ""),
                      MPLBACKEND="Agg", RAG_API_URL="", PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0"),
             steps=steps)
    save(args.queue, d)
    print("planned %d steps for %d job(s) -> %s" % (len(steps), len(args.jobs), args.queue))
    return d


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
        had = None
    after = progress_of(s)
    is_full = (had if had is not None else chunk) >= FULL_SHARE * full_chunk
    ch = dict(start=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)), end=_now(), rc=rc, seconds=round(sec),
              progress=after, had_s=round(had) if had is not None else None, full=bool(is_full))
    s["chunks"].append(ch)
    s.pop("stalled_reason", None)
    if rc == 0:
        s["state"] = "done"
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
    _log(q, "%s  %s  %-48s rc=%s seconds=%.0f state=%s%s" % (ch["start"], ch["end"], s["id"], rc, sec, s["state"],
                                                             (" (%s)" % s["stalled_reason"]) if s.get("stalled_reason") else ""))
    save(q, d)
    return rc


def _exec(a):
    """Inside the heavy slot: the chunk's deadline from now (never past the outer deadline), stamped for run_step, and
    the command run under it with a timeout (exit 124 when it is killed)."""
    t0 = time.time()
    dl = min(float(a.deadline), t0 + float(a.chunk))
    with open(a.stamp, "w", encoding="utf-8") as f:
        json.dump(dict(slot_start=t0, deadline=dl), f)
    env = dict(os.environ, SNL_DEADLINE="%.0f" % dl)
    try:
        return subprocess.call(a.command, env=env, timeout=max(1.0, dl - t0 + MARGIN_S / 2))
    except subprocess.TimeoutExpired:
        return 124


def next_steps(args, runner=None):
    """Run ready steps until the budget is spent (or --max-steps chunks). Re-check M3 a: a step that ends 'resume'
    (exit 75 / 124) is NOT run again in the same call -- what is left would be a part-chunk that mostly replays -- the
    call moves on to other ready steps; the next call gives it a full chunk."""
    lockf = open(args.queue + ".lock", "w")
    try:
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
    print("%-52s %-8s %6s %8s" % ("step", "state", "chunks", "seconds"))
    for s in d["steps"]:
        print("%-52s %-8s %6d %8d" % (s["id"], s["state"], len(s["chunks"]), sum(c["seconds"] for c in s["chunks"])))
        if s.get("stalled_reason"):
            print("    stalled: %s" % s["stalled_reason"])
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nl_orchestrate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--queue", required=True); p.add_argument("--jobs", nargs="+", required=True)
    p.add_argument("--analyses", nargs="+", default=["pushover", "nlrha", "ddm"], choices=["pushover", "nlrha", "ddm"])
    p.add_argument("--engine"); p.add_argument("--python", default=DEFAULT_PY); p.add_argument("--heavy", default=DEFAULT_HEAVY)
    p.add_argument("--force", action="store_true")
    n = sub.add_parser("next"); n.add_argument("--queue", required=True)
    n.add_argument("--budget", type=float, default=6900.0, help="seconds this call may take (default 6 900: under 2 h)")
    n.add_argument("--max-steps", type=int, default=0); n.add_argument("--dry-run", action="store_true")
    n.add_argument("--stop-on-failure", action="store_true")
    s = sub.add_parser("status"); s.add_argument("--queue", required=True)
    u = sub.add_parser("unstall"); u.add_argument("--queue", required=True)
    g = u.add_mutually_exclusive_group(required=True); g.add_argument("--step"); g.add_argument("--job")
    x = sub.add_parser("_exec", help="internal: one chunk inside the heavy slot")
    x.add_argument("--deadline", required=True); x.add_argument("--chunk", required=True); x.add_argument("--stamp", required=True)
    x.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if a.cmd == "_exec":
        a.command = a.command[1:] if a.command[:1] == ["--"] else a.command
        return _exec(a)
    r = {"plan": plan, "next": next_steps, "status": status, "unstall": unstall}[a.cmd](a)
    return r if isinstance(r, int) else 0          # plan / status return the queue (for callers), the CLI exits 0


if __name__ == "__main__":
    sys.exit(main() or 0)
