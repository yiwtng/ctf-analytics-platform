# Participant codes and the linking register

Every record about a participant — questionnaire responses, expert ratings,
behavioural telemetry — is keyed by a **participant code**. Nothing that
identifies a person is stored in either database.

---

## The code

Format `P###`, zero-padded to three digits: `P001` … `P070`.

- **Assigned at consent**, in the order people consent, before anything else
  happens. The self-efficacy scale is administered before the participant
  touches the platform, so a code must exist at that moment.
- **Never reused and never reassigned**, including after withdrawal. A withdrawn
  participant keeps their code so that the enrolled-versus-completed counts stay
  reconcilable.
- **Carries no meaning.** It does not encode condition, group, cohort, or
  enrolment date. Anything a code encodes is something an expert rater or a
  reader of the released dataset can infer.

The code is entered into `participant_enrollment` together with the CTFd user
id. That table is the single authority linking a code to platform activity.

> ### Why this matters more than it looks
> `export_anonymized_dataset.py` used to *generate* codes at export time,
> ordered by each participant's first event. Questionnaires would then carry the
> code written on the paper form, while the exported behavioural data carried a
> different one — so survey responses would join to a different participant's
> data. Every row present, every value in range, means entirely ordinary, and
> the pairing wrong. The export now reads `participant_enrollment` and refuses
> to run if it is empty or if any user has events without an enrolment record.

---

## The linking register

One file maps codes to real people. It is the only place that link exists.

**It must never be in this repository, in either database, or in any cloud
folder that syncs automatically.** Keep it on an encrypted volume or in a locked
drawer, per the approved protocol.

Template: `participant_register_template.csv`

| Column | Purpose |
| --- | --- |
| `participant_code` | `P001` … |
| `full_name` | as given on the consent form |
| `contact` | email or phone, for scheduling and withdrawal requests |
| `consent_date` | date the signed consent form was collected |
| `ctfd_username` | the account created for them |
| `ctfd_user_id` | numeric id — this is what goes into `participant_enrollment` |
| `form_pre` | form number of the CSE sheet issued before Round 1 |
| `form_post` | form number issued after Round 3 |
| `withdrawn_date` | blank unless they withdraw |
| `notes` | anything relevant to their participation |

`form_pre` and `form_post` are recorded because the printed CSE forms each carry
their own item order. If a sheet is later found with an unreadable participant
code, the form number narrows down who it belongs to; without it the responses
are unattributable and the case is lost.

---

## Order of operations at enrolment

1. Participant reads the information sheet and signs consent.
2. Assign the next unused code. Write it in the register.
3. Write the code on their CSE **pre** form. Note the form number in the register.
4. They complete the CSE form — **before** they are given platform access.
5. Create their CTFd account. Record the username and numeric user id.
6. Enter them into `participant_enrollment` (code + CTFd user id + IRB study id).
   This is also what assigns their condition.
7. Give them platform access.

Step 4 sits before step 5 deliberately. Once a participant has seen the platform,
a "confidence right now" rating is no longer a pre-exposure baseline, and the
pre-post change stops meaning what H3 claims it means.

---

## At the end of the study

The register is retained only as long as the approved protocol requires, then
destroyed. After that point the pseudonymisation is irreversible, which is the
intended end state: the released dataset carries codes that can no longer be
resolved to people by anyone, including the research team.
