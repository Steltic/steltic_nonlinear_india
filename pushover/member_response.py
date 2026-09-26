"""member_response.py -- per-member deformation recorder for the fibre NL model (WP4.3).

For every beam / column (fibre forceBeamColumn chain) and every brace (corotTruss) it samples:
  * strain_ratio : max extreme-fibre strain / eps_y over sampled integration points of the member's elements
                   (eps + |kz|·c_y + |ky|·c_z at the bounding-box corner; CHS: eps + sqrt(kz²+ky²)·D/2)
  * chord_rot    : max over both ends of the end rotation relative to the member chord (bending components only,
                   torsion excluded), rad -- compared with IS 800 §12 joint-rotation capacities as a REFERENCE (D7)
  * brace mu     : axial deformation / yield deformation (tension +, shortening -), and the buckled flag
                   (shortening beyond the buckling deformation dc)
Sampling is explicit (`sample()`), so pushover snapshots and NLRHA frames choose their own cadence.
"""
from __future__ import annotations
import math
import openseespy.opensees as ops

MM_PER_IN = 25.4


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


class MemberRecorder:
    def __init__(self, pkg, hinges: dict, stats: dict, ips=None):
        from .nonlinear_model import member_kind, SEG_ELE_BASE
        from . import india_materials as IM
        self.members = []
        self.braces = []
        nseg = int(stats.get("member_nseg") or 1)
        nip = int(stats.get("fibre_nip") or 5)
        self.ips = ips or sorted({1, (nip + 1) // 2, nip})
        india = getattr(pkg.basis, "jurisdiction", None) == "india"
        E_ksi = 29000.0
        fibre = stats.get("plasticity") == "fibre"
        self.enabled = fibre
        m = pkg.model
        from .nonlinear_model import levels
        lvz = [z for _, z, _, _ in levels(pkg)]

        def level_of(z):
            best = min(range(len(lvz)), key=lambda i: abs(lvz[i] - z)) if lvz else 0
            return best + 1

        for e in m.elements:
            kind = member_kind(pkg, e)
            sec = pkg.schedule.get(e["tag"], {}).get("section")
            if kind not in ("col", "beam") or not sec or "etype" in e:
                continue
            p1, p2 = m.nodes[e["n1"]], m.nodes[e["n2"]]
            L = math.dist(p1, p2)
            x = [(p2[i] - p1[i]) / L for i in range(3)]
            try:
                sp = IM.section_props_mm(sec)
            except Exception:
                continue
            if india:
                from . import india_model as IMD
                fy = IMD.fy_section(pkg, sec, kind, tag=e["tag"])["fye_MPa"]
            else:
                fy = 50.0 * 6.894757
            eps_y = fy / 200000.0
            d_in = (sp.get("d") or sp.get("D") or 0.0) / MM_PER_IN
            b_in = (sp.get("bf") or sp.get("D") or 0.0) / MM_PER_IN
            if sp.get("tube") and str(sp.get("type")).upper() == "CHS":
                cy = cz = d_in / 2.0; circ = True
            elif kind == "col":
                cy, cz, circ = d_in / 2.0, b_in / 2.0, False
            else:
                cy, cz, circ = b_in / 2.0, d_in / 2.0, False
            eles = [e["tag"]] + [SEG_ELE_BASE + e["tag"] * 100 + si for si in range(1, nseg)]
            # chain end nodes: fibre pins use duplicate nodes (FIB_PIN_NODE + tag*10 + 1|2) when released
            from .fibre_model import FIB_PIN_NODE
            tags = set(ops.getNodeTags()) if fibre else set()
            nA = FIB_PIN_NODE + e["tag"] * 10 + 1
            nB = FIB_PIN_NODE + e["tag"] * 10 + 2
            nA = nA if nA in tags else e["n1"]
            nB = nB if nB in tags else e["n2"]
            self.members.append(dict(tag=e["tag"], kind=kind, section=sec, eles=eles, cy=cy, cz=cz, circ=circ,
                                     eps_y=eps_y, fy_MPa=fy, nA=nA, nB=nB, x=x, L=L,
                                     z_in=max(p1[2], p2[2]), level=level_of(max(p1[2], p2[2]))))
        for t, h in hinges.items():
            if h.get("kind") != "brace":
                continue
            s = h["spec"]
            self.braces.append(dict(tag=t, section=h["section"], dT=s.dT, dc=s.dc, z_in=h["z"], level=level_of(h["z"])))

    def sample(self) -> dict:
        """{'m': {tag: (strain_ratio, chord_rot)}, 'b': {tag: (def/dT, buckled)}}"""
        out_m, out_b = {}, {}
        if self.enabled:
            for mm in self.members:
                r = 0.0
                for et in mm["eles"]:
                    for ip in self.ips:
                        try:
                            d = ops.eleResponse(et, "section", ip, "deformation")
                        except Exception:
                            d = None
                        if not d or len(d) < 3:
                            continue
                        if mm["circ"]:
                            em = abs(d[0]) + math.hypot(d[1], d[2]) * mm["cy"]
                        else:
                            em = abs(d[0]) + abs(d[1]) * mm["cy"] + abs(d[2]) * mm["cz"]
                        r = max(r, em / mm["eps_y"])
                uA, uB = ops.nodeDisp(mm["nA"]), ops.nodeDisp(mm["nB"])
                x, L = mm["x"], mm["L"]
                psi = [v / L for v in _cross(x, _sub(uB[:3], uA[:3]))]           # chord rotation vector
                th = 0.0
                for u in (uA, uB):
                    rel = _sub(u[3:6], psi)
                    tors = _dot(rel, x)
                    bend = [rel[i] - tors * x[i] for i in range(3)]
                    th = max(th, math.sqrt(_dot(bend, bend)))
                out_m[mm["tag"]] = (r, th)
        for b in self.braces:
            try:
                d = ops.eleResponse(b["tag"], "deformation")
                v = d[0] if d else 0.0
            except Exception:
                v = 0.0
            out_b[b["tag"]] = (v / b["dT"] if b["dT"] else 0.0, bool(v < -b["dc"]))
        return dict(m=out_m, b=out_b)

    @staticmethod
    def envelope(peaks: dict, smp: dict) -> dict:
        """Running peak of samples: peaks = {'m': {tag: [r, th]}, 'b': {tag: [mu_t, mu_c, buckled]}}."""
        pm = peaks.setdefault("m", {})
        for t, (r, th) in smp["m"].items():
            cur = pm.setdefault(t, [0.0, 0.0])
            cur[0] = max(cur[0], r); cur[1] = max(cur[1], th)
        pb = peaks.setdefault("b", {})
        for t, (mu, bk) in smp["b"].items():
            cur = pb.setdefault(t, [0.0, 0.0, False])
            cur[0] = max(cur[0], mu); cur[1] = max(cur[1], -mu); cur[2] = cur[2] or bk
        return peaks

    def meta(self) -> dict:
        return dict(members={mm["tag"]: dict(kind=mm["kind"], section=mm["section"], level=mm["level"], fy_MPa=mm["fy_MPa"])
                             for mm in self.members},
                    braces={b["tag"]: dict(section=b["section"], level=b["level"]) for b in self.braces},
                    ips=self.ips, enabled=self.enabled)


def group_summary(peaks_list: list, meta: dict, ref_rot: dict | None = None) -> dict:
    """Group per (kind, section, level): mean over records of the worst member and the max over records.
    peaks_list = [peaks dict per record]. Returns member_groups + brace_groups."""
    import numpy as np
    ref = (ref_rot or {}).get("value")
    groups = {}
    for tag, mt in meta["members"].items():
        k = (mt["kind"], mt["section"], mt["level"])
        groups.setdefault(k, []).append(tag)
    rows = []
    for (kind, sec, lvl), tags in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1])):
        per_rec_r, per_rec_th = [], []
        for pk in peaks_list:
            pm = pk.get("m", {})
            vals = [pm.get(t) or pm.get(str(t)) for t in tags]
            vals = [v for v in vals if v]
            if not vals:
                continue
            per_rec_r.append(max(v[0] for v in vals)); per_rec_th.append(max(v[1] for v in vals))
        if not per_rec_r:
            continue
        th_mean = float(np.mean(per_rec_th)); th_max = float(np.max(per_rec_th))
        rows.append(dict(kind=kind, section=sec, level=lvl, n=len(tags),
                         strain_ratio_mean=float(np.mean(per_rec_r)), strain_ratio_max=float(np.max(per_rec_r)),
                         yielded=bool(np.max(per_rec_r) >= 1.0),
                         chord_rot_mean_rad=th_mean, chord_rot_max_rad=th_max,
                         reference_rot_rad=ref, ratio_to_reference=(th_max / ref if ref else None)))
    bgroups = {}
    for tag, bt in meta["braces"].items():
        bgroups.setdefault((bt["section"], bt["level"]), []).append(tag)
    brows = []
    for (sec, lvl), tags in sorted(bgroups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        mt, mc, nb = [], [], []
        for pk in peaks_list:
            pb = pk.get("b", {})
            vals = [pb.get(t) or pb.get(str(t)) for t in tags]
            vals = [v for v in vals if v]
            if not vals:
                continue
            mt.append(max(v[0] for v in vals)); mc.append(max(v[1] for v in vals)); nb.append(sum(1 for v in vals if v[2]))
        if not mt:
            continue
        brows.append(dict(section=sec, level=lvl, n=len(tags), mu_tension_mean=float(np.mean(mt)),
                          mu_tension_max=float(np.max(mt)), mu_compression_mean=float(np.mean(mc)),
                          mu_compression_max=float(np.max(mc)), n_buckled_max=int(max(nb) if nb else 0),
                          yielded_tension=bool(max(mt) >= 1.0)))
    return dict(member_groups=rows, brace_groups=brows)
