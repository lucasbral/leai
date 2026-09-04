# AI Commands (ask, chat, models)

LEAI transforms your Oracle database catalog into an interactive knowledge base capable of answering complex engineering and business logic questions directly from your shell.

---

## 1. `leai ask <QUESTION>`

Answers one-off natural language queries about your database architecture, tables, procedures, and business rules.

```bash
leai ask "What is the business rule inside CALC_TERMINATION and which tables does it read?"
```

### Internal Execution Flow:
1. LEAI parses entities and technical keywords mentioned in the user prompt.
2. Dynamically fetches upstream/downstream lineage and definitions.
3. Applies PL/SQL semantic compression on large package bodies to conserve context tokens.
4. Delivers the surgical payload to the active LLM and formats the answer with rich markdown highlighting.

---

## 2. `leai chat`

Launches an interactive, stateful terminal console with the autonomous database copilot.

```bash
leai chat
```

### Key Capabilities:
* **Autonomous Tool-Calling:** The agent can independently invoke offline memory tools (`search_database_objects`, `view_object_definition`, `trace_object_lineage`) during reasoning turns before formulating its answer.
* **Session Memory:** Retains prior questions and context within the active terminal session.
* **Console Commands:**
  * `/help`: Displays available chat controls.
  * `/clear`: Clears conversation history.
  * `/exit` or `quit`: Terminates the session.

---

## 3. `leai models`

Lists all supported LLM providers, recommended models, and benchmarks API latency and credential health.

```bash
leai models
```

### Diagnostic Output:
Provides a status table highlighting:
* Provider names (OpenAI, Gemini, Claude, DeepSeek, Ollama, AWS Bedrock, etc.).
* API key detection status (`CONFIGURED` or `NOT DETECTED`).
* Real-time network latency in milliseconds.
