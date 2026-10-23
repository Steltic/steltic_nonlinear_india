"""viewer3d_india.py -- India pushover viewer (pushover/pushover_viewer_3d.html), NL-32.

The US viewer (pushover/viewer3d.py) is built around ASCE 41: IO / LS / CP hinge limits, the NSP C0-C2 target and
the FEMA P-695 factors. None of that exists on the India path (owner rulings D6 / D7), so the India run never wrote a
viewer and the Pushover tab of the Steltic viewer bundle stayed empty. This viewer shows the India pushover on the
same shared core (geometry, palette, controls, the bundle):

  * a direction selector and the capacity curve (base shear vs roof displacement) as a scrubber, with the IS-DBE
    and IS-MCE target displacements marked;
  * the deformed building at the selected step (diaphragm masters, push direction);
  * braces coloured elastic / buckled / yielded in tension, beams / columns by their fibre strain ratio (>= 1:
    yielded), EBF links by their shear ductility, NL-21 elastic gravity members by their demand / capacity ratio;
  * storey drifts at the step, with the IS 1893 7.11.1.1 0.004 h line drawn for comparison only (it is the LINEAR
    design check under VB, not an NL criterion);
  * the direction summary (T1, Vmax, Vmax / VB, the DBE / MCE targets) and the D7 sentence. No verdict.

Two data sources, one viewer:
  * "full"  -- written by the run (`_run_india`) from the per-step records; also saved as viewer_data.json.gz so
               `snl report` can rebuild the viewer without re-running;
  * "lite"  -- rebuilt from pushover_package.json alone (jobs run before NL-32): the curve plus three snapshots
               (unloaded, IS-DBE, IS-MCE target). The deformed shape comes from the saved storey drifts and the
               colours from the saved member-group peaks (kind, section, level), so it is per group, not per element.

Units: mm and kN (the model geometry is converted from the NL kip-in analysis units).
"""
from __future__ import annotations
import gzip, json, os

from . import viewer_core as VC

MM = 25.4
KN = 4.4482216152605
IS_NL_STATEMENT = ("IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; "
                   "results are for information.")
DATA_FILE = "viewer_data.json.gz"
HTML_FILE = "pushover_viewer_3d.html"
MAX_FRAMES = 200
TARGETS = ("IS-DBE", "IS-MCE")

