# SIMULATION SCRIPTS FOR LEGACY TESTING ONLY

**WARNING: THESE SCRIPTS ARE NOT PART OF THE RESEARCH METHODOLOGY.**

These files generated synthetic users (`bank.s*`, `mint.s*`, `oak.s*`)
with hardcoded behavioral trajectories (seed=20260407) and injected them
directly into the analytics database for UI/pipeline development purposes.

**MUST NOT** be run against the research database during or after IRB-approved
data collection.

**MUST NOT** be referenced in any manuscript, methodology section, or results.

The data produced by these scripts has been removed from the repository
(commit 645279b) and is not part of the extended study dataset.

## Files

| File | Description |
|------|-------------|
| `simulate_round_comparison_cohort.py` | Generates fake events for bank_s, mint_s, oak_s participants across 3 rounds |
| `round_cohort.csv` | CTFd account definitions for the 3 simulated participants |

## Historical context

These scripts were used during the NCCIT 2026 prototype phase to test the
round comparison dashboard. They are kept here for reference only.

If the research database contains users matching `bank.s*`, `mint.s*`, or
`oak.s*` patterns, run `tools/research/verify_data_provenance.py` to confirm
contamination, then use `tools/setup/reset_for_data_collection.sh` to
reset the database before starting real data collection.
