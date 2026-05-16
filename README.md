# CTF Analytics Platform

> **Automated System for Analyzing Players' Problem-Solving Skills and Providing Personalized Feedback for CTF Competitions**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](docker-compose.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](platform/orchestrator/requirements.txt)
[![CTFd](https://img.shields.io/badge/Built%20on-CTFd-red)](https://ctfd.io)

This repository contains the full implementation of a research prototype presented in:

> **T. Wutthiamornthada**, "Automated System for Analyzing Players' Problem-Solving Skills and Providing Feedback for CTF Competitions," *Independent Study, King Mongkut's University of Technology North Bangkok*, 2025.

---

## Overview

Traditional CTF platforms evaluate players solely by score or number of solved challenges — missing the richer behavioral signal embedded in *how* players solve problems. This system extends [CTFd](https://ctfd.io) with:

- **Event-level telemetry** — captures every meaningful interaction (web requests, TCP handshakes, SSH commands, flag submissions, hint usage)
- **Rule-based skill analysis** — derives 7 skill dimensions from event logs
- **AI-powered personalized reports** — uses Gemini / OpenAI to generate natural-language feedback in Thai
- **Longitudinal cohort tracking** — compares player development across multiple rounds

### Key Results (from real deployment)

| Metric | Value |
|---|---|
| Real users tracked | 32 accounts |
| Total events captured | 2,434 |
| Skill reports generated | 538 |
| AI reports generated | 172 (31/32 via Gemini 2.5) |
| Survey responses | 39 |
| Avg. solves (cohort round 1 → 3) | 4.33 → **7.00** |
| Avg. accuracy (cohort round 1 → 3) | 65.33% → **85.67%** |

---

## System Architecture

```
Players / Browser
       │
  [Traefik]  ─── reverse proxy (HTTP/HTTPS/TCP/SSH)
   /       \
[CTFd]   [Orchestrator]  ←── FastAPI analytics backend
(game UI)      │
          [Analytics DB]  ─── PostgreSQL (events, skill reports, AI reports)
               │
          [AI Backend]  ─── Gemini 2.5 / OpenAI / rule-based fallback
               │
          [Grafana]  ─── monitoring dashboards

[CTFd DB]  PostgreSQL    [Redis]  cache
```

### Data Flow

```
Player action
  → event logged (CTFd plugin / challenge container)
  → stored in analytics_db.events
  → Rule-Based Analysis → 7 skill scores
  → AI pipeline (Gemini → OpenAI → rule-based fallback)
  → personalized report (strengths, weaknesses, recommendations)
  → displayed on /report page + /admin-reports dashboard
```

---

## Challenge Set

### Red Team (Interactive — Docker-based)

| Challenge | Type | Skill Measured |
|---|---|---|
| Red - Ghost Login | Web / HTTP | Web Recon |
| Red - Protocol Probe | TCP / nc | Protocol Analysis |
| Red - Pivot Notes | SSH | SSH Pivot |
| Red - Log Poisoning | Web / HTTP | Web Recon + Accuracy |

### Blue Team (Analysis-based — Static)

| Challenge | Difficulty | Skill Measured |
|---|---|---|
| Blue - Misleading Intel | Easy | Blue Analysis |
| Blue - Slow Think Fast Guess | Easy | Blue Analysis + Time Efficiency |
| Blue - Beacon Pattern | Easy | Blue Analysis + Time Efficiency |
| Blue - Hint Dependency | Medium | Blue Analysis + Persistence |
| Blue - Suspicious Archive | Medium | Blue Analysis + Persistence |
| Blue - Multi-stage Flag | Medium | Blue Analysis + Accuracy |
| Blue - Lateral Movement Clue | Hard | Blue Analysis + Persistence |
| Blue - Persistence Finder | Hard | Blue Analysis + Accuracy |

---

## Skill Dimensions

Seven skill scores (0–100) derived from event logs:

| Dimension | Formula |
|---|---|
| Accuracy | `C / (C + W) × 100` |
| Persistence | `max(0, 40 + 5S − 10G − 3E)` |
| Web Recon | `max(0, 50 + 2Q − 8F + 15W_web)` |
| Protocol | `max(0, 50 + 10H + 20P − 6M − 5A)` |
| SSH Pivot | `max(0, 50 + 3K + 20L − 8E_ssh)` |
| Blue Analysis | `max(0, 50 + 4U + min(O,10) + 12B − 4X − 3Y)` |
| Time Efficiency | `max(0, 70 − 10R − 3W − 3E)` |

Overall level: **Developing** (<60) / **Intermediate** (60–79) / **Advanced** (≥80)

---

## Repository Structure

```
ctf-analytics-platform/
├── docker-compose.yml          # Full stack deployment
├── .env.example                # Environment variable template
├── LICENSE                     # MIT License
├── CITATION.cff                # Machine-readable citation
│
├── platform/                   # Core platform services
│   ├── ctfd/                   # CTFd customization
│   │   ├── Dockerfile
│   │   └── plugins/
│   │       └── admin_reports/  # Custom admin UI (reports, cohort comparison)
│   ├── orchestrator/           # FastAPI analytics backend
│   │   └── app/
│   │       ├── main.py         # API endpoints
│   │       ├── session_manager.py  # Docker session lifecycle
│   │       ├── report_service.py   # Skill analysis + AI pipeline
│   │       └── events.py      # Event storage
│   ├── traefik/                # Reverse proxy config
│   └── monitoring/             # Grafana dashboards
│
├── challenges/                 # CTF challenge set
│   ├── red/                    # Interactive Docker challenges
│   └── blue/                   # Analysis-based (static) challenges
│
├── database/                   # PostgreSQL schemas & migrations
│   ├── init/                   # Auto-run on first startup
│   └── migrations/
│
├── tools/                      # Research & operational scripts
│   ├── setup/                  # create_all_challenges.py, create_users.py
│   ├── research/               # simulate_round_comparison_cohort.py
│   └── analysis/               # generate_all_ai_reports.py, analyze_red_behavior.py
│
├── scripts/                    # Shell scripts (start, stop, setup)
├── apt42_ctfd_themes/          # CTFd themes (git submodule)
└── docs/                       # Documentation & figures
    ├── deployment.md
    └── figures/
```

---

## Getting Started

See [docs/deployment.md](docs/deployment.md) for full setup instructions.

**Quick start:**

```bash
git clone --recurse-submodules https://github.com/thanagrit-wutthiamornthada/ctf-analytics-platform.git
cd ctf-analytics-platform
cp .env.example .env   # fill in your credentials
docker compose up -d
```

---

## Admin Interfaces

| URL | Description |
|---|---|
| `/admin-reports` | View & generate skill + AI reports for all players |
| `/admin-feedback` | View participant survey responses |
| `/admin-round-comparison` | Compare player development across rounds |
| `/report?user=<key>` | Individual player report (player-facing) |
| `/survey` | Post-competition feedback form |

---

## Citation

If you use this system or dataset in your research, please cite:

```bibtex
@article{wutthiamornthada2025ctf,
  title     = {Automated System for Analyzing Players' Problem-Solving Skills
               and Providing Feedback for {CTF} Competitions},
  author    = {Wutthiamornthada, Thanagrit},
  journal   = {IEEE Access},
  year      = {2025},
  note      = {Under review}
}
```

---

## License

This project is licensed under the [MIT License](LICENSE).
