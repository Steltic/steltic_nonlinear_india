"""checkpoint.py -- resumable OpenSees analyses by deterministic replay (third wave, P2 / stage 2).

The NL analyses (a DDM sweep, a pushover direction, an NLRHA record) keep their whole state inside one OpenSees
process: there is nothing to save half-way, and this box stops a background command at 2 h. A run longer than that
used to be impossible (IN_Ex19 1.2DL+1.2LL+1.2EQ_Y[ea]+0.3EQ_Z: its third load-step rung alone may take 9 600 s).

The analyses are deterministic: the same model, the same sequence of OpenSees calls and the same convergence outcome
of every `analyze` give the same state, bit for bit. A failed `analyze` reverts the domain to its last committed state,
so a failed attempt leaves nothing behind. So a run is journaled at `analyze` level -- the outcome of every call, the
load factor and a displacement fingerprint after it, and the elapsed time -- and a later process resumes by running the
SAME Python code from the start against the journal:

  * a call that failed in the journal returns the same failure code at once (no computing: failed attempts -- step cuts,
    algorithm ladders -- are where the time goes);
  * a call that converged is computed again and must land on the journaled load factor and fingerprint (else
    ReplayDiverged: the code or the model changed, and the journal is not used);
  * the run's clock (`elapsed`) reads the journaled times while replaying, so time-limit decisions repeat exactly;
  * past the end of the journal the run continues live, and each call is appended.

A process stops at a call boundary once its chunk budget is spent (ChunkExpired): the journal is saved and the next
process resumes. Completed pieces (a finished sweep rung, a finished pushover direction) are stored whole in the
journal (`done`) and are not replayed at all.

Cost of a resume: the converged steps are recomputed; the failed ones are not. A run whose CONVERGED steps alone take
more than a FULL chunk cannot progress this way (review M3; re-check: judged against $SNL_FULL_CHUNK, the queue's full
chunk, never against what is left of a `next` call): the journal checks it when a piece begins (`progress_possible`)
and raises NoProgress (exit 76) with the reason; a piece whose replay diverges again after one live restart does the
same. A replay that runs out of time (a slow box) exits 75. The orchestrator stalls a step after exit 76, or after
several full chunks in a row without a finished piece, a live call or a cached record.
Keys (review M4 / M5, `run_key`): the analysis code including the drivers and post-processing, the HR engine
fingerprint, the SNL_* model knobs, an outside --params file and a fixed PYTHONHASHSEED (required, L12). The replay
fingerprint covers every node (L9).

Limit found on the real models (third wave): a failed `analyze` is NOT perfectly state-neutral in OpenSees. On the
one-bay EBF with forced failures the replayed run differs from the uninterrupted one by 4.5e-13 (relative); on IN_Ex15 Y
at a near-singular step (u = 1 000 mm, 9 step halvings) the NewtonLineSearch attempt that converged after three failed
attempts in the original failed in the replay (call 86). The fingerprint check catches this (ReplayDiverged), and the
caller then restarts the segment live (`restart_live`): correct, but that chunk gains nothing. So the journal resumes
runs whose hard steps lie after the last chunk boundary, and is a safe no-op otherwise. An exact state checkpoint was
tried with OpenSees' own `database File` + `save` / `restore`: the save works, the restore fails on these models
("database failed to restore state").
"""
from __future__ import annotations

import os
import pickle
import time

EXIT_RESUME = 75                     # EX_TEMPFAIL: "not finished, run the same command again"
EXIT_NO_PROGRESS = 76                # review M3: "this piece cannot advance in chunks of this size" -- never loop
VERSION = 1
MAX_RESTARTS = 1                     # review M3: live restarts of one piece after a diverged replay, over all chunks
REPLAY_MARGIN = 0.8                  # a replay must fit in this share of a full chunk (progress_possible)
ACTIVE = None                        # the journal whose segment is running in this process (Journal.begin / end)
SAVE_EVERY_S = 300.0                 # the journal is also saved every 5 min of live work


def full_chunk(budget_s=None):
    """Re-check M3 b: the length of a FULL chunk -- $SNL_FULL_CHUNK (set by the orchestrator: its `next` budget less
    the margin) or, for a manual run, this process's own --chunk-seconds. A process that starts part-way through a
    `next` call gets only what is left as its budget, so "cannot advance in chunks" is judged against this, never
    against the budget."""
    v = os.environ.get("SNL_FULL_CHUNK")
    try:
        return float(v) if v else budget_s
    except ValueError:
        return budget_s


def deadline():
    """$SNL_DEADLINE (epoch seconds) set by the orchestrator: no analysis call starts after it, wherever the command
    waited for a heavy slot first. None when unset."""
    v = os.environ.get("SNL_DEADLINE")
    try:
        return float(v) if v else None
    except ValueError:
        return None


