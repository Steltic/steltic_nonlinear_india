# steltic-nonlinear-india — 2026-10: HR brief ids renumbered

Branch `fix/2026-10-peb-briefs`. No analysis changes.

- The HR example briefs were renumbered in steltic_india (most common building types first; five new PEB briefs
  are IN_Ex1 … IN_Ex5, the 15 existing briefs are IN_Ex6 … IN_Ex20). Map: `steltic_india/test_buildings/RENUMBERING_2026-10.md`.
- Mechanical rename (`steltic_india/scripts/renumber_2026-10.py`): every `IN_ExN` id in file and folder names (the
  test fixtures `tests/fixtures/IN_Ex13_pkg/`, `IN_Ex16_pkg/`, `IN_Ex8_gold/`) and in every text file (code comments,
  the contract, `docs/README_pushover.md`, `scripts/run_gold_batch.sh`, tests); the reviewed short forms that meant
  IN_Ex13 ("the Ex1 roof beams", "the Ex1 mass pick") in `steltic_ddm/`, the contract and the pushover README.
- Dated records keep the old numbers and now carry a note at the top: `CHANGES_2026-09-review.md`,
  `docs/NL_REVIEW.md`, `docs/NL_RUNBOOK.md`, `docs/USA_SYNC_REPORT.md`, `docs/DDM_AGENT_SCOPE.md`.
- **Vendored HR files (`snl/vendor_steltic_india/`) re-synced** with steltic_india `fix/2026-10-peb-briefs` (brief ids
  in comments only). `check_vendored`: all 9 byte-identical. `VENDORED_FROM.md` notes the re-sync; record the merged
  steltic_india commit there after that PR merges.
- `scripts/run_gold_batch.sh` now names the gold jobs by the new numbers: rename the gold pack first
  (`python3 steltic_india/scripts/renumber_2026-10.py tree <old pack> <new pack>`) before running it.
- Full suite with `STELTIC_HR_ROOT` / `STELTIC_ENGINE_DIR` on the HR branch: **379 passed, 11 skipped** in a Linux
  shell without Node.js (the same count as `main` in that shell; the owner's Windows count was 388 passed, 2 skipped).
