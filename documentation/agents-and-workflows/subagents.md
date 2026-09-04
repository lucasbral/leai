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
| **`catalog_researcher`** | Pesquisador de Catálogo | Especialista em exploração de esquemas, localização de tabelas, colunas, sinônimos e constraints. | `search_database_objects`, `view_object_definition`, `get_glossary_terms` |
| **`plsql_analyst`** | Analista de PL/SQL | Análise estática, reversão e interpretação cirúrgica de regras em procedures, packages e triggers com compressão de tokens. | `view_object_definition`, `search_database_objects` |
| **`lineage_auditor`** | Auditor de Linhagem e Impacto | Avaliação de impacto em cascata e cálculo de risco para migrações e alterações estruturais. | `trace_object_lineage`, `search_database_objects` |
| **`patch_generator`** | Engenheiro de Refatoração e Patches | Formulação de scripts DDL, migrações seguras e correções semânticas de código. | `view_object_definition`, `trace_object_lineage` |
| **`doc_annotator`** | Especialista em Documentação | Elaboração de documentações de negócio e glossários técnicos alinhados com o domínio. | `view_object_definition`, `get_glossary_terms` |
