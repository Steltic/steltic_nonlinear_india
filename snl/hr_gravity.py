"""hr_gravity.py -- the HR engine's own gravity loads, recorded once per job and replayed on the NL models (NL-14).

The NL models used private gravity idealisations: the pushover / NLRHA put each level's seismic weight W_i as equal
point loads on the diaphragm nodes (no beam gravity moments, no tributary column axials), and the DDM re-derived
two-way 45-degree tributary line loads from cfg pressures -- on IN_Ex3 (one-way portal roof) its rafter moments were
27-35 % of the HR design values and its gravity-transfer gate failed. This module asks steltic_india itself
(static_model.build_static + apply_gravity_state, the functions the HR design uses) for the element and nodal loads
of unit load states and stores them in <job>/nl_hr_gravity.json:

    D   fD = 1   dead (floor / roof dead incl. partitions, cladding line loads, member self-weight, nodal_dead_loads)
    L   fL = 1   floor imposed
    Lr  fLr = 1  roof imposed
    S   fS = 1   snow
    EV  fEv = 1  the IS 1893 7.3 seismic weight as a load: dead + Table 10 share of the floor imposed load (7.3.2 roof
                 imposed load excluded) -- the gravity of the NL analyses (mass = W, D6)

apply_gravity_state is linear in its factors, so any combination is sum(f_i x state_i). Loads are recorded against
the parent element of the HR model_opensees.py (beam sub-segments carry their span fraction) and nodes, in N / N-mm.
The recording runs in a child process (OpenSees is a process singleton) with $STELTIC_ENGINE_DIR on the path.

    python -m snl.hr_gravity <job> [--out FILE]       (child entry point; normally called through ensure())
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

OUT_NAME = "nl_hr_gravity.json"
STATES = {"D": dict(fD=1.0), "L": dict(fL=1.0), "Lr": dict(fLr=1.0), "S": dict(fS=1.0), "EV": dict(fEv=1.0),
          # the imposed FLOOR load alone (no partitions, no cladding): the part of a column's axial force the HR engine
          # reduces by IS 875-2 3.2.1 when cfg['column_imposed_load_reduction'] is set (static_model N_LL)
          "Lfloor": dict(fL=1.0, _cfg=dict(partition_load_kNm2=0.0, clad=0.0))}
SCHEMA = 3


def pattern_key(prefix, pattern) -> str:
    """State name of a patterned load (NL-15): 'S@X,lo' (IS 875-4 4.3 partial snow on one half of the roof) or
    'C@L,S+' (crane position L/R with surge/transverse sign; 'C@L,-' for vertical wheel loads only)."""
    return "%s@%s" % (prefix, ",".join("-" if v is None else str(v) for v in (pattern or ())))


def factors_for(fD, fL, fLr, meta=None, fS=None) -> dict:
    """Replay factors of one combination: D/L/Lr from the combo tuple, snow (plain or patterned), crane (always
    patterned in the HR engine) and vertical earthquake EV (IS 1893 6.4.6 on the seismic weight) from Case.meta."""
    m = meta or {}
    f = {"D": fD, "L": fL, "Lr": fLr}
    fs = float(m.get("fS") or 0.0) if fS is None else float(fS or 0.0)
    if fs:
        f[pattern_key("S", m["snow_pattern"]) if m.get("snow_pattern") else "S"] = fs
    fc = float(m.get("fC") or 0.0)
    if fc:
        f[pattern_key("C", m.get("crane_pattern"))] = fc
    fev = float(m.get("fEv") or 0.0)
    if fev:
        f["EV"] = f.get("EV", 0.0) + fev
    return f


def _patterns(cfg):
    """Distinct snow / crane patterns the HR combinations use (india_loads.cases_from_load_plan meta)."""
    snow, crane = set(), set()
    try:
        import india_loads as IL
        for c in IL.cases_from_load_plan(cfg) or []:
            m = getattr(c, "meta", None) or {}
            if m.get("snow_pattern") and float(m.get("fS") or 0.0):
                snow.add(tuple(m["snow_pattern"]))
            if float(m.get("fC") or 0.0):
                crane.add(tuple(m.get("crane_pattern") or ()))
    except Exception as ex:                                   # noqa: BLE001
        print("[hr_gravity] combination patterns unavailable:", ex)
    return sorted(snow, key=str), sorted(crane, key=str)


def _sha(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return None


def _inputs_sha(job):
    return {rel: _sha(os.path.join(job, rel)) for rel in ("cfg.py", "model_opensees.py", os.path.join("design", "cfg_snapshot.json"))}


def load(job) -> dict | None:
    p = os.path.join(str(job), OUT_NAME)
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None
    if d.get("schema") != SCHEMA or d.get("inputs_sha256") != _inputs_sha(str(job)):
        return None                                     # stale: the package changed since it was recorded
    return d


def ensure(job, engine_dir=None, timeout=900) -> dict | None:
    """The recorded states for this job (recording them in a child process when absent or stale). None when the HR
    engine is not available -- the caller then falls back to its own idealisation and says so."""
    job = os.path.abspath(str(job))
    d = load(job)
    if d is not None:
        return d
    eng = engine_dir or os.environ.get("STELTIC_ENGINE_DIR")
    if not eng or not os.path.exists(os.path.join(eng, "static_model.py")) or not os.path.exists(os.path.join(job, "cfg.py")):
        return None
    env = dict(os.environ, STELTIC_ENGINE_DIR=eng, MPLBACKEND="Agg", PYTHONDONTWRITEBYTECODE="1")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-m", "snl.hr_gravity", job], capture_output=True, text=True, env=env,
                       timeout=timeout, cwd=root)
    if r.returncode != 0:
        print("[hr_gravity] recording failed (rc %s): %s" % (r.returncode, (r.stderr or r.stdout)[-800:]))
        return None
    return load(job)


# ------------------------------------------------------------------------------------------------ child process
def record(job) -> dict:
    job = os.path.abspath(str(job))
    eng_dir = os.environ.get("STELTIC_ENGINE_DIR")
    if eng_dir and eng_dir not in sys.path:
        sys.path.insert(0, eng_dir)
    from steltic_ddm.ingest import load_cfg
    old = os.getcwd()
    cfg = load_cfg(job, eng_dir)
    os.chdir(job)
    try:
        import engine3d as E
        import static_model as SM
        try:
            E.ensure_units(cfg)
        except Exception:
            pass
        model = SM.build_static(cfg, nseg=10)
        seg = {}
        for b in model["beams"]:
            n = len(b["segs"])
            parent = b.get("etag")
            for s, t in enumerate(b["segs"]):
                seg[t] = (parent, s / n, (s + 1) / n, "beam", b.get("A"), b.get("B"))
        for c in model["cols"]:
            seg[c["tag"]] = (c["tag"], 0.0, 1.0, "col", c.get("n1"), c.get("n2"))
        for br in model["braces"]:
            seg[br["tag"]] = (br["tag"], 0.0, 1.0, "brace", br.get("n1"), br.get("n2"))
        ops = SM.ops
        real_ele, real_load = ops.eleLoad, ops.load
        cur = {"ele": [], "node": {}, "unmapped": []}

        def rec_ele(*a):
            a = list(a)
            if len(a) >= 5 and a[0] == "-ele" and a[2] == "-type":
                tag, typ, vals = int(a[1]), str(a[3]).lstrip("-"), [float(v) for v in a[4:]]
                m = seg.get(tag)
                if m is None or m[0] is None:
                    cur["unmapped"].append([tag, typ, vals])
                else:
                    cur["ele"].append([int(m[0]), m[1], m[2], typ, vals])
            else:
                cur["unmapped"].append(["?", str(a)[:80], []])

        def rec_load(node, *vals):
            v = [float(x) for x in vals]
            acc = cur["node"].setdefault(str(int(node)), [0.0] * 6)
            for i in range(min(6, len(v))):
                acc[i] += v[i]
        ops.eleLoad, ops.load = rec_ele, rec_load
        out = {}
        states = dict(STATES)
        snow_p, crane_p = _patterns(cfg)
        for sp in snow_p:
            states[pattern_key("S", sp)] = dict(fS=1.0, snow_pattern=sp)
        for cp in crane_p:
            states[pattern_key("C", cp)] = dict(fC=1.0, crane_pattern=(cp or None))
        try:
            for name, f in states.items():
                cur.update(ele=[], node={}, unmapped=[])
                cfg_s = dict(cfg, **f["_cfg"]) if f.get("_cfg") else cfg
                kw = {k: f[k] for k in ("snow_pattern", "crane_pattern") if f.get(k)}
                lev = SM.apply_gravity_state(cfg_s, model, f.get("fD", 0.0), f.get("fL", 0.0), f.get("fLr", 0.0),
                                             fS=f.get("fS", 0.0), fC=f.get("fC", 0.0), fEv=f.get("fEv", 0.0),
                                             self_weight=cfg.get("self_weight", True), **kw)
                out[name] = dict(factors={k: (list(v) if isinstance(v, tuple) else v) for k, v in f.items()
                                          if not k.startswith("_")}, ele=list(cur["ele"]), node=dict(cur["node"]), unmapped=list(cur["unmapped"]),
                                 level_totals_N={str(k): float(v) for k, v in (lev or {}).items()},
                                 total_N=float(sum((lev or {}).values())))
        finally:
            ops.eleLoad, ops.load = real_ele, real_load
    finally:
        os.chdir(old)
    llr = {}
    if cfg.get("column_imposed_load_reduction"):
        NF = len(cfg["heights"])
        for c in model["cols"]:
            k_top = max(int(c["n1"]), int(c["n2"])) // 100000
            llr[str(c["tag"])] = SM.imposed_load_reduction_321(NF - k_top + 1)
    return dict(schema=SCHEMA, job=os.path.basename(job), units="N, mm (w in N/mm, moments N-mm)",
                column_imposed_load_reduction=llr,
                source="steltic_india static_model.build_static(nseg=10) + apply_gravity_state (the HR design's gravity)",
                engine=os.environ.get("STELTIC_ENGINE_DIR"), inputs_sha256=_inputs_sha(job), states=out,
                note=("EV = IS 1893 7.3 seismic weight as a load (dead + Table 10 imposed share, roof imposed excluded); "
                      "combinations are sum(f_i x state_i) -- apply_gravity_state is linear in its factors"))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="snl.hr_gravity")
    ap.add_argument("job"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    d = record(a.job)
    p = a.out or os.path.join(os.path.abspath(a.job), OUT_NAME)
    json.dump(d, open(p, "w", encoding="utf-8"), separators=(",", ":"))
    print("wrote", p, {k: round(v["total_N"] / 1e3, 1) for k, v in d["states"].items()})
    return 0


# ------------------------------------------------------------------------------------------------ replay helpers
def combine(d: dict, factors: dict) -> dict:
    """{'ele': [[parent, x0, x1, type, vals]], 'node': {node: [6]}} for sum(f x state). factors keys D/L/Lr/S/EV and
    the patterned states S@.. / C@.. (NL-15). A non-zero factor on a state that was not recorded raises KeyError:
    silently dropping it (the pre-NL-15 behaviour for partial snow and crane loads) under-loads the model."""
    ele, node = [], {}
    for name, f in factors.items():
        if not f:
            continue
        st = (d.get("states") or {}).get(name)
        if not st:
            raise KeyError("HR gravity state %r was not recorded for this job (states: %s)"
                           % (name, sorted((d.get("states") or {}).keys())))
        for parent, x0, x1, typ, vals in st["ele"]:
            ele.append([parent, x0, x1, typ, [f * v for v in vals]])
        for n, v in st["node"].items():
            acc = node.setdefault(n, [0.0] * 6)
            for i in range(6):
                acc[i] += f * v[i]
    return dict(ele=ele, node=node)


def apply(ops, loads: dict, chains: dict, force_scale=1.0, length_scale=1.0) -> dict:
    """Replay combined loads on a model whose parent element `p` is the chain chains[p] = [(sub_tag, s0, s1), ...]
    (span fractions). w (force / length) is scaled by force_scale / length_scale, nodal forces by force_scale and
    moments by force_scale * length_scale. Loads on a parent that is not in the model are summed in 'missing'.
    A uniform load over [x0, x1] of the HR segment goes to every sub-element overlapping it, weighted by overlap."""
    wf = force_scale / length_scale
    missing, n_ele = 0.0, 0
    per_sub = {}
    for parent, x0, x1, typ, vals in loads.get("ele", []):
        ch = chains.get(int(parent))
        if not ch:
            missing += abs(sum(vals)) * (x1 - x0)
            continue
        for sub, s0, s1 in ch:
            ov = max(0.0, min(x1, s1) - max(x0, s0))
            if ov <= 0:
                continue
            w = ov / (s1 - s0)
            acc = per_sub.setdefault((sub, typ), [0.0] * len(vals))
            if len(acc) < len(vals):
                acc += [0.0] * (len(vals) - len(acc))
            for i, v in enumerate(vals):
                acc[i] += w * v
    for (sub, typ), vals in per_sub.items():
        ops.eleLoad("-ele", sub, "-type", "-" + typ, *[v * wf for v in vals])
        n_ele += 1
    n_node = 0
    for n, v in loads.get("node", {}).items():
        if not any(abs(x) > 0 for x in v):
            continue
        ops.load(int(n), *(v[i] * force_scale for i in range(3)), *(v[i] * force_scale * length_scale for i in range(3, 6)))
        n_node += 1
    return dict(n_element_loads=n_ele, n_nodal_loads=n_node, missing=missing)


if __name__ == "__main__":
    sys.exit(main())
