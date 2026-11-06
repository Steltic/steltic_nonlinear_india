Stand-ins for the analysis packages (`snl`, `pushover`, `nlrha`, `steltic_ddm`), used only by
`tests/test_run_stage2.py`. The runner's child processes import them first (`STAGE2_PYTHONPATH`). They act like the
real commands where the runner depends on it: the arguments, a journal / record cache that a later run reuses, the
output files, the NL-21 yield flags. There is no OpenSees here.
