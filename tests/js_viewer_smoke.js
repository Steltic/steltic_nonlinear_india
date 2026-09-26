// Node smoke test for a viewer module: stub the shared core (three.js scene, DOM) and run init() + a few updates on the
// page's own DATA. Usage: node js_viewer_smoke.js <page.html>. Exits 1 on any exception.
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const main = scripts[scripts.length - 1];
const dm = main.match(/const DATA = (\{.*\});\n/);
if (!dm) { console.error('no DATA'); process.exit(1); }
const DATA = JSON.parse(dm[1]);
const modStart = main.indexOf('const N = DATA.');
const modEnd = main.indexOf('applyVis(); if (typeof init', modStart);
const mod = main.slice(modStart, modEnd);
const els = {};
const document = { getElementById: id => (els[id] = els[id] || { value: 'state', checked: false, innerHTML: '', textContent: '', max: 0,
  appendChild(){}, set onchange(f){ this._c=f; }, set oninput(f){ this._i=f; }, set onclick(f){ this._k=f; } }), createElement: () => ({}) };
const M = DATA.model;
const meshes = M.elements.map(e => ({ userData: e, visible: true }));
const TYPE_COL = {column:1, beam:2, brace:3};
const STATE = {elastic:0, yield:1, io:2, ls:3, cp:4, beyond:5, buckled:6, tension:7};
const STATE_LABEL = {elastic:'elastic', yield:'y', io:'io', ls:'ls', cp:'cp', beyond:'b', buckled:'buckled', tension:'tension'};
let painted = 0;
function applyDeformation(f){ if (!Array.isArray(f)) throw new Error('floors'); }
function setColor(m, hex){ if (hex === undefined) throw new Error('undefined colour for ' + m.userData.tag); painted++; }
function rows(p){ return p.map(x => x.join(':')).join(';'); }
function legend(){}
function drawChart(spec){ if (!spec.series.length) throw new Error('chart'); }
function showDirection(){}
function hingeDot(){ return {}; }
function setDot(){}
function memberPos(){ return {}; }
const f = new Function('DATA','M','meshes','document','TYPE_COL','STATE','STATE_LABEL','applyDeformation','setColor','rows','legend','drawChart','showDirection','hingeDot','setDot','memberPos',
  mod + '\n;init(); step = 5; update(); if (typeof memberInfo === "function") memberInfo(M.elements[0]); return {step};');
f(DATA, M, meshes, document, TYPE_COL, STATE, STATE_LABEL, applyDeformation, setColor, rows, legend, drawChart, showDirection, hingeDot, setDot, memberPos);
if (els.lvlSel && els.lvlSel._c) { els.lvlSel._c({target:{value:'1'}}); }
console.log('OK painted', painted);
