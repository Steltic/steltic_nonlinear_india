#!/usr/bin/env python3
"""run_stage2.py -- every stage-2 nonlinear analysis on one PC, in one command, resumable (Windows first).

    python scripts/run_stage2.py bundle  --jobs-root <gold job folders> --hr <steltic_india> --out <gold bundle.zip>
                                         [--nl-inputs <folder>] [--jobs NAME ...]          # the lead: make the bundle
    python scripts/run_stage2.py plan    --gold <gold bundle.zip> [--workers 12]          # what would run, how long
    python scripts/run_stage2.py run     --gold <gold bundle.zip> --engine <steltic_india/steel_engine> [--workers 12]
    python scripts/run_stage2.py status  [--work <folder>]
    python scripts/run_stage2.py results [--work <folder>]                                 # write the results zip again
    python scripts/run_stage2.py verify  --zip <results zip>                               # the lead: check a results zip

On Windows the owner runs `windows\\Run-Stage2.bat <gold bundle>` (it makes the Python environment and calls `run`);
see RUN_STAGE2.md. Defaults: work folder <home>/india/stage2_work, results folder <home>/india/_claude_stage, workers =
the CPU count less 2, memory budget 80 % of the RAM, the DDM speed factor 1.0 (the owner's PC: 2,400 CPU seconds for
a sweep's first step size).

The gold bundle carries STAGE2_BUNDLE.json: the HR engine commit and the NL commit it was made for. `plan` and `run`
refuse, with the git commands to run, when a checkout is at another commit, is not a git clone, or has local changes
in its tracked files (review B2).

What a run does:
  1. the gold job folders (the extracted zip) are synced into <work>/jobs: HR files plus the NL inputs of the bundle
     (hinge_params_collected.json, nl_plan.json); NL outputs in the work folder are never touched (nl_orchestrate.sync);
  2. the queue <work>/stage2_queue.json gets one step per analysis and job, the same analyses and options as the
     stage-2 plan (nl_orchestrate._job_steps): the HR gravity record, the pushover (X and Y), the NLRHA (11 pairs,
     DBE + MCE), the DDM, and the report (the design criteria, the four-analyses page, the gate). On a later run the
     queue is kept: finished steps whose inputs changed are put back with their outputs set aside
     (nl_orchestrate.refresh), new jobs are added;
  3. the steps run side by side on --workers processes: a pushover takes one, an NLRHA or a DDM takes several (its
     records / sweeps in a pool), within a memory budget; the longest jobs start first. After a pushover or an NLRHA
     the NL-21 yield check of the elastic gravity members runs; members above first yield are promoted to fibre and
     the analysis runs again (two rounds per design at most, as `snl run`);
  4. at the end ONE results zip is written into the results folder: every job folder with its outputs (journals and
     record caches left out) and STAGE2_MANIFEST.json -- what ran, what was skipped or failed and why, the versions,
     the engine and code fingerprints, the library versions, the timings (wall and CPU), peak memory, and the sha256 of
     every file.

Resumable: a pushover and a DDM are journaled (--checkpoint-dir; at most about 5 minutes of a piece's work is lost),
the NLRHA keeps every finished record (--record-cache; a record in flight starts again from its beginning), and the
queue keeps every finished step. While the runner works it asks Windows not to sleep. If the PC sleeps anyway, the
analyses continue when it wakes; the DDM's time limit counts CPU time, so a pause does not change a DDM result. If the
PC restarts or the window is closed (which ends the analyses too), run the same command again: finished steps are
kept, the interrupted ones continue from their last save.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
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
PROMOTION_ROUNDS = 2                                          # snl run: at most two NL-21 promotion rounds (per design)
SPEED_FACTOR = 1.0                                            # the owner's PC is the reference machine
NLRHA_RECORDS = 22                                            # 11 pairs x (DBE, MCE)
STATE_TERMINAL = ("done", "failed", "stalled", "skipped")
QUEUE_NAME = "stage2_queue.json"
BUNDLE_MANIFEST = "STAGE2_BUNDLE.json"
GRAVITY_SKIP = "the HR gravity record of this job did not finish"
WATCHDOG_S = 1800.0                                           # review L10: a step that uses no CPU for this long hangs
EXIT_REFUSED = 2                                              # a refusal or a configuration error (the message says why)


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
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def refuse(msg):
    """Stop with a plain message and exit code 2 (the launcher tells this apart from an unexpected error)."""
    print("\n" + msg.rstrip() + "\n", flush=True)
    raise SystemExit(EXIT_REFUSED)


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


def proc_token(pid):
    """Review B3: what makes a process unique beyond its pid -- its start time (psutil), or on Linux the boot id with
    the start time in clock ticks (/proc). None when it cannot be read: such a process never counts as the recorded
    one, so a pid reused after a restart can never make the runner wait or refuse."""
    try:
        import psutil
        return "psutil:%.3f" % psutil.Process(int(pid)).create_time()
    except ImportError:
        pass
    except Exception:                                            # noqa: BLE001 -- no such process
        return None
    try:
        boot = open("/proc/sys/kernel/random/boot_id").read().strip()
        start = open("/proc/%d/stat" % int(pid)).read().rsplit(")", 1)[1].split()[19]
        return "proc:%s:%s" % (boot, start)
    except Exception:                                            # noqa: BLE001
        return None


def same_process(pid, token):
    """The recorded process is still running: the pid is alive AND it is the same process (the same start token)."""
    return bool(pid) and token is not None and pid_alive(pid) and proc_token(pid) == token


def _proc_children(pid):
    """Linux /proc: {parent pid: [child pids]}."""
    kids = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                pp = int(open("/proc/%s/stat" % d).read().rsplit(")", 1)[1].split()[1])
                kids.setdefault(pp, []).append(int(d))
            except Exception:                                    # noqa: BLE001
                continue
    return kids


def _tree(pid):
    kids, out, todo = _proc_children(pid), [], [pid]
    while todo:
        x = todo.pop()
        out.append(x)
        todo += kids.get(x, [])
    return out


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
        page = os.sysconf("SC_PAGE_SIZE")
        tot = 0
        for x in _tree(pid):
            try:
                tot += int(open("/proc/%d/statm" % x).read().split()[1]) * page
            except Exception:                                    # noqa: BLE001
                pass
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
    """{(pid, start): CPU seconds so far} of a process and its descendants: psutil, else Linux /proc; {} if neither."""
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
    except ImportError:
        pass
    except Exception:                                            # noqa: BLE001
        return {}
    if not os.path.isdir("/proc"):
        return {}
    out = {}
    try:
        tick = float(os.sysconf("SC_CLK_TCK"))
        for x in _tree(pid):
            try:
                f = open("/proc/%d/stat" % x).read().rsplit(")", 1)[1].split()
                out[(x, f[19])] = (int(f[11]) + int(f[12])) / tick
            except Exception:                                    # noqa: BLE001
                pass
    except Exception:                                            # noqa: BLE001
        return {}
    return out


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


# --------------------------------------------------------------------------------------------- versions (B2)
def git_info(path):
    """The git checkout holding `path`: dict(top, commit, modified = tracked files with local changes under `path`),
    or None when it is not in a git clone (or git is not there)."""
    try:
        top = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=30)
        if top.returncode != 0 or not top.stdout.strip():
            return None
        top = os.path.normpath(top.stdout.strip())
        sha = subprocess.run(["git", "-C", top, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
        rel = os.path.relpath(os.path.abspath(path), top)
        st = subprocess.run(["git", "-C", top, "status", "--porcelain", "--untracked-files=no", "--", rel],
                            capture_output=True, text=True, timeout=60)
        mod = [ln[3:] for ln in st.stdout.splitlines() if ln.strip()]
        return dict(top=top, commit=sha.stdout.strip() or None, modified=mod)
    except Exception:                                            # noqa: BLE001
        return None


def _checkout_hint(top, commit):
    return ('    cd /d "%s"\n    git fetch\n    git checkout %s' % (top, commit) if sys.platform == "win32"
            else '    cd "%s"\n    git fetch\n    git checkout %s' % (top, commit))


def check_versions(bundle, engine, nl_root=None):
    """Review B2: the HR engine and the NL checkout against the commits the gold bundle was made for. Returns
    (problems, info); each problem is a plain message with the git commands to put it right."""
    nl_root = nl_root or NL_ROOT
    out, info = [], dict(bundle_hr_commit=(bundle or {}).get("hr_commit"), bundle_nl_commit=(bundle or {}).get("nl_commit"))
    if not bundle:
        out.append("This gold bundle has no %s, so the engine and code versions it was made for are not known. Ask "
                   "the lead for a bundle made with `run_stage2.py bundle`." % BUNDLE_MANIFEST)
    if not engine:
        out.append("No HR engine folder was given, so its version cannot be checked (--engine "
                   "<steltic_india\\steel_engine>; the launcher finds %%USERPROFILE%%\\india\\steltic_india).")
    for what, path, want, files in (("HR engine", engine, info["bundle_hr_commit"], "steel_engine"),
                                    ("nonlinear tools", nl_root, info["bundle_nl_commit"], None)):
        g = git_info(path) if path else None
        info["%s_checkout" % ("hr" if what == "HR engine" else "nl")] = g
        if not path:
            continue
        if g is None or not g.get("commit"):
            out.append("The %s folder %s is not a git clone, so its version cannot be checked. Make it one as "
                       "RUN_STAGE2.md step 1 says (rename the old folder first)." % (what, path))
            continue
        if g["modified"]:
            out.append("The %s checkout %s has local changes in %d tracked file(s) (%s). To discard them and take the "
                       "bundle's version:\n    cd %s\"%s\"\n    git checkout -- .\n    git checkout %s"
                       % (what, g["top"], len(g["modified"]), ", ".join(g["modified"][:4]),
                          "/d " if sys.platform == "win32" else "", g["top"], want or "<the commit the lead names>"))
        if want and g["commit"] != want and not g["commit"].startswith(want):
            out.append("The %s checkout is at %s, but this gold bundle was made for %s. Run:\n%s\nthen run the same "
                       "command again." % (what, g["commit"][:12], want[:12], _checkout_hint(g["top"], want)))
    info["ok"] = not out
    return out, info


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


def _find_manifest(root):
    """The folder holding STAGE2_BUNDLE.json: `root` or a folder at most two levels down."""
    for r, dirs, files in os.walk(root):
        if BUNDLE_MANIFEST in files:
            return r
        if os.path.relpath(r, root).count(os.sep) >= 2:
            dirs[:] = []
    return None


def gold_root(path, work, log=None, accept=False):
    """The folder holding the gold building folders: the folder of STAGE2_BUNDLE.json (in `path` or in the extracted
    zip, kept in <work>/gold/<sha12>, extracted once). Returns (root, source description, bundle manifest or None).
    Without a manifest (accept only) the old rule: the folder whose children are the building folders."""
    path = os.path.abspath(path)
    src = dict(path=path)
    if os.path.isfile(path):
        if not zipfile.is_zipfile(path):
            refuse("--gold %s: neither a folder nor a .zip" % path)
        sha = _sha256(path)
        src.update(kind="zip", sha256=sha, bytes=os.path.getsize(path))
        dest = os.path.join(work, "gold", sha[:12])                  # review L11: a short path whatever the zip's name
        if not os.path.exists(os.path.join(dest, ".extracted")):
            _say("extracting the gold bundle into %s" % dest, log)
            shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest)
            with zipfile.ZipFile(path) as z:
                for m in z.infolist():
                    target = os.path.normpath(os.path.join(dest, m.filename))
                    if not target.startswith(os.path.normpath(dest) + os.sep) and target != os.path.normpath(dest):
                        refuse("gold bundle: unsafe path %r" % m.filename)
                z.extractall(dest)
            open(os.path.join(dest, ".extracted"), "w").write(_now())
        path = dest
    elif os.path.isdir(path):
        src.update(kind="folder")
    else:
        refuse("--gold %s: not found" % path)
    mroot = _find_manifest(path)
    bundle = None
    if mroot:
        bundle = json.load(open(os.path.join(mroot, BUNDLE_MANIFEST), encoding="utf-8"))
        path = mroot
    elif not accept:
        refuse("The gold bundle %s has no %s (the versions it was made for). Ask the lead for a bundle made with "
               "`run_stage2.py bundle`." % (src["path"], BUNDLE_MANIFEST))
    jobs = find_jobs(path)
    if not jobs:
        refuse("--gold %s: no job folders (a job folder holds cfg.py and model_opensees.py)" % path)
    if not mroot:                                                    # no manifest: the folder of the buildings
        tops = sorted({j.split("/")[0] for j in jobs})
        while len(tops) == 1 and not os.path.exists(os.path.join(path, tops[0], "cfg.py")):
            path = os.path.join(path, tops[0])
            jobs = find_jobs(path)
            tops = sorted({j.split("/")[0] for j in jobs})
    src["root"] = path
    if bundle:
        src.update(hr_commit=bundle.get("hr_commit"), nl_commit=bundle.get("nl_commit"))
    return path, src, bundle


def cmd_bundle(a):
    """The lead: the gold bundle zip -- STAGE2_BUNDLE.json (the HR and NL commits it is made for, the jobs, the sha256
    of every file) and the HR files of the job folders, with the NL inputs (hinge_params_collected.json, nl_plan.json)
    from the jobs themselves or from --nl-inputs (the same layout). Both checkouts must be clean git clones."""
    src_root = os.path.abspath(a.jobs_root)
    hr = os.path.abspath(a.hr)
    eng = hr if os.path.exists(os.path.join(hr, "engine3d.py")) else os.path.join(hr, "steel_engine")
    if not os.path.exists(os.path.join(eng, "engine3d.py")):
        refuse("--hr %s: no steel_engine/engine3d.py there" % a.hr)
    nl_root = os.path.abspath(a.nl_repo) if getattr(a, "nl_repo", None) else NL_ROOT
    gh, gn = git_info(eng), git_info(nl_root)
    bad = []
    for what, g in (("HR engine", gh), ("nonlinear tools", gn)):
        if g is None or not g.get("commit"):
            bad.append("%s: not a git clone" % what)
        elif g["modified"]:
            bad.append("%s: local changes in %s" % (what, ", ".join(g["modified"][:6])))
    if bad and not a.accept_versions:
        refuse("bundle: the checkouts must be clean git clones (commit first):\n  " + "\n  ".join(bad))
    tops = sorted(x for x in os.listdir(src_root) if os.path.isdir(os.path.join(src_root, x)) and not NO._skipped(x))
    if a.jobs:
        missing = [j for j in a.jobs if j not in tops]
        if missing:
            refuse("bundle: not in %s: %s" % (src_root, ", ".join(missing)))
        tops = [t for t in tops if t in a.jobs]
    files, sums = [], {}
    for t in tops:
        for rel in NO._hr_files(os.path.join(src_root, t), NL_INPUT_FILES):
            files.append((os.path.join(src_root, t, rel), "%s/%s" % (t, rel.replace(os.sep, "/"))))
    if a.nl_inputs:                                                  # the NL inputs from another tree, same layout
        nlr = os.path.abspath(a.nl_inputs)
        have = {arc for _, arc in files}
        for t in tops:
            for r, ds, fs in os.walk(os.path.join(nlr, t)):
                ds[:] = [d for d in ds if not NO._is_nl(d) and not NO._skipped(d)]
                for f in fs:
                    if f in NL_INPUT_FILES:
                        arc = "%s/%s" % (t, os.path.relpath(os.path.join(r, f), os.path.join(nlr, t)).replace(os.sep, "/"))
                        if arc not in have:
                            files.append((os.path.join(r, f), arc))
    jobs = sorted({os.path.dirname(arc) for _, arc in files if arc.endswith("/cfg.py")
                   and any(x == os.path.dirname(arc) + "/model_opensees.py" for _, x in files)})
    for p, arc in files:
        sums[arc] = _sha256(p)
    man = dict(schema=1, kind="steltic nonlinear stage-2 gold bundle", created=_now(),
               hr_commit=(gh or {}).get("commit"), nl_commit=(gn or {}).get("commit"),
               hr_engine_fingerprint=_engine_fp(eng), accepted_unclean=bool(bad), jobs=jobs,
               without_collected_values=[j for j in jobs if "%s/hinge_params_collected.json" % j not in sums],
               files=sums)
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    tmp = out + ".zip_tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        z.writestr(BUNDLE_MANIFEST, json.dumps(man, indent=1))
        for p, arc in sorted(files, key=lambda x: x[1]):
            z.write(p, arc)
    NO._replace(tmp, out)
    print("gold bundle %s: %d jobs, %d files; HR %s, NL %s%s" % (out, len(jobs), len(files), (man["hr_commit"] or "?")[:12],
                                                               (man["nl_commit"] or "?")[:12],
                                                               "; no collected values: " + ", ".join(man["without_collected_values"])
                                                               if man["without_collected_values"] else ""))
    return man


def _engine_fp(eng):
    try:
        from snl.hr_gravity import engine_fingerprint
        return engine_fingerprint(eng)
    except Exception:                                            # noqa: BLE001
        return None


# ------------------------------------------------------------------------------------------------- estimates
def load_estimates():
    try:
        return json.load(open(os.path.join(HERE, "stage2_estimates.json"), encoding="utf-8")).get("jobs") or {}
    except Exception:                                            # noqa: BLE001
        return {}


def element_count(job):
    try:
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


def check_job_args(specs):
    """Review L12: a --job-args spec is JOB:KIND=ARGS; anything else is refused with a plain message."""
    for spec in specs or ():
        if ":" not in spec or "=" not in spec.split(":", 1)[1] or not spec.split(":", 1)[0]:
            refuse("--job-args %r: write it as JOB:KIND=ARGS, for example \"IN_Ex19*:pushover=--tail fine_step\"" % spec)


def plan_queue(work, jobs_root, job_ids, args, src, log=None):
    """A new queue, or the existing one brought up to date (new jobs added, the stale steps put back)."""
    q = os.path.join(work, QUEUE_NAME)
    eng = os.path.abspath(args.engine) if getattr(args, "engine", None) else ""
    table = load_estimates()
    if os.path.exists(q) or os.path.exists(q + ".bak"):
        d = NO.load(q) if os.path.exists(q) else NO.load(q + ".bak")
        d["env"]["STELTIC_ENGINE_DIR"] = eng or d["env"].get("STELTIC_ENGINE_DIR", "")
        NO.save(q, d)
        plan_ = NO.refresh(argparse.Namespace(queue=q, engine=None, include_code=False, dry_run=False))
        d = NO.load(q)
        for sid, (state, reason) in plan_.items():          # a design change: the old fibre promotions go too (M2)
            s = next(x for x in d["steps"] if x["id"] == sid)
            if s["kind"] == "gravity" and "input files changed" in reason:
                p = os.path.join(s["job"], "nl_promote_fibre.json")
                if os.path.exists(p):
                    NO._replace(p, p + ".before_refresh_" + time.strftime("%Y%m%d%H%M%S"))
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
            refuse("--job-args %r matches no new step (job args apply when a job enters the queue)" % spec)
    by_id = {s["id"]: s for s in d["steps"]}
    for s in d["steps"]:
        if s["state"] == "running":                              # an interrupted run: continue those steps
            s["state"] = "resume"
            s.setdefault("notes", []).append("%s interrupted (the runner stopped); continues from its last save" % _now())
        elif s["state"] in ("failed", "stalled") and getattr(args, "retry_failed", False):
            s["state"] = "resume" if s["chunks"] else "pending"
            s.setdefault("notes", []).append("%s put back by --retry-failed" % _now())
    for s in d["steps"]:
        if s["state"] != "skipped":
            continue
        why = s.get("skip_reason") or ""
        if why.startswith(("no hinge_params", "no analyses ran")) and skip_reasons(s["job"]) is None:
            s["state"] = "pending"; s.pop("skip_reason", None)   # the bundle has the collected values now
        elif why == GRAVITY_SKIP:                                # review M4: the gravity record runs (again)
            g = by_id.get((s.get("needs") or [None])[0])
            if g is not None and g["state"] not in ("failed", "stalled", "skipped"):
                s["state"] = "pending"; s.pop("skip_reason", None)
    NO.save(q, d)
    return q, d


# ----------------------------------------------------------------------------------------------- scheduling
class Scheduler:
    """Starts ready steps on `workers` processes within `mem_gb`, longest jobs first. Used by the live run
    (run_queue) and by the estimate (simulate, with the estimated durations): the same decisions in both."""

    def __init__(self, d, workers, mem_gb):
        self.d, self.workers, self.mem_gb = d, int(workers), float(mem_gb)
        self.running = {}                                        # step id -> (width, mem)
        self.changed = False                                     # ready() changed a state: the caller saves

    def by_id(self):
        return {s["id"]: s for s in self.d["steps"]}

    def ready(self):
        st = self.by_id()
        out = []
        for s in self.d["steps"]:
            if s["state"] not in ("pending", "resume", "recheck") or s["id"] in self.running:
                continue
            needs = [st[n] for n in (s.get("needs") or []) if n in st]
            if any(n["state"] in STATE_TERMINAL and n["state"] != "done" for n in needs):
                # review M3: a pending OR recheck step whose gravity record failed ends skipped, with the reason
                s["state"], s["skip_reason"] = "skipped", GRAVITY_SKIP
                self.changed = True
                continue
            if s["state"] == "recheck" or any(n["state"] != "done" for n in needs):
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
        """The steps to start now, with their widths: the ready steps longest job first, each as wide as the free
        workers allow, within the memory budget. (A step held back by the memory budget does not reserve its share:
        simulated on the 25 current gold jobs that made the whole run 30 % longer -- 34.9 h against 27.1 h on 12
        workers and 12.8 GB -- review L3.)"""
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
    for s in d["steps"]:
        if s["state"] == "running":
            s["state"] = "resume"
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
    """One step running: its command list (the report's criteria first), the log, the peak memory, the CPU time and
    the watchdog."""

    def __init__(self, s, width, mem, py, env, cwd, watchdog_s=WATCHDOG_S):
        self.s, self.width, self.mem, self.py, self.env, self.cwd = s, width, mem, py, env, cwd
        self.cmds = [fill(c, py, width) for c in (s.get("pre") or [])] + [fill(s["cmd"], py, width)]
        self.i, self.proc, self.peak, self.t0 = 0, None, None, time.time()
        self.cpu, self._seen = 0.0, {}                          # CPU seconds of the finished commands; tree samples
        self.cpu_known = True                                   # review L15: False when it could not be measured
        self.logp = os.path.join(s["job"], "stage2_%s.log" % s["kind"])
        self.rcs = []
        self.watchdog_s, self._last_poll, self._flat_s, self._cpu_max = watchdog_s, None, 0.0, None
        self.hung = False

    def start_next(self):
        cmd = self.cmds[self.i]
        lf = open(self.logp, "a", encoding="utf-8")
        lf.write("\n==== %s %s (workers %d)\n$ %s\n" % (_now(), self.s["id"], self.width, " ".join(shlex.quote(c) for c in cmd)))
        lf.flush()
        kw = dict(creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if sys.platform == "win32" \
            else dict(start_new_session=True)
        self.proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=self.env, cwd=self.cwd, **kw)
        self.token = proc_token(self.proc.pid)
        self._lf = lf
        self._seen, self._flat_s, self._cpu_max = {}, 0.0, None

    def _watch(self, seen):
        """Review L10: a step whose processes gain no CPU time for watchdog_s is hung (an OpenSees access violation in a
        pool worker leaves the pool waiting for ever). Re-check R1: the measure is the CUMULATIVE CPU of every process
        the step has started -- `seen` keeps the last sample of the processes that have exited -- so a step whose
        children run one after another (the pushover's X then Y since L14, a pool closed before the parent's own
        post-processing) progresses while any of them computes. Gaps between polls longer than a minute (the PC asleep)
        are not counted."""
        now = time.time()
        dt = (now - self._last_poll) if self._last_poll is not None else 0.0
        self._last_poll = now
        if not seen or not self.watchdog_s:
            return
        tot = sum(seen.values())
        if self._cpu_max is None or tot > self._cpu_max + 1e-6:
            self._cpu_max, self._flat_s = tot, 0.0
        elif dt < 60.0:
            self._flat_s += dt
            if self._flat_s > self.watchdog_s:
                self.hung = True

    def poll(self):
        """None while running; the exit code when the last command has ended."""
        m = tree_rss_mb(self.proc.pid)
        if m is not None:
            self.peak = max(self.peak or 0.0, m)
        sample = tree_cpu_s(self.proc.pid)
        self._seen.update(sample)
        self._watch(self._seen)                                  # re-check R1: cumulative, exited processes kept
        if self.hung:
            kill_tree(self.proc)
        c0 = children_cpu_s()
        rc = self.proc.poll()
        if rc is None:
            return None
        c1 = children_cpu_s()
        if c0 is not None:
            self.cpu += c1 - c0                                 # POSIX: exact, the process and its reaped children
        elif self._seen:
            self.cpu += sum(self._seen.values())                # Windows: the sampled tree (the last poll is lost)
        else:
            self.cpu_known = False
        self._lf.close()
        self.rcs.append(rc)
        if self.i + 1 < len(self.cmds) and not self.hung:        # the report's design criteria: never blocks the report
            self.i += 1
            self.start_next()
            return None
        return rc


def flagged_elastic(job, kind):
    from snl.cli import flagged_elastic as F
    return F(job, kind)


def promotion_rounds(job, analysis):
    """Review M2 / L13: the NL-21 rounds already made for THIS design -- read from nl_promote_fibre.json itself (its
    history, one entry per round), which is set aside when the design changes. A kill between the promotion and the
    queue save therefore loses no round, and an earlier design's rounds never count."""
    try:
        d = json.load(open(os.path.join(job, "nl_promote_fibre.json"), encoding="utf-8")) or {}
    except Exception:                                            # noqa: BLE001
        return 0
    return sum(1 for h in d.get("history") or [] if h.get("analysis") == analysis)


def promote(job, tags, why, analysis):
    """NL-21 (pushover/elastic_gravity.promote, without importing OpenSees here): add the tags to
    <job>/nl_promote_fibre.json under `analysis` (written atomically)."""
    p = os.path.join(job, "nl_promote_fibre.json")
    try:
        d = json.load(open(p, encoding="utf-8")) or {}
    except Exception:                                            # noqa: BLE001
        d = {}
    d[analysis] = sorted({int(t) for t in (d.get(analysis) or [])} | {int(t) for t in tags})
    d["history"] = list(d.get("history") or []) + [dict(analysis=analysis, added=sorted(int(t) for t in tags), why=why)]
    d["note"] = "members promoted from elastic to fibre after the NL-21 yield check (per analysis; 'tags' = all)"
    tmp = p + ".nl_sync_tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    NO._replace(tmp, p)
    return d[analysis]


def _finish_step(d, s, r, rc, log, py, env, live, sch):
    """The bookkeeping after one command list of a step ended. Returns True when the step runs again (NL-21)."""
    sid = s["id"]
    sec = time.time() - r.t0
    ch = dict(start=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(r.t0)), end=_now(), rc=rc,
              seconds=round(sec), cpu_s=(round(r.cpu, 1) if r.cpu_known else None), workers=r.width,
              peak_rss_mb=round(r.peak) if r.peak else None)
    s["chunks"].append(ch)
    s.pop("pid", None); s.pop("pid_token", None)
    if rc == 0 and s["kind"] in ("pushover", "nlrha"):
        fl = flagged_elastic(s["job"], s["kind"])
        rounds = promotion_rounds(s["job"], s["kind"])
        s["promotion_rounds"] = rounds
        if fl and rounds < PROMOTION_ROUNDS:
            promote(s["job"], fl, "%s yield check, round %d" % (s["kind"], rounds + 1), s["kind"])
            s["promotion_rounds"] = rounds + 1
            s.setdefault("promoted", []).append(fl)
            ch["promoted"] = fl
            _say("NL-21  %s: %d elastic gravity member(s) above first yield -> fibre, the analysis runs again (round %d)"
                 % (sid, len(fl), rounds + 1), log)
            r2 = Run(s, r.width, r.mem, py, env, s["job"])
            r2.start_next()
            s["pid"], s["pid_token"] = r2.proc.pid, r2.token
            live[sid] = r2
            return True
        if fl:
            s["note_promotion"] = ("%d member(s) still above first yield after %d promotion rounds (the gate reports "
                                   "them)" % (len(fl), rounds))
    live.pop(sid, None)
    sch.running.pop(sid, None)
    if rc == 0:
        s["state"] = "done"
        try:
            s["fingerprint"] = NO.fingerprint(d, s)
        except Exception as ex:                                  # noqa: BLE001
            s["fingerprint"] = dict(error="%s: %s" % (type(ex).__name__, ex))
        if s["kind"] == "gravity":
            NO.reconcile_rechecks(d, s["job"])
    elif r.hung:
        s["state"] = "failed"
        s["failed_reason"] = ("no CPU progress for %.0f min: an analysis process probably died (it was stopped); see "
                              "%s" % (r.watchdog_s / 60.0, r.logp))
    elif rc == NO.EXIT_NO_PROGRESS:
        s["state"] = "stalled"
        s["stalled_reason"] = "the analysis reported no progress (exit 76); see %s" % r.logp
    else:
        s["state"] = "failed"
        s["failed_reason"] = "exit code %s; see %s" % (rc, r.logp)
    _say("%-6s %-60s rc %s, %s, CPU %s, peak %s MB" % ("done" if rc == 0 else "FAILED", sid, rc, _hms(sec),
                                                      _hms(r.cpu) if r.cpu_known else "?",
                                                      ch["peak_rss_mb"] if ch["peak_rss_mb"] is not None else "?"), log)
    return False