class ChunkExpired(Exception):
    """The chunk budget is spent; the journal is saved, the same command resumes."""


class ReplayDiverged(Exception):
    """A replayed converged call did not land on the journaled state: the journal does not belong to this code / model."""


class NoProgress(Exception):
    """Review M3: this piece cannot advance in chunks of this size (its replay alone does not fit in a chunk, or its
    replay diverged again after a live restart). The command exits EXIT_NO_PROGRESS with this message; the orchestrator
    marks the step stalled. Run the piece in one process without the chunk limit, or with a longer chunk."""


def _fingerprint(ops):
    """(time, sum of squared nodal displacements over ALL nodes) -- review L9: the first 400 tags were the base and the
    lowest storeys only; a few ms per call even on the largest models."""
    try:
        t = float(ops.getTime())
    except Exception:                                    # noqa: BLE001
        t = 0.0
    s = 0.0
    try:
        for n in ops.getNodeTags():
            for v in ops.nodeDisp(n):
                s += v * v
    except Exception:                                    # noqa: BLE001
        pass
    return t, s


class Journal:
    """One resumable analysis. `path` is the journal file, `key` identifies the analysis (a different key discards the
    file), `budget_s` the wall-clock budget of this process (None: no limit)."""

    def __init__(self, path, key, budget_s=None, rtol=1e-9, t_start=None, max_live_calls=None):
        self.path, self.key, self.budget_s, self.rtol = path, key, budget_s, rtol
        self.max_live_calls = max_live_calls          # a budget in calls instead of seconds (tests)
        self._live_here = 0
        self.t_start = t_start if t_start is not None else time.time()     # the budget counts from the process start
        self.data = dict(version=VERSION, key=key, done={}, segments={}, created=time.strftime("%Y-%m-%dT%H:%M:%S"),
                         chunks=0, replayed_calls=0, live_calls=0)
        if path and os.path.exists(path):
            try:
                d = pickle.load(open(path, "rb"))
                if d.get("version") == VERSION and d.get("key") == key:
                    self.data = d
            except Exception:                            # noqa: BLE001 -- a broken journal is ignored (fresh run)
                pass
        self.data["chunks"] = int(self.data.get("chunks") or 0) + 1
        self.seg_name = None
        self.seg = None
        self.pos = 0
        self.t_seg0 = None
        self._live_t0 = None
        self._live_base = 0.0
        self._ops = None
        self._real = None
        self._last_save = time.time()
        self._seg_left0 = None

    # ------------------------------------------------------------------ pieces
    def done(self, name):
        """The stored result of a finished piece, or None."""
        return self.data["done"].get(name)

    def store(self, name, result):
        self.data["done"][name] = result
        self.data["segments"].pop(name, None)
        self.save()

    def _left(self):
        """Seconds left in this process's chunk (None: no limit)."""
        left = []
        if self.budget_s is not None:
            left.append(self.budget_s - (time.time() - self.t_start))
        if deadline() is not None:
            left.append(deadline() - time.time())
        return min(left) if left else None

    def _full_chunk(self):
        return full_chunk(self.budget_s)

    def replay_seconds(self, name=None):
        """The time the converged calls of a journaled segment took (what a replay recomputes)."""
        seg = self.data["segments"].get(name or self.seg_name) or []
        out, prev = 0.0, 0.0
        for ok, _t, _s, el in seg:
            if ok == 0:
                out += max(0.0, el - prev)
            prev = el
        return out

    def _too_long(self, replay_s):
        full = self._full_chunk()
        return full is not None and not progress_possible(replay_s, full, REPLAY_MARGIN)

    def begin(self, name, ops):
        """Start (or resume) the journaled segment `name`: patch ops.analyze. Review M3: a replay that cannot fit even in
        a full chunk raises NoProgress; one that does not fit in what is left of THIS chunk raises ChunkExpired."""
        seg = self.data["segments"].get(name) or []
        if seg:
            rs = self.replay_seconds(name)
            if self._too_long(rs):
                raise NoProgress("%s: replaying its %d journaled calls recomputes %.0f s of converged steps, more than %.0f %% "
                                 "of a %.0f s chunk -- run this piece in one process without --chunk-seconds, or with a "
                                 "chunk above %.0f s" % (name, len(seg), rs, 100 * REPLAY_MARGIN, self._full_chunk(),
                                                         rs / REPLAY_MARGIN))
            left = self._left()
            if left is not None and rs > REPLAY_MARGIN * left:
                self.save()
                raise ChunkExpired("%s: its replay (%.0f s) does not fit in the %.0f s left of this chunk" % (name, rs, left))
        self._seg_left0 = self._left()
        self.seg_name = name
        self.seg = self.data["segments"].setdefault(name, [])
        self.pos = 0
        self._ops = ops
        self._real = ops.analyze
        self._live_t0 = time.time() if not self.seg else None   # a fresh segment: the clock runs from here
        self._live_base = 0.0
        self.t_seg0 = time.time()
        journal = self

        def analyze(*a):
            return journal._analyze(*a)
        ops.analyze = analyze
        global ACTIVE
        ACTIVE = self
        return self

    def restart_live(self, name, ops):
        """After ReplayDiverged: drop the segment's journal and start it again live (the caller re-runs its piece).
        Review M3: at most MAX_RESTARTS times per piece over all chunks -- a replay that diverges again (a near-singular
        step before the chunk boundary every time) raises NoProgress instead of looping."""
        self.end()
        rs = self.data.setdefault("restarts", {})
        rs[name] = int(rs.get(name) or 0) + 1
        self.data["diverged"] = int(self.data.get("diverged") or 0) + 1
        if rs[name] > MAX_RESTARTS:
            self.save()
            raise NoProgress("%s: its replay diverged in %d chunks (a step whose convergence a replay does not repeat lies "
                             "before the chunk boundary) -- run this piece in one process without --chunk-seconds"
                             % (name, rs[name]))
        self.data["segments"][name] = []
        self.save()
        return self.begin(name, ops)

    def end(self):
        global ACTIVE
        if self._ops is not None and self._real is not None:
            self._ops.analyze = self._real
        self._ops = self._real = None
        if ACTIVE is self:
            ACTIVE = None

    # ------------------------------------------------------------------ the patched call
    @property
    def replaying(self):
        return self.seg is not None and self.pos < len(self.seg)

    def elapsed(self):
        """The segment's clock: journaled times while replaying, then journaled base + live time."""
        if self.seg is None:
            return time.time() - (self.t_seg0 or time.time())
        if self.replaying or self._live_t0 is None:
            return self.seg[self.pos - 1][3] if self.pos > 0 else 0.0
        return self._live_base + (time.time() - self._live_t0)

    def _analyze(self, *a):
        ops = self._ops
        if self.replaying:
            left = self._left()
            if left is not None and left <= 0:                     # review M3: the budget is checked while replaying
                # re-check M3 d: a replay slower than it was recorded (a busy box) is not proof that the piece cannot
                # advance -- exit 75; the orchestrator stalls a step only after NO_GAIN_LIMIT full chunks without gain
                self.save()
                raise ChunkExpired("%s: the chunk ran out during the replay (call %d of %d; the replay is slower than "
                                   "recorded)" % (self.seg_name, self.pos, len(self.seg)))
            ok0, t0, s0, el = self.seg[self.pos]
            self.pos += 1
            self.data["replayed_calls"] = int(self.data.get("replayed_calls") or 0) + 1
            if ok0 != 0:
                return ok0
            ok = self._real(*a)
            t, s = _fingerprint(ops)
            if ok != 0 or abs(t - t0) > self.rtol * max(1.0, abs(t0)) or abs(s - s0) > 1e-7 * max(1e-12, abs(s0)):
                raise ReplayDiverged("%s: call %d replayed ok=%s time %.12g (journal %.12g), disp %.12g (journal %.12g)"
                                     % (self.seg_name, self.pos, ok, t, t0, s, s0))
            return ok
        if self._live_t0 is None:                        # first live call of this process: the clock continues
            self._live_base = self.seg[-1][3] if self.seg else 0.0
            self._live_t0 = time.time()
        now = time.time()
        if now - self._last_save > SAVE_EVERY_S:              # a killed process loses at most this much live work
            self.save()
        if (self.budget_s is not None and now - self.t_start > self.budget_s) or (deadline() is not None and now > deadline()) \
                or (self.max_live_calls is not None and self._live_here >= self.max_live_calls):
            self.save()
            raise ChunkExpired("%s: chunk spent after %d journaled calls (%d replayed, %d live in this process)"
                               % (self.seg_name, len(self.seg), int(self.data.get("replayed_calls") or 0), self._live_here))
        ok = self._real(*a)
        t, s = _fingerprint(ops)
        self.seg.append((ok, t, s, self.elapsed()))
        self.pos = len(self.seg)                             # live: the journal's end moves with the run
        self.data["live_calls"] = int(self.data.get("live_calls") or 0) + 1
        self._live_here += 1
        return ok

    # ------------------------------------------------------------------ file
    def save(self):
        self._last_save = time.time()
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(self.data, f)
        os.replace(tmp, self.path)

    def summary(self):
        segs = self.data.get("segments") or {}
        return dict(chunks=self.data.get("chunks"), done=sorted(self.data.get("done") or {}),
                    pending={k: len(v) for k, v in segs.items()}, replayed_calls=self.data.get("replayed_calls"),
                    live_calls=self.data.get("live_calls"))


