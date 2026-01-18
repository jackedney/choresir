# Documentation Changes Required

**Total Tasks:** 33
**Priority:** CRITICAL (8) | HIGH (11) | MEDIUM (11) | LOW (3)
**PM Decision Status:** ALL RESOLVED

---

## CRITICAL PRIORITY (8 issues)

### C1. Fix WhatsApp Provider References in DEPLOYMENT.md
**File:** `docs/DEPLOYMENT.md`
**PM Decision:** Update ALL to Twilio - Meta is completely removed from the project
**Action:**
- Replace all Meta credential references with Twilio equivalents:
  - `WHATSAPP_VERIFY_TOKEN` → `TWILIO_ACCOUNT_SID`
  - `WHATSAPP_ACCESS_TOKEN` → `TWILIO_AUTH_TOKEN`
  - `WHATSAPP_PHONE_NUMBER_ID` → `TWILIO_WHATSAPP_NUMBER`
  - `WHATSAPP_BUSINESS_ACCOUNT_ID` → Remove (not needed for Twilio)
- Update setup instructions to reference Twilio console

### C2. Fix WhatsApp Provider References in RAILWAY_DEPLOYMENT.md
**File:** `docs/RAILWAY_DEPLOYMENT.md`
**Action:** Same as C1, update all credential references to Twilio

### C3. Fix WhatsApp Provider References in railway.toml
**File:** `railway.toml`
**Action:** Update variable comments to reflect Twilio credentials

### C4. Replace WHATSAPP_TEMPLATES.md with Twilio Guide
**File:** `docs/WHATSAPP_TEMPLATES.md`
**Action:** Completely rewrite existing file with Twilio Content API instructions:
- How to create templates in Twilio Console
- How to find Content SIDs after template approval
- How to test templates
- Which templates map to which Content SIDs (verification, household update, etc.)

### C5. Fix WhatsApp Provider References in README.md
**File:** `README.md`
**Action:**
- Update tech stack section to: "WhatsApp via Twilio Business API"
- Remove any "direct integration" or "No Twilio markup" claims

### C6. Fix WhatsApp Provider References in QUICK_START.md
**File:** `docs/QUICK_START.md`
**Action:** Update all credential references to Twilio equivalents

### C7. Fix WhatsApp Provider References in SETUP.md
**File:** `docs/SETUP.md`
**Action:** Update all credential references to Twilio equivalents

### C8. Delete CHANGELOG files
**Files:** `CHANGELOG.md`, `CHANGELOG_CHORESIR.md`
**PM Decision:** Delete both - we don't want a CHANGELOG
**Action:** Delete both files, remove any references to changelog in other docs

---

## HIGH PRIORITY (11 issues)

### H1. Add Template SID Instructions to SETUP.md
**File:** `docs/SETUP.md`
**Action:** Add section "Obtaining Template Content SIDs" with:
- Where to find Content SIDs in Twilio Console after template approval
- Which templates need which SIDs (verification, household update, etc.)

### H2. Add PocketBase Admin Credentials to .env.example
**File:** `.env.example`
**Action:**
- Add `POCKETBASE_ADMIN_EMAIL` and `POCKETBASE_ADMIN_PASSWORD`
- Add comment: "Required for PocketBase schema synchronization during deployment"
- Update `DEPLOYMENT.md` to explain these credentials

### H3. Document Redis Configuration
**Files:** `docs/SETUP.md`, `docs/DEPLOYMENT.md`
**PM Decision:** Document current Redis implementation - can update later if we change
**Action:**
- Add Redis section to SETUP.md explaining it's required for leaderboard caching
- Explain local development options (Redis Docker container, Redis Cloud)
- Document as required dependency for leaderboard functionality

### H4. Add Railway Redis Setup Instructions
**File:** `docs/RAILWAY_DEPLOYMENT.md`
**Action:** Add section showing:
- How to add Railway Redis plugin
- How Redis URL gets auto-configured
- Verification steps

### H5. Document Admin Notification Settings
**File:** `docs/SETUP.md`
**Action:** Add `ENABLE_ADMIN_NOTIFICATIONS` and `ADMIN_NOTIFICATION_COOLDOWN_MINUTES` to environment variables section with explanation

### H6. Delete Twilio Migration Doc
**File:** `docs/TWILIO_MIGRATION.md`
**PM Decision:** Migration complete, delete the migration doc
**Action:** Delete the file entirely

### H7. Create ADR: WhatsApp Provider Selection (NEW)
**File:** `docs/architecture/decisions/0XX-whatsapp-provider.md`
**PM Decision:** Twilio chosen for faster time-to-market and better DX - cost is acceptable
**Action:** Create ADR documenting:
- Decision: Use Twilio Business API for WhatsApp messaging
- Rationale: Faster time-to-market, better developer experience, cost acceptable
- Consequences: Higher per-message cost, Twilio dependency
- Alternatives considered: Meta Cloud API (rejected due to setup complexity)

### H8. Create ADR: Robin Hood Protocol (NEW)
**File:** `docs/architecture/decisions/0XX-robin-hood-protocol.md`
**PM Decision:** Feature specified with rules
**Action:** Create ADR documenting:
- Decision: Allow household members to take over each other's chores
- Rules:
  - Any member can take over another member's assigned chore
  - Original assignee can optionally take one of the taker's chores (but doesn't have to)
  - Points go to ORIGINAL assignee unless chore was OVERDUE, then points go to person who completed it
  - Limit: 3 swaps per person per week maximum
- Rationale: Flexibility for household scheduling conflicts
- Consequences: Potential for gaming (mitigated by weekly limits)

