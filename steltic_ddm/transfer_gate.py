"""
transfer_gate.py -- prove the GMNIA rebuild IS the Steltic building before anything nonlinear runs.

Compares, elastic vs elastic:
  * the first three periods (Steltic replay model with its recorded masses vs. the GMNIA topology
    with elastic fibre sections, no imperfections, same masses)
  * roof displacement under the same ELF-pattern lateral load in X and in Y
A mismatch beyond `tol` (default 5 %) blocks the run and names the likely cause (orientation,
release decoding, diaphragm membership, section mapping). India fibre I-sections carry the root
fillets (NL-26: A, Ix = IS 808 catalogue); USA W-sections ignore them (1-3 % softer, reported, not flagged).
"""
import math, re
import openseespy.opensees as ops
from .model_gmnia import GMNIAModel


def _replay(path):
    """Execute the recorded ops.* lines. Steltic's export contains the probe build followed by the real
    build, and geomTransf is only recorded in the first one -- so the transforms are re-issued after
    every ops.model(...) line (the standalone file itself fails at its first element for this reason)."""
    ops.wipe()
    ns = {"ops": ops, "math": math}
    transf = []
    for line in open(path):
        s = line.strip()
        if not s.startswith("ops.") or s.startswith(("ops.eigen", "ops.getNodeTags", "ops.getEleTags")):
            continue
        if s.startswith("ops.geomTransf"):
            transf.append(s)
        exec(s, ns)
        if s.startswith("ops.model("):
            for t in transf:
                exec(t, ns)


MAX_CONDENSED_DOFS = 60


def _condensed_periods(n, masses):
    """NL-33: exact periods when the whole mass sits on a few DOFs (a PEB shed's single roof master: ux, uy, rz).
    ARPACK cannot return n >= 2 modes when the mass matrix has rank 3 and the dense LAPACK fallback is O(neq^3)
    (4 600 - 7 000 equations for the PEB models). Static condensation is exact here, because every massless DOF is
    condensed by the static solves: F (flexibility on the mass DOFs, one unit load each), then
    eig(M^1/2 F M^1/2) = 1 / omega^2. None when the mass is spread over more than MAX_CONDENSED_DOFS DOFs."""
    import numpy as np
    dofs = [(int(t), k) for t, mm in sorted(masses.items()) for k, v in enumerate(mm) if float(v) > 0.0]
    if not dofs or len(dofs) > MAX_CONDENSED_DOFS:
        return None
    F = np.zeros((len(dofs), len(dofs)))
    for j, (t, k) in enumerate(dofs):
        ops.wipeAnalysis()
        ops.timeSeries("Constant", 9101 + j); ops.pattern("Plain", 9101 + j, 9101 + j)
        load = [0.0] * 6; load[k] = 1.0
        ops.load(t, *load)
        ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
        ops.test("NormDispIncr", 1e-12, 10, 0); ops.algorithm("Linear")
        ops.integrator("LoadControl", 1.0); ops.analysis("Static")
        if ops.analyze(1) != 0:
            return None
        for i, (ti, ki) in enumerate(dofs):
            F[i, j] = ops.nodeDisp(ti, ki + 1)
        ops.remove("loadPattern", 9101 + j)
        ops.setTime(0.0)                          # Linear algorithm: u = K^-1 P from any committed state
    ops.wipeAnalysis()
    m = np.sqrt(np.array([float(masses[t][k]) for t, k in dofs]))
    lam = np.linalg.eigvalsh(0.5 * ((m[:, None] * F * m[None, :]) + (m[:, None] * F * m[None, :]).T))
    lam = sorted((v for v in lam if v > 0), reverse=True)[:n]
    return [2 * math.pi * math.sqrt(v) for v in lam]


def _periods(n=3, masses=None):
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    try:
        w2 = ops.eigen("-genBandArpack", n)
        if len(w2) < n:
            raise RuntimeError("ARPACK returned %d of %d modes" % (len(w2), n))
    except Exception:
        T = _condensed_periods(n, masses) if masses else None
        if T and len(T) >= n:
            return T
        w2 = ops.eigen("-fullGenLapack", n)
    return [2 * math.pi / math.sqrt(max(w, 1e-12)) for w in w2]


def _lateral_disp(masters, lat, dirn):
    ops.wipe_analysis() if hasattr(ops, "wipe_analysis") else ops.wipeAnalysis()
    ops.timeSeries("Linear", 1); ops.pattern("Plain", 1, 1)
    for k, (fx, fy, mz) in lat.items():
        ops.load(k * 100000 + 99999, fx, fy, 0.0, 0.0, 0.0, mz)
    ops.constraints("Transformation"); ops.numberer("RCM"); ops.system("UmfPack")
    ops.test("NormDispIncr", 1e-8, 50, 0); ops.algorithm("Linear")
    ops.integrator("LoadControl", 1.0); ops.analysis("Static"); ok = ops.analyze(1)
    d = ops.nodeDisp(masters[-1], 1 if dirn == "X" else 2)
    ops.remove("loadPattern", 1)
    return ok, d


def run(nm, cfg, lat_x, lat_y, tol=0.05, nsub=(2, 2, 2)):
    """lat_x / lat_y: {level: (fx, fy, mz)} unit lateral patterns (e.g. the ELF pattern)."""
    replay = nm.job_dir + "/model_opensees.py"
    masters = sorted(t for t in nm.nodes if t % 100000 == 99999)
    # --- Steltic elastic model
    _replay(replay)
    T_ref = _periods(3, masses=nm.masses)
    _replay(replay); okx, dx_ref = _lateral_disp(masters, lat_x, "X")
    _replay(replay); oky, dy_ref = _lateral_disp(masters, lat_y, "Y")
    # --- GMNIA topology, elastic
    g = GMNIAModel(nm, cfg, nsub=nsub, elastic=True, residual="none", out_of_plumb=(None, 0.0), bow=0.0, brace_bow=0.0)
    g.build(with_mass=True)
    T_new = _periods(3)
    g.build(); _, dx_new = _lateral_disp(masters, lat_x, "X")
    g.build(); _, dy_new = _lateral_disp(masters, lat_y, "Y")
    rows = []
    def cmp(name, a, b):
        r = b / a if abs(a) > 1e-12 else float("nan")
        rows.append(dict(quantity=name, steltic=a, gmnia=b, ratio=r, ok=abs(r - 1) <= tol))
    for i, (a, b) in enumerate(zip(T_ref, T_new)):
        cmp("T%d (s)" % (i + 1), a, b)
    cmp("roof disp X under ELF pattern (in)", dx_ref, dx_new)
    cmp("roof disp Y under ELF pattern (in)", dy_ref, dy_new)
    ok = all(r["ok"] for r in rows)
    hint = None
    if not ok:
        worst = max(rows, key=lambda r: abs(r["ratio"] - 1))
        if "disp" in worst["quantity"] and worst["ratio"] > 1.3:
            hint = "GMNIA model much softer in that direction: check column strong_dir decoding (transf 1/2) or a lost brace pin/diaphragm membership"
        elif worst["ratio"] < 0.8:
            hint = "GMNIA model stiffer: a beam release was not decoded (relz -> -releasey) or a pin has no released DOF"
        else:
            hint = "check section-label mapping (member_schedule.csv) and node/element ordering"
    return dict(ok=ok, rows=rows, tol=tol, hint=hint, elements_steltic=len(nm.members), elements_gmnia=len(g.elems))