def run_queue(q, d, workers, mem_gb, py, log=None, poll_s=3.0, stop_after=None, watchdog_s=WATCHDOG_S):
    """Run the queue until nothing is left to start. `stop_after` (tests): stop after this many step starts. Review M7:
    an unexpected error in one step's bookkeeping marks that step failed and the others carry on."""
    env = dict(os.environ, **{k: v for k, v in (d.get("env") or {}).items() if v is not None})
    for k in [k for k in env if k.startswith("SNL_") and k not in d.get("env", {})]:
        env.pop(k)                                               # no stray model knob from the shell
    env["PYTHONPATH"] = os.pathsep.join([x for x in (os.environ.get("STAGE2_PYTHONPATH"), NL_ROOT,
                                                     env.get("PYTHONPATH")) if x])
    sch = Scheduler(d, workers, mem_gb)
    live, started = {}, 0

    def save():
        try:
            NO.save(q, d)
        except Exception as ex:                                  # noqa: BLE001 -- the next save tries again
            _say("!! could not save the queue (%s: %s); trying again at the next change" % (type(ex).__name__, ex), log)
    try:
        while True:
            picks = sch.picks()
            if sch.changed:                                      # review M4: a skip made by ready() is saved
                sch.changed = False
                save()
            for s, w, m in picks:
                if stop_after is not None and started >= stop_after:
                    break
                try:
                    r = Run(s, w, m, py, env, s["job"], watchdog_s=watchdog_s)   # cwd: the job folder, as the hub
                    if s["state"] == "pending" or "started_fingerprint" not in s:
                        try:                                     # review M5: a fresh start takes a fresh fingerprint
                            s["started_fingerprint"] = NO.fingerprint(d, s)
                        except Exception as ex:                  # noqa: BLE001
                            s["started_fingerprint"] = dict(error=type(ex).__name__)
                    r.start_next()
                except Exception as ex:                          # noqa: BLE001
                    s["state"] = "failed"
                    s["failed_reason"] = "could not start: %s: %s" % (type(ex).__name__, ex)
                    _say("FAILED %s: %s" % (s["id"], s["failed_reason"]), log)
                    save()
                    continue
                s["state"] = "running"
                s["pid"], s["pid_token"] = r.proc.pid, r.token
                sch.running[s["id"]] = (w, m)
                live[s["id"]] = r
                started += 1
                _say("start  %-60s workers %2d  (est. %s)" % (s["id"], w, _hms(step_seconds(s, w))), log)
                save()
            if not live:
                if (stop_after is None or started < stop_after) and sch.picks():
                    continue                                     # something became ready (a skip, a recheck)
                break
            time.sleep(poll_s)
            for sid, r in list(live.items()):
                try:
                    rc = r.poll()
                    if rc is None:
                        continue
                    _finish_step(d, r.s, r, rc, log, py, env, live, sch)
                except Exception as ex:                          # noqa: BLE001 -- review M7
                    s = r.s
                    try:
                        kill_tree(r.proc)
                    except Exception:                            # noqa: BLE001
                        pass
                    live.pop(sid, None); sch.running.pop(sid, None)
                    s["state"] = "failed"
                    s["failed_reason"] = "the runner's bookkeeping failed: %s: %s" % (type(ex).__name__, ex)
                    s.pop("pid", None); s.pop("pid_token", None)
                    _say("FAILED %s: %s" % (sid, s["failed_reason"]), log)
                save()
    except KeyboardInterrupt:
        _say("stopped by the user: the running steps are interrupted; run the same command again to continue", log)
        for sid, r in live.items():
            kill_tree(r.proc)
            r.s["state"] = "resume"
            r.s.pop("pid", None); r.s.pop("pid_token", None)
        save()
        raise
    return d


