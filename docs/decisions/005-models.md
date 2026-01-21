ADR 005: Model Selection via OpenRouter

Status: Accepted Date: 2026-01-14 Context: We need an LLM capable of complex Function Calling (selecting the right tool and formatting JSON arguments correctly). We also want to avoid vendor lock-in to OpenAI.

Decision: We will use OpenRouter as the gateway, defaulting to Claude 3.5 Sonnet.

    Claude 3.5 Sonnet is currently the state-of-the-art for coding and instruction following, outperforming GPT-4o in strict JSON schema adherence.

    OpenRouter allows us to switch to Llama 3 or GPT-4o by changing a single environment variable MODEL_ID without rewriting code.

Consequences:

    Positive: High intelligence for complex parsing; flexibility.

    Negative: Added latency compared to a direct API call (minimal).
