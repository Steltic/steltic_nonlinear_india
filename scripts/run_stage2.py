#!/usr/bin/env python3
"""run_stage2.py -- every stage-2 nonlinear analysis on one PC, in one command, resumable (Windows first).

    python scripts/run_stage2.py plan   --gold <gold bundle .zip or folder> [--workers 12]       # what would run, how long
    python scripts/run_stage2.py run    --gold <gold bundle .zip or folder> [--workers 12] [--engine <steel_engine>]
    python scripts/run_stage2.py status [--work <folder>]
    python scripts/run_stage2.py bundle [--work <folder>]                                      # write the results zip again

On Windows the owner runs `windows\\Run-Stage2.bat <gold bundle>` (it makes the Python environment and calls `run`);
see RUN_STAGE2.md. Defaults: work folder <home>/india/stage2_work, results folder <home>/india/_claude_stage, workers =
the CPU count less 2, the DDM speed factor 1.0 (the owner's PC: 2,400 s for a sweep's first step size).

What a run does:
  1. the gold job folders (the folder or the extracted zip) are synced into <work>/jobs: HR files plus the NL inputs
     of the bundle (hinge_params_collected.json, nl_plan.json); NL outputs in the work folder are never touched
     (nl_orchestrate.sync);
  2. the queue <work>/stage2_queue.json gets one step per analysis and job, the same analyses and options as the
     stage-2 plan (nl_orchestrate._job_steps): the HR gravity record, the pushover (X and Y), the NLRHA (11 pairs,
     DBE + MCE), the DDM, and the report (the design criteria, the four-analyses page, the gate). On a later run the
     queue is kept: finished steps whose inputs changed are put back (nl_orchestrate.refresh), new jobs are added;
  3. the steps run side by side on --workers processes: a pushover takes one, an NLRHA or a DDM takes several (its
     records / sweeps in a pool), within a memory budget; the longest jobs start first. After a pushover or an NLRHA
     the NL-21 yield check of the elastic gravity members runs; members above first yield are promoted to fibre and
     the analysis runs again (two rounds at most, as `snl run`);
  4. at the end ONE results zip is written into the results folder: every job folder with its outputs (journals and
     record caches left out) and STAGE2_MANIFEST.json -- what ran, what was skipped and why, the engine and code
     fingerprints, the timings, peak memory, and the sha256 of every file.

Resumable: a pushover and a DDM are journaled (--checkpoint-dir), the NLRHA keeps every finished record
(--record-cache), and the queue keeps every finished step. If the PC sleeps, the analyses simply continue when it
wakes; while the runner works it asks Windows not to sleep. If the PC restarts or the window is closed, run the same
command again: finished steps are kept, the interrupted ones continue from their last save (5 minutes of work lost
at most).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NL_ROOT = os.path.dirname(HERE)
for _p in (HERE, NL_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import nl_orchestrate as NO                                     # noqa: E402

KINDS = ("gravity", "pushover", "nlrha", "ddm", "report")
NL_INPUT_FILES = ("hinge_params_collected.json", "nl_plan.json")   # NL inputs a gold bundle carries (not outputs)
RESULTS_SKIP = ("nl_checkpoints", "*.before_refresh_*", "__pycache__", "*.pyc", ".nl_orchestrate_*", "*.nl_sync_tmp",
                "*.zip_tmp")
PROMOTION_ROUNDS = 2                                          # snl run: at most two NL-21 promotion rounds
SPEED_FACTOR = 1.0                                            # the owner's PC is the reference machine
NLRHA_RECORDS = 22                                            # 11 pairs x (DBE, MCE)
STATE_TERMINAL = ("done", "failed", "stalled", "skipped")
QUEUE_NAME = "stage2_queue.json"


def _home():
    return os.environ.get("USERPROFILE") or os.path.expanduser("~")


DEFAULT_WORK = os.path.join(_home(), "india", "stage2_work")
DEFAULT_RESULTS = os.path.join(_home(), "india", "_claude_stage")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _say(msg, log=None):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ------------------------------------------------------------------------------------------------- the machine
def total_ram_gb():
    """Physical memory in GB (Windows: GlobalMemoryStatusEx; Linux: /proc/meminfo); 16 when it cannot be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2 ** 30
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 2 ** 20
    except Exception:                                            # noqa: BLE001
        pass
    return 16.0


def keep_awake(on=True):
    """Windows: ask the system not to sleep while the runner works (SetThreadExecutionState); elsewhere nothing."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
        return True
    except Exception:                                            # noqa: BLE001
        return False


def pid_alive(pid):
    if not pid:
        return False
    try:
        if sys.platform == "win32":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))       # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return code.value == 259                                            # STILL_ACTIVE
        os.kill(int(pid), 0)
        return True
    except Exception:                                            # noqa: BLE001
        return False


def tree_rss_mb(pid):
    """Resident memory of a process and all its descendants (MB): psutil when installed, else Linux /proc; None."""
    try:
        import psutil
        p = psutil.Process(pid)
        procs = [p] + p.children(recursive=True)
        return sum(x.memory_info().rss for x in procs if x.is_running()) / 2 ** 20
    except ImportError:
        pass
    except Exception:                                            # noqa: BLE001 -- the process just ended
        return None
    if not os.path.isdir("/proc"):
        return None
    try:
        kids = {}
        for d in os.listdir("/proc"):
            if d.isdigit():
                try:
                    pp = int(open("/proc/%s/stat" % d).read().rsplit(")", 1)[1].split()[1])
                    kids.setdefault(pp, []).append(int(d))
                except Exception:                                # noqa: BLE001
                    continue
        tot, todo = 0, [pid]
        page = os.sysconf("SC_PAGE_SIZE")
        while todo:
            x = todo.pop()
            try:
                tot += int(open("/proc/%d/statm" % x).read().split()[1]) * page
            except Exception:                                    # noqa: BLE001
                pass
            todo += kids.get(x, [])
        return tot / 2 ** 20
    except Exception:                                            # noqa: BLE001
        return None


def children_cpu_s():
    """POSIX: CPU seconds (user + system) of every child this process has reaped, with their own reaped children --
    read just before and after one step's process is reaped, the difference is that step's CPU exactly. None on
    Windows (no resource module): the step's process tree is sampled instead (tree_cpu_s)."""
    try:
        import resource
    except ImportError:
        return None
    u = resource.getrusage(resource.RUSAGE_CHILDREN)
    return u.ru_utime + u.ru_stime


