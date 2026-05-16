# SYNTHETIC DATA — FOR UNIT TESTING ONLY

**WARNING: THE DATA IN THIS DIRECTORY IS NOT RESEARCH DATA.**

These files contain a mix of:
- Simulation output from `tools/research/simulate_round_comparison_cohort.py`
  (participants: bank_s, mint_s, oak_s — hardcoded synthetic trajectories, seed=20260407)
- Data from system testing and platform development sessions

**MUST NOT** be used in any analysis, manuscript, figure, table, or results section.
**MUST NOT** be presented as participant data in any publication or report.
**NOT** derived from IRB-approved data collection with informed consent.
**NOT** representative of real learner behavior in any study.

## Purpose

Provided only so that Jupyter notebooks and analysis scripts can be run locally
without a live database connection during development. Every notebook cell that
loads these fixtures must display a visible warning.

## Real data

Real participant data will be collected after IRB approval from the KMUTNB Human
Research Ethics Committee (expected: June 2026). It will be stored separately
and will NOT be committed to this repository.

## Files

| File | Description |
|------|-------------|
| `synthetic_sample_events.csv` | Synthetic event log (mixed simulation + test sessions) |
| `synthetic_sample_skills.csv` | Synthetic skill score snapshots |
| `synthetic_sample_survey.csv` | Synthetic survey responses |
