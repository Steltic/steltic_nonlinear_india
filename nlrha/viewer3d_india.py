"""viewer3d_india.py -- India NLRHA viewer (nlrha/nlrha_viewer_3d.html), NL-11.

The US viewer (nlrha/viewer3d.py) is built around ASCE 7 Chapter 16: IO / LS / CP hinge states, the 16.4 verdict and
the 2 x Table 12.12-1 mean drift limit. None of that exists on the India path (owner rulings D6 / D7). This viewer
shows the IS elastic-target suites (DBE and MCE) as time-history players on the same shared core (geometry, palette,
controls, the Steltic viewer bundle):

  * a level selector (IS 1893 elastic DBE (Z/2)·I·Sa/g / MCE Z·I·Sa/g, no R) and a record selector;
  * the deformed building every frame (diaphragm masters), braces coloured by their instantaneous axial state
    (elastic / buckled / yielded in tension), beams / columns / EBF links by their RECORD-PEAK fibre-strain ratio or
    link shear ductility (>= 1: yielded) -- fibre members have no per-frame hinge record;
  * storey drift bars: this record's peak, the suite mean, and the IS 1893 7.11.1.1 0.004 h line, which is the LINEAR
    design check under VB and is drawn for comparison only;
  * the level's response summary with the D7 sentence. There is no verdict, no IO / LS / CP, no acceptance limit.

Units: mm and kN (the model geometry is converted from the NL kip-in analysis units).
"""
from __future__ import annotations
import os

from . import viewer_core as VC

MM = 25.4
IS_NL_STATEMENT = ("IS 1893 (Part 1):2016 provides no acceptance criteria for nonlinear analysis; "
                   "results are for information.")

