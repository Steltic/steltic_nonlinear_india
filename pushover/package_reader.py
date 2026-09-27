"""package_reader.py -- load a Steltic HR design package (the Download .zip, or the job folder it
mirrors) into one plain-Python structure the pushover pipeline can build from.

What we read (all produced by steltic's pipeline.design_and_report / bundle.make_zip):
  <building>/model_opensees.py        the EXACT elastic OpenSeesPy model (replayed ops.* calls)
  <building>/design/member_schedule.csv   ele_tag -> member kind (col/beam/brace) + AISC section
  <building>/design/calc_package.json     roles, demands, agent capacities, capacity_design block
  <building>/cfg.py                   the agent's cfg (seis params, system, heights, loads) -- optional
  <building>/report.html              USA only: fallback source for SDS/SD1/R/Cd/Om0/Ie, W, V, T (regex)
  <building>/seismic_calc.json, load_plan.json   India: structured IS 1893 Z/I/R/soil/Ta/W/VB (no SDS/SD1/Cd/Om0)

Nothing here runs the model: model_opensees.py is PARSED (regex on `ops.<cmd>(...)` lines), never
exec'd, so a package can be inspected safely before anything is analysed.
"""
from __future__ import annotations
import ast, csv, html, io, json, os, re, tempfile, zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ElasticModel:
    ndm: int = 3
    ndf: int = 6
    nodes: dict = field(default_factory=dict)         # tag -> (x, y, z)
    fixes: dict = field(default_factory=dict)         # tag -> [6 flags]
    masses: dict = field(default_factory=dict)        # tag -> [6 values]
    transfs: dict = field(default_factory=dict)       # tag -> (type, vx, vy, vz)
    elements: list = field(default_factory=list)      # dicts: tag,n1,n2,A,E,G,J,Iy,Iz,transf,release
    materials: dict = field(default_factory=dict)     # tag -> raw uniaxialMaterial args (replayed for raw elements)
    diaphragms: list = field(default_factory=list)    # (perpDir, master, [slaves])
    equal_dofs: list = field(default_factory=list)
    other: list = field(default_factory=list)         # anything we did not classify (kept for audit)


@dataclass
class DesignBasis:
    SDS: Optional[float] = None
    SD1: Optional[float] = None
    S1: Optional[float] = None
    R: Optional[float] = None
    Cd: Optional[float] = None
    Om0: Optional[float] = None
    Ie: Optional[float] = None
    system: Optional[str] = None
    W_kip: Optional[float] = None            # effective seismic weight (report; kip after bridge)
    V_design_kip: Optional[float] = None     # ELF base shear (report; kip after bridge)
    T_design_s: Optional[float] = None       # design period used for Cs (report)
    L_floor_psf: Optional[float] = None
    heights_in: Optional[list] = None
    site_class: Optional[str] = None
    package_units: Optional[str] = None      # "kip-in" | "N-mm" | "N-mm→kip-in"
    jurisdiction: Optional[str] = None       # "india" | None (USA scaffolding)
    india: Optional[dict] = None             # structured IS 1893 inputs (zone, Z, soil, I, R, Ta, W, VB, W_by_floor)
    sources: dict = field(default_factory=dict)   # field -> where it came from


@dataclass
class Package:
    root: Path
    name: str
    model: ElasticModel
    schedule: dict                 # ele_tag -> {"member": col/beam/brace, "section": "W14X311", ...}
    calc: dict                     # calc_package.json
    basis: DesignBasis
    files: dict                    # logical name -> path