LEFT = """
<h2>Push direction</h2>
<select id="dirSel"></select>
<div id="liteNote" style="display:none;font-size:11px;color:#ffb454;line-height:1.45;margin:6px 0 2px"></div>
<h2 id="stepHead">Step on the capacity curve</h2>
<input type="range" id="step" min="0" max="1" value="0">
<div class="row"><span class="val" id="stepU" style="flex:1;text-align:left"></span></div>
<div class="btns"><button id="play" class="acc">▶ play</button><button id="toDBE">IS-DBE target</button><button id="toMCE">IS-MCE target</button><button id="toVmax">Vmax</button><button id="toEnd">end</button></div>
<h2>Colour by</h2>
<select id="colorMode"><option value="state">Component state</option><option value="type">Member type</option><option value="sec">Section</option></select>
"""
RIGHT = """
<h2 style="margin-top:0">At this step</h2>
<div id="stepStats"></div>
<h2>Storey drift at this step · 0.004 h (linear check, for comparison)</h2>
<div id="driftBars"></div>
<h2>Component census at this step</h2>
<div id="census"></div>
<h2>Direction summary (information, no verdict)</h2>
<div id="dirTable"></div>
"""
MODULE_JS = r"""
const N = DATA.pushover_india; const P = N; const DK = Object.keys(P.dirs); let di = 0, step = 0, playing = false, colorMode = 'state';
const LITE = P.mode === 'lite';
function D(){ return P.dirs[DK[di]]; }
const SECS = [...new Set(M.elements.map(e=>e.sec))]; const SEC_PAL = [0x5b8dd9,0x2ecc71,0xe67e22,0x9b59b6,0xf1c40f,0x1abc9c,0xe74c3c,0x95a5a6,0xd35400,0x3498db,0x27ae60,0xc0392b];
const SEC_COL = {}; SECS.forEach((s,i)=>SEC_COL[s]=SEC_PAL[i%SEC_PAL.length]);
const PARTIAL = 0xb5651d;                       // lite: some braces of the group buckled (which ones is not recorded)
const IDX = {}; ['member_tags','brace_tags','link_tags','elastic_tags'].forEach(k => { IDX[k] = {}; (P[k]||[]).forEach((t,i)=>IDX[k][t]=i); });
function nFrames(){ return D().frames.ci.length; }
function F(){ return D().frames; }
function statesAt(s){
  const st = {}; const fr = F();
  if (LITE){ const g = fr.groups[s] || {}; for (const [t, gid] of Object.entries(P.elem_group)) { const r = g[gid]; if (r) st[t] = r.state; } return st; }
  const m = fr.m[s]||[], bm = fr.b_mu[s]||[], bk = new Set(fr.b_bk[s]||[]), l = fr.l[s]||[], eg = fr.eg[s]||[];
  (P.member_tags||[]).forEach((t,i)=>{ st[t] = (m[i]||0) >= 1 ? 'yield' : 'elastic'; });
  (P.link_tags||[]).forEach((t,i)=>{ st[t] = (l[i]||0) >= 1 ? 'yield' : 'elastic'; });
  (P.elastic_tags||[]).forEach((t,i)=>{ st[t] = (eg[i]||0) >= 1 ? 'yield' : 'elastic'; });
  (P.brace_tags||[]).forEach((t,i)=>{ st[t] = bk.has(i) ? 'buckled' : ((bm[i]||0) >= 1 ? 'tension' : 'elastic'); });
  return st;
}
function floorsAt(s){ const dof = D().dof; return [[0,0,0]].concat(F().story[s].map(u => dof===0 ? [u,0,0] : [0,u,0])); }
function colOf(state){ return state==='partial' ? PARTIAL : STATE[state||'elastic']; }
function paint(s){
  const st = statesAt(s);
  for (const mesh of meshes){ const e=mesh.userData; let hex;
    if (colorMode==='type') hex = TYPE_COL[e.type]; else if (colorMode==='sec') hex = SEC_COL[e.sec]; else hex = colOf(st[e.tag]);
    setColor(mesh, hex); }
  return st;
}
function fmt(v,n){ return (v===null||v===undefined||Number.isNaN(v))?'—':Number(v).toFixed(n===undefined?2:n); }
function pct(v){ return (100*v).toFixed(3)+'%'; }
function curveAt(s){ const d = D(); const i = F().ci[s]; return [d.curve.u[i], d.curve.V[i]]; }
function update(){
  const n = nFrames(); step = Math.max(0, Math.min(n-1, step));
  document.getElementById('step').max = n-1; document.getElementById('step').value = step;
  applyDeformation(floorsAt(step)); const st = paint(step);
  const d = D(); const [u, V] = curveAt(step); const lab = (F().label||[])[step];
  document.getElementById('stepU').textContent = `${lab ? lab+' · ' : ''}roof ${fmt(u,1)} mm · V ${fmt(V,0)} kN`;
  const story = F().story[step]; const dr = []; let prev = 0; story.forEach((x,i)=>{ dr.push((x-prev)/P.heights[i]); prev = x; });
  document.getElementById('stepStats').innerHTML = rows([['Direction', DK[di]], ['Step', LITE ? (lab||'') : `${step+1} of ${n} shown (${d.n_steps} analysed)`],
    ['Roof displacement', `${fmt(u,1)} mm (${pct(u/P.H)} of H)`], ['Base shear', `${fmt(V,0)} kN`], ['V / VB', d.VB_kN ? fmt(V/d.VB_kN,2) : '—'],
    ['Max storey drift now', pct(Math.max(...dr.map(Math.abs)))]]);
  const lin = P.linear_drift_ratio; const scale = Math.max(0.0005, ...dr.map(Math.abs), lin)*1.25;
  const bar = v => `<span style="flex:1;margin:0 6px;height:8px;background:#1d222b;border-radius:3px;position:relative;top:4px">
      <span style="position:absolute;left:0;top:0;height:8px;width:${(100*Math.min(Math.abs(v),scale)/scale).toFixed(1)}%;background:#ffb454;border-radius:3px"></span>
      <span style="position:absolute;left:${(100*lin/scale).toFixed(1)}%;top:-2px;height:12px;width:1px;background:#8b95a3"></span></span>`;
  document.getElementById('driftBars').innerHTML = dr.map((v,i)=>`<div class="stat"><span style="min-width:54px">storey ${i+1}</span>${bar(v)}<b style="min-width:52px;text-align:right">${pct(Math.abs(v))}</b></div>`).join('')
    + `<div style="font-size:10.5px;color:#8b95a3;margin-top:4px">grey line = ${pct(lin)} (IS 1893 7.11.1.1 is the LINEAR design check under VB, shown for comparison only -- not an NL criterion)</div>`;
  if (LITE){ const c = (F().census||[])[step] || {};
    document.getElementById('census').innerHTML = rows([['Braces buckled', c.braces_buckled ?? '—'], ['Brace groups yielded in tension', c.brace_groups_tension ?? '—'],
      ['Member groups yielded (ε/εy ≥ 1)', c.member_groups_yielded === undefined ? '—' : `${c.member_groups_yielded} of ${c.member_groups}`],
      ['Link groups yielded (γ/γy ≥ 1)', c.link_groups ? `${c.link_groups_yielded} of ${c.link_groups}` : '—']]); }
  else { const B = P.brace_tags||[];
    document.getElementById('census').innerHTML = rows([['Braces buckled', B.filter(t=>st[t]==='buckled').length + ' of ' + B.length],
      ['Braces yielded in tension', B.filter(t=>st[t]==='tension').length],
      ['Beams / columns yielded (ε/εy ≥ 1)', (P.member_tags||[]).filter(t=>st[t]==='yield').length + ' of ' + (P.member_tags||[]).length],
      ['EBF links yielded (γ/γy ≥ 1)', (P.link_tags||[]).length ? (P.link_tags.filter(t=>st[t]==='yield').length + ' of ' + P.link_tags.length) : '—'],
      ['Elastic gravity members at D/C ≥ 1', (P.elastic_tags||[]).length ? (P.elastic_tags.filter(t=>st[t]==='yield').length + ' of ' + P.elastic_tags.length) : '—']]); }
  redrawChart();
}
function redrawChart(){
  const d = D(); const pts = d.curve.u.map((u,i)=>[u, d.curve.V[i]]);
  const xmax = Math.max(1e-6, ...d.curve.u)*1.03, ymax = Math.max(1e-6, ...d.curve.V, d.VB_kN||0)*1.12;
  const [u, V] = curveAt(step);
  const vlines = Object.entries(d.targets).map(([k,t],i)=>({x:t.u_mm, color: k==='IS-DBE'?'#3fc1a0':'#e74c3c', label:`${k} δt ${fmt(t.u_mm,0)} mm`, dy:i*12}));
  const hl = d.VB_kN ? [{y:d.VB_kN, color:'#8b95a3', label:''}] : [];
  drawChart({xmin:0, xmax, ymin:0, ymax, series:[{pts, color:'#ffb454', width:1.8}], vlines, hlines:hl, cursor:[u, V], cursorColor:'#ffb454',
    title:`Capacity curve — push ${DK[di]}${d.VB_kN ? ' · grey line = V-bar_B (HR design)' : ''}`, xlabel:'roof displacement (mm)', ylabel:'kN', yfmt:v=>v.toFixed(0), xfmt:v=>v.toFixed(0)});
}
function onChartSeek(x){ const d = D(); const ci = F().ci; let best=0,bd=1e18; ci.forEach((i,s)=>{ const v=Math.abs(d.curve.u[i]-x); if(v<bd){bd=v;best=s;} }); step=best; update(); }
function onDeformed(){} function onVisibility(){ paint(step); }
function onSpace(){ if (LITE) return; playing=!playing; document.getElementById('play').textContent = playing?'❚❚ pause':'▶ play'; }
let acc=0; function onTick(dt){ if(!playing) return; acc+=dt; while(acc>=0.05){ acc-=0.05; step++; if(step>=nFrames()){ step=nFrames()-1; onSpace(); break; } } update(); }
function memberInfo(e){
  const lines = [['Length', `${e.L?e.L.toFixed(0):'—'} mm`], ['Level', e._lvl], ['Section', e.sec]]; const fr = F();
  if (LITE){ const gid = P.elem_group[e.tag]; const g = gid !== undefined ? (fr.groups[step]||{})[gid] : null;
    if (g) lines.push(['Group (kind · section · level)', P.group_label[gid]], ...g.info.map(x=>[x[0], x[1]]));
    else lines.push(['Group', 'not in the saved member groups (elastic gravity member or unrecorded)']);
    return rows(lines); }
  const pick = (k, arr) => { const i = IDX[k][e.tag]; return i === undefined ? null : i; };
  let i;
  if ((i = pick('member_tags')) !== null){ const pk = Math.max(...fr.m.map(r=>r[i]||0)); lines.push(['Fibre strain ratio ε/εy now', fmt(fr.m[step][i])], ['Peak over the shown steps', fmt(pk)], ['IS 800 §12 joint rotation (reference only)', P.reference_rot ? `${P.reference_rot} rad` : '—']); }
  if ((i = pick('link_tags')) !== null) lines.push(['Link shear ductility γ/γy now', fmt(fr.l[step][i])], ['IS 18168 12.3.3.1 link rotation (reference only)', '0.08 rad']);
  if ((i = pick('elastic_tags')) !== null) lines.push(['Elastic gravity member D/C now', fmt(fr.eg[step][i])]);
  if ((i = pick('brace_tags')) !== null){ const bk = (fr.b_bk[step]||[]).includes(i); lines.push(['Axial deformation / Δy now (+tension)', fmt(fr.b_mu[step][i])], ['Buckled now', bk ? 'yes' : 'no'], ['Δc (buckling) / Δy (tension yield)', `${fmt(P.brace_spec[i][0],2)} / ${fmt(P.brace_spec[i][1],2)} mm`]); }
  return rows(lines);
}
function dirTable(){
  const d = D(); const r = [['Statement', `<i>${P.statement}</i>`], ['T1 (fibre model, push mode)', `${fmt(d.T1,3)} s`],
    ['Vmax · at roof u', `${d.lower_bound?'≥ ':''}${fmt(d.Vmax_kN,0)} kN · ${fmt(d.u_at_Vmax_mm,1)} mm${d.lower_bound?' (lower bound: the curve ended in a numerical stop)':''}`], ['V-bar_B (HR design, this direction)', d.VB_kN ? `${fmt(d.VB_kN,0)} kN` : '—'],
    ['Vmax / V-bar_B', `${d.lower_bound?'≥ ':''}${fmt(d.Vmax_over_VB,2)}`], ['Stop', d.stop||'—']];
  if (d.review) r.unshift(['UNDER REVIEW', `<b>${d.review}</b>`]);
  const nr = d.targets_not_reached || [];
  for (const [k,t] of Object.entries(d.targets)) r.push([`${k}: Te · Sa · δt`, `${fmt(t.Te,3)} s · ${fmt(t.Sa,3)} g · ${fmt(t.u_mm,1)} mm${nr.includes(k)?' (not reached)':''}`], [`${k}: V / VB · max drift${nr.includes(k)?' at the curve end':''}`, `${fmt(t.V_over_VB,2)} · ${pct(t.max_drift||0)}`]);
  document.getElementById('dirTable').innerHTML = rows(r);
}
function show(id, on){ const el = document.getElementById(id); if (el && el.style) el.style.display = on ? 'block' : 'none'; }
function jumpTo(key){ const d = D(); if (key==='end'){ step=nFrames()-1; } else if (key==='vmax'){ step = d.vmax_frame; } else { const t = d.targets[key]; if (t) step = t.frame; } update(); }
function init(){
  const ds = document.getElementById('dirSel'); DK.forEach((k,i)=>{ const o=document.createElement('option'); o.value=i; o.textContent=`push ${k}`; ds.appendChild(o); });
  ds.onchange = e => { di=parseInt(e.target.value); step = LITE ? 0 : step; dirTable(); update(); };
  document.getElementById('step').oninput = e => { step=parseInt(e.target.value); update(); };
  document.getElementById('toDBE').onclick = () => jumpTo('IS-DBE');
  document.getElementById('toMCE').onclick = () => jumpTo('IS-MCE');
  document.getElementById('toVmax').onclick = () => jumpTo('vmax');
  document.getElementById('toEnd').onclick = () => jumpTo('end');
  document.getElementById('play').onclick = onSpace;
  document.getElementById('colorMode').onchange = e => { colorMode=e.target.value; setLegend(); paint(step); };
  if (LITE){ ['play','toVmax','toEnd'].forEach(id => show(id, false));
    document.getElementById('stepHead').textContent = 'Snapshot'; show('liteNote', true); document.getElementById('liteNote').innerHTML = P.lite_note; }
  setLegend(); dirTable(); step = LITE ? 1 : 0; update();
}
function setLegend(){ if (colorMode==='state'){ const it = [[STATE.elastic,'elastic'],[STATE.yield, LITE ? 'yielded (group peak ε/εy ≥ 1, link γ/γy ≥ 1)' : 'yielded (ε/εy ≥ 1, link γ/γy ≥ 1, elastic gravity D/C ≥ 1)'],[STATE.buckled, LITE ? 'brace group: all buckled' : 'brace buckled'],[STATE.tension,'brace yielded in tension']];
    if (LITE) it.push([PARTIAL,'brace group: some buckled (which ones not recorded)']);
    legend(it, LITE ? 'Component state per member group (kind · section · level) at the snapshot' : 'Component state at this step', P.statement); }
  else if (colorMode==='type') legend([[TYPE_COL.column,'column'],[TYPE_COL.beam,'beam'],[TYPE_COL.brace,'brace']], 'Member type'); else legend(SECS.map(s=>[SEC_COL[s],s]), 'Section'); }
"""


