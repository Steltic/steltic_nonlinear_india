"""acceptance.py -- NL acceptance dispatch.

India (owner ruling D7): IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis, so India jobs
get an informative `response_summary` (nlrha/response_summary.py) -- no verdict, no ASCE 7 Ch.16 drift limits, no
Risk Category, no FC equation with S_MS. The ASCE 7-22 §16.4 evaluation lives in
usa_reference/acceptance_asce7_ch16.py and is used ONLY for the USA regression fixtures (kip-in, ASCE packages).
"""
from __future__ import annotations

from .response_summary import IS_NL_STATEMENT, summarise as response_summary, fc_columns  # noqa: F401


def _is_india(pkg) -> bool:
    return getattr(getattr(pkg, "basis", None), "jurisdiction", None) == "india"


def evaluate(results, pkg, *a, **k):
    """USA scaffolding only. India jobs must call response_summary (D7)."""
    if _is_india(pkg):
        raise RuntimeError("ASCE 7-22 §16.4 acceptance is not applied to India jobs (D7) -- use response_summary")
    from usa_reference import acceptance_asce7_ch16 as US
    return US.evaluate(results, pkg, *a, **k)


def risk_category(pkg, override=None):
    """USA scaffolding only (ASCE 7 Risk Category). IS 1893 has none -- never mapped from I for India (NLREPO-12)."""
    if _is_india(pkg):
        raise RuntimeError("Risk Category is an ASCE 7 concept; not inferred for India jobs (IS 1893 Table 8 I only)")
    from usa_reference import acceptance_asce7_ch16 as US
    return US.risk_category(pkg, override)


def __getattr__(name):
    from usa_reference import acceptance_asce7_ch16 as US
    return getattr(US, name)
