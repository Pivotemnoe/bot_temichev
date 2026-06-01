# TemichevVet Bot — Working Plan

## Workspace Rules

- Original project is not edited: `/Users/konstantin/Downloads/Temichevvet_bot LLM 2`.
- Working copy is here: `/Users/konstantin/Documents/темичев вет бот`.
- Git baseline commit: `5e20381 Baseline working copy`.
- Runtime/local files are ignored by git: `.env`, `.venv/`, `bot.db`, `errors.log`, `__pycache__/`.
- Before each implementation block: inspect status, make a small scoped change, run checks, then commit.

## New Materials Reviewed

### Relevant implementation specs

- `TemichevVet_PATCHLIST_PF_Plus_Clinic_PromptSelector_Suite.md`
  - Supersedes/combines Plus prompt mode and Clinic prompt mode.
  - Defines prompt selector priority: `clinic > plus > base`.
  - Requires `app/prompts/`, prompt addons, `prompt_mode` logging.

- `TemichevVet_PATCHLIST_P_v1_1_PlusMode_ProjectAligned.md`
  - Project-aligned replacement for older P v1.0.
  - Use `user_events`, `triage_logs`, `prompt_mode`, Plus follow-up variant.

- `TemichevVet_Plus_Expert_Prompt_FINAL.md`
  - Older/final Plus addon text. Mostly duplicated by P v1.1 and PF.
  - Keep as source text reference only.

- `TemichevVet_PATCHLIST_F_Prompts_ClinicMode.md`
  - Clinic addon texts and clinic-mode safety rules.
  - Mostly duplicated by PF; PF should be used as the master.

- `TemichevVet_PATCHLIST_E_SUITE_v1_1.md`
  - Supersedes older E/E2/E2.1.
  - Important change: use existing `user_events` instead of adding `analytics_events`.

- `TemichevVet_MASTER_PATCH_E_E2_E21_AdminDashboard.md`
  - Older master analytics spec.
  - Useful background, but E SUITE v1.1 takes precedence where they conflict.

- `TemichevVet_PATCHLIST_E2_Telegram_Admin_Dashboard.md`
  - Admin dashboard details. Covered by E SUITE v1.1, useful for report copy/layout.

- `TemichevVet_MD1_Autofollowup_Hook.md`
  - Relevant but assumes follow-up tables/services already exist.
  - In this working copy they do not exist, so implement base D/D2 first, then MD1 hook.

### Relevant reference archive

- `temichevvet_С рабочий.zip`
  - Relevant reference, not to be applied wholesale.
  - Contains later/different versions of onboarding, static banners, paywall service, YooKassa payment client, access middleware, report script, and updated handlers.
  - Use for selective backport after reviewing diffs.

### Product/clinic PDFs

- `TemichevVet_Clinic_Full_Package.pdf` and `(1).pdf`
  - Duplicate/near-duplicate clinic offer package.
  - Relevant for B2B wording and clinic product model, not direct code.

- `TemichevVet_Clinic_Pilot_30_Days.pdf`
  - Relevant for future clinic pilot onboarding/copy.
  - Not needed for immediate code stabilization.

- `TemichevVet_Clinic_Offer_RU_Emotional.pdf`
  - Relevant marketing/copy source for clinic mode.
  - Not direct implementation spec.

## Current State Summary

Implemented in current working copy:

- Telegram bot wiring with aiogram.
- User registration.
- Pets and Pets v2.
- LLM triage with one base `SYSTEM_PROMPT`.
- Subscriptions/quotas.
- Knowledge base with `for_plans`.
- Reminders.
- Pet history and observations.
- Basic `user_events` and subscription offer logs.

Not implemented or incomplete:

- A/A2 onboarding and banners.
- B2 triage history UX in pet overview and post-triage card button.
- Unified C paywall/trust layer.
- D/D2 follow-up tables/service/runner/handlers.
- E SUITE standardized analytics events and admin dashboard.
- P/PF prompt selector and Plus/Clinic addons.
- Payment flow is absent in current working copy.

