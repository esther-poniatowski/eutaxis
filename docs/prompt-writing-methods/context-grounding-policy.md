# Context and grounding policy

Modern prompt engineering is increasingly framed as **context engineering**: curating the right tokens, references, and state.

## Grounding policy for external content

For any agent that processes _external content_ — documents, tool outputs, retrieved data — the system prompt must include an explicit grounding policy specifying how the model should treat its inputs:

- **Source types**: what reference material the model may use
- **Trusted versus untrusted context**: delimiting external content with structural tags and instructing the model that content within those tags constitutes data rather than instructions
- **Citation requirements**: whether the model must quote or cite source context
- **Retrieval priority**: how retrieved context is prioritized when multiple sources are available
- **Missing-information behavior**: what to do when sources are incomplete
- **Conflict resolution across sources**: how to handle contradictions between sources
- **Injection detection policy**: specifying the response when injected instructions appear inside external content

## Tool usage

For agentic systems with tool use, the reasoning schema must additionally specify (across all regimes):

- **Pre-conditions** for invoking each tool (when, not just how)
- **Post-conditions** the model must verify before proceeding
- **Abort criteria** — conditions under which the agent should stop the current task, _what_ it should emit (a structured failure report, not merely a halt), and _to whom_ (the downstream consumer may be a controller agent, not a human). Silent halting is rarely the correct response; the abort specification must define the failure signal's format and recipient.

The agent's effective instruction set should include:

- tool descriptions,
- parameter schemas
- example usage,
- tool-choice policies

> [!NOTE]
> The detailed design of tool contracts is outside the scope of this note, but the instruction file must reference them coherently and avoid duplicating constraints that are better enforced at the schema level.