def tree_cpu_s(pid):
    """{(pid, start time): CPU seconds so far} of a process and its descendants (psutil); {} without psutil."""
    try:
        import psutil
        p = psutil.Process(pid)
        out = {}
        for x in [p] + p.children(recursive=True):
            try:
                t = x.cpu_times()
                out[(x.pid, x.create_time())] = t.user + t.system
            except Exception:                                    # noqa: BLE001 -- it just ended
                pass
        return out
    except Exception:                                            # noqa: BLE001
        return {}


def kill_tree(proc):
    """Stop a step's process and its pool workers."""
    try:
        if sys.platform == "win32":
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:                                            # noqa: BLE001
        try:
            proc.kill()
        except Exception:                                        # noqa: BLE001
            pass


# --------------------------------------------------------------------------------------------- the gold bundle
def _sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def find_jobs(root):
    """Job folders under `root` (relative paths with '/'): every folder holding cfg.py and model_opensees.py, a
    building's units included; NL output folders are not searched."""
    out = []
    for r, dirs, files in os.walk(root):
        rel = os.path.relpath(r, root)
        dirs[:] = sorted(d for d in dirs if not NO._is_nl(d) and not NO._skipped(d) and d not in ("design", "figs", "rag"))
        if "cfg.py" in files and "model_opensees.py" in files and rel != ".":
            out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def gold_root(path, work, log=None):
    """The folder holding the gold building folders: `path` itself, a folder inside it, or the extracted zip (kept in
    <work>/gold/<name>_<sha8>, extracted once). Returns (root, source description)."""
    path = os.path.abspath(path)
    src = dict(path=path)
    if os.path.isfile(path):
        if not zipfile.is_zipfile(path):
            raise SystemExit("--gold %s: neither a folder nor a .zip" % path)
        sha = _sha256(path)
        src.update(kind="zip", sha256=sha, bytes=os.path.getsize(path))
        dest = os.path.join(work, "gold", "%s_%s" % (os.path.splitext(os.path.basename(path))[0], sha[:8]))
        if not os.path.exists(os.path.join(dest, ".extracted")):
            _say("extracting the gold bundle into %s" % dest, log)
            shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest)
            with zipfile.ZipFile(path) as z:
                for m in z.infolist():
                    target = os.path.normpath(os.path.join(dest, m.filename))
                    if not target.startswith(os.path.normpath(dest) + os.sep) and target != os.path.normpath(dest):
                        raise SystemExit("gold bundle: unsafe path %r" % m.filename)
                z.extractall(dest)
            open(os.path.join(dest, ".extracted"), "w").write(_now())
        path = dest
    elif os.path.isdir(path):
        src.update(kind="folder")
    else:
        raise SystemExit("--gold %s: not found" % path)
    jobs = find_jobs(path)
    if not jobs:
        raise SystemExit("--gold %s: no job folders (a job folder holds cfg.py and model_opensees.py)" % path)
    tops = sorted({j.split("/")[0] for j in jobs})
    # the folder whose children are the building folders (a bundle may wrap them in one more folder)
    while len(tops) == 1 and not os.path.exists(os.path.join(path, tops[0], "cfg.py")):
        path = os.path.join(path, tops[0])
        jobs = find_jobs(path)
        tops = sorted({j.split("/")[0] for j in jobs})
    src["root"] = path
    return path, src


# ------------------------------------------------------------------------------------------------- estimates
def load_estimates():
    try:
        return json.load(open(os.path.join(HERE, "stage2_estimates.json"), encoding="utf-8")).get("jobs") or {}
    except Exception:                                            # noqa: BLE001
        return {}


def element_count(job):
    try:
        import re
        return len(re.findall(r"\belement\(", open(os.path.join(job, "model_opensees.py"), encoding="utf-8",
                                                   errors="replace").read()))
    except OSError:
        return 0


def estimate_for(job_id, elements, table=None):
    """PC seconds of one job's analyses: the October figure for a known job (stage2_estimates.json), else a
    proportion of the element count fitted to the known jobs (planning only)."""
    table = load_estimates() if table is None else table
    if job_id in table:
        e = dict(table[job_id]); e["basis"] = "October runs (%s)" % e.get("measured_on", "")
        return e
    known = [v for v in table.values() if v.get("elements")]
    def rate(k):
        num = sum(v.get(k) or 0 for v in known); den = sum(v["elements"] for v in known)
        return (num / den) if den else 0.0
    n = max(1, int(elements or 0))
    return dict(elements=n, pushover_s=round(rate("pushover_s") * n), nlrha_total_s=round(rate("nlrha_total_s") * n),
                nlrha_longest_s=round(rate("nlrha_longest_s") * n), ddm_work_s=round(rate("ddm_work_s") * n),
                ddm_longest_s=round(rate("ddm_longest_s") * n), ddm_sweeps=25,
                basis="no October run: scaled from the element count (%d)" % n)


def step_seconds(s, width):
    """Estimated wall seconds of a step on `width` workers."""
    e = s.get("estimate") or {}
    k = s["kind"]
    if k == "pushover":
        return float(e.get("pushover_s") or 60)
    if k == "nlrha":
        return max(float(e.get("nlrha_longest_s") or 0), float(e.get("nlrha_total_s") or 0) / max(1, width)) + 30
    if k == "ddm":
        return max(float(e.get("ddm_longest_s") or 0), float(e.get("ddm_work_s") or 0) / max(1, width)) + 30
    return 60.0 + 0.05 * float(e.get("elements") or 0)                     # gravity, report


# ------------------------------------------------------------------------------------------------- the queue
def per_worker_gb(elements):
    """Memory of one analysis process (GB): October, IN_Ex19 (1,308 elements): an NLRHA worker 0.47 GB, a DDM worker
    0.50 GB; with a margin."""
    return 0.3 + 0.0003 * float(elements or 0)