def _hms(s):
    s = int(s or 0)
    return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


# ------------------------------------------------------------------------------------------------- results
def _results_skip(rel):
    parts = rel.replace(os.sep, "/").split("/")
    return any(fnmatch.fnmatchcase(p, pat) for p in parts for pat in RESULTS_SKIP)


def fingerprints(d):
    """The code and engine the run used: the NL analysis code key and commit, the HR engine fingerprint and commit,
    the section tables, the analysis library versions."""
    CK = NO._ck()
    eng = d.get("env", {}).get("STELTIC_ENGINE_DIR") or ""
    return dict(nl_code_key=CK.code_key(), nl_repo=NL_ROOT, nl_git=git_info(NL_ROOT),
                hr_engine=eng, hr_engine_fingerprint=_engine_fp(eng) if eng else None,
                hr_git=git_info(eng) if eng else None, section_tables=CK.section_tables_key(eng),
                libraries=CK.library_versions())


def calibration_s(py):
    """Review M6: this machine's time for the fixed calibration run (in the analysis interpreter), or None."""
    try:
        r = subprocess.run([py, "-c", "from snl.checkpoint import calibration_benchmark as c; print(c())"],
                           capture_output=True, text=True, timeout=300, cwd=NL_ROOT,
                           env=dict(os.environ, PYTHONPATH=NL_ROOT))
        v = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "None"
        return None if v == "None" else float(v)
    except Exception:                                            # noqa: BLE001
        return None


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


