# GitOps & Controle de Versão (`leai git`)

O LEAI possui comandos nativos de versionamento para tratar documentação de banco de dados como código (**Docs-as-Code**).

Com a integração com Git/GitLab/GitHub, qualquer alteração em anotações de negócio ou extrações de metadados pode ser sincronizada, auditada e versionada automaticamente.

---

## ⚡ Comandos do Grupo `git`

### 1. `leai git status`
Verifica o estado do repositório Git local em relação aos arquivos gerenciados pelo LEAI (`annotations/`, `docs/`, `raw/`, `leai.yml`).

```bash
leai git status
# ou buscando novidades remotas no upstream:
leai git status --fetch
```

---

### 2. `leai git pull`
Atualiza os arquivos locais com as últimas alterações de documentação enviadas por outros membros da equipe no repositório remoto.

```bash
leai git pull
```

---

### 3. `leai git sync`
Adiciona todas as anotações e documentos modificados ao stage, realiza o commit e envia o push para o branch remoto configurado.

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-m`, `--message TEXT` | Opção | Mensagem automática | Mensagem personalizada para o commit Git. |

```bash
leai git sync --message "docs(financeiro): adiciona regras da folha de pagamento"
```

---

## ⚙️ Configuração no `leai.yml`

```yaml
git:
  enabled: true                                  # Ativa os comandos leai git e slash command /git
  remote_url: "https://gitlab.empresa.com/docs/db-oracle.git"
  branch: "main"                                 # Branch de rastreamento
  author_name: "LEAI Bot"                        # Nome do autor para commits automáticos
  author_email: "leai-bot@empresa.com"           # E-mail do autor para commits automáticos
  auto_sync: false                               # Sincronização automática após extract/compile
  tracked_paths:                                 # Pastas gerenciadas pelo versionamento
    - "annotations"
    - "docs"
    - "raw"
    - "leai.yml"
```
