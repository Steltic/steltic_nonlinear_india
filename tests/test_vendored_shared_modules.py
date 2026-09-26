"""WP1.14 / NL-1: the shared India modules are vendored byte-identically from steltic_india, the check script
resolves the HR checkout like HR/CFS (env var, sibling checkout, else SKIP), and sa_over_g is the shared one."""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "check_vendored.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_vendored as CV  # noqa: E402

HR = CV.resolve_hr_root()


def _env_without_hr():
    return {k: v for k, v in os.environ.items() if k not in ("STELTIC_HR_ROOT", "STELTIC_INDIA_HR", "STELTIC_ENGINE_DIR")}


@pytest.mark.skipif(not (HR and os.path.isdir(os.path.join(HR, "steel_engine"))),
                    reason="no steltic_india checkout (STELTIC_HR_ROOT / sibling checkout)")
def test_check_vendored_passes():
    r = subprocess.run([sys.executable, SCRIPT, "--hr", HR], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _copy_repo_skeleton(tmp_path, name="repo"):
    repo = tmp_path / name
    (repo / "scripts").mkdir(parents=True)
    (repo / "snl" / "vendor_steltic_india").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "check_vendored.py")
    for f in CV.FILES:
        (repo / "snl" / "vendor_steltic_india" / f).write_text("x = 1\n")
    return repo


def test_skip_without_any_hr_checkout(tmp_path):
    repo = _copy_repo_skeleton(tmp_path)
    r = subprocess.run([sys.executable, str(repo / "scripts" / "check_vendored.py")], capture_output=True, text=True,
                       env=_env_without_hr())
    assert r.returncode == 0 and r.stdout.startswith("SKIP")


def test_sibling_checkout_is_found_and_drift_fails(tmp_path):
    repo = _copy_repo_skeleton(tmp_path)
    eng = tmp_path / "steltic_india" / "steel_engine"
    eng.mkdir(parents=True)
    for f in CV.FILES:
        (eng / f).write_text("x = 1\n")
    env = _env_without_hr()
    r = subprocess.run([sys.executable, str(repo / "scripts" / "check_vendored.py")], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "byte-identical" in r.stdout, r.stdout
    (eng / "india_seismic.py").write_text("x = 2\n")
    r = subprocess.run([sys.executable, str(repo / "scripts" / "check_vendored.py")], capture_output=True, text=True, env=env)
    assert r.returncode == 1 and "DRIFT india_seismic.py" in r.stdout
    r = subprocess.run([sys.executable, str(repo / "scripts" / "check_vendored.py"), "--sync"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and r.stdout.strip().startswith("cp ") and "india_seismic.py" in r.stdout


def test_env_var_wins_and_no_home_paths():
    src = open(SCRIPT).read()
    assert "/home/claude" not in src and "STELTIC_HR_ROOT" in src


def test_sa_over_g_is_the_shared_rsa_branch():
    sys.path.insert(0, ROOT)
    from nlrha import india_hazard as IH
    from snl.vendor_steltic_india import shared
    IS = shared("india_seismic")
    for T, soil in ((0.05, "II"), (0.3, "I"), (1.0, "II"), (2.0, "III"), (5.0, "II")):
        assert IH.sa_over_g(T, soil) == pytest.approx(IS.sa_over_g(T, soil, "RSA"))
    assert IH.sa_over_g(0.09, "II") == pytest.approx(1 + 15 * 0.09)      # RSA branch (not the ESM plateau)
