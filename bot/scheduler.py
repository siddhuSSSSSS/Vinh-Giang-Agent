"""Proactive scheduling: hourly sweep + one-shot 24h-gate jobs.

Phase 0 scaffold stub - Phase 4 fills in: run_repeating hourly sweep with
per-timezone dedup via users.last_sweep_day, one-time job scheduling + post_init re-scan.
"""
