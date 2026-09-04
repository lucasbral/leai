# Autonomous Agent & In-Memory Tools

LEAI features an autonomous reasoning engine based on the **ReAct (Reason + Act)** paradigm via its `AgentExecutionEngine`. Instead of guessing database structures or overwhelming prompt windows, the agent actively inspects catalog metadata in real time.

---

## 🔄 How the Execution Loop Operates

```mermaid
sequenceDiagram
    autonumber
    actor Dev as User / Engineer
    participant Agent as LEAI Agent Loop
    participant Tools as In-Memory Database Tools
    participant LLM as Language Model (LLM)

    Dev->>Agent: "Which procedures update customer status to INACTIVE?"
    Agent->>LLM: Evaluate intent & pick tool
    LLM-->>Agent: Invoke search_database_objects(query='INACTIVE')
    Agent->>Tools: search_database_objects
    Tools-->>Agent: Matches: PROC_DEACTIVATE_CUST, TRG_STATUS_AUDIT
    Agent->>LLM: Evaluate tool output
    LLM-->>Agent: Invoke view_object_definition(object='PROC_DEACTIVATE_CUST')
    Agent->>Tools: view_object_definition (with semantic compression)
    Tools-->>Agent: Returns procedure body
    Agent->>LLM: Synthesize final answer
    LLM-->>Dev: Verified answer with authentic code, rules, and impact
```

The agent runs with a configurable safety guard of up to 10 reasoning cycles per turn to prevent infinite loops.

---

## 🛠️ Available Agent Tools

| Tool | Parameters | Purpose |
| :--- | :--- | :--- |
| **`search_database_objects`** | `query`, `object_type` | Global catalog search across tables, views, procedures, packages, and synonyms. |
| **`view_object_definition`** | `schema`, `object_name` | Retrieves technical DDL or PL/SQL body with surgical semantic compression. |
| **`trace_object_lineage`** | `object_name`, `depth` | Computes upstream dependencies and downstream impact with risk scoring. |
| **`get_glossary_terms`** | `term` | Queries domain glossary concepts defined by the engineering team. |

---

## 💡 Benefits of Offline Tool-Calling

1. **Zero Access to Live Data:** Tools query the extracted metadata snapshot, ensuring data privacy and enterprise compliance.
2. **Eliminates Hallucinations:** The model confirms facts by reading verified DDLs and code before forming its response.
3. **Token Efficiency:** Only relevant subprograms and table definitions enter the prompt window.
