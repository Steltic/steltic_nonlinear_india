"""Pure unit test for modal_pattern selection policy (no OpenSees solve).

Replicates / imports the ranking used in pushover.nonlinear_model so regressions
like IN_Ex1 X (T≈64 s / ~0% mass) and IN_Ex3 Y (T≈0.001 s / ~100% mass) cannot
return.
"""
from __future__ import annotations

from pushover.nonlinear_model import DEFAULT_MIN_T_S, select_modal_candidate


def _select(cands, min_meff_frac=0.05, min_T=DEFAULT_MIN_T_S):
    best, _pool = select_modal_candidate(cands, min_meff_frac=min_meff_frac, min_T=min_T)
    return best


def test_skips_spurious_soft_mode_zero_mass():
    # Mode 1: soft, ~0% mass (IN_Ex1 X anomaly). Mode 3: real X, 78% mass.
    cands = [
        dict(meff=1e-9, frac=0.0, T=64.2, mode=1, aligned=False),
        dict(meff=0.02, frac=0.02, T=1.1, mode=2, aligned=True),
        dict(meff=0.78, frac=0.78, T=0.31, mode=3, aligned=True),
        dict(meff=0.86, frac=0.86, T=0.30, mode=6, aligned=False),  # Y-ish
    ]
    best = _select(cands)
    assert best["mode"] == 3
    assert best["T"] == 0.31
    assert best["frac"] >= 0.05


def test_prefers_aligned_over_higher_meff_perp():
    cands = [
        dict(meff=0.90, frac=0.90, T=0.28, mode=2, aligned=False),  # mostly perp
        dict(meff=0.70, frac=0.70, T=0.33, mode=4, aligned=True),
    ]
    best = _select(cands)
    assert best["mode"] == 4


def test_fallback_to_max_meff_when_none_clear_threshold():
    cands = [
        dict(meff=0.01, frac=0.01, T=2.0, mode=1, aligned=True),
        dict(meff=0.03, frac=0.03, T=1.5, mode=2, aligned=True),
    ]
    best = _select(cands, min_meff_frac=0.05)
    assert best["mode"] == 2  # max meff among T-ok when none clear mass threshold


def test_rejects_near_zero_T_despite_full_mass():
    # IN_Ex3 Chennai Y: mode 10 T≈0.0007 s / 100% mass beat real sway (~0.3 s).
    cands = [
        dict(meff=0.85, frac=0.85, T=0.32, mode=2, aligned=True),
        dict(meff=1.00, frac=1.00, T=0.0007, mode=10, aligned=True),
        dict(meff=0.40, frac=0.40, T=0.18, mode=5, aligned=True),
    ]
    best, pool = select_modal_candidate(cands)
    assert best["mode"] == 2
    assert best["T"] == 0.32
    assert pool == "aligned_mass_T"
    assert best["T"] >= DEFAULT_MIN_T_S


def test_default_min_T_is_documented_floor():
    # Honesty: 0.02 s is an engineering sanity floor (~50 Hz), not a code Ta.
    assert DEFAULT_MIN_T_S == 0.02


def test_T_floor_fallback_when_all_short():
    cands = [
        dict(meff=0.9, frac=0.9, T=0.001, mode=1, aligned=True),
        dict(meff=1.0, frac=1.0, T=0.005, mode=2, aligned=True),
    ]
    best, pool = select_modal_candidate(cands, min_T=0.02)
    assert best["mode"] == 2
    assert pool == "fallback"
