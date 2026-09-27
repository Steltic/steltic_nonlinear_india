"""
sections_fiber.py -- fibre-section builders for the GMNIA model.

Default: kip, inch, ksi (USA / legacy). Stage C twin: units='N-mm' → MPa, mm, mm²
(E=2e5 MPa) with IS 808 shapes preferred when label matches; AISC inch dims ×25.4.

Sections are built from the SAME AISC shape database Steltic uses (aisc_shapes.csv: d, tw, bf, tf
for W-shapes; A, Ix for HSS with the outside dimensions parsed from the label). Fillets / k-area
are NOT in the CSV, so W-shape A and I come out 1-3 % low -- a known, conservative bias.

Residual stresses are introduced fibre-by-fibre with `InitStressMaterial` wrappers:
  * "lehigh"  -- Galambos & Ketter (1959) linear pattern for hot-rolled I-sections:
                 -sigma_rc*Fy at the flange tips, +sigma_rt*Fy at the web/flange junction and
                 uniform +sigma_rt*Fy in the web, sigma_rt = sigma_rc*Af/(Af+Aw) (self-equilibrating).
                 sigma_rc = 0.3 is the value adopted as the nominal pattern by Shayan, Rasmussen &
                 Zhang (JCSR 101, 2014) and by AISC/SSRC column-curve work.
  * "ecCS"    -- ECCS (1984) bilinear pattern, +/-0.5Fy for h/b <= 1.2 else +/-0.3Fy.
  * "none"    -- no residual stress (sensitivity runs).
  * "cf_hss_membrane" -- simplified membrane pattern for cold-formed HSS (compression at the flat
                 centres, tension at the corners; see Liu, Rasmussen & Zhang, Eng. Struct. 150, 2018).
                 PROVISIONAL: magnitudes are placeholders until the paper's pattern is transcribed.

Fibre orientation follows Steltic's element conventions (engine3d.add_column / add_beam):
  columns : strong axis = element local z  -> depth runs along local y  (axis="y")
  beams   : strong axis = element local y  -> depth runs along local z  (axis="z")
"""
import csv, math, os, re

E_KSI = 29000.0
G_KSI = 11200.0
E_MPA = 200000.0
G_MPA = E_MPA / 2.6
MM_PER_IN = 25.4

_CSV_CACHE = None
_IS808_CACHE = None


def shapes_csv_path():
    """Locate aisc_shapes.csv: $AISC_CSV, then a steltic checkout on sys.path, then the bundled copy."""
    p = os.environ.get("AISC_CSV")
    if p and os.path.exists(p):
        return p
    eng = os.environ.get("STELTIC_ENGINE_DIR")
    if eng and os.path.exists(os.path.join(eng, "aisc_shapes.csv")):
        return os.path.join(eng, "aisc_shapes.csv")
    import sys
    for d in sys.path:
        cand = os.path.join(d, "aisc_shapes.csv")
        if os.path.exists(cand):
            return cand
        cand = os.path.join(d, "steel_engine", "aisc_shapes.csv")
        if os.path.exists(cand):
            return cand
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "aisc_shapes.csv")
    if os.path.exists(here):
        return here
    raise FileNotFoundError("aisc_shapes.csv not found -- set AISC_CSV or put steltic/steel_engine on sys.path")


def shapes():
    global _CSV_CACHE
    if _CSV_CACHE is None:
        _CSV_CACHE = {}
        with open(shapes_csv_path(), newline="") as f:
            for r in csv.DictReader(f):
                _CSV_CACHE[r["AISC_Manual_Label"].upper()] = r
    return _CSV_CACHE


def is808_csv_path():
    """Locate is808_shapes.csv (bundled under steltic_ddm/data or STELTIC_ENGINE_DIR)."""
    p = os.environ.get("IS808_CSV")
    if p and os.path.exists(p):
        return p
    eng = os.environ.get("STELTIC_ENGINE_DIR")
    if eng and os.path.exists(os.path.join(eng, "is808_shapes.csv")):
        return os.path.join(eng, "is808_shapes.csv")
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "is808_shapes.csv")
    if os.path.exists(here):
        return here
    return None


