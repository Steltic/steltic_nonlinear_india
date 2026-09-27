"""NL-22: `snl collect` accepted 0.24 but rejected Z = 0.10 for zone II (the JSON value 0.1 has the bare digits '01',
which the digit-group test cannot find in the quote's '0.10'); numbers are now also compared numerically."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from snl import collect as C  # noqa: E402


def test_trailing_zero_decimal_matches():
    q = "| Z | 0.10 | 0.16 | 0.24 | 0.36 |"
    pn = C._norm(q)
    assert C.check_field("number", 0.1, q, pn) == ""
    assert C.check_field("number", 0.36, q, pn) == ""
    assert C.check_field("number", 0.2, q, pn) != ""                 # still refuses a number that is not there
    q2 = "joint rotation of 0 . 02 radians"
    assert C.check_field("number", 0.02, q2, C._norm(q2)) == ""
