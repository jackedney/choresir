# Frequently Asked Questions

Common questions about using WhatsApp Home Boss.

## Getting Started

### How do I join a household?

Send `/house join {house_name}` to the bot. You'll need the house name from an existing member. See [Onboarding Guide](./onboarding.md) for detailed steps.

### What if I don't know the house name?

Ask any existing household member for the exact house name. The house name is configured during setup and shared with members.

### Can I join multiple households?

No, each phone number can only belong to one household. If you need to switch households, contact your current admin to remove your account.

### Why is my account pending?

New members start in "pending" status and must be approved by an admin. Ask a household admin to review and approve your membership.

### Can I change my display name?

Not directly. Contact an admin to remove and re-add you with a new name.

## Chores

### How do I create a new chore?

Use natural language: `Create chore "{title}" {recurrence}`. Example: `Create chore "Take out trash" every 3 days`. See [Household Chores Guide](./chores.md) for details.

### What's the difference between household and personal chores?

**Household chores:**
- Shared responsibilities
- Visible to all members
- Require peer verification
- Appear on leaderboard

**Personal chores:**
- Private tasks (only you see)
- Self-verified or optional partner
- Not on leaderboard
- Use `/personal` prefix

See [Personal Chores Guide](./personal-chores.md) for more.

### Can I assign a chore to someone specific?

Yes: `Create chore "{title}" assigned to {name}`. Example: `Create chore "Feed cat" every morning assigned to Alex`.

### What happens if a chore is assigned to no one?

Any household member can claim and complete unassigned chores.

### Can I create one-time (non-recurring) chores?

Use `by {day}` for household chores or just specify without recurrence. For personal chores, `/personal add "{task}" by {day}` creates a one-time task.

### What if I complete someone else's assigned chore?

This is called the Robin Hood Protocol. If you log a completion for someone else's chore, points are awarded based on timing:
- **On-time completion:** Points go to original assignee
- **Overdue completion:** Points go to person who actually completed it

Weekly limit: 3 takeovers per person.

## Verification

### Why do I need verification?

Verification ensures accountability - chores must actually be done to earn points. It's a peer review system that maintains fairness.

### Can I verify my own chore?

No, you cannot verify your own completions. Ask another household member to verify.

### What if my verification is rejected?

The chore returns to TODO state. Review the rejection reason, complete the chore properly, and log it again.

### How long do verifications take?

There's no time limit, but completions can't be verified by yourself. Prompt household members to review pending verifications.

### What if no one verifies my chore?

Remind household members to check pending verifications. For personal chores with partners, auto-verification occurs after 48 hours.

## Shopping & Pantry

### How do I add items to the shopping list?

Use natural language: `Add {item} to the list`. Example: `Add milk to the list`. Include quantities: `Add 6 eggs to the list`.

### How do I indicate I bought everything?

Send `I bought the list` or `Just finished shopping`. This clears the list and updates pantry inventory.

### What if I mark an item as out of stock?

