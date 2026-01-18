# ADR 001: WhatsApp Provider Selection

## Status

Accepted

## Context

The application requires WhatsApp messaging integration to communicate with users for home service booking notifications, confirmations, and updates. Two primary options were evaluated:

1. **Twilio Business API**: A managed service providing WhatsApp Business API integration
2. **Meta Cloud API**: Direct integration with Meta's WhatsApp Cloud API

Key evaluation criteria included:
- Time-to-market
- Developer experience and ease of integration
- Per-message costs
- Setup complexity
- Vendor lock-in considerations
- Feature set and API capabilities

## Decision

We will use **Twilio Business API** for WhatsApp messaging integration.

## Rationale

### Time-to-Market
- Twilio provides a significantly faster setup process with well-documented APIs and SDKs
- Production-ready in hours rather than days/weeks
- Immediate access to sandbox environments for development

### Developer Experience
- Comprehensive SDK support across multiple languages
- Excellent documentation with code examples
- Robust error handling and debugging tools
- Unified API for multiple communication channels (future-proofing)
- Active developer community and support

### Cost Considerations
- Higher per-message cost compared to Meta Cloud API
- Cost differential is acceptable given current scale
- Pricing is predictable and transparent
- No hidden infrastructure costs

### Setup Complexity
- Meta Cloud API requires:
  - Facebook Business Manager account setup
  - Business verification process (can take days/weeks)
  - Manual phone number registration
  - Complex webhook configuration
  - Message template approval workflows
- Twilio provides streamlined onboarding with minimal verification steps

## Consequences

### Positive
- Faster time-to-market enables earlier user feedback
- Better developer productivity through superior DX
- Reduced operational complexity
- Built-in monitoring and analytics
- Access to Twilio's other communication channels (SMS, Voice) if needed

### Negative
- **Higher per-message cost**: Approximately 2-3x more expensive than Meta Cloud API
- **Vendor dependency**: Switching providers would require integration rework
- **Cost scaling**: May need to revisit this decision at significant scale (100K+ messages/month)

### Neutral
- Template approval required for both providers
- Both comply with WhatsApp Business Policy
- Similar message delivery guarantees

## Alternatives Considered

### Meta Cloud API
**Rejected** due to:
- Significant setup complexity and longer time-to-market
- Business verification delays
- Steeper learning curve for development team
- Less mature documentation and tooling
- While cheaper per message, the cost savings don't justify the delayed launch and increased development complexity at current scale

## Future Considerations

- Monitor monthly message volumes and costs
- Re-evaluate if message volume exceeds 100,000/month where cost differential becomes material
- Consider multi-provider strategy if business-critical redundancy is needed
- Evaluate new WhatsApp providers as they emerge in the market

## Related ADRs

- [ADR 003: Natural Language Processing Approach](003-nlp-approach.md) - Defines how user messages received via WhatsApp are processed and interpreted
- [ADR 005: Robin Hood Protocol](005-robin-hood-protocol.md) - Describes the chore takeover feature that users interact with through WhatsApp

## References

- [Twilio WhatsApp API Documentation](https://www.twilio.com/docs/whatsapp)
- [Meta Cloud API Documentation](https://developers.facebook.com/docs/whatsapp/cloud-api)
- PM Decision: Documented in project management records