## High-Priority Bugs/Risks Found

1. Fixed in Phase 1: `app/pets_v2/create.py` normalized v2 pet creation to supported pet values.
2. Fixed in Phase 1: `app/handlers/triage.py` now parses prompt-required red `🟥` and legacy `🔴`.
3. Fixed in Phase 1: `triage_logs.urgency_level` is populated as `green/yellow/red` when parsed.
4. Fixed in Phase 1 for new records: triage writes now pass `triage_log_id` into `pet_history`.
5. Fixed in Phase 1: paywall inline callbacks `open:subscription` / `open:main_menu` have handlers.
6. Fixed in Phase 1: `app/db.py` fresh-schema SQL for reminders now references `pet_id`.
7. Fixed in Phase 1: `app/handlers/observations.py` helper call now passes named `user_id` and `pet`.

## Progress Log

### 2026-06-01 — Phase 1 Stabilization

- Changed only the working copy in `/Users/konstantin/Documents/темичев вет бот`.
- Added `tools/check_phase1.py` for non-network checks.
- Verification passed:
  - `.venv/bin/python tools/check_phase1.py`
  - `.venv/bin/python -m compileall -q app tools main.py`
- Payment/VPS code was not touched.

### 2026-06-01 — Phase 2 UX Backport

- Selectively backported product UX from `temichevvet_С рабочий.zip`.
- Added static banners from the reference archive:
  - `onb_step1_add_pet.jpg`
  - `onb_step2_set_main.jpg`
  - `onb_step3_triage.jpg`
  - `subscription_banner.jpg`
  - `pets_banner.jpg`
  - `triage_banner.jpg`
- Added safe onboarding without wholesale copying the reference handlers.
- Added `is_main` support for pets, with idempotent DB column migration in `init_db()`.
- Added main-pet actions to the pet card.
- Added subscription, pets, and triage banners.
- Added unified Plus paywall helper, but did not wire payments.
- Added `tools/check_phase2.py`.
- Verification passed:
  - `.venv/bin/python tools/check_phase1.py`
  - `.venv/bin/python tools/check_phase2.py`
  - `.venv/bin/python -m compileall -q app tools main.py`
  - `.venv/bin/python -c "import main; print('main import ok')"`
- Payment/VPS code was not touched.

### 2026-06-01 — Phase 3 B2/C UX and Trust

- Added the last 3 triage summaries to the pet card overview.
- Changed Free full-history access limit to 3 records.
- Added post-triage inline actions:
  - open the selected pet card
  - start another triage
  - return to menu
- Ensured triage responses include the standard trust phrase when the LLM omits it.
- Normalized short triage summaries to one compact line.
- Reused unified Plus paywall for full-history gating and exhausted triage quota.
- Added `tools/check_phase3.py`.
- Verification passed:
  - `.venv/bin/python tools/check_phase1.py`
  - `.venv/bin/python tools/check_phase2.py`
  - `.venv/bin/python tools/check_phase3.py`
  - `.venv/bin/python -m compileall -q app tools main.py`
  - `.venv/bin/python -c "import main; print('main import ok')"`
- Payment/VPS code was not touched.

### 2026-06-01 — Phase 4 Follow-up D/D2/MD1

- Added `triage_followups` table with idempotency via unique `triage_event_id`.
- Added follow-up DB helpers: create, due query, sent status, answered status.
- Added rule-based D2 scenarios:
  - postop
  - GI
  - trauma
  - basic
- Added follow-up worker with tick/due/send/sent logs.
- Added follow-up callback handler for better/same/worse/retry answers.
- Added automatic MD1 hook after triage for `yellow`/`red`.
- Added 24-hour anti-spam for follow-up creation.
- Added `tools/check_phase4.py`.
- Verification passed:
  - `.venv/bin/python tools/check_phase1.py`
  - `.venv/bin/python tools/check_phase2.py`
  - `.venv/bin/python tools/check_phase3.py`
  - `.venv/bin/python tools/check_phase4.py`
  - `.venv/bin/python -m compileall -q app tools main.py`
  - `.venv/bin/python -c "import main; print('main import ok')"`
