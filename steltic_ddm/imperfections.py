"""
imperfections.py -- which imperfection cases to run for a combination.

India (WP4.9, set in steltic_ddm.cli): out-of-plumb psi = 1/200 -- equivalent to the IS 800:2007 4.3.6 notional
horizontal force of 0.5 % of the factored gravity load (an equivalence, EOR to confirm); member bow 0.001L and
0.002L for hollow sections (IS 800 Table 34). 1/500 is kept only as a labelled sensitivity value.
USA scaffolding nominal magnitudes (Rasmussen protocol / literature erection tolerances):
  out-of-plumb  psi = 1/500 (H/500)   whole-building lean, +/-X or +/-Y
  out-of-straightness  L/1000, half-sine, weak axis of columns, out-of-plane for braces
Direction rule:
  * lateral combination  -> lean WITH the lateral load (the governing direction; Shayan et al. 2014a)
  * gravity combination  -> the four directions are candidates; `gravity_dirs` selects how many run
    (default: +X and +Y -- the building is symmetric enough that -X/-Y repeat them; use "all" for the
    full search on irregular plans).
"""
PSI_DEFAULT = 1.0 / 500.0            # USA scaffolding
PSI_INDIA = 1.0 / 200.0              # IS 800 4.3.6 equivalence (0.5 %)
BOW_HOLLOW_INDIA = 1.0 / 500.0       # IS 800 Table 34: 0.002L hollow
BOW_DEFAULT = 1.0 / 1000.0


def cases_for(combo, gravity_dirs="two", psi=PSI_DEFAULT):
    from .loads import lateral_direction
    ldir, sgn = lateral_direction(combo[4])
    if ldir:
        return [dict(dir=ldir, psi=sgn * psi, bow_sign=sgn, tag="%s%s" % ("+" if sgn > 0 else "-", ldir))]
    dirs = [("X", +1), ("Y", +1)] if gravity_dirs == "two" else [("X", +1), ("X", -1), ("Y", +1), ("Y", -1)]
    if gravity_dirs == "one":
        dirs = [("X", +1)]
    return [dict(dir=d, psi=s * psi, bow_sign=s, tag="%s%s" % ("+" if s > 0 else "-", d)) for d, s in dirs]
