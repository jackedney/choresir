# Feature: Conversational House Joining Flow

## Context

The current house joining flow requires users to provide all information in a single message with exact formatting:

```
"I want to join. Code: XXXX, Password: YYYY, Name: Your Name"
```

**Problems with current approach**:
1. **Error-prone**: Regex parsing fails with minor format variations
2. **Poor UX**: Users must remember exact format
3. **Security**: Password remains visible in chat history
4. **Limited validation**: No real-time feedback on invalid inputs
5. **No international support**: Current validation doesn't handle Unicode names
6. **No rate limiting**: Vulnerable to brute force password attacks

## User Story

As a new user wanting to join a household, I want to be guided step-by-step through the joining process so that I don't need to remember exact syntax and receive immediate feedback on any errors.

## Proposed Solution

Implement a multi-step conversational flow that collects information sequentially with validation at each step.

---

## User Experience Flow

### Happy Path
```
User: /house join MyHouse

Bot: Please provide the house password:

User: secret123

Bot: ⚠️ For security, please delete your previous message containing the password
     What name would you like to use?

User: José García

Bot: Welcome José García! Your membership request has been submitted.
     An admin will review shortly.
```

### Error Handling Examples

**Invalid house name:**
```
User: /house join WrongHouse
Bot: Invalid house name. Please check and try again.
```

**Invalid password:**
```
User: wrongpassword
Bot: Invalid password. Please try again or type '/house join MyHouse' to restart.
```

**Invalid name:**
```
User: !!!emoji🎉
Bot: That name isn't usable. Please provide a different name
     (letters, spaces, hyphens, and apostrophes only).
```

**Rate limiting:**
```
User: wrongpassword1
[Immediately tries again]
User: wrongpassword2
Bot: Please wait a few seconds before trying again.
```

**Session timeout:**
```
[User waits 6 minutes after initiating join]
User: myname
Bot: Your join session has expired. Please restart with '/house join MyHouse'.
```

---

## Technical Design

### Flow Phases

1. **Command Initiation**: `/house join {house_name}`
   - Validate house name matches configured value (case-insensitive)
   - Create session in database

2. **Password Collection**
   - Prompt for password
   - Validate with constant-time comparison
   - Rate limit: 5 second delay after failed attempts
   - Send security reminder after success

3. **Name Collection**
   - Prompt for name
   - Validate Unicode support, length, character restrictions
   - Support international names: 김철수, José, Владимір, O'Brien

4. **Confirmation**
   - Complete join request
   - Clean up session
   - Send welcome message

### Database Schema

#### New Collection: `join_sessions`
```python
{
  "phone": "+1234567890",              # indexed
  "house_name": "MyHouse",
  "step": "awaiting_password",         # "awaiting_password" | "awaiting_name"
  "password_attempts_count": 0,
  "last_attempt_at": None,             # datetime | None
  "created_at": "2026-01-19T10:00:00Z",
  "expires_at": "2026-01-19T10:05:00Z" # 5 minute timeout
}
```

### Security Features

1. **House name validation**: Must match configured house name
   - Adds security layer beyond just password
   - Case-insensitive matching for UX

2. **Rate limiting**: 5 second delay after failed password attempts
   - Prevents brute force attacks
   - No hard lockout (better UX)
   - Tracks `last_attempt_at` timestamp

3. **Constant-time password comparison**: `secrets.compare_digest()`
   - Prevents timing attacks

4. **Session expiry**: 5 minute timeout
   - Automatic cleanup of abandoned sessions

