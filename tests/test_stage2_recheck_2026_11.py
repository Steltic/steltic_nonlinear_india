"""Stage 2, the re-check of c39942b (R1-R3, M6's verify check and the low notes)."""
import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_run_stage2 import RUNNER, _gold, _engine, _env, _cmd, _calls      # noqa: E402
from test_stage2_review_2026_11 import _repo, ENGINE_FILES                   # noqa: E402

BURN = "import time\nt = time.process_time()\nwhile time.process_time() - t < %s: pass\n"


def _run_to_end(NS, s, job, watchdog_s, limit=120):
    r = NS.Run(s, 1, 1.0, sys.executable, dict(os.environ), str(job), watchdog_s=watchdog_s)
    r.start_next()
    t0, rc = time.time(), None
    while rc is None and time.time() - t0 < limit:
        time.sleep(0.2)
        rc = r.poll()
    return r, rc


# ---------------------------------------------------------------------------------------------------- R1
def test_the_watchdog_counts_children_that_have_ended(tmp_path):
    """R1: the pushover runs X in one child process, then Y in another (L14). The second child computes at full speed
    from zero; the watchdog must count the first one's CPU too, or it calls a computing step hung. Each child here
    computes for longer than the watchdog's window."""
    import run_stage2 as NS
    job = tmp_path / "J"; job.mkdir()
    step = ("import subprocess, sys\n"
            "subprocess.check_call([sys.executable, '-c', %r])\n"
            "subprocess.check_call([sys.executable, '-c', %r])\n") % (BURN % 2.5, BURN % 3.5)
    s = dict(id="J/pushover", job=str(job), kind="pushover", cmd=[sys.executable, "-c", step], chunks=[],
             state="running")
    r, rc = _run_to_end(NS, s, job, watchdog_s=1.5)
    assert rc == 0 and not r.hung


def test_the_watchdog_lets_a_parent_finish_after_its_pool(tmp_path):
    """R1, the NLRHA and DDM parents: a pool of workers computes, the pool closes, and the parent's own
    post-processing then takes longer than the window while using less CPU than the pool did."""
    import run_stage2 as NS
    job = tmp_path / "J"; job.mkdir()
    step = ("import subprocess, sys, time\n"
            "pool = [subprocess.Popen([sys.executable, '-c', %r]) for _ in range(2)]\n"
            "assert all(p.wait() == 0 for p in pool)\n" + BURN % 2.5) % (BURN % 2.0)
    s = dict(id="J/nlrha", job=str(job), kind="nlrha", cmd=[sys.executable, "-c", step], chunks=[], state="running")
    r, rc = _run_to_end(NS, s, job, watchdog_s=1.5)
    assert rc == 0 and not r.hung
    # and a step that stops computing is still stopped once its children have ended
    step = "import subprocess, sys, time\nsubprocess.check_call([sys.executable, '-c', %r])\ntime.sleep(60)\n" % (BURN % 1.0)
    s = dict(id="J/ddm", job=str(job), kind="ddm", cmd=[sys.executable, "-c", step], chunks=[], state="running")
    t0 = time.time()
    r, rc = _run_to_end(NS, s, job, watchdog_s=1.0)
    assert r.hung and time.time() - t0 < 30
