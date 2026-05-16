# Design Rationale: Theoretical Foundations of the CTF Analytics Platform

This document explains the learning-theory basis for each design decision
in the platform. It is intended to support peer review and to make the
> **Data collection status:** Extended study data collection begins June 2026 after KMUTNB IRB approval.
> Prototype results (NCCIT 2026, n≈32) are preliminary and cited separately from the extended study.
> See [docs/data_provenance.md](data_provenance.md) for full chain of custody.

system's pedagogical assumptions explicit and falsifiable.

---

## 1. Theoretical Foundation

### 1.1 Hattie & Timperley (2007) — The Feedback Model

The most influential meta-analysis of feedback in educational settings
(Hattie & Timperley, 2007) identifies three feedback questions that
effective systems must answer:

| Feedback Question | What it Addresses | How This Platform Answers It |
|---|---|---|
| **Feed-up** (Where am I going?) | Learning goal clarity | The 7-dimension skill profile shows the target competency structure |
| **Feed-back** (How am I going?) | Current performance gap | The skill score radar chart shows performance vs. baseline per round |
| **Feed-forward** (Where to next?) | Next steps | LLM-generated recommendations are specific, actionable, and personalized |

The platform's report structure maps directly onto this three-question
model: the skill radar (feed-up + feed-back) followed by the
"Recommendations" section (feed-forward). Unlike conventional CTFd
which answers only "how many flags did you capture," this system
operationalizes all three feedback functions.

### 1.2 Shute (2008) — Formative Feedback Principles

Shute's review of formative feedback synthesizes eight empirically
supported principles. The platform implements five directly:

| Shute Principle | Implementation |
|---|---|
| **Specific** | Feedback references concrete events (e.g., "TCP_BAD_AUTH × 16") rather than generic advice |
| **Timely** | Reports can be generated within seconds of a round ending via `POST /generate_report/{user_key}` |
| **Actionable** | Every recommendation is a concrete drill (e.g., "Practice SSH port forwarding with SCP") |
| **Non-threatening** | Reports frame all feedback as developmental language, avoiding grade-like labels |
| **Elaborated** | LLM output provides explanation and rationale, not just a score change |

### 1.3 Sadler (1989) — Closing the Gap

Sadler's foundational work on formative assessment argues that learning
improves when students can perceive the gap between current and desired
performance and have the tools to close it. The 7-dimensional scoring
operationalizes this gap structure:

- **Current performance**: skill scores derived from event telemetry
- **Desired performance**: the 7 dimensions serve as an implicit rubric anchored to CTF security competency
- **Gap closure**: personalized recommendations provide the "how to close" guidance

Without the 7-dimensional breakdown, a total CTF score obscures which
specific competency gaps need attention. A player scoring 65% overall
might excel at Web Recon (90) while having near-zero SSH Pivot (30);
these two profiles require entirely different remediation.

### 1.4 Shute & Ventura (2013) — Stealth Assessment

The platform's event-driven architecture instantiates the stealth
assessment paradigm: evidence of competence is gathered *from the
process of solving challenges* rather than from discrete tests appended
after learning. Key events (TCP handshakes, SSH commands, web endpoint
probes) serve as evidence strands that are invisible as evaluative acts
to the learner, reducing test anxiety and performance distortion.

This is particularly significant for cybersecurity education: a learner
who is "test-aware" may change problem-solving behavior during
assessments, masking their actual competency level. Stealth assessment
mitigates this threat to internal validity.

---

## 2. Why Seven Skill Dimensions?

The seven dimensions were derived from a review of CTF skill taxonomies
(Švábenský et al., 2021; Balon & Baggili, 2023) and mapped onto the
three challenge categories in this study:

| Dimension | Challenge Type | Behavioral Evidence Collected |
|---|---|---|
| **Web Recon** | Red Team (Web) | `WEB_REQUEST` events, endpoint probing patterns |
| **Protocol** | Red Team (TCP/nc) | `TCP_CONNECT`, `TCP_INPUT`, `TCP_BAD_AUTH`, `TCP_HELLO_OK` |
| **SSH Pivot** | Red Team (SSH) | `SSH_CONNECT`, `SSH_COMMAND`, multi-step file traversal |
| **Blue Analysis** | Blue Team | `CHALLENGE_OPEN_UI`, `HINT_UNLOCK_UI`, reasoning-to-flag latency |
| **Accuracy** | All | `FLAG_SUBMIT_RESULT` correct/incorrect ratio |
| **Persistence** | All | Session restart count, give-up events, error recovery |
| **Time Efficiency** | All | Elapsed time between challenge open and submission |

The dimensions are not orthogonal by design: a skilled player excels
at multiple dimensions simultaneously. However, empirical factor
structure (see `analysis/04_skill_measurement.ipynb`) is examined to
verify that they capture meaningfully distinct variance. ICC across
expert raters (see `analysis/02_reliability_validity.ipynb`) validates
that the dimensions can be reliably judged.

---

## 3. Why Event-Driven (vs. Outcome-Based) Measurement?

Conventional CTF platforms log only discrete outcomes: flag submitted
(correct/incorrect) and time of submission. This discards the
behaviorally rich process data that distinguishes:

- A player who submitted the correct flag after one thoughtful probe
- A player who submitted the same flag after 40 brute-force attempts