5. **Password deletion reminder**: (Twilio API doesn't support message deletion)
   - Bot sends: "⚠️ For security, please delete your previous message containing the password"

### Name Validation

**Validation Rules**:
- **Length**: 1-50 characters (after trimming)
- **Allowed characters**: Unicode letters, spaces, hyphens, apostrophes
- **Regex pattern**: `[\w\s'-]` with `re.UNICODE` flag
- **Examples**:
  - ✅ Valid: "김철수", "José García", "Владимир", "O'Brien", "Mary-Jane"
  - ❌ Invalid: "", "   ", "🎉emoji", "user@123", "a"*51

**Validator Implementation**:
```python
@field_validator("name")
@classmethod
def validate_name_usable(cls, v: str) -> str:
    """Validate name is usable - allows Unicode letters and spaces."""
    v = v.strip()

    if not v or len(v) < 1:
        raise ValueError("Name cannot be empty")

    if len(v) > 50:
        raise ValueError("Name too long (max 50 characters)")

    # Unicode letters, spaces, hyphens, apostrophes
    if not re.match(r"^[\w\s'-]+$", v, re.UNICODE):
        raise ValueError(
            "Name can only contain letters, spaces, hyphens, and apostrophes"
        )

    return v
```

### Error Messages

| Scenario | Message |
|----------|---------|
| Invalid house name | "Invalid house name. Please check and try again." |
| Rate limited | "Please wait a few seconds before trying again." |
| Invalid password | "Invalid password. Please try again or type '/house join {house_name}' to restart." |
| Invalid name | "That name isn't usable. Please provide a different name (letters, spaces, hyphens, and apostrophes only)." |
| Session timeout | "Your join session has expired. Please restart with '/house join {house_name}'." |
| Already a member | "You're already a member of this household!" |
| Duplicate session | Clear old session, start fresh |

---

## Implementation Plan

### Phase 1: Database Schema
**Files**: `src/core/schema.py`

- [ ] Add `join_sessions` collection definition
- [ ] Add index on `phone` field
- [ ] Create database migration if needed
- [ ] Add cleanup logic for expired sessions

**Estimated Time**: 1-2 hours

### Phase 2: Core Logic
**Files**: `src/agents/choresir_agent.py`, `src/interface/webhook.py`

#### System Prompt Updates
- [ ] Add `/house join {house_name}` pattern recognition
- [ ] Document step-by-step flow for agent

#### Handler Functions
- [ ] `handle_house_join()` - Initialize join session
  - Validate house name
  - Create session with `awaiting_password` step
  - Respond with password prompt

- [ ] `handle_join_password_step()` - Password validation
  - Check rate limit (5 second delay)
  - Validate password with `secrets.compare_digest()`
  - Increment `password_attempts_count` on failure
  - Update session to `awaiting_name` on success
  - Send security reminder

- [ ] `handle_join_name_step()` - Name validation and completion
  - Validate name with field validator
  - Call `user_service.request_join()`
  - Delete session
  - Send welcome message

#### Routing Logic (`webhook.py`)
- [ ] Update `handle_unknown_user()` to check for active join sessions
- [ ] Route to appropriate step handler based on session state
- [ ] Handle session expiry checking

**Estimated Time**: 3-4 hours

### Phase 3: Validation Layer
**Files**: `src/domain/user.py`, `src/services/user_service.py`

- [ ] Add name field validator to User model (Unicode support)
- [ ] Add house name validation helper
- [ ] Update `request_join()` to accept session context
- [ ] Add session cleanup on successful join

**Estimated Time**: 1-2 hours

### Phase 4: Session Management
**Files**: `src/services/session_service.py` (new)

- [ ] Create session management service
- [ ] Implement session creation with expiry
- [ ] Implement session lookup by phone
- [ ] Implement session expiry checking
- [ ] Implement session cleanup
- [ ] (Optional) Add background job for batch cleanup

**Estimated Time**: 1-2 hours

### Phase 5: Testing
**Files**: `tests/integration/test_house_join.py`, `tests/unit/test_validators.py`

#### Unit Tests
- [ ] Test name validator with Unicode characters
- [ ] Test name validator edge cases (empty, too long, special chars)
- [ ] Test rate limiting logic
- [ ] Test house name validation (case-insensitive)
- [ ] Test session expiry calculation

#### Integration Tests
- [ ] Test full happy path (command → password → name → success)
- [ ] Test invalid house name rejection
- [ ] Test invalid password with retry
- [ ] Test rate limiting enforcement
- [ ] Test invalid name rejection
- [ ] Test session timeout
- [ ] Test concurrent joins (multiple users)
- [ ] Test already-member check
- [ ] Test session restart

#### Manual Testing
- [ ] End-to-end WhatsApp test with real phone
- [ ] Test with international names (Korean, Spanish, Russian, Irish)
- [ ] Test password security reminder display
- [ ] Test on multiple devices/WhatsApp clients

**Estimated Time**: 2-3 hours

### Phase 6: Documentation
**Files**: README, user docs, inline comments

- [ ] Update user documentation with `/house join` instructions
- [ ] Add inline code comments for complex logic
- [ ] Update API documentation (if applicable)
- [ ] Document rate limiting behavior
- [ ] Document session expiry policy

**Estimated Time**: 1 hour

**Total Estimated Time**: 9-14 hours

---

## Files to Modify

| File | Changes | Lines |
|------|---------|-------|
| `src/core/schema.py` | Add `join_sessions` collection | ~30 |
| `src/agents/choresir_agent.py` | Add command pattern, handler functions | ~150 |
| `src/interface/webhook.py` | Update routing logic for join sessions | ~50 |
| `src/services/user_service.py` | Update `request_join()` for session context | ~20 |
| `src/domain/user.py` | Add name field validator | ~15 |
| `src/services/session_service.py` | New service for session management | ~100 |
| `tests/unit/test_validators.py` | Unit tests for name validation | ~50 |
| `tests/integration/test_house_join.py` | Integration tests for full flow | ~150 |

**Total**: ~565 lines of code (including tests)

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: Command Initiation                                      │
├─────────────────────────────────────────────────────────────────┤
│ User: "/house join MyHouse"                                      │
│   ↓                                                              │
│ Parse command, extract house_name="MyHouse"                      │
│   ↓                                                              │
│ Validate house_name matches config (case-insensitive)            │
│   ↓                                                              │
│ Create join_session(phone, house_name, step="awaiting_password") │
│   ↓                                                              │
│ Bot: "Please provide the house password:"                        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: Password Collection                                     │
├─────────────────────────────────────────────────────────────────┤
│ User: "secret123"                                                │
│   ↓                                                              │
│ Lookup join_session by phone                                     │
│   ↓                                                              │
│ Check rate limit: last_attempt_at < 5 seconds ago? → Reject      │
│   ↓                                                              │
│ Validate password with secrets.compare_digest()                  │
│   ↓                                                              │
│ If invalid:                                                      │
│   - Increment password_attempts_count                            │
│   - Update last_attempt_at = now                                 │
│   - Bot: "Invalid password. Please try again."                   │
│   ↓                                                              │
│ If valid:                                                        │
│   - Update session(step="awaiting_name")                         │
│   - Bot: "⚠️ For security, please delete password message"       │
│   - Bot: "What name would you like to use?"                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: Name Collection                                         │
├─────────────────────────────────────────────────────────────────┤
│ User: "José García"                                              │
│   ↓                                                              │
│ Lookup join_session by phone                                     │
│   ↓                                                              │
│ Validate name with Pydantic validator                            │
│   ↓                                                              │
│ If invalid:                                                      │
│   - Bot: "Name isn't usable. Please provide different name..."   │
│   ↓                                                              │
│ If valid:                                                        │
│   - Call user_service.request_join(phone, name, house_code, ...) │
│   - Delete join_session                                          │
│   - Bot: "Welcome José García! Request submitted..."             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Acceptance Criteria

### Core Functionality
- [ ] User can initiate join with `/house join {house_name}`
- [ ] Invalid house name is rejected with helpful message
- [ ] Bot prompts for password after valid house name
- [ ] Password validation uses constant-time comparison
- [ ] Invalid password shows retry option
- [ ] Rate limiting prevents rapid password attempts (5 second delay)
- [ ] Security reminder is sent after successful password validation
- [ ] Bot prompts for name after valid password
- [ ] Name validation rejects empty/invalid names
- [ ] Name validation accepts Unicode characters (international names)
- [ ] Valid name completes join flow successfully
- [ ] Welcome message is sent after successful join

### Session Management
- [ ] Session is created on `/house join` command
- [ ] Session expires after 5 minutes of inactivity
- [ ] Expired sessions show timeout message
- [ ] User can restart join flow with new `/house join` command
- [ ] Sessions are cleaned up on successful join
- [ ] Multiple users can join simultaneously without conflicts

### Security
- [ ] House name must match configured value
- [ ] Password comparison is constant-time
- [ ] Rate limiting enforced on password attempts
- [ ] `password_attempts_count` tracked correctly
- [ ] `last_attempt_at` timestamp updated on failures
- [ ] No sensitive data logged

### Error Handling
- [ ] All error scenarios return helpful messages
- [ ] User can recover from errors without losing progress (where possible)
- [ ] Already-member check prevents duplicate joins
- [ ] Invalid input prompts for correction, not full restart

### Privacy & UX
- [ ] Password message deletion reminder is clear
- [ ] Error messages are user-friendly, not technical
- [ ] Flow completes in reasonable time (< 5 minutes)
- [ ] International names display correctly

---

## Edge Cases & Considerations

### 1. Concurrent Join Attempts
**Scenario**: User sends multiple `/house join` commands rapidly

**Solution**: Clear old session and create new one. Latest command wins.

### 2. Already a Member
**Scenario**: Existing user tries to join again

**Solution**: Check membership before creating session. Return: "You're already a member of this household!"

### 3. Session Cleanup
**Scenario**: User abandons join flow (session expires)

**Solution**:
- Check expiry on each message from unknown user
- Delete expired session automatically
- Prompt user to restart

**Optional Enhancement**: Background job to batch-delete expired sessions every hour

### 4. Case Sensitivity
**Scenario**: User types `/house join myhouse` (lowercase)

**Solution**: House name validation is case-insensitive. Normalize to lowercase for comparison.

### 5. Rate Limiting Storage
**Scenario**: How to persist rate limit state across messages?

**Solution**: Store `last_attempt_at` in session document. Check time delta on each password attempt.

### 6. Name Collision with Existing Member
**Scenario**: User chooses name already taken by another member

**Solution**: Allow duplicate names. Use phone number as unique identifier. Add validation check if uniqueness becomes requirement later.

### 7. Special Characters in House Name
**Scenario**: Configured house name contains spaces or special characters

**Solution**: Command parser should handle quoted strings: `/house join "My House"` or normalize spaces: `/house join My House` → "My House"

---

## Future Enhancements (Out of Scope for v1)

### Security
- [ ] CAPTCHA integration for bot prevention
- [ ] IP-based rate limiting (in addition to phone-based)
- [ ] Honeypot fields to catch automated bots
- [ ] Rotating house passwords after N successful joins
- [ ] Invitation codes (time-limited, single-use tokens)

### UX
- [ ] Cancel command (`/cancel` or "cancel join")
- [ ] Progress indicators ("Step 2 of 3: Password")
- [ ] Help command during flow
- [ ] Profile picture upload support
- [ ] Preview of house stats before joining

### Features
- [ ] Multi-house support (join multiple households)
- [ ] Admin approval notifications via WhatsApp (proactive, not passive)
- [ ] Join flow analytics (track drop-off rates at each step)
- [ ] Custom welcome messages per house

### Technical
- [ ] Comprehensive logging for join flow debugging
- [ ] Admin dashboard for pending join requests
- [ ] A/B testing framework for flow variations
- [ ] Prometheus metrics for success/failure rates
- [ ] Background job for expired session cleanup

---

## Testing Strategy

### Unit Tests (`tests/unit/test_validators.py`)
```python
def test_name_validator_accepts_unicode():
    """Test international names are accepted"""
    valid_names = ["김철수", "José García", "Владимир", "O'Brien", "Mary-Jane"]
    for name in valid_names:
        User(name=name, ...)  # Should not raise

def test_name_validator_rejects_invalid():
    """Test invalid names are rejected"""
    invalid_names = ["", "   ", "🎉", "user@123", "a" * 51]
    for name in invalid_names:
        with pytest.raises(ValueError):
            User(name=name, ...)

def test_rate_limiting():
    """Test 5 second delay enforcement"""
    session = JoinSession(last_attempt_at=datetime.now())
    assert is_rate_limited(session) == True

    session.last_attempt_at = datetime.now() - timedelta(seconds=6)
    assert is_rate_limited(session) == False
```

### Integration Tests (`tests/integration/test_house_join.py`)
```python
async def test_full_join_flow_happy_path():
    """Test complete join flow from command to success"""
    # Send /house join command
    # Verify password prompt
    # Send valid password
    # Verify name prompt
    # Send valid name
    # Verify welcome message
    # Verify user created in database
    # Verify session cleaned up

async def test_join_flow_with_invalid_password():
    """Test password retry flow"""
    # Send /house join command
    # Send invalid password
    # Verify retry prompt
    # Send valid password
    # Continue to name step

async def test_join_flow_rate_limiting():
    """Test rate limit enforcement"""
    # Send /house join command
    # Send invalid password
    # Immediately send another password
    # Verify rate limit message
    # Wait 5 seconds
    # Send password (should succeed)

async def test_session_expiry():
    """Test 5 minute timeout"""
    # Send /house join command
    # Advance time by 6 minutes
    # Send password
    # Verify timeout message

async def test_concurrent_joins():
    """Test multiple users joining simultaneously"""
    # Start join flow for user A
    # Start join flow for user B
    # Complete both flows
    # Verify no state leakage between sessions
```

---

## Related Documentation

- **ADR**: `docs/architecture/decisions/007-conversational-house-joining.md`
- **Design Decisions**: See ADR for detailed rationale
- **Related Issues**: None (this is a greenfield feature)

---

## Open Questions

1. **Should we support phone number changes?**
   - If user changes their WhatsApp number mid-flow, session is lost. Acceptable trade-off?

2. **Should we log join attempts for analytics?**
   - Could help identify issues (high dropout at password step = unclear instructions)
   - Privacy consideration: Don't log passwords or PII

3. **Should admins be notified of new join requests?**
   - Current: Passive (admin checks pending users)
   - Future: Active (WhatsApp notification to admins)
   - Out of scope for v1, but design should accommodate

4. **Should we support joining multiple houses?**
   - Current: Single house per user
   - Future: User could be member of multiple households
   - Requires major refactor, defer to future version

---

## Implementation Checklist

### Pre-Implementation
- [x] ADR created and reviewed
- [ ] Design approved by team
- [ ] Database schema reviewed
- [ ] Security considerations documented

### Implementation
- [ ] Database schema added
- [ ] Handler functions implemented
- [ ] Routing logic updated
- [ ] Validation added
- [ ] Session management implemented
- [ ] Error handling complete
- [ ] Unit tests written
- [ ] Integration tests written

### Pre-Merge
- [ ] All tests passing
- [ ] Manual testing complete
- [ ] Code review completed
- [ ] Documentation updated
- [ ] Security review passed

### Post-Merge
- [ ] Deploy to staging
- [ ] End-to-end testing in staging
- [ ] Monitor error rates
- [ ] Deploy to production
- [ ] Monitor join success rates

---

**Status**: Ready for Implementation
**Priority**: High (UX improvement + security enhancement)
**Estimated LOE**: 9-14 hours (1-2 days)
**Dependencies**: None
**Blocks**: None
**Related Issues**: None
