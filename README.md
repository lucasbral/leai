# LEAI - Oracle Database Documentation CLI for RAG & LLMs

O **LEAI** é uma ferramenta de linha de comando (CLI) em Python desenhada para extrair, organizar e documentar bancos de dados **Oracle Database** em arquivos Markdown otimizados especificamente para **Retrieval-Augmented Generation (RAG) e LLMs**.

---

## 🌟 Principais Recursos

- **Pipeline em 3 Estágios Desacoplados:**
  1. `raw/` ➔ Snapshot técnico 100% puro do dicionário do banco Oracle (em formato JSON).
  2. `annotations/` ➔ Camada editável de anotações de negócio em YAML (descrições, regras de negócio e comentários).
  3. `docs/` ➔ Documentos Markdown compilados e prontos para indexação por bancos vetoriais/RAG.
- **Desmembramento Inteligente de Pacotes (Package Splitting):**
  Desmembra automaticamente `PACKAGE` e `PACKAGE BODY` em sub-arquivos atômicos para cada `PROCEDURE` e `FUNCTION`, evitando arquivos gigantes e garantindo vetores de alta precisão no RAG.
- **Modo Offline (`leai compile`):**
  Re-compila toda a documentação em Markdown sem precisar estar conectado ao banco de dados Oracle.
- **Suporte a 10 Tipos de Objetos Oracle:**
  `tables`, `views`, `mviews`, `procedures`, `functions`, `packages`, `triggers`, `sequences`, `indexes` e `synonyms`.
- **Filtros e Wildcards:**
  Filtre tabelas e objetos via `include`/`exclude` com suporte a wildcards no formato LIKE (ex: `BIN$%`, `SYS_%`).

---

## 📦 Instalação

```bash
# Clone o repositório ou navegue até a pasta
cd leai

# Instale o pacote em modo editável
pip install -e .
```

---

## ⚙️ Configuração (`leai.yml`)

Crie um arquivo chamado `leai.yml` na raiz do seu projeto. 

### Exemplo Completo de `leai.yml`:

```yaml
# Conexão com o Oracle (Aceita URL oracle:// ou string DSN)
dsn: "oracle://usuario:senha@localhost:1521/ORCLPDB1"
schema: "MEU_SCHEMA"

# Diretórios do Pipeline de 3 Estágios
rawPath: "./raw"                  # Estágio 1: Snapshots brutos em JSON
annotationsPath: "./annotations"  # Estágio 2: Anotações de negócio em YAML
docPath: "./docs"                  # Estágio 3: Markdown final para RAG

# Filtros de inclusão/exclusão por nome de objeto (Suporta wildcards LIKE)
include:
  - FUNCIONARIOS
  - VENDAS_%
exclude:
  - BIN$%
  - SYS_%

# Tipos de objetos a serem processados (Descomente apenas os desejados)
object_types:
  - tables
  - views
  - mviews
  - procedures
  - functions
  - packages
  - triggers
  - sequences
  - indexes
  - synonyms
```

---

## 🚀 Como Usar o CLI

O `leai` oferece 3 comandos principais no terminal:

### 1. `leai generate` (ou apenas `leai`) - Pipeline Completo
Conecta no banco, salva o snapshot em `raw/`, garante os arquivos de anotação em `annotations/` e compila os Markdowns em `docs/`.

```bash
leai
# ou com arquivo de config personalizado:
leai generate --config meu_config.yml
```

### 2. `leai extract` - Apenas Extração RAW Técnica
Executa apenas o Estágio 1: conecta no Oracle e salva o snapshot puramente técnico em `raw/`.

```bash
leai extract
```

### 3. `leai compile` - Compilação Offline (Sem Banco)
Lê o snapshot da pasta `raw/` + as anotações em `annotations/` e compila os Markdowns da pasta `docs/` **sem precisar conectar no banco Oracle**.

```bash
leai compile
```

---

### 🎯 Filtragem Direta pelo Terminal (`-t` / `--object-type`)

Você pode aplicar filtros rápidos direto do terminal sem alterar o `leai.yml`:

```bash
# Extrair/Gerar apenas tabelas
leai generate -t tables

# Extrair apenas procedures e packages
leai extract -t procedures -t packages

# Compilar offline apenas views
leai compile -t views
```

---

## 📁 Estrutura de Pastas Gerada

```text
meu_projeto/
├── leai.yml
├── raw/                              <-- Estágio 1: Snapshots brutos (JSON)
│   ├── tables/
│   │   └── FUNCIONARIOS.json
│   └── package_bodys/
│       └── PKG_FOLHA.json
│
├── annotations/                      <-- Estágio 2: Anotações de negócio (YAML)
│   ├── tables/
│   │   └── FUNCIONARIOS.yml
│   └── package_bodys/
│       ├── PKG_FOLHA.yml
│       └── PKG_FOLHA/
│           ├── CALCULA_INSS.yml
│           └── CALCULA_IRRF.yml
│
└── docs/                             <-- Estágio 3: Markdown final para RAG
    ├── tables/
    │   └── FUNCIONARIOS.md
    └── package_bodys/
        ├── PKG_FOLHA.md              <-- Visão geral + Tabela de procedimentos
        └── PKG_FOLHA/                <-- Chunks atômicos de sub-rotinas
            ├── CALCULA_INSS.md
            └── CALCULA_IRRF.md
```

---

## ✍️ Como Enriquecer com Anotações de Negócio

Na pasta `annotations/`, cada objeto possui um arquivo `.yml` modelo pré-gerado automaticamente. Você pode preenchê-lo para enriquecer a documentação do RAG:

### Exemplo: `annotations/tables/FUNCIONARIOS.yml`
```yaml
description: "Tabela central do módulo de Recursos Humanos contendo colaboradores ativos e desligados."
business_rules:
  - "Funcionários com status_id = 3 foram desligados."
  - "O campo salario já contempla a bonificação fixa."
columns:
  ID: "Código identificador único do colaborador."
  SALARIO: "Valor bruto do salário mensal em Reais (BRL)."
```

Quando você executar `leai compile` ou `leai generate`, esses dados serão **fundidos automaticamente** dentro do arquivo Markdown em `docs/tables/FUNCIONARIOS.md`!

---

## 🧪 Executando os Testes Automatizados

O projeto possui uma suíte completa de testes unitários:

```bash
python -m unittest discover tests
```
