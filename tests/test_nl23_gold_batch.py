"""NL-23: the gold batch script (scripts/run_gold_batch.sh) is syntactically valid and lists the 19 job folders
(15 gold buildings + 4 units) smallest first."""
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.environ.get("STELTIC_GOLD_JOBS", "/home/claude/gold/jobs_hr")


def _jobs():
    src = open(os.path.join(ROOT, "scripts", "run_gold_batch.sh"), encoding="utf-8").read()
    block = re.search(r'JOBS_DEFAULT="([^"]+)"', src).group(1)
    return [x.strip() for x in block.split("\n") if x.strip()]


def test_batch_script_syntax_and_jobs():
    r = subprocess.run(["bash", "-n", os.path.join(ROOT, "scripts", "run_gold_batch.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    jobs = _jobs()
    assert len(jobs) == 19 and len(set(jobs)) == 19


def test_batch_order_is_smallest_first():
    jobs = _jobs()
    sizes = []
    for j in jobs:
        p = os.path.join(GOLD, j, "model_opensees.py")
        if not os.path.exists(p):
            import pytest
            pytest.skip("gold jobs not available")
        sizes.append(open(p, encoding="utf-8").read().count("element("))
    assert sizes == sorted(sizes)
