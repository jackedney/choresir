# Onboarding: Joining a Household

This guide covers how to join an existing household and understand your role in the system.

## Joining a Household

To start using WhatsApp Home Boss, you need to join a household. You'll need the house name from an existing member.

### Step 1: Start the Join Process

Send a message to the bot:

```
/house join {house_name}
```

Replace `{house_name}` with the actual name of the household.

**Example:**
```
/house join SmithFamily
```

### Step 2: Provide the Password

The bot will ask for the house password. Type it in a separate message.

**Important:** After sending your password, the bot will ask you to delete that message for security.

### Step 3: Enter Your Name

Provide your preferred display name. This is how other household members will see you.

**Example:**
```
Alex
```

### Step 4: Wait for Approval

Your account will be created in "pending" status. An admin must approve your membership before you can use all features.

**You'll receive:**
```
Welcome Alex! Your membership request has been submitted. An admin will review shortly.
```

### Step 5: Approved!

Once an admin approves you, you'll be able to:
- Log chore completions
- Create new chores
- View leaderboards
- Use all bot features

## Cancelling the Join Process

If you need to cancel during the join flow, send:

```
/cancel
```

You can start over by sending `/house join {house_name}` again.

## User Roles

There are two types of users in WhatsApp Home Boss:

### Regular Member

Regular members can:
- Log chore completions
- Create new household chores
- Create personal chores
- View all analytics and leaderboards
- Verify others' chore completions
- Manage shopping list
- View pantry status

### Admin

Admins have additional capabilities:
- Approve new member requests
- Manage household settings
- Ban users if necessary

Only admins can approve new household members.

## Troubleshooting

### "Invalid house name"

**Error:** The house name doesn't match what's configured.

**Solution:** Check with an existing member for the exact house name. It's case-sensitive.

### "Invalid password"

**Error:** The password doesn't match the household's configured password.

**Solution:** Double-check the password with the household admin. Passwords are case-sensitive.

### "Your membership is awaiting approval"

**Message:** You've completed the join process but an admin hasn't approved you yet.

**Solution:** Contact a household admin to approve your membership. While pending, you can only wait - you cannot use other features.

### Session expired

**Error:** If you take too long between steps, the join session expires.

**Solution:** Start over with `/house join {house_name}`.

## Common Questions

**Q: Can I join multiple households?**
A: No, each phone number can only belong to one household.

**Q: Can I change my name after joining?**
A: Not directly. Contact an admin to remove and re-add you with a new name.

**Q: What if I forget the household name?**
A: Ask any existing member. The house name is configured during setup and shared with members.

**Q: Can I rejoin if I was banned?**
A: No, banned users cannot rejoin. Contact your household admin if you believe this was in error.

## Next Steps

After joining:
- [Household Chores Guide](./chores.md) - Learn how to manage shared tasks
- [Personal Chores Guide](./personal-chores.md) - Set up private tasks
- [Pantry & Shopping Guide](./pantry.md) - Manage inventory and shopping
