# Glossário e Regras Canônicas (`leai rule`)

Em bancos de dados corporativos, regras de negócio frequentemente dependem de convenções informais ou filtros SQL específicos (ex: `WHERE STATUS = 'A' AND FL_EXCLUIDO = 'N'`).

O grupo de comandos `leai rule` permite documentar, auditar e injetar essas regras e filtros canônicos de negócio diretamente no contexto semântico das LLMs e dos subagentes do LEAI.

---

## ⚡ Comandos do Grupo `rule`

### 1. `leai rule list`
Lista todas as regras de negócio e termos do glossário cadastrados no projeto.

```bash
leai rule list
```

---

### 2. `leai rule add <TERM>`
Cadastra ou atualiza uma regra de negócio ou definição canônica de domínio.

| Parâmetro / Flag | Tipo | Obrigatório | Descrição |
| :--- | :--- | :--- | :--- |
| `TERM` | Argumento | Sim | Nome ou identificador do termo de negócio (ex: `CLIENTE_ATIVO`). |
| `--definition` | Opção | Não | Definição textual da regra de negócio. |
| `--table` | Opção | Não | Tabela do banco de dados associada à regra. |
| `--canonical-filter` | Opção | Não | Cláusula SQL canônica exata (ex: `STATUS = 'A'`). |
| `--tags` | Opção | Não | Tags e categorias separadas por vírgula (ex: `vendas,faturamento`). |
| `-c`, `--config PATH` | Opção | Não | Caminho para o `leai.yml`. |

#### Exemplo de Cadastro:
```bash
leai rule add "CLIENTE_ATIVO" \
  --table "TB_CLIENTES" \
  --canonical-filter "ST_CADASTRO = 'A' AND FL_BLOQUEADO = 0" \
  --definition "Clientes habilitados a realizar novos pedidos e emissão de notas" \
  --tags "comercial,compliance"
```

---

### 3. `leai rule del <TERM>` (ou `delete`)
Remove um termo ou regra do glossário local e do bucket SeaweedFS.

```bash
leai rule del CLIENTE_ATIVO
```

---

### 4. `leai rule show <TERM>`
Exibe a ficha completa de uma regra de negócio cadastrada, incluindo tabela associada, filtro SQL canônico e metadados.

```bash
leai rule show CLIENTE_ATIVO
```

---

## ☁️ Sincronização Contínua com SeaweedFS (S3)

Se o SeaweedFS estiver configurado no `leai.yml` (ou com a flag `-W` / `--seaweed`), o glossário corporativo é automaticamente gerenciado na nuvem:

- **Persistência Imediata**: Toda inclusão (`leai rule add`) ou exclusão (`leai rule del`) salva no arquivo local e envia para a chave `annotations/glossary.yml` no bucket S3.
- **Pipelines Automáticos (`annotate` e `update`)**: Os comandos `leai annotate` e `leai update` realizam a **mesclagem não destrutiva** entre o glossário local e o remoto. Se houver divergências de definição para um mesmo termo, a definição do SeaweedFS é priorizada para proteger o conhecimento institucional, unificando tags e exemplos.
- **Modo Desconectado / `--no-cache`**: A IA no terminal e os subagentes carregam o glossário diretamente do SeaweedFS se o arquivo local não existir.

---

## 💻 Comandos no Terminal Interativo (TUI Copilot)

Durante a sessão interativa (`leai chat`), você pode gerenciar o glossário sem sair do console:

| Comando | Descrição |
| :--- | :--- |
| `/rule list` | Exibe tabela visual formatada com todos os termos e regras cadastrados. |
| `/rule add [termo]` | Formulário guiado com prompts interativos para cadastrar termo, definição, tabela e filtro SQL. |
| `/rule del <termo>` | Remove o termo especificado do glossário local e do bucket SeaweedFS. |
| `/rule find <termo>` | Busca termos no glossário por relevância e similaridade semântica. |

---

## 🎯 Como as Regras Potencializam o RAG e a IA

Quando você utiliza `leai ask` ou `leai chat`, o assistente consulta o repositório de regras antes de gerar consultas SQL ou responder perguntas de negócio.

* **Exemplo de Pergunta do Usuário:** *"Quantos clientes ativos temos cadastrados?"*
* **Ação do Agente:** Em vez de fazer `SELECT COUNT(*) FROM TB_CLIENTES` ou chutar filtros, o modelo invoca a ferramenta de regras e recupera o filtro oficial `ST_CADASTRO = 'A' AND FL_BLOQUEADO = 0`.