def ddm_settings(job):
    """The DDM's own record of its budget (review M6): the speed factor, the limit, the calibration run, per sweep the
    wall and CPU seconds and the limit it ran under."""
    try:
        d = json.load(open(os.path.join(job, "ddm_results.json"), encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        return None
    o = d.get("options") or {}
    return dict(speed_factor=o.get("speed_factor"), time_limit=o.get("time_limit"), time_limit_base=o.get("time_limit_base"),
                calibration_s=o.get("calibration_s"),
                sweeps=[dict(label=r.get("label"), imp=r.get("imp"), status=r.get("status"), termination=r.get("termination"),
                             seconds=r.get("seconds"), cpu_seconds=r.get("cpu_seconds"), time_limit_s=r.get("time_limit_s"))
                        for r in d.get("runs") or []])


def _sum_or_none(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs), 1) if xs else None


def manifest(d, work, args, totals):
    jobs, fps = {}, {}
    for s in d["steps"]:
        jid = s["id"].rsplit("/", 1)[0]
        j = jobs.setdefault(jid, dict(folder="jobs/" + jid, steps={}))
        j["steps"][s["kind"]] = {k: s.get(k) for k in ("state", "skip_reason", "failed_reason", "stalled_reason",
                                                         "refresh_reason", "code_changed", "note_promotion", "promoted",
                                                         "promotion_rounds", "chunks", "fingerprint", "notes")
                                 if s.get(k) is not None}
        ch = s.get("chunks") or []
        j["steps"][s["kind"]]["seconds"] = sum(c.get("seconds") or 0 for c in ch)
        # CPU time beside the wall time (all processes of the step): a pause of the PC shows as seconds >> cpu_s;
        # None where it was not measured (review L15)
        j["steps"][s["kind"]]["cpu_s"] = _sum_or_none(c.get("cpu_s") for c in ch)
        pk = [c.get("peak_rss_mb") for c in ch if c.get("peak_rss_mb") is not None]
        j["steps"][s["kind"]]["peak_rss_mb"] = max(pk) if pk else None
        if s["state"] == "done" and isinstance(s.get("fingerprint"), dict):
            fps.setdefault("engine", set()).add(s["fingerprint"].get("engine"))
            fps.setdefault("code", set()).add(s["fingerprint"].get("code"))
        if s.get("estimate"):
            j["estimate_basis"] = s["estimate"].get("basis")
        if s["kind"] == "nlrha":
            j["nlrha_records"] = nlrha_record_times(s["job"])
        if s["kind"] == "ddm":
            j["ddm"] = ddm_settings(s["job"])
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
    mixed = {k: sorted(str(x) for x in v) for k, v in fps.items() if len(v) > 1}
    return dict(schema=2, kind="steltic nonlinear stage-2 results", created=_now(),
                host=dict(platform=platform.platform(), machine=platform.machine(), cpus=os.cpu_count(),
                          ram_gb=round(total_ram_gb(), 1), python=sys.version.split()[0],
                          calibration_s=totals.pop("calibration_s", None)),
                settings=dict(workers=getattr(args, "workers", None), memory_gb=getattr(args, "memory_gb", None),
                              speed_factor=SPEED_FACTOR, ddm_time_limit_cpu_s=2400.0 * SPEED_FACTOR,
                              env={k: v for k, v in (d.get("env") or {}).items()}),
                gold=d.get("gold"), versions=d.get("versions"), fingerprints=fingerprints(d),
                mixed_versions=mixed or None,
                summary=dict(steps=len(st), **{k: st.count(k) for k in sorted(set(st))}, **totals),
                not_done_here=["the pushover review flags of the EBF jobs (scripts/pushover_review.py --clear): the "
                               "lead, after reading the results"],
                jobs=jobs)


def write_results(work, d, args, results_dir, log=None, totals=None):
    """ONE results zip: jobs/<job>/... (journals and record caches left out), STAGE2_MANIFEST.json (with the sha256 of
    every file) and STAGE2_RUN.log. Written beside as <zip>.manifest.json too."""
    os.makedirs(results_dir, exist_ok=True)
    for f in os.listdir(results_dir):                            # review L11: a zip left half-written by a kill
        if f.endswith((".zip_tmp", ".json_tmp")):
            try:
                os.remove(os.path.join(results_dir, f))
            except OSError:
                pass
    jobs_root = os.path.join(work, "jobs")
    totals = dict(totals or {})
    totals["calibration_s"] = calibration_s(getattr(args, "python", None) or sys.executable)
    man = manifest(d, work, args, totals)
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
    NO._replace(tmp, out)
    side = out + ".manifest.json"
    with open(side + ".json_tmp", "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, default=str)
    NO._replace(side + ".json_tmp", side)
    _say("results: %s (%d files, %.0f MB)" % (out, len(files), os.path.getsize(out) / 2 ** 20), log)
    return out, man


# ------------------------------------------------------------------------------------------------- commands
class Lock:
    """One runner per work folder: a lock file with the runner's pid and its start token. Review B3: a lock whose
    process is gone, or whose pid now belongs to another process (a restart reuses pids), is taken over."""

    def __init__(self, work):
        self.p = os.path.join(work, "stage2.lock")

    def __enter__(self):
        if os.path.exists(self.p):
            try:
                f = open(self.p).read().split()
                pid, token = int(f[0]), (f[1] if len(f) > 1 and f[1] != "-" else None)
            except Exception:                                    # noqa: BLE001
                pid, token = None, None
            if pid and pid != os.getpid() and same_process(pid, token):
                refuse("Another run_stage2 is working in this folder (pid %s). Wait for it to finish, or close its "
                       "window, then run the command again." % pid)
        open(self.p, "w").write("%d %s %s\n" % (os.getpid(), proc_token(os.getpid()) or "-", _now()))
        return self

    def __exit__(self, *a):
        try:
            os.remove(self.p)
        except OSError:
            pass


def _defaults(a):
    a.work = os.path.abspath(a.work or DEFAULT_WORK)
    a.results = os.path.abspath(getattr(a, "results", None) or DEFAULT_RESULTS)
    a.ram_gb = round(total_ram_gb(), 1)
    if getattr(a, "workers", None) in (None, 0):
        a.workers = max(1, (os.cpu_count() or 4) - 2)
    if getattr(a, "memory_gb", None) in (None, 0):
        a.memory_gb = round(0.8 * a.ram_gb, 1)
    return a


def _wait_for_orphans(d, log):
    """A step of an earlier runner whose process is still running (the runner was stopped, its analysis was not):
    wait. Review B3: only the very process recorded (pid AND start token) counts, so a reused pid never makes the
    runner wait."""
    for s in d["steps"]:
        if s.get("pid") and same_process(s["pid"], s.get("pid_token")):
            _say("waiting for %s (pid %s) from an earlier run to end before it continues" % (s["id"], s["pid"]), log)
            while same_process(s["pid"], s.get("pid_token")):
                time.sleep(10)


def _prepare(a, log):
    os.makedirs(a.work, exist_ok=True)
    groot, src, bundle = gold_root(a.gold, a.work, log, accept=a.accept_versions)
    jobs_root = os.path.join(a.work, "jobs")
    os.makedirs(jobs_root, exist_ok=True)
    NO.sync(argparse.Namespace(src=groot, dst=jobs_root, jobs=list(getattr(a, "jobs", None) or []) and
                               sorted({j.split("/")[0] for j in a.jobs}), dry_run=False, inputs=NL_INPUT_FILES, quiet=True))
    ids = find_jobs(jobs_root)
    gold_ids = set(find_jobs(groot))
    ids = [j for j in ids if j in gold_ids]
    if getattr(a, "jobs", None):
        ids = [j for j in ids if j in a.jobs or j.split("/")[0] in a.jobs]
    return jobs_root, ids, src, bundle


def _zip_bundle(path):
    """(root prefix inside the zip, the bundle manifest or None, the zip's names)."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        ms = sorted((n for n in names if n.rsplit("/", 1)[-1] == BUNDLE_MANIFEST), key=lambda n: n.count("/"))
        man = json.loads(z.read(ms[0])) if ms else None
    return (ms[0].rsplit("/", 1)[0] if ms and "/" in ms[0] else ""), man, names


def _zip_root(jobs):
    """The folder inside a zip whose children are the building folders (the parent of the top-most job folders)."""
    import posixpath
    tops = [j for j in jobs if not any(j.startswith(o + "/") for o in jobs if o != j)]
    parents = sorted({posixpath.dirname(t) for t in tops})
    if not parents:
        return ""
    return parents[0] if len(parents) == 1 else posixpath.commonpath(parents)


def _versions_or_refuse(a, bundle, log=None):
    """Review B2: the version check of `plan` and `run`. --accept-versions (the lead's tests only) records the
    problems instead of refusing."""
    problems, info = check_versions(bundle, getattr(a, "engine", None))
    info["accepted"] = bool(problems) and bool(a.accept_versions)
    print("Versions: HR engine %s (bundle %s), nonlinear tools %s (bundle %s)" % (
        ((info.get("hr_checkout") or {}).get("commit") or "?")[:12], (info.get("bundle_hr_commit") or "?")[:12],
        ((info.get("nl_checkout") or {}).get("commit") or "?")[:12], (info.get("bundle_nl_commit") or "?")[:12]), flush=True)
    if problems and not a.accept_versions:
        refuse("Stage 2 cannot start: the versions do not match the gold bundle.\n\n" + "\n\n".join(problems))
    if problems:
        _say("!! versions not checked (--accept-versions): " + " | ".join(p.splitlines()[0] for p in problems), log)
    info["problems"] = problems
    return info


def cmd_plan(a):
    """Dry run: what would run, with the estimated time on --workers and this PC's memory. Nothing is written (a zip
    is listed, not extracted)."""
    a = _defaults(a)
    check_job_args(a.job_args)
    path = os.path.abspath(a.gold)
    if not os.path.exists(path):
        refuse("--gold %s: not found" % path)
    if os.path.isfile(path):
        if not zipfile.is_zipfile(path):
            refuse("--gold %s: neither a folder nor a .zip" % path)
        pre, bundle, names = _zip_bundle(path)
        if bundle is None and not a.accept_versions:
            refuse("The gold bundle %s has no %s (the versions it was made for). Ask the lead for a bundle made with "
                   "`run_stage2.py bundle`." % (path, BUNDLE_MANIFEST))
        dirs = {}
        for n in names:
            parts = n.rstrip("/").split("/")
            dirs.setdefault("/".join(parts[:-1]), set()).add(parts[-1])
        jobs = sorted(k for k, v in dirs.items() if {"cfg.py", "model_opensees.py"} <= v and (not pre or k.startswith(pre + "/")))
        if bundle is None:
            pre = _zip_root(jobs)
        ids = [j[len(pre) + 1:] if pre else j for j in jobs]
        has = {j: dirs.get(j, set()) for j in jobs}
        with zipfile.ZipFile(path) as z:
            info = {i: dict(params="hinge_params_collected.json" in has[j],
                            elements=len(re.findall(r"\belement\(", z.read(j + "/model_opensees.py").decode("utf-8", "replace"))))
                    for i, j in zip(ids, jobs)}
        root = None
    else:
        root, _src, bundle = gold_root(path, a.work, accept=a.accept_versions)
        ids = find_jobs(root)
        info = {i: dict(params=os.path.exists(os.path.join(root, *i.split("/"), "hinge_params_collected.json")),
                        elements=element_count(os.path.join(root, *i.split("/")))) for i in ids}
    _versions_or_refuse(a, bundle)
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
    print("Stage-2 plan: %d job(s) from %s; %d workers (this PC has %s CPUs), memory budget %.0f GB (this PC has %.0f GB "
          "of RAM), DDM speed factor %g (first rung %.0f CPU seconds)" % (len(ids), path, a.workers, os.cpu_count(),
                                                                         a.memory_gb, a.ram_gb, SPEED_FACTOR,
                                                                         2400 * SPEED_FACTOR))
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
    print("\nEstimated: %s of analysis in all (one worker each); about %s wall time on %d workers with %.0f GB, plus "
          "NL-21 promotion re-runs where gravity members yield (October: up to one more pushover / NLRHA per job)."
          % (_hms(tot_serial), _hms(wall), a.workers, a.memory_gb))
    full = None
    if skipped:
        import copy
        d2 = copy.deepcopy(d)
        for s in d2["steps"]:
            s["state"] = "pending"
        full, _ = simulate(d2, a.workers, a.memory_gb)
        print("%d job(s) would be SKIPPED (no hinge_params_collected.json in the bundle): %s. With them: about %s on %d "
              "workers." % (len(skipped), ", ".join(skipped), _hms(full), a.workers))
    print("Planning figures from the October runs; the stage-2 designs differ, so take them as +/- 30 %. More memory "
          "lets more analyses run side by side.")
    return dict(wall_s=wall, serial_s=tot_serial, jobs=ids, skipped=skipped, wall_s_all=full)


def cmd_run(a):
    a = _defaults(a)
    check_job_args(a.job_args)
    os.makedirs(a.work, exist_ok=True)
    if not a.gold:                                               # resume: the bundle of the earlier run
        try:
            a.gold = NO.load(os.path.join(a.work, QUEUE_NAME))["gold"]["path"]
        except Exception:                                        # noqa: BLE001
            refuse("Give the gold bundle (.zip): it is needed for a first run.")
    log = os.path.join(a.work, "stage2_run.log")
    with Lock(a.work):
        if not a.engine:
            refuse("--engine: the HR engine folder (steltic_india\\steel_engine) is needed for the gravity record")
        if not os.path.exists(os.path.join(a.engine, "engine3d.py")):
            refuse("--engine %s: not an HR engine folder (no engine3d.py)" % a.engine)
        _say("stage 2 on %d workers, memory budget %.0f GB (RAM %.0f GB), work folder %s"
             % (a.workers, a.memory_gb, a.ram_gb, a.work), log)
        jobs_root, ids, src, bundle = _prepare(a, log)
        versions = _versions_or_refuse(a, bundle, log)
        q, d = plan_queue(a.work, jobs_root, ids, a, src, log)
        d["versions"] = versions
        NO.save(q, d)
        _wait_for_orphans(d, log)
        wall, _ = simulate(d, a.workers, a.memory_gb)
        left = [s for s in d["steps"] if s["state"] not in STATE_TERMINAL]
        _say("%d job(s); %d step(s) to run, estimated %s" % (len(ids), len(left), _hms(wall)), log)
        keep_awake(True)
        t0 = time.time()
        try:
            d = run_queue(q, d, a.workers, a.memory_gb, a.python or sys.executable, log, poll_s=a.poll,
                          stop_after=getattr(a, "stop_after", None), watchdog_s=a.watchdog_minutes * 60.0)
        finally:
            keep_awake(False)
        st = [s["state"] for s in d["steps"]]
        _say("finished this run in %s: %s" % (_hms(time.time() - t0), ", ".join("%d %s" % (st.count(k), k)
                                                                              for k in sorted(set(st)))), log)
        if any(x in ("pending", "resume", "running", "recheck") for x in st):
            _say("some steps are still to run (see `status`); run the same command again", log)
            return 75
        write_results(a.work, d, a, a.results, log, totals=dict(wall_s_this_run=round(time.time() - t0)))
        bad = [s["id"] for s in d["steps"] if s["state"] in ("failed", "stalled")]
        skipped = [s["id"] for s in d["steps"] if s["state"] == "skipped" and s.get("skip_reason") == GRAVITY_SKIP]
        if bad:
            _say("%d step(s) failed or stalled (listed in the manifest): %s%s" % (
                len(bad), ", ".join(bad[:8]), ("; %d analyses skipped after a failed gravity record" % len(skipped))
                if skipped else ""), log)
        return 0 if not bad else 3


def cmd_status(a):
    a = _defaults(a)
    q = os.path.join(a.work, QUEUE_NAME)
    if not os.path.exists(q) and not os.path.exists(q + ".bak"):
        print("no stage-2 queue in %s" % a.work)
        return 1
    d = NO.load(q) if os.path.exists(q) else NO.load(q + ".bak")
    print("%-62s %-8s %4s %9s %9s %8s" % ("step", "state", "runs", "time", "CPU", "peak MB"))
    for s in d["steps"]:
        ch = s["chunks"]
        pk = [c.get("peak_rss_mb") for c in ch if c.get("peak_rss_mb") is not None]
        cpu = _sum_or_none(c.get("cpu_s") for c in ch)
        print("%-62s %-8s %4d %9s %9s %8s" % (s["id"], s["state"], len(ch), _hms(sum(c["seconds"] for c in ch)),
                                              _hms(cpu) if cpu is not None else "-", ("%.0f" % max(pk)) if pk else "-"))
        for k in ("skip_reason", "failed_reason", "stalled_reason", "note_promotion"):
            if s.get(k) and (k != "skip_reason" or s["kind"] == "gravity" or s.get(k) == GRAVITY_SKIP):
                print("    %s" % s[k])
    left = [s for s in d["steps"] if s["state"] not in STATE_TERMINAL]
    if left:
        wall, _ = simulate(d, a.workers, a.memory_gb)
        print("\n%d step(s) left, about %s on %d workers" % (len(left), _hms(wall), a.workers))
    return 0


def cmd_results(a):
    a = _defaults(a)
    q = os.path.join(a.work, QUEUE_NAME)
    d = NO.load(q)
    write_results(a.work, d, a, a.results, os.path.join(a.work, "stage2_run.log"))
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
    print("%s: %d files checked, %d problem(s); steps %s; versions ok %s%s" % (
        a.zip, n, len(bad), {k: v for k, v in s.items()}, (man.get("versions") or {}).get("ok"),
        "; MIXED versions %s" % man["mixed_versions"] if man.get("mixed_versions") else ""))
    for b in bad[:50]:
        print("  " + b)
    return 0 if not bad else 4


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run_stage2", description="stage-2 nonlinear runs on one PC (resumable)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "status", "results"):
        p = sub.add_parser(name)
        p.add_argument("--work", default=None, help="work folder (default %s)" % DEFAULT_WORK)
        p.add_argument("--results", default=None, help="folder for the results zip (default %s)" % DEFAULT_RESULTS)
        p.add_argument("--workers", type=int, default=None, help="processes at once (default: CPUs - 2)")
        p.add_argument("--memory-gb", type=float, default=None, help="memory budget (default: 80 %% of the RAM)")
        if name in ("plan", "run"):
            p.add_argument("--gold", required=(name == "plan"),
                           help="the gold bundle: a .zip made by `bundle` (run: default, the earlier run's)")
            p.add_argument("--jobs", nargs="+", default=[], help="only these jobs (building or unit ids)")
            p.add_argument("--job-args", nargs="+", default=[], metavar="JOB:KIND=ARGS",
                           help="per-job options, as nl_orchestrate plan --job-args")
            p.add_argument("--engine", default=os.environ.get("STELTIC_ENGINE_DIR"),
                           help="the HR engine folder (steltic_india/steel_engine)")
            p.add_argument("--accept-versions", action="store_true",
                           help="the lead's tests only: run although the versions do not match the bundle (recorded)")
        if name == "plan":
            p.add_argument("--verbose", action="store_true", help="print every command")
        if name == "run":
            p.add_argument("--python", default=None, help="the interpreter for the analyses (default: this one)")
            p.add_argument("--retry-failed", action="store_true", help="run failed / stalled steps again")
            p.add_argument("--watchdog-minutes", type=float, default=WATCHDOG_S / 60.0,
                           help="stop a step whose processes use no CPU for this long (0: never)")
            p.add_argument("--poll", type=float, default=3.0, help=argparse.SUPPRESS)
            p.add_argument("--stop-after", type=int, default=None, help=argparse.SUPPRESS)
    b = sub.add_parser("bundle", help="the lead: make the gold bundle zip")
    b.add_argument("--jobs-root", required=True, help="the folder of gold job folders (jobs_hr layout)")
    b.add_argument("--hr", required=True, help="the steltic_india checkout (or its steel_engine) the golds are for")
    b.add_argument("--out", required=True, help="the bundle .zip to write")
    b.add_argument("--nl-inputs", default=None, help="a folder with the NL inputs per job, in the same layout")
    b.add_argument("--jobs", nargs="+", default=[], help="only these building folders")
    b.add_argument("--accept-versions", action="store_true", help="the lead's tests only: allow unclean checkouts")
    b.add_argument("--nl-repo", default=None, help=argparse.SUPPRESS)
    v = sub.add_parser("verify", help="check a results zip against its manifest")
    v.add_argument("--zip", required=True)
    a = ap.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "status": cmd_status, "results": cmd_results, "verify": cmd_verify,
            "bundle": cmd_bundle}[a.cmd](a)


if __name__ == "__main__":
    r = main()
    sys.exit(r if isinstance(r, int) else 0)
