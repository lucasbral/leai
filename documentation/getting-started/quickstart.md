# Guia Rápido (Quickstart)

Este guia prático mostra como configurar e executar o LEAI do zero em qualquer projeto contendo um banco Oracle.

---

## ⚡ Passo a Passo em 3 Minutos

### Passo 1: Inicializar o Projeto

Crie um diretório de trabalho para sua documentação e execute o comando `init`:

```bash
mkdir meu-banco-doc
cd meu-banco-doc
leai init
```

Esse comando criará automaticamente um arquivo `leai.yml` com modelos de conexão e opções de filtros pré-configurados.

---

### Passo 2: Configurar a Conexão com o Oracle

Edite o arquivo `leai.yml` gerado. Você pode utilizar variáveis de ambiente para manter suas credenciais seguras:

```yaml
# leai.yml
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# Schemas que deseja extrair:
schemas:
  - RH
  - FINANCEIRO

# Diretórios do pipeline:
rawPath: "./raw"
annotationsPath: "./annotations"
docPath: "./docs"

# Categorias de objetos a processar:
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - triggers
  - synonyms
```

Defina as variáveis no seu terminal antes de rodar:

=== "Linux / macOS"
    ```bash
    export DB_USER="consulta_metadata"
    export DB_PASS="senha_secreta"
    export DB_HOST="db.empresa.com"
    export DB_SERVICE="ORCLPDB1"
    ```

=== "Windows PowerShell"
    ```powershell
    $env:DB_USER="consulta_metadata"
    $env:DB_PASS="senha_secreta"
    $env:DB_HOST="db.empresa.com"
    $env:DB_SERVICE="ORCLPDB1"
    ```

---

### Passo 3: Executar o Pipeline Completo

Para rodar todo o pipeline (extração do banco, geração das anotações e compilação em Markdown) em um único comando:

```bash
leai
# ou explicitamente:
leai generate
```

O LEAI executará as 3 fases sequencialmente:
1. **Extração:** Conecta ao Oracle e salva snapshots técnicos em `./raw/*.json`.
2. **Anotação:** Cria stubs de negócio em `./annotations/*.yml` (preservando edições existentes).
3. **Compilação:** Gera a documentação final em `./docs/*.md` com diagramas Mermaid.js e cabeçalhos YAML estruturados.

---

### Passo 4: Explorar com a Linha de Comando

#### Rastrear o impacto de um objeto
```bash
leai trace FUNCIONARIOS --depth 2
```

#### Fazer uma pergunta em linguagem natural com IA
```bash
export OPENAI_API_KEY="sk-..."
leai ask "Qual a tabela principal onde os salários são calculados e quais triggers são disparados?"
```

#### Iniciar um chat interativo com ferramentas
```bash
leai chat
```
