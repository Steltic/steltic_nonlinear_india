"""NL-12: the India push stops once the descending branch is captured (V <= 0.8 Vmax past the peak, beyond twice the
largest target estimate) instead of grinding on to 10 % roof drift; the USA path (no fraction) is unchanged."""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pushover import nonlinear_model as NM  # noqa: E402


class FakeOps:
    """Roof displacement advances by the requested step; base shear follows a peak-then-soften curve."""
    def __init__(self):
        self.u = 0.0; self.dU = 0.0

    def __getattr__(self, name):
        return lambda *a, **k: 0

    def integrator(self, *a):
        self.dU = a[-1]

    def analyze(self, n):
        self.u += self.dU
        return 0

    def nodeDisp(self, node, dof=None):
        return self.u

    def nodeReaction(self, node, dof):
        u = self.u
        V = 1000.0 * u / 2.0 if u <= 2.0 else max(0.0, 1000.0 - 60.0 * (u - 2.0))
        return -V

    def eleResponse(self, *a):
        return [0.0]


def _run(monkeypatch, frac):
    fake = FakeOps()
    monkeypatch.setattr(NM, "ops", fake)
    monkeypatch.setattr(NM, "_apply_gravity", lambda loads: 0)
    monkeypatch.setattr(NM, "modal_pattern", lambda pkg, d: dict(F={1: 1.0}, T1=0.5, mode=1, meff_frac=0.9, phi={1: 1.0}, masses={1: 1.0}))
    monkeypatch.setattr(NM, "levels", lambda pkg: [(1, 100.0, 99, [1, 2])])
    pkg = types.SimpleNamespace(model=types.SimpleNamespace(fixes={1: [1] * 6}, elements=[]), schedule={})
    return NM.pushover(pkg, {}, "X", {}, {}, max_roof_drift=0.5, dU0=0.1, verbose=False, tail_strategies=(),
                       target_estimator=lambda pat: [0.5, 1.0], stop_at_strength_fraction=frac)


def test_stop_when_descending_branch_captured(monkeypatch):
    run = _run(monkeypatch, 0.8)
    assert run["stop_reason"].startswith("descending branch captured")
    u_end = run["rec"]["u"][-1]
    assert 2.0 < u_end < 7.0                    # 0.8 Vmax at u = 2 + 200/60 = 5.33 (and past 2 x 1.0 target estimate)
    assert run["tail"]["captured"] and run["tail"]["status"] == "captured"


def test_no_fraction_pushes_to_max_drift(monkeypatch):
    run = _run(monkeypatch, None)
    assert run["rec"]["u"][-1] >= 0.5 * 100.0 - 1e-6 or "strength dropped" in run["stop_reason"]