### H9. Create ADR: Natural Language Processing (NEW)
**File:** `docs/architecture/decisions/0XX-nlp-approach.md`
**PM Decision:** Using OpenRouter for model flexibility, likely a cheaper fast model as task is simple
**Action:** Create ADR documenting:
- Decision: Use Pydantic AI with OpenRouter for conversational command processing
- Rationale: Model flexibility via OpenRouter, task is simple enough for fast/cheap models
- Consequences: External API dependency, per-request cost, requires internet
- Note: Not locked to Claude - can switch models via OpenRouter

### H10. Create ADR: Redis Caching (NEW)
**File:** `docs/architecture/decisions/0XX-redis-caching.md`
**PM Decision:** Document current implementation, evaluate alternatives later
**Action:** Create ADR documenting:
- Decision: Use Redis for leaderboard caching
- Status: Implemented, alternatives under evaluation
- Rationale: Performance improvement for aggregation queries
- Consequences: Additional infrastructure dependency

### H11. Create ADR: Version Management Strategy (NEW)
**File:** `docs/architecture/decisions/0XX-version-management.md`
**PM Decision:** Upgrade PocketBase to v0.23.6, test/prod parity required
**Action:** Create ADR documenting:
- Decision: Test and production environments must use identical dependency versions
- Current action: Upgrade PocketBase to v0.23.6 everywhere
- Process: Version changes require updating both test and prod configs

---

## MEDIUM PRIORITY (11 issues)

### M1. Renumber ALL ADRs Sequentially
**Files:** All ADR files in `docs/architecture/decisions/`
**PM Decision:** Renumber everything sequentially to clean up
**Action:**
- Audit current ADR numbers
- Renumber all ADRs sequentially (001, 002, 003...)
- Include the 5 new ADRs (H7-H11) in the sequence
- Update any cross-references between ADRs

### M2. Add ADR Cross-References
**Files:** All ADR files in `docs/architecture/decisions/`
**Action:** Add "Related ADRs" section to each ADR linking to related decisions

### M3. Update ADR 002 with Prompt Evolution
**File:** `docs/architecture/decisions/002-agent-framework.md`
**Action:** Add "Revisions" section documenting prompt evolution after Gamification and Smart Pantry integration

### M4. Update ADR 006 Type Checker Status
**File:** `docs/architecture/decisions/006-type-safety.md`
**PM Decision:** ty IS installed - just needs uv active to run
**Action:** Update ADR to clarify:
- `ty` is installed and available
- Run with `uv run ty` or activate uv environment first
- Document the correct usage

### M5. Add Gamification to README Features
**File:** `README.md`
**Action:** Add row to features table:
```
| 📊 Weekly Leaderboard | Gamified chore completion tracking with weekly stats and analytics |
```

### M6. Add Smart Pantry to README Features
**File:** `README.md`
**Action:** Add row to features table:
```
| 🛒 Smart Pantry | Inventory tracking and smart shopping list generation |
```

### M7. Standardize Template Button Text
**Files:** `docs/WHATSAPP_TEMPLATES.md`, `app/whatsapp_templates.py`
**Action:** Standardize on "✅ Approve / ❌ Reject" everywhere (matches ADR 008)

### M8. Fix PocketBase Admin Env Var Docs Inconsistency
**File:** `docs/QUICK_START.md`
**Action:** Ensure consistent with `.env.example` after H2 is completed

### M9. Update Roadmap - Type Checker Status
**File:** `ROADMAP.md`
**PM Decision:** ty is installed, clarify usage
**Action:** Update "Type Safety" section to reflect that ty is available via uv

### M10. Update Roadmap - Post-MVP Features
**File:** `ROADMAP.md`
**Action:** Backfill Post-MVP section with implemented features:
- Redis caching for leaderboard performance
- Weekly leaderboard analytics
- Smart pantry inventory tracking

### M11. Document Redis Required Status
**Files:** `docs/SETUP.md`, `docs/DEPLOYMENT.md`
**Action:** Clarify that Redis is REQUIRED for leaderboard functionality - without Redis, leaderboard endpoints will fail

---

## LOW PRIORITY (3 issues)

### L1. Verify Ngrok Documentation Accuracy
**File:** `docs/NGROK.md`
**Action:** Quick review to confirm it correctly references Twilio (not Meta)

### L2. Remove Changelog References
**Files:** Various docs that may reference CHANGELOG.md
**Action:** After C8, search for and remove any references to changelog files

### L3. Update CONTRIBUTING.md
**File:** `CONTRIBUTING.md`
**PM Decision:** No changelog wanted
**Action:** Remove any changelog update guidelines if present

---

## Implementation Notes

### Suggested Order
1. **Critical fixes first (C1-C8):** WhatsApp provider contradictions and changelog deletion
2. **High priority (H1-H11):** Missing setup instructions and new ADRs
3. **Medium priority (M1-M11):** ADR improvements and feature documentation
4. **Low priority (L1-L3):** Cleanup tasks

### ADR Numbering Plan
After renumbering (M1), suggested final sequence:
- 001-009: Existing ADRs (renumbered)
- 010: WhatsApp Provider Selection (H7)
- 011: Robin Hood Protocol (H8)
- 012: Natural Language Processing (H9)
- 013: Redis Caching (H10)
- 014: Version Management Strategy (H11)

### Verification
After making changes:
- Search codebase for remaining Meta/WHATSAPP_VERIFY_TOKEN references
- Verify all setup docs reference consistent Twilio credential names
- Test that a new developer can follow docs without confusion
- Verify no orphaned changelog references remain
