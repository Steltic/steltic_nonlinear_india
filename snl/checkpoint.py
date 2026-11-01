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
more than a chunk cannot progress this way -- `progress_possible` says so, and the orchestrator reports it.
"""
from __future__ import annotations

import os
import pickle
import time

EXIT_RESUME = 75                     # EX_TEMPFAIL: "not finished, run the same command again"
VERSION = 1
ACTIVE = None                        # the journal whose segment is running in this process (Journal.begin / end)
SAVE_EVERY_S = 300.0                 # the journal is also saved every 5 min of live work


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


def _fingerprint(ops):
    """(time, sum of squared nodal displacements over the first 400 nodes) -- cheap, and any divergence shows."""
    try:
        t = float(ops.getTime())
    except Exception:                                    # noqa: BLE001
        t = 0.0
    s = 0.0
    try:
        for n in sorted(ops.getNodeTags())[:400]:
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

    # ------------------------------------------------------------------ pieces
    def done(self, name):
        """The stored result of a finished piece, or None."""
        return self.data["done"].get(name)

    def store(self, name, result):
        self.data["done"][name] = result
        self.data["segments"].pop(name, None)
        self.save()

    def begin(self, name, ops):
        """Start (or resume) the journaled segment `name`: patch ops.analyze."""
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
                  "nlrha/ground_motions.py", "snl/hr_gravity.py", "snl/india_units.py", "snl/checkpoint.py")


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


def clock(t0):
    """Elapsed seconds of a run: the active journal's clock (replayed times, then live), else wall time since t0."""
    j = ACTIVE
    return j.elapsed() if j is not None and j.seg is not None else time.time() - t0


def progress_possible(replay_seconds, budget_s, margin=0.8):
    """A resume makes progress only if replaying the converged steps fits well inside a chunk."""
    return replay_seconds < margin * budget_s
