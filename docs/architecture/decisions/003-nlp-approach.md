# ADR 003: Natural Language Processing Approach

## Status

Accepted

## Context

The application requires natural language processing to interpret conversational commands from users via WhatsApp for home service booking. Users should be able to interact naturally rather than using rigid command structures.

Key evaluation criteria included:
- Ease of integration with existing Python stack
- Model flexibility and cost optimization
- Development velocity and testing capabilities
- Maintenance burden and complexity
- Per-request cost and scalability
- Internet connectivity requirements

## Decision

We will use **Pydantic AI with OpenRouter** for conversational command processing.

## Rationale

### Model Flexibility
- OpenRouter provides access to multiple LLM providers through a single API
- Enables switching between models (Claude, GPT-4, Gemini, etc.) without code changes
- Can optimize for cost/performance based on actual usage patterns
- Not locked into a single vendor's pricing or availability

### Task Simplicity
- Command interpretation is a relatively simple NLP task
- Does not require the most powerful (expensive) models
- Can use faster, cheaper models (e.g., GPT-3.5-turbo, Claude Haiku) effectively
- Conversation context is short (single-turn or few-turn interactions)

### Development Experience
- Pydantic AI provides type-safe, structured output from LLMs
- Natural integration with existing Pydantic models in the codebase
- Built-in validation and error handling
- Easy to test with deterministic outputs
- Excellent Python developer experience

### Cost Optimization
- Pay-per-request model aligns with actual usage
- No fixed infrastructure costs for model hosting
- Can start with cheapest viable model and upgrade if needed
- OpenRouter's aggregation provides competitive pricing

### Time-to-Market
- No model training or fine-tuning required
- Well-documented integration paths
- Minimal setup complexity
- Can iterate quickly on prompt engineering

## Consequences

### Positive
- Rapid development and deployment
- Type-safe structured outputs reduce runtime errors
- Easy to test and validate command parsing
- Can optimize model selection based on real usage data
- Lower barrier to adding new command types
- No infrastructure to manage for model serving

### Negative
- **External API dependency**: Requires internet connectivity for all NLP operations
- **Per-request cost**: Variable costs based on usage volume (though aligned with revenue)
- **Latency**: Network round-trip adds 100-500ms per request
- **Rate limits**: Subject to OpenRouter and upstream provider limits
- **Model availability**: Dependent on third-party uptime

### Neutral
- Prompt engineering required for accuracy (true for all LLM approaches)
- Need to handle API failures gracefully
- Conversation context management still required

## Alternatives Considered

### Self-hosted Local Models
**Rejected** due to:
- Significant infrastructure overhead (GPU requirements)
- Fixed costs regardless of usage
- Model maintenance and updates burden
- Longer time-to-market
- Unnecessary complexity for simple command parsing
- Cost-prohibitive at low volumes

### Single Provider API (e.g., OpenAI, Anthropic)
**Rejected** due to:
- Vendor lock-in for pricing and availability
- Less flexibility to optimize cost/performance
- Similar external dependency without the provider flexibility
- OpenRouter provides same models with added flexibility

### Rule-based NLU (e.g., spaCy + Intent Classification)
**Rejected** due to:
- Requires training data collection and labeling
- Brittle to natural language variation
- Higher maintenance burden as command types grow
- Longer development cycle
- Less adaptable to new command patterns

## Implementation Notes

### Typical Flow
1. User sends WhatsApp message
2. Message forwarded to Pydantic AI endpoint
3. Structured command extracted via OpenRouter
4. Validated against Pydantic schema
5. Execute booking/query logic

### Model Selection Guidelines
- Start with cost-effective models (Claude Haiku, GPT-3.5-turbo)
- Monitor accuracy and latency metrics
- Upgrade to more capable models only if needed
- Use model routing for different command complexities

### Error Handling
- Graceful fallback for API failures
- User-friendly error messages for parsing failures
- Logging for prompt refinement
- Retry logic for transient failures

## Future Considerations

- Monitor per-request costs and optimize model selection
- Consider caching for common command patterns
- Evaluate adding local fallback for critical commands if uptime becomes an issue
- May fine-tune a smaller model if command patterns stabilize and volume justifies it
- Track user satisfaction to validate model quality

## Related ADRs

- [ADR 001: WhatsApp Provider Selection](001-whatsapp-provider.md) - Defines the messaging platform where NLP processes user inputs
- [ADR 005: Robin Hood Protocol](005-robin-hood-protocol.md) - Feature that requires NLP to interpret chore takeover commands

## References

- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [OpenRouter API Documentation](https://openrouter.ai/docs)
- PM Decision: Documented in AUDIT_PM_DECISIONS.md
