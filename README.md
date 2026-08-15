# LEAI - Oracle Database Documentation CLI for RAG & LLMs

O **LEAI** é uma ferramenta de linha de comando (CLI) em Python desenhada para extrair, organizar e documentar bancos de dados **Oracle Database** em arquivos Markdown otimizados especificamente para **Retrieval-Augmented Generation (RAG) e LLMs**.

---

## 🌟 Principais Recursos

- **Pipeline em 3 Estágios Desacoplados:**
  1. `raw/` ➔ Snapshot técnico 100% puro do dicionário do banco Oracle (em formato JSON).
  2. `annotations/` ➔ Camada editável de anotações de negócio em YAML (descrições, regras de negócio e comentários).
  3. `docs/` ➔ Documentos Markdown compilados e prontos para indexação por bancos vetoriais/RAG.
- **Suporte Multi-Schema e Modo `"ALL"`:**
  Configure schemas individuais (`schema: "HR"`), listas de schemas (`schemas: ["HR", "SALES"]`) ou extraia automaticamente **todos os schemas do banco** (`schemas: "ALL"`).
- **Detecção Automática de Visões `DBA_*` / `ALL_*`:**
  Detecta automaticamente se o usuário possui `GRANT SELECT ANY DICTIONARY` ou role `DBA`, utilizando as visões mestre `DBA_*` para garantir 100% de cobertura dos objetos sem necessidade de privilégios em cada tabela.
- **Desmembramento e Consolidação de Código PL/SQL:**
  Extrai `PROCEDURE`, `FUNCTION`, `PACKAGE` + `PACKAGE BODY` e `TYPE` + `TYPE BODY`. Consolida especificação e corpo no mesmo arquivo atômico por objeto de código e cria sub-arquivos atômicos para subprogramas de pacotes.
- **Interface Terminal Rich:**
  Barra de progresso animada em tempo real com porcentagem intra-schema (`[50%]`), contador acumulativo de objetos (`(14.739 objetos)`), cronômetro de tempo de execução (`25.14s`) e painel de resumo unificado.
- **Pronto para CI/CD e Segurança:**
  Suporta interpolação de variáveis de ambiente `${VAR}` no `leai.yml` e sobrescrita direta de credenciais sensíveis via `LEAI_DSN`.
- **Modo Offline (`leai compile`):**
  Re-compila toda a documentação em Markdown sem precisar estar conectado ao banco de dados Oracle.

---

## 📦 Instalação e Execução

### Opção 1: Usando `uv` (Recomendado)
O **`uv`** oferece gerenciamento de dependências e execução ultrarrápida:

```bash
# Clone o repositório ou navegue até a pasta
cd leai

# Sincronize o ambiente virtual e dependências
uv sync

# Execute o CLI via uv
uv run leai
```

### Opção 2: Usando `pip`

#### A. Instalação Local (Modo Editável)
Na raiz do projeto clonado:
```bash
pip install -e .

# Executar o CLI diretamente
leai
```

#### B. Instalação Direta via Git / GitHub
Instale diretamente a partir do repositório remoto sem precisar clonar manualmente:
```bash
pip install git+https://github.com/lucasbral/leai.git

# Executar o CLI diretamente
leai
```

---

## ⚙️ Configuração (`leai.yml`)

Crie um arquivo chamado `leai.yml` na raiz do seu projeto:

```yaml
# Conexão com o Oracle (Aceita URL oracle://, DSN ou variáveis de ambiente)
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# 1. Schema único:
schemas:
  - C_ERGON

# 2. Ou múltiplos schemas:
# schemas:
#   - HR
#   - SALES
#   - FINANCAS

# 3. Ou TODOS os schemas não-sistema do banco (requer SELECT ANY DICTIONARY):
# schemas: "ALL"

# Diretórios do Pipeline
rawPath: "./raw"                  # Snapshots brutos em JSON
annotationsPath: "./annotations"  # Anotações de negócio em YAML
docPath: "./docs"                  # Markdown final para RAG

# Filtros de inclusão/exclusão por nome de objeto (Suporta wildcards LIKE)
include:
  - FUNCIONARIOS
  - VENDAS_%
exclude:
  - BIN$%
  - SYS_%

# Tipos de objetos a serem processados
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - types
  - triggers
  - sequences
  - indexes
  - synonyms
```

---

## 🚀 Comandos Disponíveis no CLI

O `leai` disponibiliza 3 subcomandos e uma execução padrão:

### 1. `uv run leai` (ou `uv run leai generate`) - Pipeline Completo
Executa o fluxo completo: conecta ao banco Oracle, salva os snapshots em `raw/`, sincroniza as anotações em `annotations/` e compila os Markdowns em `docs/`.

```bash
uv run leai
# ou apontando para outro arquivo de configuração:
uv run leai generate --config producao.yml
```

### 2. `uv run leai extract` - Extração RAW Técnica
Conecta no banco de dados Oracle e realiza apenas a extração dos snapshots técnicos em formato JSON na pasta `raw/`.

```bash
uv run leai extract
```

### 3. `uv run leai annotate` - Sincronização de Anotações YAML (Offline)
Lê os snapshots da pasta `raw/` e gera/sincroniza **apenas o diretório de anotações** `annotations/` em YAML (com descrições e colunas pré-preenchidas), sem regerar os Markdowns.

```bash
uv run leai annotate
```