ANALYSIS_FILES = ("pushover/nonlinear_model.py", "pushover/fibre_model.py", "pushover/hinge_models.py",
                  "pushover/member_response.py", "pushover/india_model.py", "pushover/india_materials.py",
                  "pushover/india_sections.py", "pushover/sections_db.py", "pushover/elastic_gravity.py",
                  "pushover/package_reader.py", "steltic_ddm/solver.py", "steltic_ddm/model_gmnia.py",
                  "steltic_ddm/sections_fiber.py", "steltic_ddm/loads.py", "steltic_ddm/imperfections.py",
                  "steltic_ddm/ingest.py", "steltic_ddm/peb_restraints.py", "nlrha/run.py", "nlrha/model.py",
                  "nlrha/ground_motions.py", "snl/hr_gravity.py", "snl/india_units.py", "snl/checkpoint.py",
                  # review M5: the drivers and the post-processing whose results the journals store
                  "pushover/postprocess.py", "pushover/cli.py", "nlrha/cli.py", "nlrha/india_hazard.py",
                  "steltic_ddm/cli.py", "steltic_ddm/india_checks.py", "steltic_ddm/imposed_reduction.py",
                  "steltic_ddm/portal_adapter.py")


def code_key() -> str:
    """sha256 (16 hex) of the source files that make an analysis (ANALYSIS_FILES): a journal written by other analysis
    code is never replayed. Report-only modules are left out, so a report fix does not discard a pending run."""
    import hashlib
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    h = hashlib.sha256()
    for rel in ANALYSIS_FILES:
        p = os.path.join(root, rel)
        if os.path.exists(p):
            h.update(rel.encode()); h.update(open(p, "rb").read())
    return h.hexdigest()[:16]


