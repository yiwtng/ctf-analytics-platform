# Dataset Description

This dataset accompanies the manuscript:

> T. Wutthiamornthada and N. Wisitpongphan, "Automated Analysis of
> Problem-Solving Skills with LLM-Generated Feedback in
> Capture-the-Flag Cybersecurity Education,"
> *IEEE Transactions on Learning Technologies*, 2026. (Under review)

## Anonymization

All participant identifiers have been replaced with stable codes
(P001, P002, …) sorted by enrollment order. The mapping is stored
in a private file (`_code_map_private.csv`) that is excluded from
version control via `.gitignore`.

Timestamps are expressed as `ts_offset_seconds` — the number of
seconds elapsed since each participant's first recorded event in
that round — to prevent re-identification through wall-clock time.

Free-text survey responses have been scrubbed using regex patterns
targeting emails, phone numbers, national IDs, and name prefixes.

## Ethics

This study received IRB approval from the KMUTNB Human Research Ethics
Committee and complies with Thailand's PDPA (B.E. 2562).
See `docs/ethics/` for consent and compliance documents.

## Files

### events_anonymized.csv

| Column | Type | Description |
|---|---|---|
| participant_code | string | Anonymized participant ID (P001 …) |
| ts_offset_seconds | integer | Seconds since participant's first event |
| action_type | string | CTF event type (e.g., FLAG_SUBMIT_RESULT) |
| challenge_id | string | Challenge identifier |
| success | integer | 1 if action succeeded, 0 otherwise |

### skill_scores.csv

| Column | Type | Description |
|---|---|---|
| participant_code | string | Anonymized participant ID |
| accuracy | float | Accuracy score (0–100) |
| persistence | float | Persistence score (0–100) |
| web_recon | float | Web Recon score (0–100) |
| protocol | float | Protocol score (0–100) |
| ssh_pivot | float | SSH Pivot score (0–100) |
| blue_analysis | float | Blue Analysis score (0–100) |
| time_efficiency | float | Time Efficiency score (0–100) |
| overall_level | string | Developing / Intermediate / Advanced |
| condition | string | control or treatment |

### survey_responses.csv

| Column | Type | Description |
|---|---|---|
| participant_code | string | Anonymized participant ID |
| usability | integer | Usability rating (1–5 Likert) |
| challenge_quality | integer | Challenge quality rating (1–5) |
| recommendation_quality | integer | Feedback quality rating (1–5) |
| confidence_improvement | integer | Self-efficacy improvement (1–5) |
| favorite_part_redacted | string | Open-ended response (PII scrubbed) |
| improvement_point_redacted | string | Open-ended response (PII scrubbed) |
| comments_redacted | string | Open-ended response (PII scrubbed) |

### expert_ratings.csv

| Column | Type | Description |
|---|---|---|
| rater_id | string | Blinded expert ID (E01, E02 …) |
| participant_code | string | Anonymized participant ID |
| round_no | integer | CTF round (1, 2, or 3) |
| dimension | string | Skill dimension rated |
| score | float | Expert judgment score (0–100) |
