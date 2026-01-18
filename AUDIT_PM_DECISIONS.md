# PM/Client Decision Items

**Total Items:** 5
**Type:** Missing Architectural Decision Records (ADRs)
**Status:** ALL DECISIONS RESOLVED - Ready for implementation

---

## Decision Summary

| Item | Decision | Action |
|------|----------|--------|
| D1. Conversational Config | OpenRouter for model flexibility, cheap/fast models | Create ADR |
| D2. Redis Caching | Document current implementation, evaluate later | Create ADR |
| D3. Robin Hood Protocol | Fully specified with rules | Create ADR |
| D4. WhatsApp Provider | Twilio for DX and time-to-market | Create ADR |
| D5. Version Management | Test/prod parity required, upgrade to v0.23.6 | Create ADR |

---

## D1. Conversational Configuration Decision - RESOLVED

### PM Decision
**Use OpenRouter for model flexibility. Task is simple enough for cheap/fast language models.**

### Key Points
- Not locked to Claude - can switch models via OpenRouter
- Task complexity is low, doesn't require expensive models
- Model choice can evolve based on cost/performance needs

### Action
Create ADR documenting:
- Decision: Pydantic AI with OpenRouter for NLP
- Rationale: Model flexibility, cost optimization for simple task
- Consequences: External API dependency, per-request cost

---

## D2. Redis Caching Decision - RESOLVED

### PM Decision
**Document current Redis implementation. Evaluate alternatives later if needed.**

### Key Points
- Current Redis implementation works
- May revisit decision as scale requirements become clearer
- Document current state, don't block on alternative evaluation

### Action
Create ADR documenting current Redis usage with note that alternatives may be evaluated.

---

## D3. Robin Hood Protocol Decision - RESOLVED

### PM Decision
**Feature fully specified with the following rules:**

1. **Swap Mechanism:** Any member can take over another member's assigned chore
2. **Reciprocity:** Original assignee CAN take one of the taker's chores but DOESN'T HAVE TO
3. **Point Allocation:**
   - Points go to ORIGINAL assignee by default
   - Exception: If chore was OVERDUE, points go to the person who completed it
4. **Limits:** Maximum 3 swaps per person per week

### Action
Create ADR documenting these rules as the authoritative specification.

---

## D4. WhatsApp Provider Selection - RESOLVED

### PM Decision
**Twilio chosen for faster time-to-market and better developer experience. Cost is acceptable.**

### Key Points
- Meta is completely removed from the project
- All documentation should reference Twilio only
- No plans to support Meta as alternative

### Action
Create ADR and update all documentation to Twilio.

---

## D5. Version Management Strategy - RESOLVED

### PM Decision
**Upgrade production to PocketBase v0.23.6. Test and production must use identical versions.**

### Key Points
- Tests already validate v0.23.6 successfully
- "Test what you deploy" principle applies
- Version drift between test/prod is not acceptable

### Action
1. Create ADR documenting version parity requirement
2. Update docker-compose.yml to v0.23.6
3. Update deployment docs to v0.23.6

---

## Implementation

All decisions have been incorporated into:
- `AUDIT_CODE_CHANGES.md` - 1 task (PocketBase upgrade)
- `AUDIT_DOCUMENTATION_CHANGES.md` - 33 tasks including 5 new ADRs

No further PM input required. Ready for implementation.
