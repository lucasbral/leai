# Utilitários, Diagnóstico e Governança

Esta seção cobre comandos essenciais para diagnóstico de ambiente, inicialização de workspaces e auditoria de alterações no banco de dados.

---

## 1. `leai init`

Inicializa um diretório de trabalho criando o arquivo de modelo `leai.yml`.

```bash
leai init
# Gerar exemplo completo totalmente documentado:
leai init --example
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-f`, `--force` | Flag | `False` | Sobrescreve `leai.yml` existente sem confirmação prévia. |
| `-e`, `--example` | Flag | `False` | Gera o arquivo `leai.example.yml` com exemplos detalhados de todos os recursos. |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho do arquivo de configuração a ser gerado. |

---

## 2. `leai doctor` (ou `leai check`)

Executa uma bateria preventiva de testes automatizados para garantir a integridade do ambiente.

```bash
leai doctor
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho para o `leai.yml`. |

### O que o `doctor` valida:
* **Conectividade:** Estabelece conexão com o listener do Oracle Database.
* **Permissões de Catálogo:** Valida acesso de leitura em `ALL_TABLES`, `ALL_TAB_COLUMNS`, `ALL_CONSTRAINTS`, `ALL_SOURCE` e `ALL_SYNONYMS`.
* **Diretórios do Pipeline:** Verifica existência e permissão de escrita em `rawPath`, `annotationsPath` e `docPath`.
* **Armazenamento S3:** Testa conectividade e bucket do SeaweedFS caso configurado.
* **Modelos de IA:** Verifica se as chaves de API estão configuradas e operacionais.

---

## 3. `leai changes`

Analisa e lista objetos do banco criados ou modificados recentemente através da coluna `LAST_DDL_TIME` do dicionário de dados da Oracle.

```bash
leai changes --days 15
leai changes --days 30 -u HR
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-d`, `--days INT` | Opção | `7` | Quantidade de dias anteriores a auditar. |
| `-u`, `--user TEXT` | Opção | `None` | Filtra por usuário ou schema Oracle específico. |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho para o arquivo `leai.yml`. |
| `--seaweed` | Flag | `False` | Compara snapshots persistidos no bucket S3. |
| `--no-cache` | Flag | `False` | Não grava snapshots no disco local. |