These two players have identical outcome data but radically different
competency profiles. The event-driven architecture captures both
*technical interaction events* (connection, command, request) and
*platform-side events* (UI open, hint use, restart) to reconstruct
a full behavioral trace.

Bimba et al. (2017) show that learning analytics systems using process
data (clickstreams, interaction logs) outperform outcome-only systems
in the precision of adaptive feedback generation. The CTF context
presents richer process data than typical e-learning environments:
each TCP handshake, each SSH command, and each web endpoint probe
carries diagnostic signal about the learner's mental model.

---

## 4. Why Large Language Models for Feedback Generation?

### 4.1 Personalization at Scale

The core pedagogical value of LLM-generated feedback is *personalization
at scale*: the system can produce narrative explanations tailored to
each participant's specific behavioral trace without requiring a human
expert for each report. Prior work on intelligent tutoring systems (ITS)
achieves personalization through rule-based template selection; LLMs
allow richer, contextually appropriate language that adapts to the
specific combination of behavioral evidence presented.

### 4.2 The Hybrid Rule-Based + LLM Architecture

A naive approach — feeding raw event logs directly to an LLM — would
be unreliable due to context length limits and irrelevant noise. This
platform uses a *hybrid approach*:

1. **Rule-based preprocessing**: Raw events → 7 skill scores + behavioral
   profiles (e.g., "excessive restarts detected"). This step filters,
   aggregates, and structures the evidence.
2. **LLM generation**: The structured summary is passed as a prompt to
   Gemini 2.5 / OpenAI GPT-4o-mini, which generates natural-language
   feedback incorporating the specific numerical evidence.

This architecture ensures that LLM output is *grounded* in verified
behavioral data from the system, preventing hallucination of non-existent
events. The prompt explicitly instructs the model to reference specific
evidence values (e.g., `TCP_BAD_AUTH: 16`) rather than making
unsupported claims.

### 4.3 Fallback Reliability

A pure LLM-dependent system is unsuitable for a research context where
consistent, comparable feedback is required. The platform implements a
three-tier fallback:

1. **Gemini 2.5** (primary) — multi-model rotation across flash/flash-lite
2. **OpenAI GPT-4o-mini** (secondary) — invoked if Gemini quota is exhausted
3. **Rule-based fallback** (tertiary) — deterministic Thai-language feedback
   from template rules, ensuring every participant always receives a report

---

## 5. Feature-to-Theory Mapping Table

| System Feature | Learning Theory | Reference |
|---|---|---|
| 7-dimension skill scores | Formative assessment gap analysis | Sadler (1989) |
| Skill radar chart | Feed-up + feed-back visualization | Hattie & Timperley (2007) |
| Actionable LLM recommendations | Elaborated, specific formative feedback | Shute (2008) |
| Event-level telemetry | Stealth assessment | Shute & Ventura (2013) |
| Multi-round longitudinal tracking | Deliberate practice, spaced retrieval | Ericsson et al. (1993) |
| Block-randomized control group | Experimental design validity | Shadish et al. (2002) |
| Expert rating of AI feedback | Feedback quality evaluation | Sadler (1989); Narciss (2008) |
| ICС reliability measurement | Psychometric validation | Koo & Mae (2016) |
| Cronbach's alpha | Internal consistency | Nunnally (1978) |

---

## 6. References

- Balon, T., & Baggili, I. (2023). Cybercompetitions: A survey of
  competitions, tools, and systems to support cybersecurity education.
  *Education and Information Technologies*, 28(9), 11759–11791.

- Bimba, A. T., Idris, N., Al-Hunaiyyan, A., Mahmud, R. B., & Shuib,
  N. L. B. M. (2017). Adaptive feedback in computer-based learning
  environments: A review. *Adaptive Behavior*, 25(5), 217–234.

- Ericsson, K. A., Krampe, R. T., & Tesch-Römer, C. (1993). The role
  of deliberate practice in the acquisition of expert performance.
  *Psychological Review*, 100(3), 363–406.

- Hattie, J., & Timperley, H. (2007). The power of feedback.
  *Review of Educational Research*, 77(1), 81–112.

- Koo, T. K., & Mae, M. Y. (2016). A guideline of selecting and
  reporting intraclass correlation coefficients for reliability
  research. *Journal of Chiropractic Medicine*, 15(2), 155–163.

- Narciss, S. (2008). Feedback strategies for interactive learning
  tasks. In J. M. Spector et al. (Eds.), *Handbook of Research on
  Educational Communications and Technology* (3rd ed., pp. 125–144).

- Nunnally, J. C. (1978). *Psychometric Theory* (2nd ed.).
  McGraw-Hill.

- Sadler, D. R. (1989). Formative assessment and the design of
  instructional systems. *Instructional Science*, 18(2), 119–144.

- Shadish, W. R., Cook, T. D., & Campbell, D. T. (2002).
  *Experimental and Quasi-Experimental Designs for Generalized
  Causal Inference*. Houghton Mifflin.

- Shute, V. J. (2008). Focus on formative feedback.
  *Review of Educational Research*, 78(1), 153–189.

- Shute, V. J., & Ventura, M. (2013). *Measuring and Supporting
  Learning in Games: Stealth Assessment*. MIT Press.

- Švábenský, V., Čeleda, P., Vykopal, J., & Brišáková, S. (2021).
  Cybersecurity knowledge and skills taught in capture the flag
  challenges. *Computers & Security*, 102, 102154.
