# India_package_stub — interface with steltic_india packages

This is a **stub**, not a runnable OpenSees job. It documents the package shape that
`steltic_nonlinear_india` expects from **steltic_india** (HR) and the India NL gates.

## Required files (same names as USA; India contents)

| Path | Producer | Notes |
|------|----------|-------|
| `cfg.py` | steltic_india | `jurisdiction='india'`, `seismic_zone`, `load_plan` (IS 875+1893 RAG), metric or kip geometry |
| `model_opensees.py` | steltic_india | IS 808 sections OK (dual-path); fibre mapping must tolerate MB/WB/… |
| `design/calc_package.json` | steltic_india | filled D/C |
| `design/member_schedule.csv` | steltic_india | |
| `report.html` | steltic_india | |
| `nl_plan.json` or `nlrha/nl_plan.json` | NL agent | LIVE RAG retrieval for IS 1893 §7.7 / 7.7.4 / 7.11.1 |
| `nlrha/site_hazard.json` | `python -m nlrha hazard … --zone III` | IS 1893 Ah spectrum — **not** USGS |

## Environment

```bash
export STELTIC_ENGINE_DIR=/path/to/steltic_india/steel_engine
# RAG → /workspace/engineering_rag_india (never USA engineering_rag)
```

## Three-analysis architecture (unchanged)

1. **Pushover** — scaffolding; hinge_params `verified:false` (ASCE 41 analogue found:false)
2. **NLRHA** — IS 1893 §7.7.4 spectrum compatibility + §7.11.1.1 drift 0.004 h; Ch.16 suite numerics scaffolding only
3. **DDM** — combinations from `cfg['load_plan']` via steltic_india `india_loads`

Then `python -m snl run <package>` for the four-analyses comparison.

## Hazard (India)

```bash
python -m nlrha hazard examples/India_package_stub --zone III --soil-type II \
  --importance 1.0 --R-factor 5.0 --t1 1.0
# → nlrha/site_hazard.json with targets.is1893_design (Ah in g)

python -m nlrha scale <real_steltic_india_package> --target is1893
```

## Units

Metric briefs: `from snl.india_units import apply_metric_geometry` at the cfg boundary.
Stages A–B: SI display via `display_scale`; N-mm HR packages convert once at `package_reader.apply_nl_unit_bridge` → analysis stays kip-in until Stage D.