def _r(v, n=3):
    try:
        x = round(float(v), n)
        return 0 if x == 0 else x
    except Exception:
        return None


def _mm_model(pkg):
    model = VC.model_from_package(pkg)
    model["nodes"] = {k: [round(v * MM, 1) for v in xyz] for k, xyz in model["nodes"].items()}
    model["cm"] = {k: [round(v * MM, 1) for v in xy] for k, xy in (model.get("cm") or {}).items()}
    model["slabs"] = [[round(v * MM, 1) for v in s] for s in model.get("slabs") or []]
    model["levels"] = [round(v * MM, 1) for v in model.get("levels") or []]
    for e in model["elements"]:
        n1, n2 = model["nodes"][str(e["n"][0])], model["nodes"][str(e["n"][1])]
        e["L"] = round(sum((a - c) ** 2 for a, c in zip(n1, n2)) ** 0.5, 1)
    return model


def _heights(pkg):
    from .nonlinear_model import levels
    zs = [z for _, z, _, _ in levels(pkg)]
    return [round((z - (zs[i - 1] if i else 0.0)) * MM, 1) for i, z in enumerate(zs)], zs


def _frame_indices(n, must):
    """At most MAX_FRAMES curve indices: evenly spaced, plus every index in `must` (targets, Vmax, the end)."""
    if n <= MAX_FRAMES:
        return list(range(n))
    k = MAX_FRAMES - len(must)
    base = {round(i * (n - 1) / max(k - 1, 1)) for i in range(k)}
    return sorted(base | {i for i in must if 0 <= i < n})