def _india_csv_paths():
    """is808_shapes.csv + is1161_tubes.csv (CHS/RHS) under STELTIC_ENGINE_DIR or steltic_ddm/data."""
    paths = []
    eng = os.environ.get("STELTIC_ENGINE_DIR")
    if eng:
        for name in ("is808_shapes.csv", "is1161_tubes.csv"):
            pp = os.path.join(eng, name)
            if os.path.exists(pp):
                paths.append(pp)
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("is808_shapes.csv", "is1161_tubes.csv"):
        pp = os.path.join(here, "data", name)
        if os.path.exists(pp):
            paths.append(pp)
    env = os.environ.get("IS808_CSV")
    if env and os.path.exists(env):
        paths.insert(0, env)
    # dedupe preserve order
    seen=set(); out=[]
    for pp in paths:
        if pp not in seen:
            seen.add(pp); out.append(pp)
    return out


def is808_shapes():
    global _IS808_CACHE
    if _IS808_CACHE is None:
        _IS808_CACHE = {}
        paths = _india_csv_paths()
        if not paths:
            p0 = is808_csv_path()
            paths = [p0] if p0 else []
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            with open(path, newline="") as f:
                for r in csv.DictReader(f):
                    lab = (r.get("AISC_Manual_Label") or r.get("Label") or "").upper().replace(" ", "")
                    if lab:
                        _IS808_CACHE.setdefault(lab, r)
                    des = (r.get("Designation_IS") or "").upper().replace(" ", "")
                    if des:
                        _IS808_CACHE.setdefault(des, r)
    return _IS808_CACHE


def _f(v):
    try:
        return float(v)
    except Exception:
        return None


def shape(label, prefer_is808=False):
    key = str(label).upper().strip().replace(" ", "")
    if prefer_is808:
        r = is808_shapes().get(key)
        if r is not None:
            return r
    r = shapes().get(key)
    if r is None:
        r = is808_shapes().get(key)
    if r is None:
        raise KeyError("section %r not in aisc_shapes.csv / is808_shapes.csv" % label)
    return r


def hss_dims(label):
    """'HSS8X8X1/2' -> (H, B, t_nominal). Returns None for round/other."""
    m = re.match(r"HSS(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:/\d+)?(?:\.\d+)?)$", label.upper().replace("-", ""))
    if not m:
        return None
    H, B = float(m.group(1)), float(m.group(2))
    t = m.group(3)
    t = float(t.split("/")[0]) / float(t.split("/")[1]) if "/" in t else float(t)
    return H, B, t



# Hardcoded secondary Z props (same as export_cfs_portal_3d_bay.py)
_CFS_Z_PROPS = {
    "800Z250-54": dict(A=0.515, Ix=5.60, Iy=0.98, J=0.0008),
    "800Z250-68": dict(A=0.647, Ix=7.15, Iy=1.25, J=0.0012),
    "800Z250-97": dict(A=0.910, Ix=9.80, Iy=1.70, J=0.0020),
}


def cfs_section_props(label):
    """Gross A/Ix/Iy/J for CFS designators (built-up Nx... or hardcoded Z)."""
    lab = str(label).strip()
    key = lab.upper().replace(" ", "")
    for k, v in _CFS_Z_PROPS.items():
        if key == k.upper():
            return dict(v)
    # Named secondaries from Sena portal export (elastic-only path)
    if any(t in key for t in ("EAVE_STRUT", "RESTRAINT_PURLIN", "RESTRAINT_GIRT", "PURLIN", "GIRT", "EAVESTRUT")):
        return dict(A=0.5, Ix=5.0, Iy=1.0, J=1e-3)
    # built-up e.g. 6x1200S300-118
    try:
        import cfs_frame as CF
        import cfs_sections as SEC
        fs = CF.frame_section(lab)
        gp = SEC.gross_props(fs["base"])
        n = int(fs["n_ply"])
        return dict(A=n * gp["A"], Ix=n * gp["Ix"], Iy=n * gp["Iy"], J=n * gp["J"])
    except Exception:
        return None