- Payment/VPS code was not touched.

## Work Plan

### Phase 0 — Safety and Baseline

- Keep original project untouched.
- Commit baseline and this work plan.
- Use small commits per phase.
- Do not commit secrets, DB, logs, virtualenv, caches.

### Phase 1 — Stabilize Existing Product

1. Done: fix Pets v2 creation type validation.
2. Done: fix urgency extraction for `🟥` and normalize urgency to `green/yellow/red`.
3. Done: store `urgency_level` in `triage_logs`.
4. Done: make triage history writes capture `triage_log_id` for new records.
5. Done: add missing callback handlers for `open:subscription` and `open:main_menu`.
6. Done: fix `observations.py` helper call.
7. Done: fix fresh DB schema typo. No existing-data migration needed for this specific typo.
8. Done: add a small non-network verification script for fresh schema and pure triage logic.

### Phase 2 — Backport Safe Product UX from Reference Zip

1. Done: review and selectively port static banners.
2. Done: port onboarding texts/handlers after adapting to current handlers.
3. Done: port unified paywall service after ensuring callback handlers work.
4. Done: avoid wholesale copying zip files because its schema and handlers diverge.
5. Done: add `is_main` support needed by onboarding, with safe migration.

### Phase 3 — B2 and C Completion

1. Done: add last 3 triage entries into pet overview.
2. Done: add "full history" gating according to final product rules.
3. Done: add post-triage buttons: open pet card and start another triage.
4. Done: standardize paywall copy and trust wording.
5. Done: ensure free/plus/pro history limits match the chosen B2 rule.

### Phase 4 — Follow-up D/D2 + MD1

1. Done: add `triage_followups` schema and DB helpers.
2. Done: add `app/services/followup.py` with scenario detection: basic/postop/GI/trauma.
3. Done: add `app/services/followup_runner.py`.
4. Done: add `app/handlers/followup.py`.
5. Done: add MD1 hook after `triage_completed` for yellow/red only.
6. Done: add anti-spam/idempotency.
7. Done: verify by using a test DB. Telegram delivery smoke can be done later when needed.

### Phase 5 — E SUITE Analytics and Admin Dashboard

1. Standardize `user_events` payloads; do not add `analytics_events`.
2. Add `app_start`, `pet_created`, `triage_started`, `triage_completed`, `paywall_shown`, `pay_clicked`, `payment_success`, `followup_*`.
3. Add indexes for `user_events` and `triage_logs`.
4. Add DB aggregation functions.
5. Add `/admin` dashboard gated by `ADMIN_IDS`.
6. Add reports: today, 7 days, 30 days, funnel, subscriptions, retention, cost proxy, sources.

### Phase 6 — Prompt Selector PF

1. Add `app/prompts/triage_plus_expert_addon.py`.
2. Add `app/prompts/triage_clinic_addons.py`.
3. Refactor LLM call to assemble `final_system_prompt`.
4. Return or expose `prompt_mode` for logging.
5. Implement priority: clinic > plus > base.
6. Keep base `SYSTEM_PROMPT` unchanged.

### Phase 7 — Clinic/B2B MVP

1. Add `clinic_id` storage only after schema plan is agreed.
2. Parse clinic deep links.
3. Use clinic PDF copy for clinic onboarding/contact surfaces.
4. Add clinic-mode prompt behavior and analytics fields.
5. Defer full CRM/clinic dashboard unless explicitly requested.

### Phase 8 — Payments

1. Decide whether YooKassa from reference zip is the target provider.
2. Add payment config safely with env-only secrets.
3. Implement pay click, payment creation/status handling, and `payment_success`.
4. Keep payment code isolated and test with mocked calls before live network.

## Files to Ignore for Immediate Implementation

- Duplicate older MD specs when superseded by PF or E SUITE v1.1.
- Clinic PDFs for direct coding; use only for wording/product decisions.
- `temichevvet_С рабочий.zip` as a deployable artifact; use only as reference.