def _common(pkg, ppkg_basis=None):
    from . import india_materials as IM
    heights, _ = _heights(pkg)
    return dict(statement=IS_NL_STATEMENT, heights=heights, H=round(sum(heights), 1), linear_drift_ratio=0.004,
                reference_rot=IM.reference_rotation(pkg.basis.system).get("value"))


# ------------------------------------------------------------------ full: from the in-memory run (India _run_india)
def data_from_run(pkg, runs: dict, results: dict, brace_dims: dict | None = None) -> dict:
    """Viewer data from the India run records: run['rec'] (u, V, story_u, members = MemberRecorder samples, elastic),
    results[d] (nsp, capacity, resp, meta) and brace_dims {tag: (dc_in, dT_in)} from the MemberRecorder."""
    first = results[next(iter(results))]
    meta = first.get("meta") or {}
    member_tags = sorted(int(t) for t in (meta.get("members") or {}))
    brace_tags = sorted(int(t) for t in (meta.get("braces") or {}))
    link_tags = sorted(int(t) for t in (meta.get("links") or {}))
    eg_tags = sorted({int(t) for r in runs.values() for smp in (r["rec"].get("elastic") or []) for t in smp})
    bd = {int(t): v for t, v in (brace_dims or {}).items()}
    brace_spec = [[_r(bd[t][0] * MM, 3), _r(bd[t][1] * MM, 3)] if t in bd else [None, None] for t in brace_tags]
    dirs = {}
    for d, run in runs.items():
        rec = run["rec"]; R = results[d]
        n = len(rec["u"])
        tgt_idx = {}
        for lvn in TARGETS:
            rp = (R.get("resp") or {}).get(lvn) or {}
            br = rp.get("step_bracket")
            if br:
                i0, i1 = int(br[0]), int(br[1]); w = float(rp.get("weight") or 0.0)
                tgt_idx[lvn] = i1 if w >= 0.5 else i0
        vmax_i = max(range(n), key=lambda i: rec["V"][i]) if n else 0
        idx = _frame_indices(n, set(tgt_idx.values()) | {vmax_i, n - 1, 0})
        samples = rec.get("members") or []
        eg = rec.get("elastic") or []
        fr = dict(ci=idx, story=[[_r(u * MM, 2) for u in rec["story_u"][i]] for i in idx], m=[], b_mu=[], b_bk=[], l=[], eg=[])
        for i in idx:
            smp = samples[i] if i < len(samples) else {}
            m, b, l = smp.get("m") or {}, smp.get("b") or {}, smp.get("l") or {}
            fr["m"].append([_r((m.get(t) or m.get(str(t)) or (0.0, 0.0))[0], 2) for t in member_tags])
            bv = [b.get(t) or b.get(str(t)) or (0.0, False) for t in brace_tags]
            fr["b_mu"].append([_r(v[0], 2) for v in bv]); fr["b_bk"].append([j for j, v in enumerate(bv) if v[1]])
            fr["l"].append([_r((l.get(t) or l.get(str(t)) or (0.0, 0.0))[1], 2) for t in link_tags])
            e_ = eg[i] if i < len(eg) else {}
            fr["eg"].append([_r(e_.get(t) or e_.get(str(t)) or 0.0, 2) for t in eg_tags])
        cap = R.get("capacity") or {}
        targets = {}
        for lvn in TARGETS:
            nn = (R.get("nsp") or {}).get(lvn) or {}; rp = (R.get("resp") or {}).get(lvn) or {}
            if not nn:
                continue
            targets[lvn] = dict(u_mm=_r(nn.get("target_disp_in", 0) * MM, 1), Te=_r(nn.get("Te"), 4), Sa=_r(nn.get("Sa"), 4),
                                V_over_VB=_r(rp.get("V_over_VB"), 3), max_drift=_r(rp.get("max_story_drift"), 6),
                                frame=idx.index(tgt_idx[lvn]) if lvn in tgt_idx else 0)
        dirs[d] = dict(dof=0 if d.upper() == "X" else 1, T1=_r(run["pattern"]["T1"], 4), n_steps=n,
                       curve=dict(u=[_r(x * MM, 2) for x in rec["u"]], V=[_r(x * KN, 1) for x in rec["V"]]),
                       Vmax_kN=_r(cap.get("Vmax_kN"), 1), u_at_Vmax_mm=_r((cap.get("u_at_Vmax_in") or 0) * MM, 1),
                       Vmax_over_VB=_r(cap.get("Vmax_over_VB"), 3), VB_kN=_r((cap.get("V_design_kip") or 0) * KN, 1) or None,
                       stop=run.get("stop_reason"), targets=targets, vmax_frame=idx.index(vmax_i), frames=fr)
    return dict(mode="full", **_common(pkg), member_tags=member_tags, brace_tags=brace_tags, link_tags=link_tags,
                elastic_tags=eg_tags, brace_spec=brace_spec, dirs=dirs)