NON_MODEL_ENV = ("SNL_DEADLINE", "SNL_JOBS", "SNL_FULL_CHUNK")   # scheduling, not model knobs


def model_env() -> dict:
    """Review M4: the SNL_* environment knobs that change a model (fibre settings, member subdivisions, gravity-elastic
    members, plasticity, DDM options, record trimming); the scheduling ones are left out."""
    return {k: v for k, v in sorted(os.environ.items()) if k.startswith("SNL_") and k not in NON_MODEL_ENV}


def file_digest(*paths) -> str:
    """sha256 (16 hex) of the named files' contents (a missing file counts as missing)."""
    import hashlib
    h = hashlib.sha256()
    for p in paths:
        if not p:
            continue
        h.update(os.path.basename(str(p)).encode())
        h.update(open(p, "rb").read() if os.path.exists(p) else b"<missing>")
    return h.hexdigest()[:16]


def engine_key() -> str:
    """Review M4: the fingerprint of the HR engine in $STELTIC_ENGINE_DIR (snl.hr_gravity.engine_fingerprint)."""
    eng = os.environ.get("STELTIC_ENGINE_DIR")
    if not eng:
        return "no engine"
    try:
        from snl.hr_gravity import engine_fingerprint
        return engine_fingerprint(eng)
    except Exception as ex:                              # noqa: BLE001
        return "engine unreadable (%s)" % type(ex).__name__


def require_hash_seed() -> str:
    """Review L12: a resumable run needs a fixed PYTHONHASHSEED (the orchestrator sets 0). Without it the order of a set
    of strings can differ between chunks, every replay would diverge and no chunk would gain anything."""
    v = os.environ.get("PYTHONHASHSEED")
    if v in (None, "", "random"):
        raise SystemExit("resumable runs need a fixed hash seed: set PYTHONHASHSEED=0 (the orchestrator does) -- otherwise "
                         "the iteration order of sets can differ between chunks and the replay cannot be used")
    return v


def run_key(params_path=None) -> dict:
    """The parts every journal / cache key carries: the analysis code, the engine, the model knobs, the hash seed and
    an outside --params file."""
    return dict(code=code_key(), engine=engine_key(), env=model_env(), hashseed=require_hash_seed(),
                params=file_digest(params_path) if params_path else None)


def clock(t0):
    """Elapsed seconds of a run: the active journal's clock (replayed times, then live), else wall time since t0."""
    j = ACTIVE
    return j.elapsed() if j is not None and j.seg is not None else time.time() - t0


def progress_possible(replay_seconds, budget_s, margin=0.8):
    """A resume makes progress only if replaying the converged steps fits well inside a chunk."""
    return replay_seconds < margin * budget_s