LEFT = """
<h2>Hazard level</h2>
<select id="lvlSel"></select>
<h2>Ground motion (scaled pair)</h2>
<select id="recSel"></select>
<h2>Time</h2>
<input type="range" id="step" min="0" max="1" value="0">
<div class="row"><span class="val" id="stepT" style="min-width:110px;text-align:left"></span><span class="val" id="stepU" style="flex:1"></span></div>
<div class="btns"><button id="play" class="acc">▶ play</button><button id="toPX">peak X</button><button id="toPY">peak Y</button><button id="toEnd">end (residual)</button></div>
<div class="row"><span>speed</span><select id="speed"><option value="0.5">0.5×</option><option value="1" selected>1× real time</option><option value="2">2×</option><option value="4">4×</option></select></div>
<h2>Timeline trace</h2>
<select id="chartMode"><option value="roof">Roof displacement (mm)</option><option value="drift">Roof drift ratio (%)</option><option value="ag">Ground acceleration (g)</option></select>
<h2>Colour by</h2>
<select id="colorMode"><option value="state">Component state</option><option value="type">Member type</option><option value="sec">Section</option></select>
<label><input type="checkbox" id="fAg"> Ground-acceleration vector (live)</label>
"""
RIGHT = """
<h2 style="margin-top:0">At this instant</h2>
<div id="stepStats"></div>
<h2>Storey drift · this record (bar) · suite mean (tick) · 0.004 h (linear check, for comparison)</h2>
<div id="driftBars"></div>
<h2>Component census</h2>
<div id="census"></div>
<h2>Level summary (information, no verdict)</h2>
<div id="suiteTable"></div>
"""
MODULE_JS = r"""
const N = DATA.nlrha_india; const LV = Object.keys(N.levels); let li = 0, ri = 0, step = 0, playing = false, colorMode = 'state', chartMode = 'roof', speed = 1;
function L(){ return N.levels[LV[li]]; } function R(){ return L().records[ri]; }
const eleByTag = {}; meshes.forEach(m => eleByTag[m.userData.tag] = m);
const SECS = [...new Set(M.elements.map(e=>e.sec))]; const SEC_PAL = [0x5b8dd9,0x2ecc71,0xe67e22,0x9b59b6,0xf1c40f,0x1abc9c,0xe74c3c,0x95a5a6,0xd35400,0x3498db,0x27ae60,0xc0392b];
const SEC_COL = {}; SECS.forEach((s,i)=>SEC_COL[s]=SEC_PAL[i%SEC_PAL.length]);
const BR = N.braces;                              // [{tag, dT, dc}] in frames.brace order
function braceState(b, v){ if (v < -b.dc) return 'buckled'; if (v > b.dT) return 'tension'; return 'elastic'; }
function frameCount(){ return R().frames.t.length; }
function statesAt(s){
  const st = {}; const rec = R();
  for (const [t, r] of Object.entries(rec.member_peak)) st[t] = r >= 1.0 ? 'yield' : 'elastic';
  for (const [t, r] of Object.entries(rec.link_peak)) st[t] = r >= 1.0 ? 'yield' : 'elastic';
  const fb = rec.frames.brace[s] || []; BR.forEach((b,j)=>{ st[b.tag] = braceState(b, fb[j]||0); });
  return st;
}
function floorsAt(s){ return [[0,0,0]].concat(R().frames.story[s]); }
function paint(s){
  const st = statesAt(s);
  for (const mesh of meshes){ const e=mesh.userData; let hex;
    if (colorMode==='type') hex = TYPE_COL[e.type]; else if (colorMode==='sec') hex = SEC_COL[e.sec]; else hex = STATE[st[e.tag]||'elastic'];
    setColor(mesh, hex); }
  return st;
}
function fmt(v,n){ return (v===null||v===undefined||Number.isNaN(v))?'—':Number(v).toFixed(n===undefined?2:n); }
function pct(v){ return (100*v).toFixed(3)+'%'; }
function update(){
  const rec = R(); const F = rec.frames; const n = F.t.length; step = Math.max(0, Math.min(n-1, step));
  document.getElementById('step').max = n-1; document.getElementById('step').value = step;
  applyDeformation(floorsAt(step)); const st = paint(step);
  const t = F.t[step]; const roof = F.story[step][F.story[step].length-1]; const ag = F.ag[step];
  document.getElementById('stepT').textContent = `t = ${t.toFixed(2)} s${t>rec.t_sig?' · free vibration':''}`;
  document.getElementById('stepU').textContent = `roof ${roof[0].toFixed(1)} / ${roof[1].toFixed(1)} mm · ag ${ag[0].toFixed(3)} / ${ag[1].toFixed(3)} g`;
  if (document.getElementById('fAg').checked){ const a = Math.hypot(ag[0], ag[1]); showDirection(a > 0.02*rec.pga ? [ag[0]/a, ag[1]/a, 0] : null, 0x3fc1a0); } else showDirection(null);
  const dX=[], dY=[]; let px=0, py=0; F.story[step].forEach((f,i)=>{ dX.push((f[0]-px)/N.heights[i]); dY.push((f[1]-py)/N.heights[i]); px=f[0]; py=f[1]; });
  document.getElementById('stepStats').innerHTML = rows([['Level', L().label], ['Record', rec.label], ['Scale factor · components', `${rec.sf.toFixed(3)} · ${rec.x_comp===1?'H1→X, H2→Y':'H2→X, H1→Y'}`],
    ['Roof displacement X / Y', `${roof[0].toFixed(1)} / ${roof[1].toFixed(1)} mm`], ['Roof rotation (torsion)', `${(roof[2]*1e3).toFixed(3)} mrad`],
    ['Storey drift now, max X / Y', `${pct(Math.max(...dX.map(Math.abs)))} / ${pct(Math.max(...dY.map(Math.abs)))}`],
    ['Record peak drift X / Y (edges)', `${pct(Math.max(...rec.peak_drift.map(d=>d[0])))} / ${pct(Math.max(...rec.peak_drift.map(d=>d[1])))}`],
    ['Residual drift (end)', pct(Math.max(...rec.residual))], ['Converged', rec.converged ? 'yes' : '<span class="badge ng">no</span> '+(rec.reason||'')]]);
  const lin = N.linear_drift_ratio; const scale = Math.max(0.0005, ...rec.peak_drift.flat(), ...L().story.map(s=>Math.max(s.mean_X||0, s.mean_Y||0)), lin)*1.25;
  const bar = (v, pk, mean, col) => `<span style="flex:1;margin:0 6px;height:8px;background:#1d222b;border-radius:3px;position:relative;top:4px">
      <span style="position:absolute;left:0;top:0;height:8px;width:${(100*Math.min(pk,scale)/scale).toFixed(1)}%;background:${col};opacity:.35;border-radius:3px"></span>
      <span style="position:absolute;left:0;top:0;height:8px;width:${(100*Math.min(Math.abs(v),scale)/scale).toFixed(1)}%;background:${col};border-radius:3px"></span>
      <span style="position:absolute;left:${(100*Math.min(mean||0,scale)/scale).toFixed(1)}%;top:-2px;height:12px;width:2px;background:#dde3ea"></span>
      <span style="position:absolute;left:${(100*lin/scale).toFixed(1)}%;top:-2px;height:12px;width:1px;background:#8b95a3"></span></span>`;
  document.getElementById('driftBars').innerHTML = dX.map((d,i)=>{ const S = L().story[i]||{}; return `<div class="stat"><span style="min-width:54px">storey ${i+1}</span><span style="color:#3fc1a0;min-width:10px">X</span>${bar(d, rec.peak_drift[i][0], S.mean_X, '#3fc1a0')}<b style="min-width:52px;text-align:right">${pct(rec.peak_drift[i][0])}</b></div>
      <div class="stat" style="margin-top:-2px"><span style="min-width:54px"></span><span style="color:#5b8dd9;min-width:10px">Y</span>${bar(dY[i], rec.peak_drift[i][1], S.mean_Y, '#5b8dd9')}<b style="min-width:52px;text-align:right">${pct(rec.peak_drift[i][1])}</b></div>`; }).join('')
    + `<div style="font-size:10.5px;color:#8b95a3;margin-top:4px">solid = now (masters) · faded = record peak (edges) · white tick = suite mean · grey line = ${pct(lin)} (IS 1893 7.11.1.1 is the LINEAR design check under VB, shown for comparison only -- not an NL criterion)</div>`;
  const vals = Object.values(st);
  document.getElementById('census').innerHTML = rows([['Braces buckled now', BR.filter(b=>st[b.tag]==='buckled').length], ['Braces yielded in tension now', BR.filter(b=>st[b.tag]==='tension').length],
    ['Beams / columns yielded · record peak (ε/εy ≥ 1)', Object.values(rec.member_peak).filter(r=>r>=1).length + ' of ' + Object.keys(rec.member_peak).length],
    ['EBF links yielded · record peak (γ/γy ≥ 1)', Object.keys(rec.link_peak).length ? Object.values(rec.link_peak).filter(r=>r>=1).length + ' of ' + Object.keys(rec.link_peak).length : '—']]);
  redrawChart();
}
function redrawChart(){
  const rec = R(); const F = rec.frames; const tmax = F.t[F.t.length-1];
  let s1, s2, ylabel, yfmt, title;
  if (chartMode==='ag'){ s1 = F.t.map((t,i)=>[t, F.ag[i][0]]); s2 = F.t.map((t,i)=>[t, F.ag[i][1]]); ylabel='g'; yfmt=v=>v.toFixed(2); title=`Scaled ground acceleration — ${rec.label} · SF ${rec.sf.toFixed(2)}`; }
  else if (chartMode==='drift'){ s1 = F.t.map((t,i)=>{ const r=F.story[i][F.story[i].length-1]; return [t, 100*r[0]/N.H]; }); s2 = F.t.map((t,i)=>{ const r=F.story[i][F.story[i].length-1]; return [t, 100*r[1]/N.H]; }); ylabel='% H'; yfmt=v=>v.toFixed(3); title=`Roof drift ratio — ${rec.label}`; }
  else { s1 = F.t.map((t,i)=>{ const r=F.story[i][F.story[i].length-1]; return [t, r[0]]; }); s2 = F.t.map((t,i)=>{ const r=F.story[i][F.story[i].length-1]; return [t, r[1]]; }); ylabel='mm'; yfmt=v=>v.toFixed(0); title=`Roof displacement — ${rec.label} · ${L().label}`; }
  const ymax = Math.max(1e-6, ...s1.map(p=>Math.abs(p[1])), ...s2.map(p=>Math.abs(p[1])))*1.15;
  const cur = chartMode==='ag' ? F.ag[step][0] : (chartMode==='drift' ? 100*F.story[step][F.story[step].length-1][0]/N.H : F.story[step][F.story[step].length-1][0]);
  drawChart({xmin:0, xmax:tmax, ymin:-ymax, ymax:ymax, series:[{pts:s1, color:'#3fc1a0', width:1.5}, {pts:s2, color:'#5b8dd9', width:1.5}],
    bands:[{x0:rec.t_start, x1:rec.t_sig, color:'rgba(63,193,160,0.07)', label:'significant duration (Arias 0.1–99.5%)'}, {x0:rec.t_sig, x1:tmax, color:'rgba(255,255,255,0.03)', label:'free vibration'}],
    hlines:[{y:0, color:'#3a4656', label:''}], cursor:[F.t[step], cur], cursorColor:'#3fc1a0', title, xlabel:'t (s)   —  X green · Y blue', ylabel, yfmt, xfmt:v=>v.toFixed(0)});
}
function onChartSeek(x){ const T=R().frames.t; let best=0,bd=1e9; T.forEach((t,i)=>{const d=Math.abs(t-x); if(d<bd){bd=d;best=i;}}); step=best; update(); }
function onDeformed(){} function onVisibility(){ paint(step); }
function onSpace(){ playing=!playing; document.getElementById('play').textContent = playing?'❚❚ pause':'▶ play'; }
let acc=0; function onTick(dt){ if(!playing) return; acc+=dt*speed; const fdt = R().frames.dt; while(acc>=fdt){ acc-=fdt; step++; if(step>=frameCount()){ step=0; } } update(); }
function memberInfo(e){
  const rec = R(); const lines = [['Length', `${e.L?e.L.toFixed(0):'—'} mm`], ['Level', e._lvl], ['Section', e.sec]];
  if (e.tag in rec.member_peak) lines.push(['Peak fibre strain ratio ε/εy (this record)', fmt(rec.member_peak[e.tag])], ['Peak chord rotation (this record)', `${fmt(rec.member_rot[e.tag], 4)} rad`], ['IS 800 §12 joint rotation (reference only)', N.reference_rot ? `${N.reference_rot} rad` : '—']);
  if (e.tag in rec.link_peak) lines.push(['Peak link shear ductility γ/γy', fmt(rec.link_peak[e.tag])], ['Peak link rotation γ', `${fmt(rec.link_gamma[e.tag], 4)} rad`], ['IS 18168 12.3.3.1 link rotation (reference only)', '0.08 rad']);
  const bi = BR.findIndex(b=>b.tag===e.tag); if (bi >= 0){ const b = BR[bi]; const v = (rec.frames.brace[step]||[])[bi]||0;
    lines.push(['Axial deformation now (+tension)', `${fmt(v, 2)} mm`], ['Δc (buckling) / Δy (tension yield)', `${fmt(b.dc, 2)} / ${fmt(b.dT, 2)} mm`], ['State now', STATE_LABEL[braceState(b, v)]]); }
  return rows(lines);
}
function suite(){
  const S = L().summary; const r = [];
  r.push(['Statement', `<i>${N.statement}</i>`], ['Target', L().label], ['Records · converged', `${S.n_records} · ${S.n_converged}`],
    ['Max mean / peak storey drift', `${pct(S.max_mean_drift||0)} / ${pct(S.max_peak_drift||0)}`],
    ['Mean base shear X / Y', `${fmt(S.base_shear.mean_X_kN,0)} / ${fmt(S.base_shear.mean_Y_kN,0)} kN`],
    ['V-bar_B X / Y (HR design)', `${fmt(S.base_shear.VB_design_X_kN,0)} / ${fmt(S.base_shear.VB_design_Y_kN,0)} kN`],
    ['Elastic Sa(T1)·W at this level', `${fmt(S.base_shear.elastic_kN,0)} kN (Sa ${fmt(S.base_shear.Sa_T1_g,3)} g)`],
    ['Viscous damping (model)', `${fmt(100*N.xi,1)}% (IS 1893 7.2.4: 5% for Ah -- reference)`], ['T1 X / Y (fibre model)', `${fmt(N.T1x,3)} / ${fmt(N.T1y,3)} s`]);
  document.getElementById('suiteTable').innerHTML = rows(r);
}
function fillRecords(){ const sel = document.getElementById('recSel'); sel.innerHTML=''; L().records.forEach((r,i)=>{ const o=document.createElement('option'); o.value=i; o.textContent=`${i+1}. ${r.label} · SF ${r.sf.toFixed(2)} · drift ${pct(Math.max(...r.peak_drift.flat()))}${r.converged?'':' · NOT CONVERGED'}`; sel.appendChild(o); }); }
function init(){
  const ls = document.getElementById('lvlSel'); LV.forEach((k,i)=>{ const o=document.createElement('option'); o.value=i; o.textContent=N.levels[k].label; ls.appendChild(o); });
  ls.onchange = e => { li=parseInt(e.target.value); ri=0; step=0; fillRecords(); suite(); update(); };
  fillRecords();
  document.getElementById('recSel').onchange = e => { ri=parseInt(e.target.value); step=0; update(); };
  document.getElementById('step').oninput = e => { step=parseInt(e.target.value); update(); };
  const peakIdx = c => { const F=R().frames; let b=0,bv=-1; F.story.forEach((f,i)=>{ const v=Math.abs(f[f.length-1][c]); if(v>bv){bv=v;b=i;} }); return b; };
  document.getElementById('toPX').onclick = () => { step=peakIdx(0); update(); };
  document.getElementById('toPY').onclick = () => { step=peakIdx(1); update(); };
  document.getElementById('toEnd').onclick = () => { step=frameCount()-1; update(); };
  document.getElementById('play').onclick = onSpace;
  document.getElementById('speed').onchange = e => { speed=parseFloat(e.target.value); };
  document.getElementById('chartMode').onchange = e => { chartMode=e.target.value; redrawChart(); };
  document.getElementById('colorMode').onchange = e => { colorMode=e.target.value; setLegend(); paint(step); };
  document.getElementById('fAg').onchange = () => update();
  setLegend(); suite(); update();
}
function setLegend(){ if (colorMode==='state') legend([[STATE.elastic,'elastic'],[STATE.yield,'yielded (record peak: ε/εy ≥ 1, link γ/γy ≥ 1)'],[STATE.buckled,'brace buckled (now)'],[STATE.tension,'brace yielded in tension (now)']], 'Component state · braces at this instant, beams / columns / links at their record peak (fibre model: no per-frame hinge record)', N.statement);
  else if (colorMode==='type') legend([[TYPE_COL.column,'column'],[TYPE_COL.beam,'beam'],[TYPE_COL.brace,'brace']], 'Member type'); else legend(SECS.map(s=>[SEC_COL[s],s]), 'Section'); }
"""