class FiberSectionBuilder:
    """Stateful builder: hands out unique material tags and records what it made."""

    def __init__(self, ops, Fy=None, E=None, hardening=0.002, residual="lehigh", sigma_rc=0.3,
                 mat_tag0=1000, elastic=False, units="kip-in", G=None):
        """units='kip-in' (default) or 'N-mm' (Stage C SI twin: E MPa, dims/areas mm)."""
        self.ops = ops
        u = str(units or "kip-in").strip()
        self.units = "N-mm" if u.lower() in ("n-mm", "n-mm-s", "n-mm-sec", "si", "metric", "mm") else "kip-in"
        if self.units == "N-mm":
            self.E = float(E if E is not None else E_MPA)
            self.G = float(G if G is not None else G_MPA)
            self.Fy = float(Fy if Fy is not None else 250.0)
            self.length_scale = MM_PER_IN  # inch CSV → mm
            self.prefer_is808 = True
        else:
            self.E = float(E if E is not None else E_KSI)
            self.G = float(G if G is not None else G_KSI)
            self.Fy = float(Fy if Fy is not None else 50.0)
            self.length_scale = 1.0
            self.prefer_is808 = False
        self.b = hardening
        self.residual = residual
        self.sigma_rc = sigma_rc
        self.next_mat = mat_tag0
        self.elastic = elastic          # elastic sections (transfer gate)
        self.log = []                   # (secTag, label, kind, nfib, note)
        self._mat_cache = {}

    # ---- materials -------------------------------------------------------------------------
    def _mat(self, sig0_frac):
        """Steel01 (+InitStress) for a residual-stress level sig0_frac*Fy; cached per level."""
        key = round(sig0_frac, 4)
        if key in self._mat_cache:
            return self._mat_cache[key]
        tag = self.next_mat; self.next_mat += 1
        if self.elastic:
            self.ops.uniaxialMaterial("Elastic", tag, self.E)
            self._mat_cache[key] = tag
            return tag
        self.ops.uniaxialMaterial("Steel01", tag, self.Fy, self.E, self.b)
        if abs(sig0_frac) > 1e-9:
            wtag = self.next_mat; self.next_mat += 1
            self.ops.uniaxialMaterial("InitStressMaterial", wtag, tag, sig0_frac * self.Fy)
            self._mat_cache[key] = wtag
            return wtag
        self._mat_cache[key] = tag
        return tag

    # ---- W-shape ---------------------------------------------------------------------------
    def w_shape(self, secTag, label, axis="y", nf_flange=(8, 2), nf_web=(12, 1), residual=None):
        """Fibre W/I-section. axis="y": depth along local y (column); "z": depth along local z (beam).

        Stage C: when units='N-mm', inch CSV dims × length_scale (25.4) → mm; E/Fy/G in MPa.
        Prefers is808_shapes.csv when available for Indian designations (MB/HB/UB/…).
        """
        r = shape(label, prefer_is808=self.prefer_is808)
        sc = self.length_scale
        d, tw, bf, tf = (_f(r["d"]), _f(r["tw"]), _f(r["bf"]), _f(r["tf"]))
        if None in (d, tw, bf, tf):
            raise ValueError("%s has no d/tw/bf/tf in the CSV" % label)
        d, tw, bf, tf = d * sc, tw * sc, bf * sc, tf * sc
        J = (_f(r["J"]) or 1.0) * (sc ** 4)
        hw = d - 2 * tf
        Af, Aw = bf * tf, hw * tw
        res = self.residual if residual is None else residual
        if res == "lehigh":
            rc = self.sigma_rc; rt = rc * Af / (Af + Aw)
            def sig_fl(zfrac): return rt + (-rc - rt) * zfrac       # zfrac 0 (junction) .. 1 (tip)
            sig_web = rt
        elif res == "eccs":
            a = 0.5 if d / bf <= 1.2 else 0.3
            def sig_fl(zfrac): return a * (1 - 2 * zfrac)            # +a at junction, -a at tips
            sig_web = a                                              # ECCS: web +a at flanges -> -a mid; use mean + for simplicity
        else:
            def sig_fl(zfrac): return 0.0
            sig_web = 0.0
        self.ops.section("Fiber", secTag, "-GJ", self.G * J)
        nb, nt = nf_flange
        dz = bf / nb
        nfib = 0
        for i in range(nb):
            zc = -bf / 2 + (i + 0.5) * dz
            m = self._mat(sig_fl(abs(zc) / (bf / 2)))
            for j in range(nt):
                for sgn in (+1, -1):
                    yc = sgn * (d / 2 - (j + 0.5) * tf / nt)
                    if axis == "y":
                        self.ops.fiber(yc, zc, dz * tf / nt, m)
                    else:
                        self.ops.fiber(zc, yc, dz * tf / nt, m)
                    nfib += 1
        nwy, nwz = nf_web
        m = self._mat(sig_web)
        dy = hw / nwy; dzw = tw / nwz
        for j in range(nwy):
            yc = -hw / 2 + (j + 0.5) * dy
            for q in range(nwz):
                zc = -tw / 2 + (q + 0.5) * dzw
                if axis == "y":
                    self.ops.fiber(yc, zc, dy * dzw, m)
                else:
                    self.ops.fiber(zc, yc, dy * dzw, m)
                nfib += 1
        self.log.append((secTag, label, "W", nfib, "residual=%s axis=%s units=%s" % (res, axis, self.units)))
        return dict(A=2 * Af + Aw, Ix=2 * (bf * tf ** 3 / 12 + Af * ((d - tf) / 2) ** 2) + tw * hw ** 3 / 12,
                    Iy=2 * tf * bf ** 3 / 12 + hw * tw ** 3 / 12, d=d, bf=bf, tf=tf, tw=tw, nfib=nfib)

    # ---- rectangular HSS --------------------------------------------------------------------
    def hss_rect(self, secTag, label, t_design_factor=0.93, n_per_side=8, n_thick=2, residual=None):
        """Fibre rectangular HSS (A500: design thickness = 0.93 t_nom, AISC B4.2). Corners squared off,
        area then scaled to the CSV gross area by adjusting the fibre areas (keeps A, ~I)."""
        r = shape(label)
        dims = hss_dims(label)
        if dims is None:
            raise ValueError("%s is not a rectangular HSS label" % label)
        sc = self.length_scale
        H, B, tn = dims[0] * sc, dims[1] * sc, dims[2] * sc
        t = tn * t_design_factor
        J = (_f(r["J"]) or 1.0) * (sc ** 4)
        A_csv = _f(r["A"])
        if A_csv is not None:
            A_csv = A_csv * (sc ** 2)
        res = self.residual if residual is None else residual
        self.ops.section("Fiber", secTag, "-GJ", self.G * J)
        # walls as strips: two flanges (width B, thick t) at +/-(H-t)/2 ; two webs (height H-2t) at +/-(B-t)/2
        A_model = 2 * B * t + 2 * (H - 2 * t) * t
        scale = (A_csv / A_model) if A_csv else 1.0
        nfib = 0
        def fib(y, z, a, sig):
            self.ops.fiber(y, z, a * scale, self._mat(sig))
        for sgn in (+1, -1):
            for i in range(n_per_side):
                zc = -B / 2 + (i + 0.5) * B / n_per_side
                # membrane residual: compression at flat centre, tension near corners (provisional)
                sig = 0.0
                if res == "cf_hss_membrane":
                    frac = abs(zc) / (B / 2)
                    sig = -0.15 + 0.30 * frac ** 2
                for j in range(n_thick):
                    yc = sgn * ((H - t) / 2 - t / 2 + (j + 0.5) * t / n_thick)
                    fib(yc, zc, (B / n_per_side) * (t / n_thick), sig); nfib += 1
        for sgn in (+1, -1):
            for i in range(n_per_side):
                yc = -(H - 2 * t) / 2 + (i + 0.5) * (H - 2 * t) / n_per_side
                sig = 0.0
                if res == "cf_hss_membrane":
                    frac = abs(yc) / ((H - 2 * t) / 2)
                    sig = -0.15 + 0.30 * frac ** 2
                for j in range(n_thick):
                    zc = sgn * ((B - t) / 2 - t / 2 + (j + 0.5) * t / n_thick)
                    fib(yc, zc, ((H - 2 * t) / n_per_side) * (t / n_thick), sig); nfib += 1
        self.log.append((secTag, label, "HSS", nfib, "residual=%s t_des=%.3f" % (res, t)))
        return dict(A=A_csv or A_model, H=H, B=B, t=t, nfib=nfib)

    # ---- generic dispatcher ----------------------------------------------------------------

    # ---- cold-formed built-up / Z (equivalent rectangle matching A, Ix) ---------------------
    def cfs_equiv_rect(self, secTag, label, props, residual="none", axis="y"):
        """Thin-walled C/channel fibre from label dims (Cdddxbbxtt) or props.

        Matches gross A/Ix/Iy much better than a solid A+Ix rectangle (which crushed Iy by
        ~1e4 and caused false OOP geometric instability on Sena portals). Still NO local /
        distortional buckling — disclose. Residual ignored (no calibrated CFS pattern).

        axis='y' (columns): web along local y (strong Ix about z).
        axis='z' (beams): web along local z (strong Ix about y).
        """
        import re as _re
        A = float(props["A"]); Ix = float(props["Ix"]); Iy = float(props.get("Iy") or Ix * 0.05)
        J = float(props.get("J") or 1e-4)
        labU = str(label).upper().replace(" ", "")
        # built-up e.g. 2xC203x76x2p4 or single C302x96x1p5
        m = _re.match(r"(?:(\d+)X)?C(\d+)X(\d+)X(\d+)P(\d+)", labU)
        n_ply = 1
        if m:
            if m.group(1):
                n_ply = max(int(m.group(1)), 1)
            d_mm, bf_mm, t_int, t_dec = map(int, m.groups()[1:])
            d = d_mm / 25.4
            bf = bf_mm / 25.4
            t = float("%d.%d" % (t_int, t_dec)) / 25.4
            lip = min(1.0, 0.3 * bf)
            # n_ply side-by-side (built-up): thicken web stack in weak dir by n_ply
            # fibre mesh below is single C; scale area by n_ply after A_model
        else:
            n_ply = 1
            d = (12.0 * Ix / max(A, 1e-9)) ** 0.5
            t = max(A / (2.0 * d), 0.04)
            bf = max(Iy / max(t * (d / 2.0) ** 2, 1e-9), 4.0 * t)
            lip = 0.0
        hw = max(d - 2.0 * t, d * 0.85)
        A_model = n_ply * (hw * t + 2.0 * bf * t + (2.0 * lip * t if lip > 1.5 * t else 0.0))
        scale = A / max(A_model, 1e-9)
        self.ops.section("Fiber", secTag, "-GJ", max(self.G * J * (self.length_scale ** 4 if self.units == "N-mm" else 1.0), 1.0))
        nfib = 0
        mat = self._mat(0.0)
        def add_rect(y0, z0, hy, hz, ny=4, nz=2):
            nonlocal nfib
            for i in range(ny):
                for j in range(nz):
                    yc = y0 - hy / 2 + (i + 0.5) * hy / ny
                    zc = z0 - hz / 2 + (j + 0.5) * hz / nz
                    area = scale * (hy / ny) * (hz / nz)
                    if axis == "z":
                        self.ops.fiber(zc, yc, area, mat)
                    else:
                        self.ops.fiber(yc, zc, area, mat)
                    nfib += 1
        y_fl = (d / 2 - t / 2)
        add_rect(0.0, 0.0, hw, t, ny=10, nz=2)
        add_rect(+y_fl, bf / 2 - t / 2, t, bf, ny=2, nz=6)
        add_rect(-y_fl, bf / 2 - t / 2, t, bf, ny=2, nz=6)
        if lip > 1.5 * t:
            z_lip = bf - t / 2
            add_rect(+y_fl - lip / 2, z_lip, lip, t, ny=4, nz=2)
            add_rect(-y_fl + lip / 2, z_lip, lip, t, ny=4, nz=2)
        self.log.append((secTag, label, "CFS-C", nfib,
                         "A=%.3f Ix=%.2f Iy=%.2f d=%.2f bf=%.2f t=%.3f n_ply=%d axis=%s scale=%.3f (NO local/distortional)" % (
                             A, Ix, Iy, d, bf, t, n_ply, axis, scale)))
        return dict(A=A, H=d, B=bf, t=t, nfib=nfib, Ix=Ix, Iy=Iy, J=J)


    def hss_round(self, secTag, label, n_radial=3, n_circ=16, residual=None):
        """Fibre circular hollow section (AISC HSS round or IS 1161 CHS).

        Uses CSV d (=OD) and tw/tf (=wall). Stage C: inch CSV × length_scale → mm when N-mm.
        """
        import math
        r = shape(label, prefer_is808=True)
        sc = self.length_scale
        od = _f(r.get("d") or r.get("OD") or r.get("bf"))
        t = _f(r.get("tw") or r.get("tf") or r.get("t"))
        if od is None or t is None or od <= 0 or t <= 0:
            raise ValueError("%s missing OD/t for round HSS/CHS" % label)
        od *= sc; t *= sc
        id_ = max(od - 2 * t, 0.1 * od)
        J = (_f(r.get("J")) or (math.pi / 32.0) * (od ** 4 - id_ ** 4)) * (1.0 if sc == 1.0 else 1.0)
        # when CSV J is inch^4 and sc=mm, J already from CSV in inch — scale
        if sc != 1.0:
            J = (_f(r.get("J")) or 0.0)
            if J:
                J = J * (sc ** 4)
            else:
                J = (math.pi / 32.0) * (od ** 4 - id_ ** 4)
        self.ops.section("Fiber", secTag, "-GJ", max(self.G * J, 1.0))
        mat = self._mat(0.0)
        nfib = 0
        for ir in range(n_radial):
            ri = id_ / 2 + (ir + 0.5) * t / n_radial
            dr = t / n_radial
            for ic in range(n_circ):
                th = 2 * math.pi * (ic + 0.5) / n_circ
                yc = ri * math.cos(th)
                zc = ri * math.sin(th)
                area = (2 * math.pi * ri / n_circ) * dr
                self.ops.fiber(yc, zc, area, mat)
                nfib += 1
        A = math.pi / 4.0 * (od ** 2 - id_ ** 2)
        I = math.pi / 64.0 * (od ** 4 - id_ ** 4)
        self.log.append((secTag, label, "CHS", nfib, "OD=%.3f t=%.3f units=%s" % (od, t, self.units)))
        return dict(A=A, Ix=I, Iy=I, d=od, bf=od, tf=t, tw=t, nfib=nfib)

    # ---- built-up welded box (HR custom_sections, NL-4) ------------------------------------
    def box_plates(self, secTag, label, axis="y", n_per_side=10, n_thick=2, residual=None):
        """Fibre built-up welded box from its four plates (pushover.india_sections registry, mm): flanges B x tf at
        +/-(D - tf)/2 along the depth axis, webs (D - 2 tf) x tw at +/-(B - tw)/2. axis="y": depth along local y
        (column, strong axis local z, as w_shape); "z": depth along local z (beam). No residual stress pattern
        (welded-box residual stresses are not modelled -- disclosed in the section log)."""
        from pushover import india_sections as IS_
        p = IS_.get_mm(label)
        if p is None:
            raise ValueError("%s is not a declared built-up box" % label)
        sc = 1.0 if self.units == "N-mm" else 1.0 / MM_PER_IN
        B, D, tf, tw = p["bf"] * sc, p["d"] * sc, p["tf"] * sc, p["tw"] * sc
        J = p["J"] * sc ** 4
        self.ops.section("Fiber", secTag, "-GJ", self.G * J)
        m = self._mat(0.0)
        nfib = 0

        def put(yc, zc, a):
            nonlocal nfib
            if axis == "y":
                self.ops.fiber(yc, zc, a, m)
            else:
                self.ops.fiber(zc, yc, a, m)
            nfib += 1
        for sgn in (+1, -1):                                     # flanges (full width B)
            for i in range(n_per_side):
                zc = -B / 2 + (i + 0.5) * B / n_per_side
                for j in range(n_thick):
                    yc = sgn * (D / 2 - (j + 0.5) * tf / n_thick)
                    put(yc, zc, (B / n_per_side) * (tf / n_thick))
        hw = D - 2 * tf
        for sgn in (+1, -1):                                     # webs between the flanges
            for i in range(n_per_side):
                yc = -hw / 2 + (i + 0.5) * hw / n_per_side
                for j in range(n_thick):
                    zc = sgn * (B / 2 - (j + 0.5) * tw / n_thick)
                    put(yc, zc, (hw / n_per_side) * (tw / n_thick))
        self.log.append((secTag, label, "BOX", nfib, "built-up box B=%.1f D=%.1f tf=%.1f tw=%.1f (%s) axis=%s units=%s; "
                         "no residual stress" % (p["bf"], p["d"], p["tf"], p["tw"], "mm", axis, self.units)))
        return dict(A=p["A"] * sc ** 2, Ix=p["Ix"] * sc ** 4, Iy=p["Iy"] * sc ** 4, d=D, bf=B, tf=tf, tw=tw, nfib=nfib)

    # ---- EBF shear link (NL-10) -------------------------------------------------------------
    def link_aggregator(self, aggTag, fibreTag, label, fy_MPa, box=False, hardening=0.005):
        """IS 18168:2023 11.2 shear yielding of an EBF link, added to the flexural fibre section `fibreTag`:
        V_pL = fy A_wL / sqrt(3), A_wL = (d_L - 2 t_f) t_w (x2 for a box link); elastic shear stiffness G A_wL;
        Steel01 on the vertical shear resultant (section code Vz: beams are built with their depth along local z).
        The post-yield slope (`hardening`, default 0.5 % of G A_wL, about 1.2 V_pL at 0.08 rad) is a MODELLING
        ASSUMPTION -- IS 18168 gives the strength, not a link hysteresis. Returns the record for the report."""
        from pushover import india_materials as IM
        sp = IM.section_props_mm(label)
        d, tf, tw = float(sp["d"]), float(sp["tf"]), float(sp["tw"])
        Aw_mm2 = (2.0 if box else 1.0) * (d - 2.0 * tf) * tw
        Vp_N = float(fy_MPa) * Aw_mm2 / math.sqrt(3.0)
        G_MPa_ = E_MPA / 2.6
        if self.units == "N-mm":
            Vp, K = Vp_N, G_MPa_ * Aw_mm2
        else:
            Vp, K = Vp_N / 4448.2216152605, (G_MPa_ / 6.894757293168361) * Aw_mm2 / MM_PER_IN ** 2
        mt = self.next_mat; self.next_mat += 1
        self.ops.uniaxialMaterial("Steel01", mt, Vp, K, hardening)
        self.ops.section("Aggregator", aggTag, mt, "Vz", "-section", fibreTag)
        rec = dict(section=label, Aw_mm2=Aw_mm2, fy_MPa=float(fy_MPa), Vp_kN=Vp_N / 1e3, gamma_y=float(fy_MPa) / math.sqrt(3.0) / G_MPa_,
                   hardening=hardening, clause="IS 18168:2023 11.2 a) V_pL = fy A_wL / sqrt(3) (Pu/Py <= 0.15)",
                   hardening_basis="modelling assumption (no IS link hysteresis)")
        self.log.append((aggTag, label, "LINK", 0, "shear Vp %.1f kN on Vz, fibre section %d" % (Vp_N / 1e3, fibreTag)))
        return rec

    def build(self, secTag, label, kind, axis=None):
        lab = str(label).upper().replace(" ", "")
        if lab.startswith("BOX"):
            return self.box_plates(secTag, lab, axis=(axis or ("y" if kind == "col" else "z")))
        if lab.startswith("HSS") and hss_dims(lab):
            return self.hss_rect(secTag, lab, residual=("none" if self.residual == "none" else "cf_hss_membrane"))
        # IS 1161 CHS / round HSS (no XxY rect dims)
        if lab.startswith("CHS") or (lab.startswith("HSS") and hss_dims(lab) is None):
            return self.hss_round(secTag, lab, residual="none")
        # AISC W/HP/M/S or IS 808 MB/HB/UB/JB/SC/… I-sections
        _is_i = lab.startswith(("W", "HP", "M", "S", "MB", "HB", "UB", "JB", "SC", "NPB", "WPB", "ISMB", "ISMC"))
        if _is_i and not lab.startswith("MC"):
            return self.w_shape(secTag, lab, axis=(axis or ("y" if kind == "col" else "z")))
        props = cfs_section_props(label)
        if props:
            return self.cfs_equiv_rect(secTag, lab, props, residual="none", axis=(axis or ("y" if kind == "col" else "z")))
        raise ValueError("no fibre builder for section %s (kind %s)" % (label, kind))


def elastic_props(label):
    """(A, Ix, Iy, J) from the CSV -- for gates and reporting."""
    r = shape(label)
    return _f(r["A"]), _f(r["Ix"]), _f(r["Iy"]), _f(r["J"])
