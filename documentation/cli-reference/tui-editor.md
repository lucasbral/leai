# Editor Interativo de Documentação no Terminal (`leai doc`)

O comando `leai doc` disponibiliza uma **interface rica no terminal (TUI - Terminal User Interface)** desenvolvida com `prompt_toolkit` e `rich`. Ele permite que engenheiros e DBAs documentem esquemas, colunas e regras de negócio sem sair da linha de comando e sem precisar editar arquivos YAML manualmente.

---

## ⚡ Como Iniciar o Editor TUI

Você pode abrir o editor de duas maneiras:

### Modo 1: Catálogo Interativo Geral
```bash
leai doc
```
Lista todos os objetos do banco em uma tabela paginada com indicador visual de completude da documentação.

### Modo 2: Abertura Direta de um Objeto
```bash
leai doc TB_CLIENTES
# ou com schema explícito:
leai doc FINANCEIRO.PKG_FOLHA_PAGTO
```

Também é possível acionar dentro do chat interativo (`leai chat`):
```text
/doc TB_CLIENTES
```

---

## 📋 O Catálogo Paginado de Objetos

Ao executar `leai doc` sem argumentos, o LEAI apresenta o catálogo completo:

```text
✦ Database Objects Catalog (142 objects) • Page 1/12
┌────┬────────────┬─────────┬──────────────────────┬──────────────────────┬──────────────────┐
│  # │ Schema     │ Type    │ Object Name          │ Technical Details    │ Doc Status       │
├────┼────────────┼─────────┼──────────────────────┼──────────────────────┼──────────────────┤
│  1 │ FINANCEIRO │ TABLE   │ TB_CONTRATOS         │ 18 cols (PK: ID)     │ ██████████ 100%  │
│  2 │ FINANCEIRO │ TABLE   │ TB_LANCAMENTOS       │ 12 cols (PK: ID)     │ ████░░░░░░  40%  │
│  3 │ RH         │ PACKAGE │ PKG_FOLHA_PAGTO      │ 14 routines          │ ░░░░░░░░░░   0%  │
└────┴────────────┴─────────┴──────────────────────┴──────────────────────┴──────────────────┘
```

### Navegação no Catálogo:
* **Digitar o número (`1`, `2`, ...):** Abre imediatamente o editor para aquele objeto.
* **Digitar o nome do objeto (`TB_CONTRATOS`):** Localiza e abre diretamente.
* **Navegar páginas:** Digite `n` (*próxima página*) ou `p` (*página anterior*).
* **Filtros rápidos de busca:**
  * Digite `pending` ou `pendente`: lista apenas objetos com 0% documentados.
  * Digite `partial` ou `parcial`: lista objetos parcialmente documentados.
  * Digite `done`: lista objetos 100% concluídos.
  * Digite qualquer texto (ex: `rh`, `cliente`): filtra por nome ou schema.
* **Sair:** Digite `0` ou `q`.

---

## 📊 Cálculo de Completude da Documentação

Para cada entidade, o LEAI calcula automaticamente uma pontuação de 0 a 100%:

| Critério | Peso | Descrição |
| :--- | :--- | :--- |
| **Descrição Principal** | **35%** | Explicação textual do propósito funcional da tabela ou pacote. |
| **Colunas / Rotinas** | **35%** | Proporção de colunas com comentários preenchidos. |
| **Regras de Negócio** | **20%** | Pelo menos uma regra de negócio cadastrada em tópicos. |
| **Tags / Domínio** | **10%** | Classificação de domínio funcional (ex: `faturamento`, `lgpd`). |

---

## 🛠️ Menu Principal do Formulário Interativo

Ao selecionar um objeto, o painel do editor é exibido com detalhes técnicos do Oracle (Chaves Primárias, Estrangeiras, `LAST_DDL_TIME`):

```text
✦ LEAI Documentation Studio • FINANCEIRO.TB_CONTRATOS [TABLE]
┌──────────────────┬────────────────────────────────────────────────────────┐
│ Context Badges   │ SCHEMA: FINANCEIRO   TYPE: TABLE   OBJECT: TB_CONTRATOS │
│ Doc Completeness │ ██████████ 100%                                        │
│ Primary Keys     │ ID_CONTRATO                                            │
│ Foreign Keys     │ 2 FK constraints                                       │
│ Description      │ Tabela principal de custódia e vigência de contratos   │
│ Columns Done     │ 18 / 18                                                │
│ Business Rules   │ 3 rules registered                                     │
│ Tags / Domain    │ comercial, compliance                                  │
└──────────────────┴────────────────────────────────────────────────────────┘

Select an action to edit:
  1 • 📝 Edit Main Object Description
  2 • 📊 Edit Column / Routine Comments
  3 • 📌 Edit Business Rules (Bullet Points)
  4 • 🏷️  Edit Tags & Functional Domain
  5 • ⚠️  Edit Technical Warnings / Alerts
  6 • 🔗 Edit Related Objects Lineage
  7 • 💾 Preview YAML & Save Changes
  0 • ❌ Cancel & Back
```

---

## ⌨️ Fluxo de Edição Seção por Seção

### 1. Descrição do Objeto (`Opção 1`)
Abre um prompt de texto multilinhas com a descrição atual pré-carregada para ajuste rápido.

### 2. Comentários de Colunas (`Opção 2`)
Apresenta uma lista numerada de todas as colunas com status visual:
* `[green]✓[/green]`: Coluna já documentada.
* `[red]✕[/red]`: Coluna pendente de documentação.
* Digite o número da coluna para inserir ou atualizar seu comentário funcional.

### 3. Regras de Negócio em Tópicos (`Opção 3`)
Permite gerenciar as regras de negócio em formato de bullet points:
* Digite `a` para adicionar uma nova regra.
* Digite o número de uma regra existente para editá-la ou excluí-la.

### 4. Tags e Domínio (`Opção 4`)
Insira tags separadas por vírgula para categorização semântica (ex: `fiscal, folha, lgpd`).

---

## ⚡ Salvamento e Recompilação Instantânea em 1 Tecla

Ao selecionar a **Opção 7** (ou digitar `s` / `save`):

1. **Gravação Não-Destrutiva no Disco Local:** O LEAI persiste imediatamente o arquivo YAML em `./annotations/<SCHEMA>/tables/<OBJETO>.yml`, permitindo validação e versionamento local seguro antes de qualquer sincronização com o storage ou repositório Git.
2. **Preview com Syntax Highlighting:** O conteúdo atualizado do YAML é exibido no terminal.
3. **Recompilação sob Demanda:** O terminal pergunta automaticamente:
   ```text
   Recompile Markdown doc for TB_CONTRATOS now? [Y/n]:
   ```
   Ao pressionar **`Enter`** ou digitar **`y`**, o LEAI compila **imediatamente apenas aquele documento Markdown específico** (`./docs/<SCHEMA>/tables/TB_CONTRATOS.md`), atualizando o frontmatter, diagramas Mermaid e tabelas de colunas em menos de 1 segundo!
