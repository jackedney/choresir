# ADR 016: Conversational House Joining Flow

**Status:** Proposed

## Context

The current house joining flow requires users to provide all information in a single message using a specific format:

```text
"I want to join. Code: XXXX, Password: YYYY, Name: Your Name"
```

This approach has several problems:

1. **Error-prone**: Requires regex parsing that can fail with minor formatting variations
2. **Poor user experience**: Users must remember the exact format
3. **Security concerns**: Password remains visible in chat history
4. **Limited validation**: Cannot provide real-time feedback on invalid inputs
5. **No international name support**: Current validation doesn't handle Unicode characters well
6. **No rate limiting**: Vulnerable to brute force password attempts

The project needs a more user-friendly and secure approach to house joining.

## Decision

We will implement a multi-step conversational flow for house joining with the following characteristics:

### Flow Design

#### Phase 1: Command Initiation

- User sends: `/house join {house_name}`
- System validates house name against configured value (case-insensitive)
- Creates session state in database

#### Phase 2: Password Collection

- Bot prompts: "Please provide the house password:"
- User sends password
- System validates with constant-time comparison
- On success, sends security reminder: "⚠️ For security, please delete your previous message containing the password"

#### Phase 3: Name Collection

- Bot prompts: "What name would you like to use?"
- User sends name
- System validates name (Unicode support, length checks, character restrictions)

#### Phase 4: Confirmation

- Bot responds: "Welcome {name}! Your membership request has been submitted. An admin will review shortly."

### Technical Architecture

#### State Management

New `join_sessions` collection with fields:

- `phone` (indexed): User identifier
- `house_name`: House being joined
- `step`: Current flow step ("awaiting_password" | "awaiting_name")
- `password_attempts_count`: Failed attempt counter
- `last_attempt_at`: Timestamp for rate limiting
- `created_at`: Session creation time
- `expires_at`: Auto-expire after 5 minutes

#### Security Features

1. **House name validation**: Must match configured house name
2. **Rate limiting**: 5 second delay after each failed password attempt
3. **Constant-time password comparison**: Use `secrets.compare_digest()`
4. **Session expiry**: 5 minute timeout
5. **No hard lockouts**: Unlimited attempts with rate limiting (better UX, prevents DoS)

#### Name Validation

