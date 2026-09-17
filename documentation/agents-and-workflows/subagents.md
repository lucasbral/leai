# Subagentes Especializados (`leai agent`)

O LEAI introduz uma arquitetura de **Subagentes Especializados**, onde tarefas complexas de banco de dados não são tratadas por um prompt genérico, mas delegadas a personas técnicas isoladas com permissões estritas de ferramentas.

---

## ⚡ Comandos do Grupo `agent`

### 1. `leai agent list`
Lista todos os subagentes registrados, seus papéis, descrições e ferramentas permitidas.

```bash
leai agent list
```

---

### 2. `leai agent run <ROLE> <TASK>`
Executa um subagente específico em um contexto limpo e isolado com streaming de raciocínio no terminal.

| Parâmetro / Flag | Tipo | Obrigatório | Descrição |
| :--- | :--- | :--- | :--- |
| `ROLE` | Argumento | Sim | Identificador do especialista (ex: `plsql_analyst`, `lineage_auditor`). |
| `TASK` | Argumento | Sim | Descrição clara da tarefa, dúvida ou objetivo a ser executado. |
| `-c`, `--config PATH` | Opção | Não | Caminho para o arquivo `leai.yml` (Padrão: `leai.yml`). |
| `-p`, `--provider TEXT` | Opção | Não | Sobrescreve o provedor de IA ativo. |
| `-m`, `--model TEXT` | Opção | Não | Sobrescreve o modelo de IA específico. |

#### Exemplos de Uso:

```bash
# Análise profunda de um procedimento PL/SQL
leai agent run plsql_analyst "Explique como funciona o cálculo de juros na package PKG_FINANCEIRO"

# Auditoria de linhagem antes de alterar uma tabela
leai agent run lineage_auditor "Quais objetos downstream quebram se a coluna SALDO for renomeada na tabela TB_CONTA?"

# Gerar script de migração e patch seguro
leai agent run patch_generator "Gere um script DDL seguro para adicionar a coluna DT_ATUALIZACAO na tabela TB_CLIENTES"
```

---

## 👥 Especialistas Disponíveis

| Papel / ID | Nome do Especialista | Descrição e Foco de Atuação | Ferramentas Permitidas |
| :--- | :--- | :--- | :--- |
| **`catalog_researcher`** | Pesquisador de Catálogo | Especialista em exploração de esquemas, localização de tabelas, colunas, sinônimos e constraints. | `get_table_schema`, `search_catalog`, `lookup_business_term` |
| **`plsql_analyst`** | Analista de PL/SQL | Análise estática, reversão e interpretação de rotinas PL/SQL, diagnósticos de sargabilidade, compatibilidade Oracle e tuning de SQL. | `get_subprogram_source`, `grep_plsql_code`, `get_table_schema`, `explain_and_tune_sql`, `validate_oracle_sql` |
| **`lineage_auditor`** | Auditor de Linhagem e Impacto | Avaliação de impacto em cascata, cálculo de score de risco e grafo de dependências para migrações. | `trace_object_lineage`, `search_catalog`, `get_table_schema` |
| **`patch_generator`** | Engenheiro de Refatoração e Patches | Formulação de scripts DDL com validação de compatibilidade Oracle, migrações seguras e scripts de rollback. | `get_table_schema`, `get_subprogram_source`, `grep_plsql_code`, `validate_oracle_sql`, `explain_and_tune_sql` |
| **`doc_annotator`** | Especialista em Documentação | Elaboração de documentações de negócio e glossários técnicos alinhados com o domínio. | `get_table_schema`, `get_subprogram_source`, `lookup_business_term` |
