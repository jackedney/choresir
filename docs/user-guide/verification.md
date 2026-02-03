# Verification System

The verification system ensures accountability by requiring peer review of chore completions.

## Overview

Household chore completions require verification from another household member. This prevents false claims and encourages quality standards.

### How Verification Works

1. **You complete a chore** - Send "Done {chore_name}"
2. **Bot requests verification** - Notifies household members
3. **Another member reviews** - They approve or reject your completion
4. **Chore status updates** - Approved = complete, Rejected = needs attention

### Why Verification Matters

- **Prevents false claims** - Ensures chores are actually done
- **Maintains quality** - Others can confirm work meets standards
- **Builds trust** - Transparent process for household accountability
- **Fair competition** - Leaderboard reflects real contributions

## Verifying a Chore Completion

When someone logs a completion, you'll receive a notification. To verify:

### Approving a Completion

If you confirm the chore was actually done:

```
Approve {log_id}
```

**Example:**
```
Approve abc123xyz
```

The chore is marked complete and the person earns points.

### Rejecting a Completion

If the chore wasn't done properly:

```
Reject {log_id} - {reason}
```

**Example:**
```
Reject abc123xyz - Dishes are still in the sink
```

The chore returns to TODO state and no points are awarded.

### Finding Log IDs

When someone logs a completion, the bot provides the log ID. Check your chat history or ask the person who logged it.

**Example notification:**
```
Sam logged completion of 'Clean bathroom'.
Log ID: abc123xyz
Verify with: Approve abc123xyz
```

## Verification Rules

### Self-Verification Prohibited

You cannot verify your own chore completions.

**Error message:**
```
Error: You cannot verify your own chore claim.
```

**Solution:** Ask another household member to verify.

### Any Member Can Verify

Any active household member (except the claimant) can verify a chore. You don't need to be an admin.

### One Verification Required

Only one approval is needed per chore completion. Once approved, the chore is complete.

## Pending Verifications

Chores awaiting verification are in "pending" state.

### Viewing Pending Verifications

Check if there are completions waiting for review:

```
Pending verifications
What needs verification?
Status
```

Your personal stats also show pending count:

```
Stats
```

**Example output includes:**
```
Pending Verification: 2
```

### Why Verifications Get Stuck

- No one has checked the chore
- Members aren't aware of pending requests
- Busy household with delayed reviews

**Solution:** Prompt household members to review pending completions.

## Rejection Handling

When a completion is rejected, the chore returns to TODO state.

### What Happens After Rejection

1. Chore status changes to "TODO"
2. Person can log completion again
3. Points are not awarded for rejected attempts
4. Rejection reason is recorded

### Resolving Rejections

If your completion was rejected:

1. **Understand the reason** - Review the rejection feedback
2. **Complete the chore properly** - Address any issues
3. **Log completion again** - Send "Done {chore_name}" once finished

### Disputes

If you believe a rejection was unfair:

1. **Communicate directly** - Discuss with the verifier
2. **Provide evidence** - Photos or witnesses if available
3. **Ask another member to verify** - Different perspective

**Note:** The system doesn't currently have voting/dispute resolution - handled by household communication.

## Personal Chore Verification

Personal chores have different verification rules.

### Self-Verification

If you have no accountability partner, personal chores are auto-verified when you log them.

```
/personal done gym
✅ Logged 'Gym'. Nice work!
```

### Partner Verification

If you set an accountability partner, they must verify your completions.

**For you:**
```
/personal done gym
✅ Logged 'Gym'. Awaiting verification from Alex.
```

**For your partner:**
```
Alex logged personal chore 'Gym'.
Verify with: Approve [log_id]
```

### Auto-Verification (48-hour timeout)

If your partner doesn't respond within 48 hours, the system auto-approves:

```
✅ 'Gym' auto-verified (partner did not respond within 48 hours)
```

This prevents tasks from getting stuck while maintaining accountability.

## Verification Best Practices

### For Claimants

1. **Log completions promptly** - Don't wait until bedtime
2. **Include details** - Notes help verifiers confirm work
3. **Be present for verification** - Be available if questions arise

### For Verifiers

1. **Review promptly** - Check soon after notification
2. **Be fair** - Approve if work meets reasonable standards
3. **Provide clear feedback** - Explain reasons for rejection
4. **Don't be a bottleneck** - Keep the system flowing

### For the Household

1. **Establish standards** - Agree on what "done" means for each chore
2. **Rotate verification duties** - Share the responsibility
3. **Communicate openly** - Discuss disputes constructively

## Common Error Messages

### "You cannot verify your own chore claim"

**Cause:** You tried to approve your own completion.

**Solution:** Ask another household member to verify. This is intentional design.

### "Log not found or already verified"

**Cause:** The log ID doesn't exist or is already processed.

**Solutions:**
1. Check the log ID is correct
2. Verify it hasn't already been approved/rejected
3. Ask for a fresh notification if needed

### "Permission denied"

**Cause:** You're not authorized to verify (rare, typically for special cases).

**Solution:** Contact an admin if this occurs unexpectedly.

## Verification Workflows

### Standard Workflow

```
1. You: Done dishes
   Bot: Logged 'dishes'. Awaiting verification from another member.

2. Sam (verifier): Approve abc123
   Bot: Chore 'dishes' approved. Next deadline: Friday.
```

### Rejection Workflow

```
1. You: Done dishes
   Bot: Logged 'dishes'. Awaiting verification...

2. Sam (verifier): Reject abc123 - Dishes still dirty
   Bot: Chore 'dishes' rejected. Moving to conflict resolution.

3. You: (complete dishes properly) Done dishes
   Bot: Logged 'dishes'. Awaiting verification...
```

### Personal Chore with Partner

```
1. You: /personal done gym
   Bot: Logged 'Gym'. Awaiting verification from Alex.

2. Alex (partner): Approve xyz789
   Bot: Verified your 'Gym'. Keep it up!
```

## Related Topics

- [Household Chores](./chores.md) - Managing shared tasks
- [Personal Chores](./personal-chores.md) - Private task verification
- [Analytics & Stats](./analytics.md) - Viewing performance
