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
MARGIN_S = 300.0                    # a chunk ends this long before the budget (the journal save, the report)
MIN_CHUNK_S = 600.0                 # no step is started with less than this left
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
    d = dict(version=1, created=_now(), nl_root=NL_ROOT, heavy=args.heavy,
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


def run_step(q, d, s, remaining, dry=False, runner=None):
    """One chunk of step `s` with `remaining` seconds left in this call. Returns the exit code."""
    deadline = time.time() + remaining - MARGIN_S
    timeout = int(remaining - MARGIN_S / 2)
    env = dict(os.environ, **{k: v for k, v in (d.get("env") or {}).items() if v is not None})
    env["SNL_DEADLINE"] = "%.0f" % deadline
    env["PYTHONPATH"] = d.get("nl_root", NL_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = list(s["cmd"])
    if s["kind"] in ("pushover", "ddm", "nlrha"):
        cmd += ["--chunk-seconds", "%.0f" % (remaining - MARGIN_S)]
    full = [d.get("heavy") or DEFAULT_HEAVY, "timeout", str(timeout)] + cmd
    t0 = time.time()
    print("[%s] %s: %s" % (_now(), s["id"], " ".join(shlex.quote(c) for c in full)), flush=True)
    if dry:
        return 0
    logp = os.path.join(s["job"], "nl_orchestrate_%s.log" % s["id"].split("/")[-1])
    with open(logp, "a", encoding="utf-8") as lf:
        lf.write("\n==== %s chunk start %s\n" % (s["id"], _now())); lf.flush()
        rc = (runner or subprocess.call)(full, stdout=lf, stderr=subprocess.STDOUT, env=env, cwd=d.get("nl_root", NL_ROOT))
    sec = time.time() - t0
    s["chunks"].append(dict(start=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0)), end=_now(), rc=rc, seconds=round(sec)))
    s["state"] = "done" if rc == 0 else ("resume" if rc in (EXIT_RESUME, 124) else "failed")
    if rc == 124:
        s["note_timeout"] = "killed at the chunk timeout: resumes from the last journal save (5 min)"
    _log(q, "%s  %s  %-48s rc=%s seconds=%.0f state=%s" % (s["chunks"][-1]["start"], s["chunks"][-1]["end"], s["id"], rc, sec,
                                                           s["state"]))
    save(q, d)
    return rc


def next_steps(args, runner=None):
    """Run ready steps until the budget is spent (or --max-steps chunks). A step that ends 'resume' is run again at
    once while time remains -- each chunk replays its journal, so consecutive chunks are only worth it with time to
    spare (MIN_CHUNK_S)."""
    lockf = open(args.queue + ".lock", "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit("another `next` is running on %s" % args.queue)
    t_end = time.time() + args.budget
    n = 0
    d_dry = None
    while True:
        d = d_dry if (args.dry_run and d_dry is not None) else load(args.queue)
        ready = [s for s in d["steps"] if _ready(d, s)]
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
        rc = run_step(args.queue, d, s, remaining, dry=args.dry_run, runner=runner)
        n += 1
        if args.dry_run:                               # print the commands in order, change nothing on disk
            d_dry = d if n == 1 else d_dry
            s["state"] = "done"
            continue
        if rc not in (0, EXIT_RESUME, 124) and args.stop_on_failure:
            print("step %s failed (rc %s); stopping" % (s["id"], rc))
            return rc


def status(args):
    d = load(args.queue)
    print("%-52s %-8s %6s %8s" % ("step", "state", "chunks", "seconds"))
    for s in d["steps"]:
        print("%-52s %-8s %6d %8d" % (s["id"], s["state"], len(s["chunks"]), sum(c["seconds"] for c in s["chunks"])))
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
    a = ap.parse_args(argv)
    r = {"plan": plan, "next": next_steps, "status": status}[a.cmd](a)
    return r if isinstance(r, int) else 0          # plan / status return the queue (for callers), the CLI exits 0


if __name__ == "__main__":
    sys.exit(main() or 0)