# ------------------------------------------------------------------ lite: from pushover_package.json (pre-NL-32 jobs)
LITE_NOTE = ("Lite viewer, rebuilt from the stored pushover results: this job was run before the step-by-step viewer "
             "existed, so the per-step member states were not saved. Three snapshots (unloaded, IS-DBE and IS-MCE target); deformed shape from the saved "
             "storey drifts; colours per member group (kind · section · level) from the saved group peaks. Re-run the "
             "pushover for the step-by-step viewer.")


def _lite_groups(pkg):
    """element tag -> group id, with the group keys of member_response.group_summary: (kind, section, level) for
    beams / columns, ('brace', section, level), ('link', section, level)."""
    from .nonlinear_model import member_kind
    _, zs = _heights(pkg)

    def level_of(z):
        return (min(range(len(zs)), key=lambda i: abs(zs[i] - z)) + 1) if zs else 1
    keys, elem = [], {}
    for e in pkg.model.elements:
        row = pkg.schedule.get(e["tag"], {}); sec = row.get("section")
        if not sec:
            continue
        kind = member_kind(pkg, e)
        p1, p2 = pkg.model.nodes[e["n1"]], pkg.model.nodes[e["n2"]]
        lvl = level_of(max(p1[2], p2[2]))
        if row.get("role") == "link":
            k = ("link", sec, lvl)
        elif kind == "brace":
            k = ("brace", sec, lvl)
        elif kind in ("col", "beam"):
            k = (kind, sec, lvl)
        else:
            continue
        if k not in keys:
            keys.append(k)
        elem[e["tag"]] = keys.index(k)
    return keys, elem