It's automatically added to the shopping list. Example: `We're out of milk` marks it out AND adds it to the list.

### Can I see what's running low?

Send `What do we need?` or `Pantry status` to see items that are low or out of stock.

## Analytics & Leaderboard

### When do I get the weekly report?

Automated weekly reports are sent every Sunday at 8pm. They show the top 3 performers and your ranking.

### How is the leaderboard calculated?

Based on verified chore completions in the time period. Pending verifications don't count until approved.

### What do the performance titles mean?

Based on your completion count:
- **The Machine** 🏆: 10+ completions (outstanding)
- **Solid Contributor** 💪: 5-9 completions (strong)
- **Getting Started** 👍: 1-4 completions (engaged)
- **The Observer** 😴: 0 completions (not started yet)

### Can I see stats for longer than a week?

Yes: `Stats this month` or specify days: `Stats for 14 days`. Default is weekly (7 days).

### Do personal chores affect my ranking?

No, personal chores are completely private and never appear on the household leaderboard.

## Troubleshooting

### "No household chore found matching '{chore_name}'"

- Check spelling and exact chore name
- Try partial match (e.g., "dish" instead of "dishes")
- Create the chore if it doesn't exist
- Check if you meant a personal chore (use `/personal done`)

### "You cannot verify your own chore claim"

This is intentional design. Ask another household member to verify your completion.

### "Invalid password" when joining

- Check with admin for exact password
- Passwords are case-sensitive
- Spaces matter - copy carefully

### "Session expired" during join

The join process times out if you wait too long between steps. Start over with `/house join {house_name}`.

### Bot isn't responding to my messages

1. Check your user status is "active" (not "pending" or "banned")
2. Verify you're using the correct WhatsApp number
3. Check for error messages in the chat
4. Contact an admin if issues persist

### I'm not receiving notifications

- Check WhatsApp notifications are enabled
- Ensure the bot number isn't blocked
- Verify you're using the correct phone number in the system

## Advanced

### What's the weekly takeover limit?

Each person can participate in 3 Robin Hood takeovers per week (either as the helper or the original assignee). This prevents gaming the system.

### Can I export my data?

Not currently. All data is stored in the household's PocketBase database. Contact an admin for access.

### Is my data private?

- **Personal chores:** Completely private - only you see them
- **Personal chore verification:** Partner only sees verification requests, not stats or lists
- **Household chores:** Visible to all members (intentional for transparency)
- **Analytics:** Personal stats are private; leaderboards are shared

### Can I customize my notification schedule?

Not currently. Weekly reports are Sunday 8pm, daily reports 9pm, overdue reminders 8am. Contact an admin if adjustments are needed.

### What if I forget a command?

The bot understands natural language. Just describe what you want in plain English. Examples:
- Instead of remembering commands, say: "I need to add eggs to the list"
- Instead of `/personal done gym`, say: "I finished my gym workout"
- Instead of `/personal list`, say: "Show me my personal tasks"

## Privacy & Security

### Can other members see my personal chores?

No, personal chores are completely private. Only you can see your personal chore list and stats.

### What can my accountability partner see?

Your accountability partner can only:
- Receive verification requests for your completions
- Approve or reject those requests

They **cannot** see:
- Your personal chore list
- Your personal stats
- Your other personal chore logs

### Is my WhatsApp data stored?

The bot stores your phone number, name, chore completions, and other household data in the household's private PocketBase database. Your WhatsApp messages are processed by the AI but not stored permanently.

### Can I leave a household?

Contact a household admin to remove your account. All your data will be archived but you won't be able to access it after removal.

## Getting Help

### Where can I find more detailed guides?

See the full [User Guide](./index.md) with detailed documentation for all features:
- [Getting Started](./onboarding.md)
- [Household Chores](./chores.md)
- [Personal Chores](./personal-chores.md)
- [Pantry & Shopping](./pantry.md)
- [Analytics & Stats](./analytics.md)
- [Verification System](./verification.md)

### Who do I contact for technical issues?

For account issues, contact your household admin. For technical bugs, see the [Contributors Guide](../contributors/index.md) or open an issue in the project repository.

### Can I suggest features?

Feature suggestions are welcome! Contact your household admin or contribute to the open-source project.

## Best Practices

### Tips for Success

1. **Be specific with chore names** - Use exact titles to avoid confusion
2. **Log completions promptly** - Don't wait until bedtime
3. **Verify teammates' work** - Help keep the system flowing
4. **Check stats regularly** - Stay aware of your performance
5. **Use personal chores wisely** - Track private goals separately
6. **Keep the shopping list current** - Add items as soon as you notice need
7. **Communicate openly** - Discuss issues constructively with household members

### Common Mistakes to Avoid

1. **Not verifying** - Leaving completions pending hurts the leaderboard
2. **Vague chore names** - "Clean kitchen" is better than "Clean" (which kitchen?)
3. **Ignoring overdue tasks** - Address them promptly or ask for help
4. **Forgetting the `/personal` prefix** - Logs household chore instead of personal task
5. **Not checking status** - Review your pending tasks and verifications regularly

### Encouraging Household Culture

- **Celebrate wins** - Acknowledge teammates' contributions
- **Be fair with verification** - Approve reasonable completions
- **Help with overdue tasks** - Use Robin Hood Protocol appropriately
- **Communicate expectations** - Agree on chore standards together
- **Stay positive** - The system works best with constructive communication