def step_memory_gb(s, width):
    el = float((s.get("estimate") or {}).get("elements") or 0)
    if s["kind"] == "pushover":                         # the arc-length tail: the stem (540 elements) reached 5 GB
        return min(6.0, 1.0 + 0.008 * el)
    if s["kind"] in ("nlrha", "ddm"):
        return 0.5 + per_worker_gb(el) * max(1, width)
    return 1.0


def want_width(s, workers):
    if s["kind"] == "nlrha":
        return max(1, min(workers, NLRHA_RECORDS))
    if s["kind"] == "ddm":
        return max(1, min(workers, int((s.get("estimate") or {}).get("ddm_sweeps") or 25)))
    return 1


def min_width(s, workers):
    return max(1, min(want_width(s, workers), workers // 3)) if s["kind"] in ("nlrha", "ddm") else 1


def job_steps(job, job_id, py="{python}"):
    """The steps of one job, as nl_orchestrate._job_steps (the same analyses and options), with the pool sizes left
    as '{workers}', no chunk budget, and the report step making the design criteria first. `after` (for `refresh`)
    lists every earlier step; `needs` the ones that must have FINISHED (gravity); the rest only have to have ended."""
    steps = NO._job_steps(job, {"pushover", "nlrha", "ddm"}, py)
    out = []
    for s in steps:
        s = dict(s)
        s["id"] = "%s/%s" % (job_id, s["kind"])
        c = list(s["cmd"])
        if s["kind"] == "nlrha":
            c[c.index("--parallel") + 1] = "{workers}"
        elif s["kind"] == "ddm":
            c[c.index("--workers") + 1] = "{workers}"
            c += ["--speed-factor", "%g" % SPEED_FACTOR]
        elif s["kind"] == "report":
            s["pre"] = [[py, "-m", "nlrha", "criteria", job]]
        s["cmd"] = c
        out.append(s)
    ids = {s["kind"]: s["id"] for s in out}
    for s in out:
        k = s["kind"]
        s["needs"] = [] if k == "gravity" else [ids["gravity"]]
        s["after"] = {"gravity": [], "pushover": [ids["gravity"]], "nlrha": [ids["gravity"], ids["pushover"]],
                      "ddm": [ids["gravity"]], "report": [ids[x] for x in ("gravity", "pushover", "nlrha", "ddm")]}[k]
    return out


def skip_reasons(job):
    """Why a job's analyses cannot run here, if they cannot."""
    if not os.path.exists(os.path.join(job, "hinge_params_collected.json")):
        return ("no hinge_params_collected.json: the collected IS specification values (snl collect) are not in the "
                "gold bundle for this job")
    return None


def plan_queue(work, jobs_root, job_ids, args, src, log=None):
    """A new queue, or the existing one brought up to date (new jobs added, the stale steps put back)."""
    q = os.path.join(work, QUEUE_NAME)
    eng = os.path.abspath(args.engine) if getattr(args, "engine", None) else ""
    table = load_estimates()
    if os.path.exists(q):
        d = NO.load(q)
        d["env"]["STELTIC_ENGINE_DIR"] = eng or d["env"].get("STELTIC_ENGINE_DIR", "")
        NO.save(q, d)
        plan_ = NO.refresh(argparse.Namespace(queue=q, engine=None, include_code=False, dry_run=False))
        d = NO.load(q)
        for sid, (state, reason) in plan_.items():          # a design change: the old fibre promotions go too
            s = next(x for x in d["steps"] if x["id"] == sid)
            if s["kind"] == "gravity" and "input files changed" in reason:
                p = os.path.join(s["job"], "nl_promote_fibre.json")
                if os.path.exists(p):
                    os.replace(p, p + ".before_refresh_" + time.strftime("%Y%m%d%H%M%S"))
                    _say("%s: the design changed -- the earlier fibre promotions set aside" % sid, log)
        have = {s["id"].rsplit("/", 1)[0] for s in d["steps"]}
    else:
        d = dict(version=1, kind="stage2_pc", created=_now(), nl_root=NL_ROOT, python="{python}",
                 env=dict(STELTIC_ENGINE_DIR=eng, MPLBACKEND="Agg", RAG_API_URL="", PYTHONDONTWRITEBYTECODE="1",
                          PYTHONHASHSEED="0", SNL_SPEED_FACTOR="%g" % SPEED_FACTOR, OMP_NUM_THREADS="1",
                          PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),   # Windows: reports print lambda, +/- ...
                 steps=[])
        have = set()
    d["gold"] = src
    for jid in job_ids:
        if jid in have:
            continue
        job = os.path.join(jobs_root, *jid.split("/"))
        steps = job_steps(job, jid)
        est = estimate_for(jid, element_count(job), table)
        why = skip_reasons(job)
        for s in steps:
            s["estimate"] = est
            if why and s["kind"] != "report":
                s["state"], s["skip_reason"] = "skipped", why
            elif why:
                s["state"], s["skip_reason"] = "skipped", "no analyses ran (see the other steps)"
        for spec in getattr(args, "job_args", None) or []:      # per-job options (nl_orchestrate --job-args)
            try:
                NO.apply_job_args([s for s in steps if s["state"] == "pending"], [spec])
            except SystemExit:
                pass                                             # a spec for another job
        d["steps"] += steps
    for spec in getattr(args, "job_args", None) or []:          # a spec must match some step of the queue
        if not any(spec.split("=", 1)[1] in (s.get("job_args") or []) for s in d["steps"]):
            raise SystemExit("--job-args %r matches no new step (job args apply when a job enters the queue)" % spec)
    for s in d["steps"]:
        if s["state"] == "running":                              # an interrupted run: continue those steps
            s["state"] = "resume"
            s.setdefault("notes", []).append("%s interrupted (the runner stopped); continues from its last save" % _now())
        elif s["state"] == "skipped" and (s.get("skip_reason") or "").startswith(("no hinge_params", "no analyses ran")):
            if skip_reasons(s["job"]) is None:                   # the bundle has the collected values now
                s["state"] = "pending"; s.pop("skip_reason", None)
        elif s["state"] in ("failed", "stalled") and getattr(args, "retry_failed", False):
            s["state"] = "resume" if s["chunks"] else "pending"
            s.setdefault("notes", []).append("%s put back by --retry-failed" % _now())
    NO.save(q, d)
    return q, d


# ----------------------------------------------------------------------------------------------- scheduling
class Scheduler:
    """Starts ready steps on `workers` processes within `mem_gb`, longest jobs first. Used by the live run
    (run_queue) and by the estimate (simulate, with the estimated durations): the same decisions in both."""

    def __init__(self, d, workers, mem_gb):
        self.d, self.workers, self.mem_gb = d, int(workers), float(mem_gb)
        self.running = {}                                        # step id -> (width, mem)

    def by_id(self):
        return {s["id"]: s for s in self.d["steps"]}

    def ready(self):
        st = self.by_id()
        out = []
        for s in self.d["steps"]:
            if s["state"] not in ("pending", "resume") or s["id"] in self.running:
                continue
            if any(st[n]["state"] != "done" for n in s.get("needs") or [] if n in st):
                if any(st[n]["state"] in STATE_TERMINAL for n in s.get("needs") or [] if n in st):
                    s["state"], s["skip_reason"] = "skipped", "the HR gravity record of this job did not finish"
                continue
            if any(st[a]["state"] not in STATE_TERMINAL for a in s.get("after") or [] if a in st):
                continue
            out.append(s)
        rem = self.remaining_by_job()
        order = {k: i for i, k in enumerate(KINDS)}
        out.sort(key=lambda s: (-rem.get(s["id"].rsplit("/", 1)[0], 0.0), order.get(s["kind"], 9)))
        return out

    def remaining_by_job(self):
        rem = {}
        for s in self.d["steps"]:
            if s["state"] not in STATE_TERMINAL:
                j = s["id"].rsplit("/", 1)[0]
                rem[j] = rem.get(j, 0.0) + step_seconds(s, want_width(s, self.workers))
        return rem

    def picks(self):
        """The steps to start now, with their widths."""
        free = self.workers - sum(w for w, _ in self.running.values())
        mem = self.mem_gb - sum(m for _, m in self.running.values())
        out = []
        for s in self.ready():
            if free < 1:
                break
            w = min(want_width(s, self.workers), free)
            if w < min_width(s, self.workers) and (self.running or out):
                continue
            m = step_memory_gb(s, w)
            if m > mem and (self.running or out):
                continue
            out.append((s, w, m))
            free -= w; mem -= m
        return out


def simulate(d, workers, mem_gb):
    """Wall seconds of the queue's unfinished steps on `workers` processes, with the estimated durations."""
    import copy
    d = copy.deepcopy(d)
    sch = Scheduler(d, workers, mem_gb)
    t, ends, timeline = 0.0, {}, []
    while True:
        for s, w, m in sch.picks():
            sch.running[s["id"]] = (w, m)
            s["state"] = "running"
            ends[s["id"]] = t + step_seconds(s, w)
            timeline.append((t, s["id"], w))
        if not sch.running:
            break
        sid = min(sch.running, key=lambda k: ends[k])
        t = ends.pop(sid)
        sch.running.pop(sid)
        next(x for x in d["steps"] if x["id"] == sid)["state"] = "done"
    return t, timeline


# ------------------------------------------------------------------------------------------------- execution
def fill(cmd, py, width):
    return [py if c == "{python}" else (str(width) if c == "{workers}" else c) for c in cmd]


class Run:
    """One step running: its command list (the report's criteria first), the log, the peak memory."""

    def __init__(self, s, width, mem, py, env, cwd):
        self.s, self.width, self.mem, self.py, self.env, self.cwd = s, width, mem, py, env, cwd
        self.cmds = [fill(c, py, width) for c in (s.get("pre") or [])] + [fill(s["cmd"], py, width)]
        self.i, self.proc, self.peak, self.t0 = 0, None, None, time.time()
        self.cpu, self._seen = 0.0, {}                          # CPU seconds of the finished commands; tree samples
        self.logp = os.path.join(s["job"], "stage2_%s.log" % s["kind"])
        self.rcs = []

    def start_next(self):
        cmd = self.cmds[self.i]
        lf = open(self.logp, "a", encoding="utf-8")
        lf.write("\n==== %s %s (workers %d)\n$ %s\n" % (_now(), self.s["id"], self.width, " ".join(shlex.quote(c) for c in cmd)))
        lf.flush()
        kw = dict(creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if sys.platform == "win32" \
            else dict(start_new_session=True)
        self.proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=self.env, cwd=self.cwd, **kw)
        self._lf = lf

    def poll(self):
        """None while running; the exit code when the last command has ended (or a command failed)."""
        m = tree_rss_mb(self.proc.pid)
        if m is not None:
            self.peak = max(self.peak or 0.0, m)
        c0 = children_cpu_s()
        if c0 is None:                                          # Windows: sample the tree (the last poll is lost)
            self._seen.update(tree_cpu_s(self.proc.pid))
        rc = self.proc.poll()
        if rc is None:
            return None
        c1 = children_cpu_s()
        self.cpu += (c1 - c0) if c0 is not None else sum(self._seen.values())
        self._seen = {}
        self._lf.close()
        self.rcs.append(rc)
        if self.i + 1 < len(self.cmds):                          # the report's design criteria: never blocks the report
            self.i += 1
            self.start_next()
            return None
        return rc


def flagged_elastic(job, kind):
    from snl.cli import flagged_elastic as F
    return F(job, kind)


def promote(job, tags, why, analysis):
    """NL-21 (pushover/elastic_gravity.promote, without importing OpenSees here): add the tags to
    <job>/nl_promote_fibre.json under `analysis`."""
    p = os.path.join(job, "nl_promote_fibre.json")
    try:
        d = json.load(open(p, encoding="utf-8")) or {}
    except Exception:                                            # noqa: BLE001
        d = {}
    d[analysis] = sorted({int(t) for t in (d.get(analysis) or [])} | {int(t) for t in tags})
    d["history"] = list(d.get("history") or []) + [dict(analysis=analysis, added=sorted(int(t) for t in tags), why=why)]
    d["note"] = "members promoted from elastic to fibre after the NL-21 yield check (per analysis; 'tags' = all)"
    json.dump(d, open(p, "w", encoding="utf-8"), indent=1)
    return d[analysis]


def run_queue(q, d, workers, mem_gb, py, log=None, poll_s=3.0, stop_after=None):
    """Run the queue until nothing is left to start. `stop_after` (tests): stop after this many step starts."""
    env = dict(os.environ, **{k: v for k, v in (d.get("env") or {}).items() if v is not None})
    for k in [k for k in env if k.startswith("SNL_") and k not in d.get("env", {})]:
        env.pop(k)                                               # no stray model knob from the shell
    env["PYTHONPATH"] = os.pathsep.join([x for x in (os.environ.get("STAGE2_PYTHONPATH"), NL_ROOT,
                                                     env.get("PYTHONPATH")) if x])
    sch = Scheduler(d, workers, mem_gb)
    live, started = {}, 0
    try:
        while True:
            for s, w, m in sch.picks():
                if stop_after is not None and started >= stop_after:
                    break
                r = Run(s, w, m, py, env, s["job"])     # cwd: the job folder, as the hub runs NL
                if "started_fingerprint" not in s:
                    try:
                        s["started_fingerprint"] = NO.fingerprint(d, s)
                    except Exception as ex:                      # noqa: BLE001
                        s["started_fingerprint"] = dict(error=type(ex).__name__)
                r.start_next()
                s["state"] = "running"
                s["pid"] = r.proc.pid
                sch.running[s["id"]] = (w, m)
                live[s["id"]] = r
                started += 1
                _say("start  %-60s workers %2d  (est. %s)" % (s["id"], w, _hms(step_seconds(s, w))), log)
                NO.save(q, d)
            if not live:
                break
            time.sleep(poll_s)
            for sid, r in list(live.items()):
                rc = r.poll()
                if rc is None:
                    continue
                s = r.s
                sec = time.time() - r.t0
                ch = dict(start=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(r.t0)), end=_now(), rc=rc,
                          seconds=round(sec), cpu_s=round(r.cpu, 1), workers=r.width,
                          peak_rss_mb=round(r.peak) if r.peak else None)
                s["chunks"].append(ch)
                s.pop("pid", None)
                again = False
                if rc == 0 and s["kind"] in ("pushover", "nlrha"):
                    fl = flagged_elastic(s["job"], s["kind"])
                    rounds = int(s.get("promotion_rounds") or 0)
                    if fl and rounds < PROMOTION_ROUNDS:
                        promote(s["job"], fl, "%s yield check, round %d" % (s["kind"], rounds + 1), s["kind"])
                        s["promotion_rounds"] = rounds + 1
                        s.setdefault("promoted", []).append(fl)
                        ch["promoted"] = fl
                        _say("NL-21  %s: %d elastic gravity member(s) above first yield -> fibre, the analysis runs "
                             "again (round %d)" % (s["id"], len(fl), rounds + 1), log)
                        again = True
                    elif fl:
                        s["note_promotion"] = ("%d member(s) still above first yield after %d promotion rounds (the "
                                               "gate reports them)" % (len(fl), rounds))
                if again:
                    r2 = Run(s, r.width, r.mem, py, env, s["job"])
                    r2.start_next()
                    s["pid"] = r2.proc.pid
                    live[sid] = r2
                    NO.save(q, d)
                    continue
                live.pop(sid)
                sch.running.pop(sid)
                if rc == 0:
                    s["state"] = "done"
                    try:
                        s["fingerprint"] = NO.fingerprint(d, s)
                    except Exception as ex:                      # noqa: BLE001
                        s["fingerprint"] = dict(error="%s: %s" % (type(ex).__name__, ex))
                    if s["kind"] == "gravity":
                        NO.reconcile_rechecks(d, s["job"])
                elif rc == NO.EXIT_NO_PROGRESS:
                    s["state"] = "stalled"
                    s["stalled_reason"] = "the analysis reported no progress (exit 76); see %s" % r.logp
                else:
                    s["state"] = "failed"
                    s["failed_reason"] = "exit code %s; see %s" % (rc, r.logp)
                _say("%-6s %-60s rc %s, %s, CPU %s, peak %s MB" % ("done" if rc == 0 else "FAILED", sid, rc, _hms(sec),
                                                                  _hms(r.cpu),
                                                                  ch["peak_rss_mb"] if ch["peak_rss_mb"] is not None else "?"), log)
                NO.save(q, d)
    except KeyboardInterrupt:
        _say("stopped by the user: the running steps are interrupted; run the same command again to continue", log)
        for sid, r in live.items():
            kill_tree(r.proc)
            r.s["state"] = "resume"
            r.s.pop("pid", None)
        NO.save(q, d)
        raise
    return d


def _hms(s):
    s = int(s or 0)
    return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


# ------------------------------------------------------------------------------------------------- results
def _results_skip(rel):
    parts = rel.replace(os.sep, "/").split("/")
    import fnmatch
    return any(fnmatch.fnmatchcase(p, pat) for p in parts for pat in RESULTS_SKIP)


def fingerprints(d):
    """The code and engine the run used: the NL analysis code key and commit, the HR engine fingerprint and commit,
    the section tables."""
    CK = NO._ck()
    from snl.hr_gravity import engine_fingerprint
    eng = d.get("env", {}).get("STELTIC_ENGINE_DIR") or ""

    def git(path):
        try:
            r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
            sha = r.stdout.strip() if r.returncode == 0 else None
            r = subprocess.run(["git", "-C", path, "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                               text=True, timeout=20)
            return dict(commit=sha, modified=bool(r.stdout.strip())) if sha else None
        except Exception:                                        # noqa: BLE001
            return None
    return dict(nl_code_key=CK.code_key(), nl_repo=NL_ROOT, nl_git=git(NL_ROOT),
                hr_engine=eng, hr_engine_fingerprint=engine_fingerprint(eng) if eng else None,
                hr_git=git(os.path.dirname(eng)) if eng else None, section_tables=CK.section_tables_key(eng))


def nlrha_record_times(job):
    """Per NLRHA record: the wall and CPU seconds the analysis recorded (nlrha/<level>/nlrha_package.json)."""
    out = []
    for lv in ("DBE", "MCE"):
        try:
            d = json.load(open(os.path.join(job, "nlrha", lv, "nlrha_package.json"), encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for r in ((d.get("response_summary") or d).get("per_record") or []):
            out.append(dict(level=lv, record=r.get("record"), seconds=r.get("seconds"), cpu_seconds=r.get("cpu_seconds")))
    return out


def manifest(d, work, args, totals):
    jobs = {}
    for s in d["steps"]:
        jid = s["id"].rsplit("/", 1)[0]
        j = jobs.setdefault(jid, dict(folder="jobs/" + jid, steps={}))
        j["steps"][s["kind"]] = {k: s.get(k) for k in ("state", "skip_reason", "failed_reason", "stalled_reason",
                                                         "refresh_reason", "note_promotion", "promoted", "chunks",
                                                         "fingerprint", "notes") if s.get(k) is not None}
        sec = sum(c.get("seconds") or 0 for c in s.get("chunks") or [])
        j["steps"][s["kind"]]["seconds"] = sec
        # CPU time beside the wall time (all processes of the step): a pause of the PC shows as seconds >> cpu_s
        j["steps"][s["kind"]]["cpu_s"] = round(sum(c.get("cpu_s") or 0 for c in s.get("chunks") or []), 1)
        if s["kind"] == "nlrha":
            j["nlrha_records"] = nlrha_record_times(s["job"])
        pk = [c.get("peak_rss_mb") for c in s.get("chunks") or [] if c.get("peak_rss_mb") is not None]
        j["steps"][s["kind"]]["peak_rss_mb"] = max(pk) if pk else None
        if s.get("estimate"):
            j["estimate_basis"] = s["estimate"].get("basis")
        try:
            j["inputs"] = NO._ck().hr_digest(s["job"])
        except Exception:                                        # noqa: BLE001
            pass
        try:
            g = json.load(open(os.path.join(s["job"], "complete_gate.json"), encoding="utf-8"))
            j["gate"] = dict(status=g.get("status"), reasons=g.get("reasons"))
        except Exception:                                        # noqa: BLE001
            pass
    st = [s["state"] for s in d["steps"]]
    return dict(schema=1, kind="steltic nonlinear stage-2 results", created=_now(),
                host=dict(platform=platform.platform(), machine=platform.machine(), cpus=os.cpu_count(),
                          ram_gb=round(total_ram_gb(), 1), python=sys.version.split()[0]),
                settings=dict(workers=getattr(args, "workers", None), memory_gb=getattr(args, "memory_gb", None),
                              speed_factor=SPEED_FACTOR, ddm_first_rung_time_limit_s=2400.0 * SPEED_FACTOR,
                              env={k: v for k, v in (d.get("env") or {}).items()}),
                gold=d.get("gold"), fingerprints=fingerprints(d),
                summary=dict(steps=len(st), **{k: st.count(k) for k in sorted(set(st))}, **totals),
                not_done_here=["the pushover review flags of the EBF jobs (scripts/pushover_review.py --clear): the "
                               "lead, after reading the results"],
                jobs=jobs)


def write_bundle(work, d, args, results_dir, log=None, totals=None):
    """ONE results zip: jobs/<job>/... (journals and record caches left out), STAGE2_MANIFEST.json (with the sha256 of
    every file) and STAGE2_RUN.log. Written beside as <zip>.manifest.json too."""
    os.makedirs(results_dir, exist_ok=True)
    jobs_root = os.path.join(work, "jobs")
    man = manifest(d, work, args, totals or {})
    files = []
    tops = sorted({s["id"].split("/")[0] for s in d["steps"]})
    for top in tops:
        base = os.path.join(jobs_root, top)
        for r, dirs, fs in os.walk(base):
            rel_r = os.path.relpath(r, jobs_root)
            dirs[:] = sorted(x for x in dirs if not _results_skip(os.path.join(rel_r, x)))
            for f in sorted(fs):
                rel = os.path.join(rel_r, f)
                if not _results_skip(rel) and not os.path.islink(os.path.join(r, f)):
                    files.append(rel.replace(os.sep, "/"))
    stamp = time.strftime("%Y%m%d_%H%M")
    name = "stage2_results_%s.zip" % stamp
    out = os.path.join(results_dir, name)
    tmp = out + ".zip_tmp"
    sums = {}
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for rel in files:
            p = os.path.join(jobs_root, *rel.split("/"))
            sums["jobs/" + rel] = _sha256(p)
            z.write(p, "jobs/" + rel)
        man["files"] = sums
        z.writestr("STAGE2_MANIFEST.json", json.dumps(man, indent=1, default=str))
        lp = os.path.join(work, "stage2_run.log")
        if os.path.exists(lp):
            z.write(lp, "STAGE2_RUN.log")
    os.replace(tmp, out)
    json.dump(man, open(out + ".manifest.json", "w", encoding="utf-8"), indent=1, default=str)
    _say("results: %s (%d files, %.0f MB)" % (out, len(files), os.path.getsize(out) / 2 ** 20), log)
    return out, man


# ------------------------------------------------------------------------------------------------- commands
class Lock:
    """One runner per work folder (a lock file with the runner's pid; a lock whose pid is gone is taken over)."""

    def __init__(self, work):
        self.p = os.path.join(work, "stage2.lock")

    def __enter__(self):
        if os.path.exists(self.p):
            try:
                pid = int(open(self.p).read().split()[0])
            except Exception:                                    # noqa: BLE001
                pid = None
            if pid and pid != os.getpid() and pid_alive(pid):
                raise SystemExit("another run_stage2 is working in this folder (pid %s); wait for it or close it" % pid)
        open(self.p, "w").write("%d %s\n" % (os.getpid(), _now()))
        return self

    def __exit__(self, *a):
        try:
            os.remove(self.p)
        except OSError:
            pass


def _defaults(a):
    a.work = os.path.abspath(a.work or DEFAULT_WORK)
    a.results = os.path.abspath(getattr(a, "results", None) or DEFAULT_RESULTS)
    if getattr(a, "workers", None) in (None, 0):
        a.workers = max(1, (os.cpu_count() or 4) - 2)
    if getattr(a, "memory_gb", None) in (None, 0):
        a.memory_gb = round(0.8 * total_ram_gb(), 1)
    return a


def _wait_for_orphans(d, log):
    """A step of an earlier runner whose process is still alive (the runner window was closed, not the PC): wait."""
    for s in d["steps"]:
        if s.get("pid") and pid_alive(s["pid"]):
            _say("waiting for %s (pid %s) from an earlier run to end before it continues" % (s["id"], s["pid"]), log)
            while pid_alive(s["pid"]):
                time.sleep(10)


def _prepare(a, log):
    os.makedirs(a.work, exist_ok=True)
    groot, src = gold_root(a.gold, a.work, log)
    jobs_root = os.path.join(a.work, "jobs")
    os.makedirs(jobs_root, exist_ok=True)
    NO.sync(argparse.Namespace(src=groot, dst=jobs_root, jobs=list(getattr(a, "jobs", None) or []) and
                               sorted({j.split("/")[0] for j in a.jobs}), dry_run=False, inputs=NL_INPUT_FILES, quiet=True))
    ids = find_jobs(jobs_root)
    gold_ids = set(find_jobs(groot))
    ids = [j for j in ids if j in gold_ids]
    if getattr(a, "jobs", None):
        ids = [j for j in ids if j in a.jobs or j.split("/")[0] in a.jobs]
    return jobs_root, ids, src


def _zip_root(jobs):
    """The folder inside a zip whose children are the building folders (the parent of the top-most job folders)."""
    import posixpath
    tops = [j for j in jobs if not any(j.startswith(o + "/") for o in jobs if o != j)]
    parents = sorted({posixpath.dirname(t) for t in tops})
    if not parents:
        return ""
    return parents[0] if len(parents) == 1 else posixpath.commonpath(parents)


def cmd_plan(a):
    """Dry run: what would run, with the estimated time on --workers. Nothing is written (a zip is listed, not
    extracted)."""
    a = _defaults(a)
    path = os.path.abspath(a.gold)
    if os.path.isfile(path):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        dirs = {}
        for n in names:
            parts = n.rstrip("/").split("/")
            dirs.setdefault("/".join(parts[:-1]), set()).add(parts[-1])
        jobs = sorted(k for k, v in dirs.items() if {"cfg.py", "model_opensees.py"} <= v)
        pre = _zip_root(jobs)
        ids = [j[len(pre) + 1:] if pre else j for j in jobs]
        has = {j: dirs.get(j, set()) for j in jobs}
        import re
        with zipfile.ZipFile(path) as z:
            info = {i: dict(params="hinge_params_collected.json" in has[j],
                            elements=len(re.findall(r"\belement\(", z.read(j + "/model_opensees.py").decode("utf-8", "replace"))))
                    for i, j in zip(ids, jobs)}
        root = None
    else:
        root, _ = gold_root(path, a.work)
        ids = find_jobs(root)
        info = {i: dict(params=os.path.exists(os.path.join(root, *i.split("/"), "hinge_params_collected.json")),
                        elements=element_count(os.path.join(root, *i.split("/")))) for i in ids}
    if a.jobs:
        ids = [j for j in ids if j in a.jobs or j.split("/")[0] in a.jobs]
    table = load_estimates()
    d = dict(steps=[], env={})
    for jid in ids:
        job = os.path.join(root or "<work>", *jid.split("/"))
        steps = job_steps(job, jid, "python")
        est = estimate_for(jid, info[jid]["elements"] or (table.get(jid) or {}).get("elements"), table)
        for s in steps:
            s["estimate"] = est
            if not info[jid]["params"]:
                s["state"], s["skip_reason"] = "skipped", "no hinge_params_collected.json in the bundle"
        d["steps"] += steps
    for spec in a.job_args or []:
        NO.apply_job_args([s for s in d["steps"] if s["state"] == "pending"], [spec])
    print("Stage-2 plan: %d job(s) from %s; %d workers, memory budget %.0f GB, DDM speed factor %g (first rung %.0f s)"
          % (len(ids), path, a.workers, a.memory_gb, SPEED_FACTOR, 2400 * SPEED_FACTOR))
    tot_serial = 0.0
    for jid in ids:
        ss = [s for s in d["steps"] if s["id"].rsplit("/", 1)[0] == jid]
        e = ss[0]["estimate"]
        ser = sum(step_seconds(s, 1) for s in ss if s["state"] != "skipped")
        tot_serial += ser
        print("\n%s  [%s]%s" % (jid, e.get("basis"), "" if info[jid]["params"] else "  SKIPPED: no hinge_params_collected.json"))
        for s in ss:
            w = want_width(s, a.workers)
            cmds = [fill(c, "python", w) for c in (s.get("pre") or [])] + [fill(s["cmd"], "python", w)]
            print("  %-9s %-8s est. %s on %2d worker(s)" % (s["kind"], s["state"], _hms(step_seconds(s, w)), w))
            if a.verbose:
                for c in cmds:
                    print("      $ " + " ".join(shlex.quote(x) for x in c))
    wall, _ = simulate(d, a.workers, a.memory_gb)
    skipped = sorted({s["id"].rsplit("/", 1)[0] for s in d["steps"] if s["state"] == "skipped"})
    print("\nEstimated: %s of analysis in all (one worker each); about %s wall time on %d workers, plus NL-21 "
          "promotion re-runs where gravity members yield (October: up to one more pushover / NLRHA per job)."
          % (_hms(tot_serial), _hms(wall), a.workers))
    full = None
    if skipped:
        import copy
        d2 = copy.deepcopy(d)
        for s in d2["steps"]:
            s["state"] = "pending"
        full, _ = simulate(d2, a.workers, a.memory_gb)
        print("%d job(s) would be SKIPPED (no hinge_params_collected.json in the bundle): %s. With them: about %s on %d "
              "workers." % (len(skipped), ", ".join(skipped), _hms(full), a.workers))
    print("Planning figures from the October runs; the stage-2 designs differ, so take them as +/- 30 %.")
    return dict(wall_s=wall, serial_s=tot_serial, jobs=ids, skipped=skipped, wall_s_all=full)


def cmd_run(a):
    a = _defaults(a)
    os.makedirs(a.work, exist_ok=True)
    if not a.gold:                                               # resume: the bundle of the earlier run
        try:
            a.gold = NO.load(os.path.join(a.work, QUEUE_NAME))["gold"]["path"]
        except Exception:                                        # noqa: BLE001
            raise SystemExit("--gold: the gold bundle (.zip or folder) is needed for a first run")
    log = os.path.join(a.work, "stage2_run.log")
    with Lock(a.work):
        if not a.engine:
            raise SystemExit("--engine: the HR engine folder (steltic_india/steel_engine) is needed for the gravity record")
        if not os.path.exists(os.path.join(a.engine, "engine3d.py")):
            raise SystemExit("--engine %s: not an HR engine folder (no engine3d.py)" % a.engine)
        _say("stage 2 on %d workers, memory budget %.0f GB, work folder %s" % (a.workers, a.memory_gb, a.work), log)
        jobs_root, ids, src = _prepare(a, log)
        q, d = plan_queue(a.work, jobs_root, ids, a, src, log)
        _wait_for_orphans(d, log)
        wall, _ = simulate(d, a.workers, a.memory_gb)
        left = [s for s in d["steps"] if s["state"] not in STATE_TERMINAL]
        _say("%d job(s); %d step(s) to run, estimated %s" % (len(ids), len(left), _hms(wall)), log)
        keep_awake(True)
        t0 = time.time()
        try:
            d = run_queue(q, d, a.workers, a.memory_gb, a.python or sys.executable, log, poll_s=a.poll,
                          stop_after=getattr(a, "stop_after", None))
        finally:
            keep_awake(False)
        st = [s["state"] for s in d["steps"]]
        _say("finished this run in %s: %s" % (_hms(time.time() - t0), ", ".join("%d %s" % (st.count(k), k)
                                                                              for k in sorted(set(st)))), log)
        if any(x in ("pending", "resume", "running", "recheck") for x in st):
            _say("some steps are still to run (see `status`); run the same command again", log)
            return 75
        out, man = write_bundle(a.work, d, a, a.results, log, totals=dict(wall_s_this_run=round(time.time() - t0)))
        bad = [s["id"] for s in d["steps"] if s["state"] in ("failed", "stalled")]
        if bad:
            _say("%d step(s) failed or stalled (listed in the manifest): %s" % (len(bad), ", ".join(bad[:8])), log)
        return 0 if not bad else 3


def cmd_status(a):
    a = _defaults(a)
    q = os.path.join(a.work, QUEUE_NAME)
    if not os.path.exists(q):
        print("no stage-2 queue in %s" % a.work)
        return 1
    d = NO.load(q)
    print("%-62s %-8s %4s %9s %8s" % ("step", "state", "runs", "time", "peak MB"))
    for s in d["steps"]:
        pk = [c.get("peak_rss_mb") for c in s["chunks"] if c.get("peak_rss_mb") is not None]
        print("%-62s %-8s %4d %9s %8s" % (s["id"], s["state"], len(s["chunks"]), _hms(sum(c["seconds"] for c in s["chunks"])),
                                          ("%.0f" % max(pk)) if pk else "-"))
        for k in ("skip_reason", "failed_reason", "stalled_reason", "note_promotion"):
            if s.get(k) and (k != "skip_reason" or s["kind"] == "gravity"):
                print("    %s" % s[k])
    left = [s for s in d["steps"] if s["state"] not in STATE_TERMINAL]
    if left:
        wall, _ = simulate(d, _defaults(a).workers, a.memory_gb)
        print("\n%d step(s) left, about %s on %d workers" % (len(left), _hms(wall), a.workers))
    return 0


def cmd_bundle(a):
    a = _defaults(a)
    q = os.path.join(a.work, QUEUE_NAME)
    d = NO.load(q)
    write_bundle(a.work, d, a, a.results, os.path.join(a.work, "stage2_run.log"))
    return 0


def cmd_verify(a):
    """The lead's side: every file of a results zip against the sha256 in its manifest."""
    bad, n = [], 0
    with zipfile.ZipFile(a.zip) as z:
        man = json.loads(z.read("STAGE2_MANIFEST.json"))
        names = set(z.namelist())
        for rel, sha in sorted((man.get("files") or {}).items()):
            n += 1
            if rel not in names:
                bad.append("missing: " + rel); continue
            h = hashlib.sha256()
            with z.open(rel) as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    h.update(b)
            if h.hexdigest() != sha:
                bad.append("changed: " + rel)
        extra = sorted(x for x in names if x.startswith("jobs/") and not x.endswith("/") and x not in man.get("files", {}))
    bad += ["not in the manifest: " + x for x in extra]
    s = man.get("summary") or {}
    print("%s: %d files checked, %d problem(s); steps %s" % (a.zip, n, len(bad), {k: v for k, v in s.items()}))
    for b in bad[:50]:
        print("  " + b)
    return 0 if not bad else 4


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run_stage2", description="stage-2 nonlinear runs on one PC (resumable)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "status", "bundle"):
        p = sub.add_parser(name)
        p.add_argument("--work", default=None, help="work folder (default %s)" % DEFAULT_WORK)
        p.add_argument("--results", default=None, help="folder for the results zip (default %s)" % DEFAULT_RESULTS)
        p.add_argument("--workers", type=int, default=None, help="processes at once (default: CPUs - 2)")
        p.add_argument("--memory-gb", type=float, default=None, help="memory budget (default: 80 %% of the RAM)")
        if name in ("plan", "run"):
            p.add_argument("--gold", required=(name == "plan"),
                           help="the gold bundle: a .zip or a folder of job folders (run: default, the earlier run's)")
            p.add_argument("--jobs", nargs="+", default=[], help="only these jobs (building or unit ids)")
            p.add_argument("--job-args", nargs="+", default=[], metavar="JOB:KIND=ARGS",
                           help="per-job options, as nl_orchestrate plan --job-args")
        if name == "plan":
            p.add_argument("--verbose", action="store_true", help="print every command")
        if name == "run":
            p.add_argument("--engine", default=os.environ.get("STELTIC_ENGINE_DIR"),
                           help="the HR engine folder (steltic_india/steel_engine)")
            p.add_argument("--python", default=None, help="the interpreter for the analyses (default: this one)")
            p.add_argument("--retry-failed", action="store_true", help="run failed / stalled steps again")
            p.add_argument("--poll", type=float, default=3.0, help=argparse.SUPPRESS)
            p.add_argument("--stop-after", type=int, default=None, help=argparse.SUPPRESS)
    v = sub.add_parser("verify", help="check a results zip against its manifest")
    v.add_argument("--zip", required=True)
    a = ap.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "status": cmd_status, "bundle": cmd_bundle, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    r = main()
    sys.exit(r if isinstance(r, int) else 0)
