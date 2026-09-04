# Workflows Autônomos (`leai workflow`)

Workflows são procedimentos multi-etapas predefinidos que orquestram tarefas complexas de ponta a ponta, gerando relatórios de engenharia completos e patches de migração.

---

## ⚡ Comandos do Grupo `workflow`

### 1. `leai workflow list`
Lista os workflows registrados no sistema com seus aliases e descrições.

```bash
leai workflow list
```

---

### 2. `leai workflow run <NAME> <TARGET>`
Executa um fluxo de trabalho orquestrado sobre um objeto de banco específico.

| Parâmetro / Flag | Tipo | Obrigatório | Descrição |
| :--- | :--- | :--- | :--- |
| `NAME` | Argumento | Sim | Nome ou alias do workflow (ex: `impact-analysis`, `safe-refactor`). |
| `TARGET` | Argumento | Sim | Nome do objeto alvo da execução (ex: tabela ou procedure). |
| `-c`, `--config PATH` | Opção | Não | Caminho para `leai.yml`. |
| `-p`, `--provider TEXT` | Opção | Não | Sobrescreve o provedor de IA. |
| `-o`, `--output PATH` | Opção | Não | Caminho do arquivo para salvar o relatório final gerado. |

---

## 🚀 Workflows Nativos

### 1. `impact-analysis` (Alias: `impact`)
Orquestra uma investigação completa de dependências antes de refatorar uma entidade:
1. **Inspeção de Linhagem:** Rastreia todos os objetos dependentes upstream e downstream.
2. **Avaliação de Risco:** Calcula métricas de impacto e severidade de quebra.
3. **Análise Semântica:** Inspeciona o código fonte dos dependentes downstream para verificar como o objeto alvo é consumido.
4. **Relatório Consolidado:** Gera um dossiê em Markdown com sumário executivo, diagramas Mermaid e recomendações de mitigação.

```bash
leai workflow run impact TB_CLIENTES --output ./relatorio_impacto_clientes.md
```

---

### 2. `safe-refactor` (Alias: `refactor`)
Planeja e elabora uma refatoração assistida para procedimentos e tabelas:
1. Analisa a estrutura e constraints do objeto atual.
2. Identifica todos os pontos de consumo afetados.
3. Propõe o plano de migração em fases (zero-downtime / expand-contract).
4. Gera os scripts DDL de aplicação e os scripts de rollback correspondentes.

```bash
leai workflow run refactor PKG_FATURAMENTO -p claude
```