def _lite_snapshot(keys, resp, eg=None):
    mem = (resp or {}).get("members") or {}
    by = {}
    for g in mem.get("member_groups") or []:
        by[(g["kind"], g["section"], g["level"])] = ("m", g)
    for g in mem.get("brace_groups") or []:
        by[("brace", g["section"], g["level"])] = ("b", g)
    for g in mem.get("link_groups") or []:
        by[("link", g["section"], g["level"])] = ("l", g)
    out = {}
    eg = eg or {}
    for gid, k in enumerate(keys):
        hit = by.get(k)
        if not hit:
            if eg.get("n_elastic") and k[0] in ("col", "beam"):        # NL-21 gravity members: elastic, no fibre group
                out[gid] = dict(state="elastic", info=[
                    ["Model", "elastic gravity member: gravity-only, pinned beam or HR gravity column"],
                    ["First-yield ratio, worst elastic member, whole push this direction", "%.2f (limit 1.0)" % (eg.get("max_ratio") or 0)],
                    ["Elastic members above first yield", ", ".join(str(t) for t in eg.get("flagged_elastic") or []) or "none"]])
            continue
        typ, g = hit
        if typ == "m":
            st = "yield" if g.get("yielded") else "elastic"
            info = [["Peak fibre strain ratio ε/εy (worst member of the group)", "%.2f" % g.get("strain_ratio_max", 0)],
                    ["Peak chord rotation (worst member)", "%.4f rad" % g.get("chord_rot_max_rad", 0)],
                    ["Members in the group", g.get("n")]]
        elif typ == "b":
            nb, n = int(g.get("n_buckled_max") or 0), int(g.get("n") or 0)
            st = "buckled" if (n and nb >= n) else ("partial" if nb else ("tension" if g.get("yielded_tension") else "elastic"))
            info = [["Braces buckled in the group", "%d of %d" % (nb, n)],
                    ["Peak tension Δ/Δy (worst brace)", "%.2f" % g.get("mu_tension_max", 0)],
                    ["Peak shortening Δ/Δy (worst brace)", "%.2f" % g.get("mu_compression_max", 0)]]
        else:
            st = "yield" if g.get("yielded") else "elastic"
            info = [["Peak link shear ductility γ/γy", "%.2f" % g.get("shear_ductility_max", 0)],
                    ["Peak link rotation γ", "%.4f rad" % g.get("gamma_max_rad", 0)],
                    ["IS 18168 12.3.3.1 link rotation (reference only)", "0.08 rad"]]
        out[gid] = dict(state=st, info=info)
    return out


