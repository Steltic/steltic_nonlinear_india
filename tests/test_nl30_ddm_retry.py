"""NL-30: a DDM sweep that stops numerically (SOLVER_FAILURE) is re-run with a smaller load step before it may block
the COMPLETE gate; every attempt is recorded."""
from steltic_ddm import cli


def _sweeps(statuses):
    calls = []

    def do(dl, k):
        st = statuses[len(calls)]
        calls.append((dl, k))
        return dict(status=st, termination="step_exhausted" if st == "SOLVER_FAILURE" else "limit", lambda_end=1.2 + len(calls) / 10,
                    steps=10 * k, seconds=1.0)
    return do, calls


def test_a_clean_sweep_runs_once_and_records_no_retries():
    do, calls = _sweeps(["LIMIT_POINT"])
    res = cli.sweep_with_retries(do, 0.05)
    assert calls == [(0.05, 1)] and "retries" not in res


def test_a_solver_failure_is_retried_with_half_then_quarter_steps():
    do, calls = _sweeps(["SOLVER_FAILURE", "NO_LIMIT_POINT"])
    res = cli.sweep_with_retries(do, 0.05)
    assert calls == [(0.05, 1), (0.025, 2)]
    assert res["status"] == "NO_LIMIT_POINT" and [r["status"] for r in res["retries"]] == ["SOLVER_FAILURE", "NO_LIMIT_POINT"]


def test_a_persistent_solver_failure_stays_a_solver_failure():
    do, calls = _sweeps(["SOLVER_FAILURE"] * 3)
    res = cli.sweep_with_retries(do, 0.05)
    assert [k for _, k in calls] == [1, 2, 4] and res["status"] == "SOLVER_FAILURE" and len(res["retries"]) == 3


def test_retry_is_a_cli_command():
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["retry", "--help"])