# --------------------------------------------------------------------------- locating the package
def locate(path: str | os.PathLike) -> Path:
    """Accept a .zip (Steltic Download) or a folder; return the folder that holds model_opensees.py."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".zip":
        out = Path(tempfile.mkdtemp(prefix="steltic_pkg_"))
        with zipfile.ZipFile(p) as z:
            z.extractall(out)
        p = out
    if (p / "model_opensees.py").is_file():
        return p                                        # the package root itself -- never a nested copy below it
    # otherwise the shallowest hit (a zip wrapped in one top folder); feedback/<loop>/candidate/ or
    # archive/<stamp>/ copies deeper in the tree must never shadow the package the caller named
    hits = sorted(p.rglob("model_opensees.py"), key=lambda h: (len(h.parts), str(h)))
    if not hits:
        raise FileNotFoundError(f"no model_opensees.py under {p} -- is this a Steltic design package?")
    return hits[0].parent


# --------------------------------------------------------------------------- model_opensees.py
_CALL = re.compile(r"^\s*ops\.(\w+)\((.*)\)\s*$")


def _args(s: str) -> list:
    """Parse the argument list of an `ops.cmd(...)` line into Python literals."""
    try:
        node = ast.parse(f"f({s})", mode="eval").body
        return [ast.literal_eval(a) for a in node.args]
    except Exception:
        return [s]


def parse_model_script(path: Path) -> ElasticModel:
    m = ElasticModel()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        mo = _CALL.match(line)
        if not mo:
            continue
        cmd, a = mo.group(1), _args(mo.group(2))
        if cmd == "model":
            if "-ndm" in a: m.ndm = int(a[a.index("-ndm") + 1])
            if "-ndf" in a: m.ndf = int(a[a.index("-ndf") + 1])
        elif cmd == "node":
            m.nodes[int(a[0])] = tuple(float(v) for v in a[1:4])
        elif cmd == "fix":
            m.fixes[int(a[0])] = [int(v) for v in a[1:]]
        elif cmd == "mass":
            m.masses[int(a[0])] = [float(v) for v in a[1:]]
        elif cmd == "geomTransf":
            m.transfs[int(a[1])] = (str(a[0]), float(a[2]), float(a[3]), float(a[4]))
        elif cmd == "element" and a[0] == "elasticBeamColumn":
            e = dict(tag=int(a[1]), n1=int(a[2]), n2=int(a[3]), A=float(a[4]), E=float(a[5]),
                     G=float(a[6]), J=float(a[7]), Iy=float(a[8]), Iz=float(a[9]), transf=int(a[10]),
                     release=None)
            rel = [i for i, v in enumerate(a) if isinstance(v, str) and v.startswith("-release")]
            if rel:                                   # native end releases: "-releasey", code, "-releasez", code (code 1=I 2=J 3=both)
                e["release"] = a[rel[0]:]
            m.elements.append(e)
        elif cmd == "element":                        # truss / other -> keep for audit; braces come as trusses in some builds
            m.elements.append(dict(tag=int(a[1]), n1=int(a[2]), n2=int(a[3]), etype=str(a[0]), raw=a))
        elif cmd == "uniaxialMaterial":
            m.materials[int(a[1])] = a
        elif cmd == "rigidDiaphragm":
            m.diaphragms.append((int(a[0]), int(a[1]), [int(v) for v in a[2:]]))
        elif cmd == "equalDOF":
            m.equal_dofs.append(a)
        elif cmd in ("wipe",):
            pass
        else:
            m.other.append((cmd, a))
    # Steltic's export records the engine's PROBE build followed by the real build (nodes/elements/masses/
    # diaphragms appear twice with the same tags; geomTransf only once). Keep the LAST definition of each tag.
    last = {}
    for e in m.elements:
        last[e["tag"]] = e
    m.elements = list(last.values())
    if len(m.diaphragms) > 1:
        seen = {}
        for d in m.diaphragms:
            seen[d[1]] = d
        m.diaphragms = list(seen.values())
    return m


# --------------------------------------------------------------------------- schedule / calc package
def read_schedule(path: Path) -> dict:
    """Read member_schedule.csv; normalize SI (N-mm) columns to kip-in analysis fields.

    Accepts USA kip columns (length_in, P_comp_kip, Mx_kipft) and India HR SI columns
    (length_mm, P_comp_N / P_comp_kN, Mx_kNm, …). Always returns kip-in keys for the NL engine.
    """
    try:
        from snl.india_units import schedule_row_to_kip_in
    except Exception:  # pragma: no cover
        schedule_row_to_kip_in = None
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                tag = int(row["ele_tag"])
                if schedule_row_to_kip_in is not None:
                    out[tag] = schedule_row_to_kip_in(row)
                else:
                    out[tag] = {"member": row["member"].strip(), "section": row["section"].strip(),
                                "length_in": float(row.get("length_in") or 0),
                                "P_comp_kip": float(row.get("P_comp_kip") or 0),
                                "Mx_kipft": float(row.get("Mx_kipft") or 0),
                                "governing_combo": row.get("governing_combo", "")}
            except Exception:
                continue
    return out


# --------------------------------------------------------------------------- design basis
_NUM = r"([0-9]+(?:\.[0-9]+)?)"


def _basis_from_cfg(cfg_py: Path, b: DesignBasis):
    """Regex the seis(...) / dict literals out of cfg.py WITHOUT importing it (it imports engine3d)."""
    src = cfg_py.read_text(encoding="utf-8", errors="replace")
    def grab(key, pat):
        mo = re.search(pat, src)
        if mo:
            setattr(b, key, float(mo.group(1)) if key not in ("system",) else mo.group(1))
            b.sources[key] = "cfg.py"
    for key in ("SDS", "SD1", "S1", "R", "Cd", "Om0", "Ie"):
        grab(key, rf"['\"]{key}['\"]\s*:\s*{_NUM}")
        if getattr(b, key) is None:
            grab(key, rf"\b{key}\s*=\s*{_NUM}")
    mo = re.search(r"seis\(\s*" + r"\s*,\s*".join([_NUM] * 4), src)   # seis(SDS,SD1,S1,R,...) positional
    if mo and b.SDS is None:
        b.SDS, b.SD1, b.S1, b.R = (float(mo.group(i)) for i in range(1, 5)); b.sources["SDS"] = "cfg.py seis()"
    mo = re.search(r"['\"]?\bsystem['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", src)
    if mo: b.system = mo.group(1); b.sources["system"] = "cfg.py"
    mo = re.search(r"['\"]?L_floor['\"]?\s*[:=]\s*" + _NUM, src)
    if mo: b.L_floor_psf = float(mo.group(1)); b.sources["L_floor_psf"] = "cfg.py"
    mo = re.search(r"heights\s*[:=]\s*(\[[^\]]*\])", src)
    if mo:
        try:
            b.heights_in = [float(v) for v in ast.literal_eval(mo.group(1))]; b.sources["heights_in"] = "cfg.py"
        except Exception:
            pass
    mo = re.search(r"['\"]?units['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", src)
    if mo:
        b.package_units = mo.group(1); b.sources["package_units"] = "cfg.py"


def _basis_from_report(report_html: Path, b: DesignBasis):
    t = report_html.read_text(encoding="utf-8", errors="replace")
    txt = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))
    def grab(key, pat, conv=float):
        if getattr(b, key) is not None:
            return
        mo = re.search(pat, txt)
        if mo:
            setattr(b, key, conv(mo.group(1))); b.sources[key] = "report.html"
    grab("SDS", r"S\s*DS\s*=\s*" + _NUM)
    grab("SD1", r"S\s*D1\s*=\s*" + _NUM)
    grab("S1", r"S\s*1\s*=\s*" + _NUM)
    grab("R", r"\bR\s*=\s*" + _NUM)
    grab("Ie", r"I\s*e\s*=\s*" + _NUM)
    mo = re.search(r"R\s*/\s*Cd\s*/\s*Ω0\s*/\s*Ie\s*" + r"\s*/\s*".join([_NUM] * 4), txt)
    if mo:
        for k, i in (("R", 1), ("Cd", 2), ("Om0", 3), ("Ie", 4)):
            if getattr(b, k) is None:
                setattr(b, k, float(mo.group(i))); b.sources[k] = "report.html"
    # Prefer unit-tagged force lines (kN first for India SI reports, then kip / bare)
    if b.W_kip is None:
        mo = re.search(r"Seismic weight W\s*=\s*" + _NUM + r"\s*kN", txt)
        if mo:
            try:
                from snl.india_units import KN_TO_KIP
                b.W_kip = float(mo.group(1)) * KN_TO_KIP
                b.sources["W_kip"] = "report.html (kN→kip)"
            except Exception:
                pass
    if b.W_kip is None:
        grab("W_kip", r"Seismic weight W\s*=\s*" + _NUM + r"(?:\s*kip)?")
    if b.V_design_kip is None:
        mo = re.search(r"Base shear[^0-9]*" + _NUM + r"\s*kN", txt)
        if mo:
            try:
                from snl.india_units import KN_TO_KIP
                b.V_design_kip = float(mo.group(1)) * KN_TO_KIP
                b.sources["V_design_kip"] = "report.html (kN→kip)"
            except Exception:
                pass
    if b.V_design_kip is None:
        grab("V_design_kip", r"Base shear ΣF\s*=\s*" + _NUM + r"(?:\s*kip)?")
    grab("T_design_s", r"design period T\s*=\s*min\([^)]*\)\s*=\s*" + _NUM)


def is_india_package(root: Path, calc: dict | None = None) -> bool:
    """India HR package: calc/load_plan jurisdiction india, or an IS seismic_calc.json next to the model."""
    calc = calc or {}
    if str(calc.get("jurisdiction") or "").lower() == "india" or "IS 800" in str(calc.get("code") or ""):
        return True
    lp = root / "load_plan.json"
    if lp.exists():
        try:
            if str((json.load(open(lp, encoding="utf-8")) or {}).get("jurisdiction") or "").lower() == "india":
                return True
        except Exception:
            pass
    return (root / "seismic_calc.json").exists()


def _basis_india(root: Path, b: DesignBasis):
    """India: structured IS 1893 values only. SDS/SD1/Cd/Om0 are ASCE quantities and are NEVER read (WP4.1)."""
    from nlrha.india_hazard import inputs_from_package
    from snl.india_units import KN_TO_KIP
    ind = inputs_from_package(root)
    b.jurisdiction = "india"
    b.india = ind
    if ind.get("R") is not None:
        b.R = float(ind["R"]); b.sources["R"] = ind["sources"].get("R")
    if ind.get("I") is not None:
        b.Ie = float(ind["I"]); b.sources["Ie"] = ind["sources"].get("I") + " (IS 1893 Table 8 I)"
    if ind.get("W_kN") is not None:
        b.W_kip = float(ind["W_kN"]) * KN_TO_KIP; b.sources["W_kip"] = ind["sources"].get("W_kN") + " (kN→kip)"
    if ind.get("VB_kN") is not None:
        b.V_design_kip = float(ind["VB_kN"]) * KN_TO_KIP; b.sources["V_design_kip"] = ind["sources"].get("VB_kN") + " (kN→kip)"
    if ind.get("Ta") is not None:
        b.T_design_s = float(ind["Ta"]); b.sources["T_design_s"] = ind["sources"].get("Ta")
    b.SDS = b.SD1 = b.S1 = b.Cd = b.Om0 = None
    b.sources["SDS/SD1/Cd/Om0"] = "not read for India (ASCE quantities; IS 1893 elastic spectrum used, D6)"


def read_basis(root: Path, calc: dict) -> DesignBasis:
    b = DesignBasis()
    if is_india_package(root, calc):
        _basis_india(root, b)
        if (root / "cfg.py").exists():
            src = (root / "cfg.py").read_text(encoding="utf-8", errors="replace")
            mo = re.search(r"['\"]?\bsystem['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", src)
            if mo:
                b.system = mo.group(1); b.sources["system"] = "cfg.py"
            mo = re.search(r"['\"]?\bunits['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", src)
            if mo:
                b.package_units = mo.group(1); b.sources["package_units"] = "cfg.py"
    else:
        if (root / "cfg.py").exists():
            _basis_from_cfg(root / "cfg.py", b)
        if (root / "report.html").exists():
            _basis_from_report(root / "report.html", b)
    dr = root / "design" / "design_report.md"
    if b.system is None and dr.exists():
        mo = re.search(r";\s*system\s+([A-Za-z0-9 +/-]+?)\s*;", dr.read_text(errors="replace"))
        if mo:
            b.system = mo.group(1).strip(); b.sources["system"] = "design_report.md (engine label)"
    cd = calc.get("capacity_design") or {}
    if b.system is None and cd.get("system"):
        b.system = cd["system"]; b.sources["system"] = "calc_package.capacity_design"
    if b.system is None and b.jurisdiction == "india":
        lp = root / "load_plan.json"
        try:
            sysn = ((json.load(open(lp, encoding="utf-8")) or {}).get("seismic_summary") or {}).get("system")
            if sysn:
                b.system = sysn; b.sources["system"] = "load_plan.seismic_summary.system"
        except Exception:
            pass
    return b


# --------------------------------------------------------------------------- entry point
def load(path: str | os.PathLike, apply_is_mass: bool = True) -> Package:
    root = locate(path)
    files = {"model": root / "model_opensees.py",
             "schedule": root / "design" / "member_schedule.csv",
             "calc": root / "design" / "calc_package.json",
             "cfg": root / "cfg.py", "report": root / "report.html",
             "design_report": root / "design" / "design_report.md"}
    model = parse_model_script(files["model"])
    from . import india_sections as _ISEC
    _ISEC.register_from_package(root)            # NL-4: the package's built-up boxes before any section lookup
    schedule = read_schedule(files["schedule"]) if files["schedule"].exists() else {}
    calc = json.load(open(files["calc"])) if files["calc"].exists() else {}
    basis = read_basis(root, calc)
    name = calc.get("building") or root.name
    pkg = Package(root=root, name=name, model=model, schedule=schedule, calc=calc, basis=basis,
                  files={k: str(v) for k, v in files.items() if v.exists()})
    apply_nl_unit_bridge(pkg)  # Stage B: N-mm HR → kip-in analysis (no-op if already kip-in)
    if basis.jurisdiction == "india" and apply_is_mass:
        from . import india_model as IMD
        IMD.apply_is_seismic_mass(pkg)   # WP4.8: mass = IS seismic weight W_i/g (gate <= 1 %)
    return pkg


def _schedule_csv_fieldnames(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f).fieldnames or [])


def apply_nl_unit_bridge(pkg: "Package") -> "Package":
    """Stage B: if package is N-mm, convert model/basis once to kip-in; set calc['_nl_unit_bridge'].

    Schedule rows are already normalized to kip-in by read_schedule. Idempotent when
    bridge already recorded or package is kip-in.
    """
    if not isinstance(pkg.calc, dict):
        pkg.calc = {}
    if pkg.calc.get("_nl_unit_bridge"):
        return pkg
    try:
        from snl import india_units as U
    except Exception:
        return pkg

    sched_path = Path(pkg.files["schedule"]) if pkg.files.get("schedule") else (pkg.root / "design" / "member_schedule.csv")
    fieldnames = _schedule_csv_fieldnames(sched_path)
    sample_E = next((e.get("E") for e in pkg.model.elements if e.get("E") is not None), None)
    max_c = 0.0
    for xyz in pkg.model.nodes.values():
        max_c = max(max_c, max(abs(float(v)) for v in xyz))
    signals = U.detect_package_si_signals(
        schedule_fieldnames=fieldnames,
        sample_E=sample_E,
        max_node_coord=max_c,
        cfg_units=pkg.basis.package_units,
    )
    calc_units = str(pkg.calc.get("units") or "").lower()
    if calc_units in ("n-mm", "n-mm-sec", "si", "metric"):
        signals = dict(signals, likely_si=True, cfg_units_si=True)

    if not signals.get("likely_si"):
        pkg.basis.package_units = pkg.basis.package_units or "kip-in"
        return pkg

    # Stage D (native N-mm analysis) is DISABLED for pushover/NLRHA until brace_spec, column capacity,
    # pushover gravity and the NSP delta_t are ported to N-mm (NLREPO-09 / WP4.7). Always Stage B.
    cfg_probe = dict(pkg.calc or {})
    if pkg.basis.package_units:
        cfg_probe.setdefault("units", pkg.basis.package_units)
    if U.wants_native_nmm_analysis(cfg_probe):
        print("[unit_bridge] native N-mm analysis requested but NOT ported for pushover/NLRHA "
              "(WP4.7) -- forcing Stage B (N-mm -> kip-in at ingest)")
        pkg.basis.sources["stage_d_refused"] = "WP4.7: Stage B forced"
    if False:  # Stage D path kept for reference; re-enable per routine once ported
        U.set_analysis_units("N-mm")
        pkg.calc["_nl_analysis_units"] = "N-mm"
        pkg.calc["_nl_unit_bridge"] = {
            "from": "N-mm", "to": "N-mm", "analysis": "N-mm", "stage": "D",
            "note": "Native N-mm analysis — Stage B kip bridge skipped",
            "detail": dict(signals),
        }
        pkg.basis.package_units = "N-mm"
        pkg.basis.sources["unit_bridge"] = "native N-mm (Stage D)"
        return pkg

    # Convert model geometry + section props mm/MPa → in/ksi
    n_nodes = 0
    for tag, xyz in list(pkg.model.nodes.items()):
        pkg.model.nodes[tag] = tuple(float(v) * U.MM_TO_IN for v in xyz)
        n_nodes += 1
    n_mass = 0
    for tag, mvec in list(pkg.model.masses.items()):
        # translations: tonne -> kip·s²/in ; rotations (Izz etc.): tonne·mm² -> kip·s²·in (WP4.2)
        pkg.model.masses[tag] = [
            U.mass_tonne_to_kip_sec2_in(v) if i < 3 else U.rot_mass_tonne_mm2_to_kip_s2_in(v)
            for i, v in enumerate(mvec)
        ]
        n_mass += 1
    n_ele = 0
    for e in pkg.model.elements:
        if e.get("A") is not None and e.get("E") is not None:
            A, E, G, J, Iy, Iz = U.convert_elastic_section_mm_to_in(
                e["A"], e["E"], e.get("G", e["E"] / 2.6), e.get("J", 0.0),
                e.get("Iy", 0.0), e.get("Iz", 0.0),
            )
            e["A"], e["E"], e["G"], e["J"], e["Iy"], e["Iz"] = A, E, G, J, Iy, Iz
            n_ele += 1

    n_raw = convert_raw_elements_mm_to_in(pkg.model)

    if pkg.basis.heights_in:
        h0 = pkg.basis.heights_in[0]
        if h0 is not None and float(h0) >= 500:  # mm storeys
            pkg.basis.heights_in = [float(h) * U.MM_TO_IN for h in pkg.basis.heights_in]
            pkg.basis.sources["heights_in"] = (
                (pkg.basis.sources.get("heights_in") or "cfg") + " (mm→in bridge)"
            )

    detail = dict(signals, n_nodes=n_nodes, n_mass_nodes=n_mass, n_elements=n_ele, raw_elements=n_raw)
    bridge = U.build_nl_unit_bridge(source="N-mm", detail=detail)
    pkg.calc["_nl_unit_bridge"] = bridge
    pkg.calc["_nl_analysis_units"] = "kip-in"      # explicit: fibre/hinge builders must not assume N-mm (WP4.7)
    pkg.basis.package_units = "N-mm→kip-in"
    pkg.basis.sources["unit_bridge"] = "apply_nl_unit_bridge Stage B"
    return pkg


_MPA_TO_KSI = 1.0 / 6.894757293168361
_N_TO_KIP = 1.0 / 4448.2216152605
_MM_TO_IN = 1.0 / 25.4
# what one unit of a uniaxialMaterial's "stiffness" argument means, by the element that uses it
_MAT_SCALE = {"stress": _MPA_TO_KSI,                              # Truss: stress-strain (MPa -> ksi)
              "force": _N_TO_KIP / _MM_TO_IN,                     # zeroLength dir 1-3: N/mm -> kip/in
              "moment": _N_TO_KIP * _MM_TO_IN}                   # zeroLength dir 4-6: N-mm/rad -> kip-in/rad


def convert_raw_elements_mm_to_in(model: "ElasticModel") -> dict:
    """NL-4: the Stage-B bridge converted only elasticBeamColumn properties; the raw (replayed) elements kept their N-mm
    arguments inside a kip-in model. Convert them, by element type:
      * Truss / corotTruss: A mm^2 -> in^2; its material becomes a 'stress' copy (MPa -> ksi);
      * ElasticTimoshenkoBeam (EBF links): E, G MPa -> ksi; A, Avy, Avz mm^2 -> in^2; J, Iy, Iz mm^4 -> in^4;
      * zeroLength: each -mat of a translational -dir becomes a 'force' copy (N/mm -> kip/in), of a rotational -dir a
        'moment' copy (N-mm/rad -> kip-in/rad).
    Materials are cloned per usage (a tag used as stress and as force gets two copies), so no argument is converted
    twice. Only 'Elastic' materials are converted; any other raw material type used by a raw element is an error."""
    counts = dict(truss=0, timoshenko=0, zerolength=0, other=[], materials_cloned=0)
    clones = {}                                      # (old tag, usage) -> new tag
    next_tag = max([990000000] + [int(t) + 1 for t in model.materials])

    def clone(tag, usage):
        nonlocal next_tag
        key = (int(tag), usage)
        if key in clones:
            return clones[key]
        a = model.materials.get(int(tag))
        if a is None:
            raise ValueError("raw element uses uniaxialMaterial %s which the model script does not define" % tag)
        if str(a[0]) != "Elastic":
            raise ValueError("raw element material %s is %r: only 'Elastic' can be unit-converted (NL-4)" % (tag, a[0]))
        f = _MAT_SCALE[usage]
        new = ["Elastic", next_tag, float(a[2]) * f] + [(float(v) * f if i == 1 else v) for i, v in enumerate(a[3:])]
        model.materials[next_tag] = new
        clones[key] = next_tag; next_tag += 1; counts["materials_cloned"] += 1
        return clones[key]

    for e in model.elements:
        if "etype" not in e or e.get("_si_converted"):
            continue
        raw = list(e["raw"]); et = str(raw[0])
        if et in ("Truss", "truss", "corotTruss"):
            raw[4] = float(raw[4]) * _MM_TO_IN ** 2
            raw[5] = clone(raw[5], "stress")
            counts["truss"] += 1
        elif et == "ElasticTimoshenkoBeam":
            # eleTag iNode jNode E G A Jx Iy Iz Avy Avz transfTag
            raw[4] = float(raw[4]) * _MPA_TO_KSI; raw[5] = float(raw[5]) * _MPA_TO_KSI
            raw[6] = float(raw[6]) * _MM_TO_IN ** 2
            for i in (7, 8, 9):
                raw[i] = float(raw[i]) * _MM_TO_IN ** 4
            for i in (10, 11):
                raw[i] = float(raw[i]) * _MM_TO_IN ** 2
            counts["timoshenko"] += 1
        elif et == "zeroLength":
            im, idr = raw.index("-mat"), raw.index("-dir")
            mats = raw[im + 1:idr]; dirs = raw[idr + 1:idr + 1 + len(mats)]
            raw[im + 1:idr] = [clone(m, "force" if int(d) <= 3 else "moment") for m, d in zip(mats, dirs)]
            counts["zerolength"] += 1
        else:
            counts["other"].append(et)
            continue
        e["raw"] = raw; e["_si_converted"] = True
    return counts


def summary(p: Package) -> str:
    m = p.model
    kinds = {}
    for e in m.elements:
        k = p.schedule.get(e["tag"], {}).get("member", e.get("etype", "?"))
        kinds[k] = kinds.get(k, 0) + 1
    b = p.basis
    bridge = (p.calc or {}).get("_nl_unit_bridge")
    bridge_s = (" bridged %s→%s" % (bridge.get("from"), bridge.get("to"))) if bridge else ""
    return ("package %s @ %s%s\n  nodes %d, elements %d %s, diaphragms %d, fixed nodes %d, mass nodes %d\n"
            "  basis: SDS=%s SD1=%s R=%s Cd=%s Om0=%s Ie=%s system=%s W=%s kip V=%s kip T=%s s\n  sources: %s"
            % (p.name, p.root, bridge_s, len(m.nodes), len(m.elements), kinds, len(m.diaphragms), len(m.fixes),
               len(m.masses), b.SDS, b.SD1, b.R, b.Cd, b.Om0, b.Ie, b.system, b.W_kip, b.V_design_kip,
               b.T_design_s, b.sources))


if __name__ == "__main__":
    import sys
    print(summary(load(sys.argv[1])))
