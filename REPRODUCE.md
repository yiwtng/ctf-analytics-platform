# Reproduction Guide

This document describes how to reproduce every number reported in the
manuscript from source code and raw data.

> **Manuscript:** T. Wutthiamornthada and N. Wisitpongphan,
> "Automated Analysis of Problem-Solving Skills with LLM-Generated
> Feedback in Capture-the-Flag Cybersecurity Education,"
> *IEEE Transactions on Learning Technologies*, 2026.

---

## 1. Environment Setup

```bash
git clone --recurse-submodules https://github.com/yiwtng/ctf-analytics-platform.git
cd ctf-analytics-platform

# Python dependencies (pinned versions)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-pinned.txt
playwright install chromium
```

---

## 2. Start the Platform

```bash
cp .env.example .env
# Fill in ANALYTICS_DB_*, CTF_DOMAIN, ORCH_DOMAIN, and AI API keys

docker compose up -d
docker compose ps   # verify all 7 services are healthy
```

---

## 3. Initialize Database

```bash
# Run migrations (auto-applied on first startup via database/init/)
# For subsequent migrations:
for f in database/migrations/*.sql; do
  docker exec -i analytics_db psql -U analytics -d analytics < "$f"
done
```

---

## 4. Regenerate All Numbers in the Paper

### Step 1 — Export anonymized dataset

```bash
python tools/research/export_anonymized_dataset.py --out data/
# Outputs: data/events_anonymized.csv, data/skill_scores.csv,
#          data/survey_responses.csv, data/expert_ratings.csv
# PRIVATE (do not commit): data/_code_map_private.csv
```

Random seed used for participant code assignment: **deterministic by enrollment timestamp** (no additional seed needed).

### Step 2 — Run statistical analysis

```bash
python tools/analysis/statistical_tests.py --out-dir analysis/results/
# Outputs: analysis/results/stats.json
#          analysis/results/stats_table.tex   (Table 3 in manuscript)
```

Experiment assignment seed: **42** (set via `EXPERIMENT_SEED=42`).

### Step 3 — Run Jupyter notebooks

```bash
pip install jupyter nbconvert
jupyter nbconvert --to notebook --execute analysis/01_descriptive_stats.ipynb
jupyter nbconvert --to notebook --execute analysis/02_reliability_validity.ipynb
jupyter nbconvert --to notebook --execute analysis/03_feedback_effect.ipynb
jupyter nbconvert --to notebook --execute analysis/04_skill_measurement.ipynb
```

---

## 5. Generate AI Reports (requires live API key)

```bash
export ORCH_BASE=http://orch.yourdomain.com
python tools/analysis/generate_all_ai_reports.py
```

---

## 6. Verified Environment

| Component | Version |
|---|---|
| Python | 3.12 |
| Docker Compose | v2.24+ |
| PostgreSQL | 16 |
| OS | Ubuntu 24.04 LTS |

---

## 7. Pinned Dependencies

See `requirements-pinned.txt` for the exact package versions used
during the study analysis phase.

---

## 8. Contact

For questions about reproduction, open a GitHub Issue or contact
thanagrit.yiw@gmail.com.