### 4. `uv run leai trace <OBJECT>` - Dossiê de Linhagem e Análise de Impacto Focal (Novo!)
Gera uma **análise minuciosa e raio-x de impacto relacional** em torno de um objeto específico (ex: uma tabela `FUNCIONARIOS` ou pacote `PKG_FOLHA`) e de todos os objetos do banco que se conectam a ele.

```bash
# 1. Rastreamento padrão (Nível 1 - Vizinhos diretos)
uv run leai trace FUNCIONARIOS

# 2. Rastreamento multinível recursivo (Nível 2 - Vizinhos indiretos)
uv run leai trace FUNCIONARIOS --depth 2

# 3. Modo Offline (Resolve o grafo a partir dos snapshots RAW locais, sem conexão com o Oracle)
uv run leai trace FUNCIONARIOS --offline --depth 2

# 4. Gerar também o Chunk JSON estruturado para RAG / Vector DB
uv run leai trace FUNCIONARIOS --rag-json

# 5. Salvar em arquivo de saída customizado
uv run leai trace FUNCIONARIOS -o ./docs/dossier_funcionarios.md
```

#### 📊 O Que é Gerado no Dossiê Focal (`docs/dossiers/<OBJECT>.md`):
- **Frontmatter YAML no Topo (`rag_metadata`):** Cabeçalho estruturado legível por LLMs contendo `risk_level` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), lista de tabelas pais (`upstream_parents`), filhas (`downstream_children`) e consumidores (`consumers`).
- **Card de Raio-X de Impacto:** Bloco visual com badges de alerta indicando o risco de alteração e contagem de entidades afetadas.
- **Resumo Narrativo Semântico (RAG Ready):** Parágrafo contínuo em linguagem natural otimizado especificamente para **embeddings vetoriais de altíssima precisão** (`pgvector`, Chroma, etc.).
- **Grafo de Linhagem em Mermaid.js:** Diagrama visual com badges de distância `(L1)`, `(L2)` e destaque dourado para o nó focal.
- **Tabela de Impacto e Estrutura Técnica:** Chaves estrangeiras, colunas, tipos e resumo dos objetos conectados.
- **Preservação de Documentação Humana:** Seção `<!-- LEAI:MANUAL:START -->` mantida intacta entre regenerações.

---

### 5. `uv run leai changes` - Auditoria e Rastreamento de DDL (Offline)
Rastreia e exibe no terminal os objetos do banco de dados que foram **criados ou modificados recentemente** (via `LAST_DDL_TIME` do dicionário Oracle).

```bash
# Consultar objetos alterados nos últimos 7 dias (Padrão)
uv run leai changes

# Consultar objetos alterados nos últimos 30 dias
uv run leai changes -d 30

# Filtrar por usuário modificador ou schema
uv run leai changes -d 15 -u C_ERGON
```

---

### 🎯 Filtragem Direta pelo Terminal (`-t` / `--object-type`)

Você pode aplicar filtros rápidos direto do terminal para processar apenas tipos específicos de objetos:

```bash
# Extrair/Gerar apenas tabelas
uv run leai generate -t tables

# Extrair apenas procedimentos, pacotes e tipos
uv run leai extract -t procedures -t packages -t types

# Compilar offline apenas views
uv run leai compile -t views
```

---

## 📁 Estrutura de Diretórios Gerada

Em projetos multi-schema ou com `"ALL"`, o `leai` organiza os arquivos em subpastas isoladas por schema:

```text
meu_projeto/
├── leai.yml
├── raw/                              <-- Snapshots brutos (JSON)
│   └── C_ERGON/
│       ├── tables/
│       │   └── FUNCIONARIOS.json
│       └── code_objects/
│           └── PKG_FOLHA.json
│
├── annotations/                      <-- Anotações de negócio em YAML
│   └── C_ERGON/
│       ├── tables/
│       │   └── FUNCIONARIOS.yml
│       ├── dossiers/                 <-- Anotações de dossiês focais
│       │   └── FUNCIONARIOS.yml
│       └── code_objects/
│           ├── PKG_FOLHA.yml
│           └── PKG_FOLHA/
│               ├── CALCULA_INSS.yml
│               └── CALCULA_IRRF.yml
│
└── docs/                             <-- Markdown final compilado para RAG
    └── C_ERGON/
        ├── tables/
        │   └── FUNCIONARIOS.md
        ├── dossiers/                 <-- Dossiês de impacto e linhagem (Mermaid)
        │   └── FUNCIONARIOS.md
        ├── chunks/                   <-- Chunks estruturados para RAG (--rag-json)
        │   └── FUNCIONARIOS.json
        └── code_objects/
            ├── PKG_FOLHA.md          <-- Visão geral do pacote
            └── PKG_FOLHA/            <-- Sub-rotinas atômicas
                ├── CALCULA_INSS.md
                └── CALCULA_IRRF.md
```

---

## 🔒 Ambientes de Produção & CI/CD

Para executar o `leai` em pipelines de integração contínua (GitHub Actions, GitLab CI, Jenkins):

### 1. Interpolação no `leai.yml`:
```yaml
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"
```

### 2. Sobrescrita direta por Variável de Ambiente:
```bash
export LEAI_DSN="oracle://USER:SENHA@prod.empresa.com:1521/PRODDB"
uv run leai
```

---

## 🧪 Executando a Suíte de Testes

Para rodar todos os testes automatizados da aplicação:

```bash
uv run python -m unittest discover tests
```