- Unicode letter support for international names (김철수, José, Владimír, O'Brien)
- Allows: letters, spaces, hyphens, apostrophes
- Length: 1-50 characters
- Regex pattern: `[\w\s'-]` with `re.UNICODE` flag

#### Message Deletion

- Twilio WhatsApp API does not support message deletion
- Solution: Send security reminder after password collection
- User must manually delete their password message

### Implementation Components

**Files to Modify:**

1. `src/core/schema.py`: Add `join_sessions` collection definition
2. `src/agents/choresir_agent.py`: Add command pattern and handler functions
3. `src/interface/webhook.py`: Update `handle_unknown_user()` routing logic
4. `src/services/user_service.py`: Update `request_join()` for session context
5. `src/domain/user.py`: Add name field validator

**Error Handling:**

- Invalid house name: "Invalid house name. Please check and try again."
- Rate limited: "Please wait a few seconds before trying again."
- Invalid password: "Invalid password. Please try again or type '/house join {house_name}' to restart."
- Invalid name: "That name isn't usable. Please provide a different name (letters, spaces, hyphens, and apostrophes only)."
- Session timeout: "Your join session has expired. Please restart with '/house join {house_name}'."
- Already a member: "You're already a member of this household!"

**Session Cleanup:**

- Immediate deletion on successful join
- Auto-expire after 5 minutes (checked on each message)
- Manual restart via new `/house join {house_name}` command
- Optional: Background job for batch cleanup

## Consequences

### Positive

1. **Better user experience**: Step-by-step guidance is more intuitive
2. **Improved error handling**: Real-time validation with helpful error messages
3. **Enhanced security**:
   - Rate limiting prevents brute force attacks
   - House name validation adds security layer
   - Security reminder for password deletion
4. **International support**: Unicode name validation supports global users
5. **Clearer state management**: Explicit session tracking in database
6. **No hard lockouts**: Users can't be permanently blocked (better UX)
7. **Flexible**: Easy to add more steps (e.g., profile picture, preferences)

### Negative

1. **Added complexity**: Requires state management and session handling
2. **Database overhead**: New collection and queries for session management
3. **Multiple messages**: Requires more back-and-forth than a single message
4. **Time constraint**: Users must complete flow within 5 minutes
5. **No password deletion**: Cannot automatically delete password messages (API limitation)
6. **Concurrent sessions**: Multiple users joining simultaneously requires careful state isolation

### Trade-offs

1. **Timeout duration**: 5 minutes balances convenience vs. security
   - Alternative considered: 10 minutes (too permissive), 2 minutes (too restrictive)
2. **Rate limiting approach**: 5 second delay balances security vs. UX
   - Alternative considered: Hard lockout after 3 attempts (rejected - too restrictive)
   - Alternative considered: Exponential backoff (rejected - too complex for this use case)
3. **House name validation**: Adds security but requires exact match
   - Alternative considered: Skip validation (rejected - reduces security)
4. **Name character restrictions**: Allows Unicode but restricts special characters
   - Alternative considered: Allow all characters (rejected - potential display issues)
   - Alternative considered: ASCII only (rejected - excludes international users)

## Alternatives Considered

### Keep Single-Message Flow

**Rejected**: Poor UX, difficult to debug, hard to extend

### Button-Based Flow

**Rejected**: Not suitable for sensitive input like passwords; WhatsApp API limitations

### Email Verification

**Rejected**: Adds dependency on email system; out of scope for WhatsApp-first experience

### Hard Lockout After Failed Attempts

**Rejected**: Too restrictive; users could be permanently blocked without admin intervention

### CAPTCHA Integration

**Deferred**: Consider for future enhancement if bot abuse becomes an issue

## Implementation Plan

### Phase 1: Database Schema (Est. 1-2 hours)

- [ ] Add `join_sessions` collection to `src/core/schema.py`
- [ ] Create database migration if needed
- [ ] Add indexes on `phone` field

### Phase 2: Core Logic (Est. 3-4 hours)

- [ ] Add `/house join` pattern to system prompt in `src/agents/choresir_agent.py`
- [ ] Implement `handle_house_join()` function
- [ ] Implement `handle_join_password_step()` with rate limiting
- [ ] Implement `handle_join_name_step()` with validation
- [ ] Update `src/interface/webhook.py` routing logic

### Phase 3: Validation (Est. 1-2 hours)

- [ ] Add name field validator to `src/domain/user.py`
- [ ] Add house name validation logic
- [ ] Add password validation with `secrets.compare_digest()`

### Phase 4: Session Management (Est. 1-2 hours)

- [ ] Implement session creation
- [ ] Implement session expiry checking
- [ ] Implement session cleanup on success
- [ ] Consider background cleanup job

### Phase 5: Testing (Est. 2-3 hours)

- [ ] Unit tests for name validator
- [ ] Unit tests for rate limiting
- [ ] Integration tests for full flow
- [ ] Manual end-to-end testing with real WhatsApp

### Phase 6: Documentation (Est. 1 hour)

- [ ] Update user documentation
- [ ] Add inline code comments
- [ ] Update API documentation if applicable

**Total Estimated Time**: 9-14 hours

## Testing Strategy

### Unit Tests

- Name validator: Test Unicode support, length limits, special characters
- Rate limiting: Test timing constraints and attempt counting
- House name validation: Test case-insensitivity and exact matching

### Integration Tests

- Full join flow: Test complete happy path
- Error paths: Test each error condition
- Session timeout: Test expiry logic
- Concurrent joins: Test multiple users joining simultaneously

### Manual Testing

- End-to-end WhatsApp testing with real phone numbers
- Test on multiple devices and WhatsApp clients
- Test with various international names
- Test password security reminder display

## Verification Checklist

- [ ] User can initiate join with `/house join {name}`
- [ ] Invalid house name shows error message
- [ ] Bot prompts for password after valid house name
- [ ] Password validation works correctly with constant-time comparison
- [ ] Invalid password shows helpful error with retry option
- [ ] Rate limiting prevents rapid password attempts
- [ ] Security reminder is sent after password validation
- [ ] Bot prompts for name after valid password
- [ ] Name validation rejects empty/invalid names
- [ ] Name validation accepts Unicode characters correctly
- [ ] Valid name completes join flow successfully
- [ ] Session expires after 5 minutes of inactivity
- [ ] Multiple users can join simultaneously without interference
- [ ] User can restart join flow with new command
- [ ] Already-member check prevents duplicate joins

## Future Enhancements

Consider these improvements in future iterations:

**Security:**

- CAPTCHA or challenge-response for bot prevention
- IP-based rate limiting in addition to phone-based
- Honeypot fields to catch automated bots
- Rotating house passwords after N joins

**UX:**

- Cancel command (`/cancel` or "cancel join")
- Progress indicators ("Step 2 of 3: Password")
- Help command during flow
- Profile picture upload support

**Features:**

- Multi-house support (join multiple households)
- Invitation codes (time-limited, single-use tokens)
- Admin approval notifications via WhatsApp
- Join flow analytics and metrics

**Technical:**

- Comprehensive logging for debugging
- Admin dashboard for pending requests
- A/B testing framework
- Prometheus metrics for success/failure rates

## References

- [Twilio WhatsApp API Documentation](https://www.twilio.com/docs/whatsapp)
- [Python secrets module](https://docs.python.org/3/library/secrets.html) (constant-time comparison)
- [Unicode in Python regex](https://docs.python.org/3/library/re.html#re.UNICODE)
- [Rate Limiting Best Practices](https://www.ietf.org/rfc/rfc6585.txt)

## Notes

- This ADR documents the design; implementation will be tracked in a separate GitHub issue
- The 5-minute session timeout was chosen based on typical user interaction patterns
- House name validation adds minimal overhead but significant security benefit
- Rate limiting values (5 second delay) may be adjusted based on production metrics

## Related ADRs

- [ADR 007: Operations](007-operations.md) - Original onboarding protocol (this ADR enhances the UX)