def _r(v, n=4):
    try:
        return round(float(v), n)
    except Exception:
        return None


def _record(r):
    F = r["frames"]
    ag = F["ag"]
    pga = max((max(abs(a[0]), abs(a[1])) for a in ag), default=1.0) or 1.0
    story = [[[_r(f[0] * MM, 2), _r(f[1] * MM, 2), _r(f[2], 6)] for f in fr] for fr in F["story"]]
    brace = [[_r(v * MM, 3) for v in row] for row in F.get("brace") or []]
    mp = (r.get("member_peaks") or {})
    mpk = {str(t): _r(v[0], 3) for t, v in (mp.get("m") or {}).items()}
    mrot = {str(t): _r(v[1], 5) for t, v in (mp.get("m") or {}).items()}
    lpk = {str(t): _r(v[1], 3) for t, v in (mp.get("l") or {}).items()}
    lg = {str(t): _r(v[0], 5) for t, v in (mp.get("l") or {}).items()}
    return dict(id=r["record"], label=r["label"], sf=_r(r["sf"], 4), x_comp=r["x_comp"], converged=bool(r.get("converged")),
                reason=r.get("reason"), peak_drift=[[_r(v, 6) for v in row] for row in r["peak_story_drift"]],
                residual=[_r(v, 6) for v in r["residual_drift"]], t_start=_r(r["t_window"][0], 2), t_sig=_r(r["t_window"][1], 2),
                pga=pga, member_peak=mpk, member_rot=mrot, link_peak=lpk, link_gamma=lg,
                frames=dict(t=F["t"], dt=(F["t"][1] - F["t"][0]) if len(F["t"]) > 1 else 0.1, story=story, brace=brace, ag=ag))