def data_from_package(pkg, ppkg: dict) -> dict:
    """Lite viewer data from a saved pushover_package.json (India)."""
    heights, _ = _heights(pkg)
    keys, elem = _lite_groups(pkg)
    dirs = {}
    for d, dd in (ppkg.get("directions") or {}).items():
        u = dd.get("curve_u_mm") or [x * MM for x in dd.get("curve_u_in") or []]
        V = dd.get("curve_V_kN") or [x * KN for x in dd.get("curve_V_kip") or []]
        n = min(len(u), len(V))
        if n < 2:
            continue
        u, V = [_r(x, 2) for x in u[:n]], [_r(x, 1) for x in V[:n]]
        ci, story, groups, census, labels, targets = [0], [[0.0] * len(heights)], [{}], [{}], ["unloaded"], {}
        for lvn in TARGETS:
            rp = (dd.get("response") or {}).get(lvn); nn = (dd.get("nsp") or {}).get(lvn) or {}
            if not rp:
                continue
            ut = rp.get("roof_disp_mm")
            ut = ut if ut is not None else (rp.get("roof_disp_in") or 0) * MM
            i = min(range(n), key=lambda j: abs(u[j] - ut))
            drifts = {int(s["story"]): float(s["drift_ratio"]) for s in rp.get("story_drifts") or []}
            acc, row = 0.0, []
            for k, h in enumerate(heights):
                acc += drifts.get(k + 1, 0.0) * h; row.append(_r(acc, 2))
            snap = _lite_snapshot(keys, rp, ((ppkg.get("elastic_members") or {}).get("directions") or {}).get(d))
            cen = rp.get("census") or {}
            mg = ((rp.get("members") or {}).get("member_groups")) or []
            bg = ((rp.get("members") or {}).get("brace_groups")) or []
            lg = ((rp.get("members") or {}).get("link_groups")) or []
            ci.append(i); story.append(row); groups.append(snap); labels.append("%s target" % lvn)
            census.append(dict(braces_buckled=cen.get("braces_buckled"), brace_groups_tension=sum(1 for g in bg if g.get("yielded_tension")),
                               member_groups=len(mg), member_groups_yielded=sum(1 for g in mg if g.get("yielded")),
                               link_groups=len(lg), link_groups_yielded=sum(1 for g in lg if g.get("yielded"))))
            targets[lvn] = dict(u_mm=_r(ut, 1), Te=_r(nn.get("Te"), 4), Sa=_r(nn.get("Sa"), 4), V_over_VB=_r(rp.get("V_over_VB"), 3),
                                max_drift=_r(rp.get("max_story_drift"), 6), frame=len(ci) - 1)
        cap = dd.get("capacity") or {}
        vb = (cap.get("V_design_kip") or 0) * KN or None
        for lvn in TARGETS:
            vb = vb or ((dd.get("response") or {}).get(lvn) or {}).get("VB_design_kN")
        dirs[d] = dict(dof=0 if d.upper() == "X" else 1, T1=_r(dd.get("T1"), 4), n_steps=n, curve=dict(u=u, V=V),
                       Vmax_kN=_r(cap.get("Vmax_kN"), 1), u_at_Vmax_mm=_r((cap.get("u_at_Vmax_in") or 0) * MM, 1),
                       Vmax_over_VB=_r(cap.get("Vmax_over_VB"), 3), VB_kN=_r(vb, 1), stop=dd.get("stop_reason"),
                       targets=targets, vmax_frame=0, frames=dict(ci=ci, story=story, groups=groups, census=census, label=labels))
    labels = ["%s · %s · L%d" % (("column" if k[0] == "col" else k[0]), k[1], k[2]) for k in keys]
    return dict(mode="lite", **_common(pkg), lite_note=LITE_NOTE, elem_group={str(t): g for t, g in elem.items()},
                group_label=labels, dirs=dirs)


