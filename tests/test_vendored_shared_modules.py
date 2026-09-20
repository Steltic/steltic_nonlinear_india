"""WP1.14: the shared India modules are vendored byte-identically from steltic_india and sa_over_g is the shared one."""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HR = os.environ.get("STELTIC_INDIA_HR", "/home/claude/rv/work/hr")


@pytest.mark.skipif(not os.path.isdir(os.path.join(HR, "steel_engine")), reason="steltic_india checkout not available")
def test_check_vendored_passes():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_vendored.py"), "--hr", HR],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_sa_over_g_is_the_shared_rsa_branch():
    sys.path.insert(0, ROOT)
    from nlrha import india_hazard as IH
    from snl.vendor_steltic_india import shared
    IS = shared("india_seismic")
    for T, soil in ((0.05, "II"), (0.3, "I"), (1.0, "II"), (2.0, "III"), (5.0, "II")):
        assert IH.sa_over_g(T, soil) == pytest.approx(IS.sa_over_g(T, soil, "RSA"))
    assert IH.sa_over_g(0.09, "II") == pytest.approx(1 + 15 * 0.09)      # RSA branch (not the ESM plateau)