def write(outdir, pkg, per_level: dict, modal: dict, numerics: dict, prm=None) -> str:
    """nlrha/nlrha_viewer_3d.html for an India job. per_level = {level: (d, summary)} as _finish_india holds them
    (d['results'] with per-record frames and member peaks, d['gm'] with the target label)."""
    model = VC.model_from_package(pkg)
    model["nodes"] = {k: [round(v * MM, 1) for v in xyz] for k, xyz in model["nodes"].items()}
    model["cm"] = {k: [round(v * MM, 1) for v in xy] for k, xy in (model.get("cm") or {}).items()}
    model["slabs"] = [[round(v * MM, 1) for v in s] for s in model.get("slabs") or []]
    model["levels"] = [round(v * MM, 1) for v in model.get("levels") or []]
    for e in model["elements"]:
        n1, n2 = model["nodes"][str(e["n"][0])], model["nodes"][str(e["n"][1])]
        e["L"] = round(sum((a - c) ** 2 for a, c in zip(n1, n2)) ** 0.5, 1)
    levels, braces, heights = {}, None, None
    for lv, (d, summ) in per_level.items():
        good = [r for r in d["results"] if r.get("converged") and "frames" in r]
        if not good:
            continue
        ref = good[0]
        if braces is None:
            tags = ref["frames"].get("brace_tags") or []
            specs = ref.get("specs") or {}
            braces = [dict(tag=int(t), dT=_r(specs[t].dT * MM, 3) if t in specs else 0.0,
                           dc=_r(specs[t].dc * MM, 3) if t in specs else 0.0) for t in tags]
            heights = [h * MM for h in ref["heights"]]
        levels[lv] = dict(label=d["gm"].get("target_label") or lv,
                          records=[_record(r) for r in d["results"] if "frames" in r],
                          story=[dict(story=s["story"], mean_X=s.get("mean_X"), mean_Y=s.get("mean_Y"), max_X=s.get("max_X"),
                                      max_Y=s.get("max_Y")) for s in summ.get("story") or []],
                          summary={k: summ.get(k) for k in ("n_records", "n_converged", "max_mean_drift", "max_peak_drift", "base_shear")})
    if not levels:
        raise RuntimeError("no converged records with viewer frames")
    from pushover import india_materials as IM
    ref_rot = IM.reference_rotation(pkg.basis.system).get("value")
    xi = ((numerics or {}).get("damping") or {}).get("xi")
    extra = dict(nlrha_india=dict(levels=levels, braces=braces or [], heights=heights, H=sum(heights or [0]),
                                  linear_drift_ratio=0.004, reference_rot=ref_rot, xi=xi, T1x=modal.get("T1x"), T1y=modal.get("T1y"),
                                  statement=IS_NL_STATEMENT))
    n = sum(len(v["records"]) for v in levels.values())
    meta = dict(title=f"{pkg.name} · NLRHA (IS 1893 elastic DBE / MCE)", subtitle=f"{pkg.basis.system or ''}",
                accline=f"Steltic viewer bundle · India NLRHA · {', '.join(levels)} · {n} records · information only (D7)",
                caveat=("Deformed shape from the diaphragm masters; braces by their instantaneous axial deformation, beams / columns / "
                        "EBF links by their record-peak fibre strain ratio or link shear ductility. mm, kN. " + IS_NL_STATEMENT
                        + " Not for construction."))
    return VC.render(os.path.join(outdir, "nlrha_viewer_3d.html"), f"{pkg.name} · NLRHA viewer", "nlrha", meta, model, extra,
                     LEFT, RIGHT, MODULE_JS, amp=20, root=str(pkg.root))