# ------------------------------------------------------------------ render / persist / rebuild
def annotate(outdir, data: dict) -> dict:
    """2026-10 check fixes (findings 1, 2, 4): per direction, from the stored package and the review record -- whether
    Vmax is a lower bound (printed with '≥'), the targets the curve did not reach, and the 'under review' summary.
    Stop messages in mm. Returns `data` (changed in place)."""
    try:
        pp = json.load(open(os.path.join(outdir, "pushover_package.json"), encoding="utf-8"))
    except Exception:                                              # noqa: BLE001
        pp = {}
    from .report_india import _lower_bound, stop_reason_mm
    from .review import directions_under_review
    rv = directions_under_review(os.path.dirname(os.path.abspath(outdir)))
    for d, dd in (data.get("dirs") or {}).items():
        pd = (pp.get("directions") or {}).get(d) or {}
        dd["lower_bound"] = bool(_lower_bound(pd)) if pd else False
        dd["targets_not_reached"] = [lv for lv, n in (pd.get("nsp") or {}).items() if n.get("reached_target") is False]
        dd["review"] = (rv.get(d) or {}).get("summary")
        dd["stop"] = stop_reason_mm(dd.get("stop"))
    return data


def write(outdir, pkg, data: dict) -> str:
    """Render pushover/pushover_viewer_3d.html from viewer data (full or lite) and refresh the bundle hub."""
    if not data.get("dirs"):
        raise RuntimeError("no pushover direction to show")
    annotate(outdir, data)
    model = _mm_model(pkg)
    mode = "step by step" if data["mode"] == "full" else "lite (rebuilt from the package)"
    meta = dict(title=f"{pkg.name} · Pushover (IS 1893 elastic DBE / MCE targets)", subtitle=f"{pkg.basis.system or ''}",
                accline=f"Steltic viewer bundle · India pushover · {', '.join(data['dirs'])} · {mode} · information only (D7)",
                caveat=("Deformed shape from the diaphragm masters (push direction). Braces by their axial deformation, beams / "
                        "columns by their fibre strain ratio, EBF links by their shear ductility"
                        + ("" if data["mode"] == "full" else " -- per member group at the IS-DBE / IS-MCE targets") + ". mm, kN. "
                        + IS_NL_STATEMENT + " Not for construction."))
    return VC.render(os.path.join(outdir, HTML_FILE), f"{pkg.name} · Pushover viewer", "pushover", meta, model,
                     dict(pushover_india=data), LEFT, RIGHT, MODULE_JS, amp=20, root=str(pkg.root))


def save_data(outdir, data: dict) -> str:
    p = os.path.join(outdir, DATA_FILE)
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    return p


def load_data(outdir) -> dict | None:
    p = os.path.join(outdir, DATA_FILE)
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def write_from_run(outdir, pkg, runs, results, brace_dims=None) -> str:
    """Called by the India pushover run: save the full data, then render."""
    data = data_from_run(pkg, runs, results, brace_dims)
    save_data(outdir, data)
    return write(outdir, pkg, data)


def ensure(job_dir, force=False) -> str | None:
    """(Re)build <job>/pushover/pushover_viewer_3d.html for an India job: from viewer_data.json.gz when the run saved it
    (full), else from pushover_package.json (lite). Returns the path, or None when there is no India pushover.
    Never raises: a viewer problem must not hide a report."""
    try:
        out = os.path.join(job_dir, "pushover")
        pp = os.path.join(out, "pushover_package.json")
        if not os.path.exists(pp):
            return None
        html = os.path.join(out, HTML_FILE)
        rv = os.path.join(out, "pushover_review.json")
        # 2026-10 check fixes: a viewer written before the annotations ("lower_bound") or before the review record is
        # rebuilt once from the same stored data (deterministic; a few tenths of a second)
        if os.path.exists(html) and not force and os.path.getmtime(html) >= os.path.getmtime(pp) \
                and (not os.path.exists(rv) or os.path.getmtime(html) >= os.path.getmtime(rv)) \
                and '"lower_bound"' in open(html, encoding="utf-8", errors="replace").read():
            return html
        ppkg = json.load(open(pp, encoding="utf-8"))
        if str(ppkg.get("jurisdiction") or "").lower() != "india":
            return None
        from . import package_reader as PR
        pkg = PR.load(job_dir)
        data = load_data(out) or data_from_package(pkg, ppkg)
        return write(out, pkg, data)
    except Exception as ex:                                       # noqa: BLE001
        print("[pushover viewer] India viewer not built:", ex)
        return None
