# Agente Autônomo e Ferramentas In-Memory

O LEAI incorpora um motor autônomo de raciocínio baseado no padrão **ReAct (Reason + Act)** através da classe `AgentExecutionEngine`. Em vez de tentar "adivinhar" estruturas de banco de dados ou depender de contexto estático, o agente investiga o catálogo em tempo real.

---

## 🔄 Como Funciona o Loop de Execução

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Usuário / Engenheiro
    participant Agent as LEAI Agent Loop
    participant Tools as Ferramentas In-Memory
    participant LLM as Modelo de Linguagem (LLM)

    Dev->>Agent: "Quais procedures alteram o status do cliente para INATIVO?"
    Agent->>LLM: Analisar intenção e selecionar ferramenta
    LLM-->>Agent: Chamar search_database_objects(query='INATIVO')
    Agent->>Tools: search_database_objects
    Tools-->>Agent: Encontradas: PROC_INATIVAR_CLI, TRG_STATUS_LOG
    Agent->>LLM: Avaliar resultados
    LLM-->>Agent: Chamar view_object_definition(object='PROC_INATIVAR_CLI')
    Agent->>Tools: view_object_definition (com compressão semântica)
    Tools-->>Agent: Retorna corpo da procedure
    Agent->>LLM: Sintetizar resposta final
    LLM-->>Dev: Resposta precisa com código, regras e dependências
```

O agente possui um limite de segurança de até 10 iterações por turno para evitar loops infinitos.

---

## 🛠️ Ferramentas Disponíveis ao Agente

| Ferramenta | Parâmetros | Finalidade |
| :--- | :--- | :--- |
| **`search_database_objects`** | `query`, `object_type` | Busca global no catálogo por tabelas, views, procedures, pacotes ou sinônimos. |
| **`view_object_definition`** | `schema`, `object_name` | Recupera a DDL ou código fonte com compressão semântica cirúrgica. |
| **`trace_object_lineage`** | `object_name`, `depth` | Executa análise de dependências upstream e downstream com avaliação de risco. |
| **`get_glossary_terms`** | `term` | Consulta o glossário de negócios e termos de domínio definidos pela equipe. |

---

## 💡 Vantagens do Raciocínio Offline com Ferramentas

1. **Sem Acesso Direto a Dados:** As ferramentas operam exclusivamente sobre o snapshot de metadados extraídos, garantindo conformidade com políticas de segurança de dados.
2. **Alta Fidelidade:** O modelo só responde após inspecionar o código fonte real de procedures e colunas, eliminando alucinações.
3. **Eficiência de Contexto:** Apenas as informações estritamente necessárias são carregadas na memória durante o diálogo.
