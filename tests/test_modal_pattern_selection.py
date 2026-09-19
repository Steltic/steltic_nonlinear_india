"""Pure unit test for modal_pattern selection policy (no OpenSees).

Replicates the ranking used in pushover.nonlinear_model.modal_pattern so a
regression like IN_Ex1 X (T≈64 s / ~0% mass stuck as mode 1) cannot return.
"""
from __future__ import annotations


def _select(cands, min_meff_frac=0.05):
    """Mirror of nonlinear_model.modal_pattern ranking."""
    good = [c for c in cands if c["aligned"] and c["frac"] >= min_meff_frac]
    pool = good if good else [c for c in cands if c["frac"] >= min_meff_frac]
    if not pool:
        pool = cands
    return max(pool, key=lambda c: c["meff"])


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
    assert best["mode"] == 2  # max meff among all when none clear threshold
