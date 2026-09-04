# Configuração (`leai.yml`)

O arquivo de configuração `leai.yml` controla todos os aspectos de extração, filtragem, armazenamento e integração com IA do LEAI.

---

## 📄 Exemplo Completo Comentado

```yaml
# ==============================================================================
# Configuração do LEAI
# ==============================================================================

# 1. Conexão com o Oracle (DSN)
# Suporta interpolação de variáveis de ambiente com ${VARIAVEL}
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# 2. Schemas a Extrair
# Pode ser uma lista de schemas ou "ALL" (requer permissão de DBA/SELECT ANY DICTIONARY)
schemas:
  - RH
  - FINANCEIRO

# 3. Diretórios do Pipeline
rawPath: "./raw"                  # Snapshots técnicos em JSON
annotationsPath: "./annotations"  # Camada de anotações em YAML
docPath: "./docs"                  # Documentação final em Markdown

# 4. Filtros de Inclusão e Exclusão (Padrão SQL LIKE)
include:
  - FUNCIONARIOS
  - VENDAS_%
exclude:
  - BIN$%                         # Tabelas da lixeira do Oracle
  - SYS_%

# 5. Categorias de Objetos
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - triggers
  - synonyms

# 6. Configurações de IA (Opcional - para leai ask, leai chat e leai enrich)
ai:
  provider: "openai"              # openai | gemini | claude | deepseek | qwen | ollama
  model: "gpt-4o"
  temperature: 0.2
  max_iterations: 10              # Limite de voltas no loop autônomo de ferramentas
```

---

## 🔑 Formatos Suportados de DSN

O LEAI suporta diversas formas de declarar a string de conexão:

### Sintaxe de URL (Padrão)
```yaml
dsn: "oracle://usuario:senha@host:1521/nome_servico"
```

### Sintaxe EZCONNECT (Oracle)
```yaml
dsn: "usuario/senha@host:1521/nome_servico"
```

### TNS / Descriptor Completo (para TCPS, Wallets ou Oracle Cloud / Autonomous DB)
```yaml
dsn: "usuario/senha@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCPS)(HOST=db.exemplo.com)(PORT=1522))(CONNECT_DATA=(SERVICE_NAME=meu_servico)))"
```

---

## 🎯 Filtros de Objetos

Você pode usar os filtros `include` e `exclude` para focar estritamente nas tabelas de interesse do seu domínio:

* `%`: Corresponde a zero ou mais caracteres (ex: `TB_%` inclui todas as tabelas iniciadas por `TB_`).
* `_`: Corresponde a exatamente um caractere.

> [!TIP]
> Se a lista `include` estiver vazia, o LEAI processará **todos** os objetos do schema que correspondam aos `object_types`, exceto aqueles listados em `exclude`.
