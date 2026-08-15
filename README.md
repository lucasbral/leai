# LEAI — Oracle Database Intelligence & Documentation Engine

O **LEAI** é um motor de engenharia reversa, análise de impacto e documentação para bancos de dados **Oracle Database**, projetado para alimentar aplicações de **RAG (Retrieval-Augmented Generation)**, **LLMs** e desenvolvedores que mantêm sistemas corporativos complexos.

---

## 📌 O Que É?

Bancos Oracle corporativos acumulam anos de regras de negócio espalhadas em centenas de tabelas, views, triggers e pacotes PL/SQL gigantescos (3.000 a 10.000 linhas). 

Fazer com que um desenvolvedor ou uma IA entenda esse ambiente é difícil por três motivos:
1. **Desperdício de Tokens:** Enviar pacotes inteiros para um LLM é caro, lento e gera alucinações ("Lost in the Middle").
2. **Dependências Ocultas:** Uma alteração em uma coluna pode quebrar triggers, views e procedures de múltiplos schemas.
3. **Sinônimos e Aliases:** Procedures chamam tabelas via sinônimos privados ou públicos (`PUBLIC SYNONYM`), criando a ilusão de que o objeto não existe ou pertence a outro lugar.

O LEAI resolve isso extraindo o dicionário de dados do Oracle, mapeando o grafo real de dependências entre schemas e estruturando o contexto técnico em formato otimizado para humanos e LLMs.

---

## ⚙️ Como Funciona?

O LEAI opera através de uma arquitetura modular dividida em **3 camadas desacopladas**:

```
 [Banco Oracle]
       │
       ▼ (leai extract)
 ┌─────────────┐
 │ 1. RAW JSON │ ──> Snapshot técnico puro do dicionário (DDL, colunas, tipos, PKs, FKs, Sinônimos).
 └─────────────┘
       │
       ▼ (leai annotate / leai enrich)
 ┌─────────────┐
 │ 2. YAML     │ ──> Camada de negócio editável (descrições, regras, tags). Preserva o que o
 └─────────────┘     humano escreve e permite que a IA complete stubs vazios sem sobrescrever.
       │
       ▼ (leai compile / leai trace)
 ┌─────────────┐
 │ 3. DOCS     │ ──> Markdown com Frontmatter YAML + Diagramas Mermaid.js de linhagem + Chunks
 └─────────────┘     estruturados para Vector DBs (pgvector, Chroma, Qdrant).
```

### Tecnologias e Mecanismos Internos:

- **Rastreamento de Linhagem Multinível (`trace`):**
  Identifica o que um objeto referencia (upstream) e quem depende dele (downstream) com profundidade configurável (`--depth N`), calculando o nível de risco de alteração (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- **Resolução Transparente de Sinônimos:**
  Mapeia `ALL_SYNONYMS` e `PUBLIC SYNONYMS` diretamente para a tabela física de destino, inclusive através de **Database Links (`@dblink`)**.
- **Compressão Semântica PL/SQL:**
  Quando você consulta uma procedure (`TESTE`) dentro de um pacote de 10.000 linhas, o LEAI extrai cirurgicamente apenas o bloco da procedure e gera o esqueleto de assinaturas do restante do pacote, **reduzindo o consumo de tokens em até 95%**.
- **RAG Contextual Dinâmico (`ask` & `chat`):**
  Detecta entidades na sua pergunta, executa o trace em tempo de execução e entrega ao LLM um contexto cirúrgico sem ruídos.
- **Suporte Multi-Provedor Nativo:**
  Conecta diretamente via HTTP REST em **OpenAI (ChatGPT)**, **Google Gemini**, **Anthropic Claude**, **DeepSeek**, **Qwen**, **Kimi** e **Ollama (local)** sem dependências externas pesadas.

---

## 🚀 Como Fazer Funcionar? (Guia Prático)

### 1. Instalação

Recomendamos o uso do **`uv`** pela velocidade e isolamento:

```bash
# Clonar o repositório e entrar na pasta
cd leai

# Instalar dependências e sincronizar ambiente
uv sync
```

*(Ou usando `pip install -e .`)*

---

### 2. Configuração (`leai.yml`)

Crie um arquivo `leai.yml` na raiz do projeto:

```yaml
# String de conexão Oracle (suporta variáveis de ambiente ${VAR})
dsn: "oracle://${DB_USER}:${DB_PASS}@${DB_HOST}:1521/${DB_SERVICE}"

# Schemas que fazem parte do seu ecossistema integrado
schemas:
  - C_ERGON
  # - CADASTRO
  # - FINANCEIRO

# Pastas de saída do pipeline
rawPath: "./raw"                  # Snapshots técnicos brutos
annotationsPath: "./annotations"  # Anotações de negócio
docPath: "./docs"                  # Documentação final compilada

# Provedores de IA para enrich, ask e chat
ai:
  default_provider: "openai"      # openai, gemini, anthropic, deepseek, qwen, kimi, ollama
  temperature: 0.2
  providers:
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
    gemini:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-1.5-flash"
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      model: "claude-3-5-sonnet-20241022"
    ollama:
      base_url: "http://localhost:11434/v1"
      model: "llama3.1"
```

---

## 📖 Referência Completa de Comandos e Parâmetros

### 1. `uv run leai` (ou `leai generate`)
Executa o pipeline completo (extração ➔ sincronização de anotações ➔ compilação dos Markdowns).

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `-c`, `--config PATH` | Opção | Caminho para o arquivo de configuração (Padrão: `leai.yml`). |
| `-t`, `--object-type TEXT` | Opção | Filtra tipos de objetos (ex: `-t tables -t views -t packages`). |

```bash
uv run leai
uv run leai generate -t tables -t packages --config prod.yml
```

---

### 2. `uv run leai extract`
Conecta no banco de dados Oracle e extrai snapshots técnicos em formato JSON para a pasta `raw/`.

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `-s`, `--schema TEXT` | Opção | Extrai apenas um schema específico. |
| `-t`, `--object-type TEXT` | Opção | Extrai apenas tipos específicos de objetos. |
| `-c`, `--config PATH` | Opção | Caminho para o `leai.yml`. |

```bash
uv run leai extract
uv run leai extract -s C_ERGON -t tables -t views
```

---

### 3. `uv run leai annotate`
Lê os snapshots de `raw/` e cria/sincroniza stubs YAML em `annotations/` preservando anotações humanas existentes (Modo Offline).

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `-t`, `--object-type TEXT` | Opção | Sincroniza apenas tipos específicos de objetos. |
| `-c`, `--config PATH` | Opção | Caminho para o `leai.yml`. |

```bash
uv run leai annotate
uv run leai annotate -t tables
```

---

### 4. `uv run leai compile`
Re-compila toda a documentação em Markdown em `docs/` unindo `raw/` e `annotations/` sem precisar de conexão com o banco.

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `-t`, `--object-type TEXT` | Opção | Compila apenas tipos específicos de objetos. |
| `-c`, `--config PATH` | Opção | Caminho para o `leai.yml`. |

```bash
uv run leai compile
uv run leai compile -t views
```

---

### 5. `uv run leai trace <OBJECT>`
Gera análise minuciosa de impacto, árvore hierárquica no terminal, cálculo de risco e dossiê com diagramas Mermaid.js.

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `OBJECT` | **Argumento Obrigatório** | Nome da tabela, view, procedure ou sinônimo a rastrear (ex: `FUNCIONARIOS`). |
| `-d`, `--depth INT` | Opção | Profundidade da busca no grafo (Padrão: `1` para diretos, `2+` para multinível). |
| `--rag-json`, `--rag` | Flag | Exporta também chunk JSON estruturado para ingestão em Vector DBs. |
| `--offline` | Flag | Resolve o grafo a partir dos snapshots `raw/` locais sem conectar ao banco. |
| `-s`, `--schema TEXT` | Opção | Schema do objeto alvo (se omitido, busca em todos os configurados). |
| `-o`, `--output PATH` | Opção | Caminho customizado para salvar o arquivo Markdown gerado. |
| `-c`, `--config PATH` | Opção | Caminho para o `leai.yml`. |

```bash
# Rastreamento multinível Nível 2
uv run leai trace FUNCIONARIOS --depth 2

# Modo Offline com exportação de chunk RAG
uv run leai trace FUNCIONARIOS --offline --depth 2 --rag-json
```

---

### 6. `uv run leai enrich`
Utiliza IA (LLMs) para analisar DDLs e códigos PL/SQL, preenchendo automaticamente regras de negócio e comentários de colunas faltantes em `annotations/`.

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `-o`, `--object-name TEXT` | Opção | Nome de um objeto específico para enriquecer (ex: `-o FUNCIONARIOS`). |
| `-p`, `--provider TEXT` | Opção | Provedor de IA (`openai`, `gemini`, `anthropic`, `deepseek`, `qwen`, `kimi`, `ollama`). |
| `-m`, `--model TEXT` | Opção | Nome do modelo (ex: `gpt-4o-mini`, `gemini-1.5-flash`, `claude-3-5-sonnet-20241022`). |
| `--overwrite` | Flag | Força a regeração de descrições e comentários já preenchidos. |
| `-t`, `--object-type TEXT` | Opção | Tipos de objeto a enriquecer (ex: `-t tables -t packages`). |
| `-c`, `--config PATH` | Opção | Caminho para o `leai.yml`. |

```bash
# Enriquecer com provedor padrão
uv run leai enrich

# Enriquecer com Google Gemini ou Claude
uv run leai enrich --provider gemini --model gemini-1.5-flash
uv run leai enrich --provider anthropic --model claude-3-5-sonnet-20241022

# Enriquecer apenas uma tabela forçando sobrescrita
uv run leai enrich -o FUNCIONARIOS --overwrite
```

---

### 7. `uv run leai ask <QUESTION>`
Faz uma pergunta pontual em linguagem natural com RAG contextual dinâmico.

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `QUESTION` | **Argumento Obrigatório** | A pergunta a ser respondida pela IA sobre o banco de dados. |
| `-p`, `--provider TEXT` | Opção | Provedor de IA a ser utilizado. |
| `-m`, `--model TEXT` | Opção | Nome do modelo a ser utilizado. |
| `-c`, `--config PATH` | Opção | Caminho para o `leai.yml`. |

```bash
uv run leai ask "Quais views ou procedures consultam a tabela FUNCIONARIOS?"
uv run leai ask "Como funciona o cálculo de folha de pagamento?" --provider gemini
```

---

### 8. `uv run leai chat`
Inicia um chat interativo multi-turno no terminal com memória de contexto e RAG acumulativo.

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Opção | Provedor de IA a ser utilizado. |
| `-m`, `--model TEXT` | Opção | Nome do modelo a ser utilizado. |
| `-c`, `--config PATH` | Opção | Caminho para o `leai.yml`. |

```bash
uv run leai chat
uv run leai chat --provider anthropic --model claude-3-5-sonnet-20241022
uv run leai chat --provider ollama --model llama3.1
```

#### 🎮 Comandos Interativos Disponíveis Dentro da Sessão:
- `/clear`: Limpa o histórico de mensagens e entidades acumuladas na sessão.
- `/save [arquivo.md]`: Salva a transcrição completa da conversa em arquivo Markdown.
- `/help`: Exibe os comandos de ajuda no terminal.
- `/exit` ou `/quit`: Encerra o chat.

---

### 9. `uv run leai changes`
Audita e lista no terminal os objetos criados ou modificados recentemente no banco (via `LAST_DDL_TIME`).

| Parâmetro / Opção | Tipo | Descrição |
| :--- | :--- | :--- |
| `-d`, `--days INT` | Opção | Quantidade de dias retroativos a auditar (Padrão: `7`). |
| `-u`, `--user TEXT` | Opção | Filtrar pelo usuário modificador / schema (ex: `-u C_ERGON`). |
| `-s`, `--schema TEXT` | Opção | Schema alvo da consulta. |
| `-t`, `--object-type TEXT` | Opção | Filtrar tipos de objeto modificados. |
| `-c`, `--config PATH` | Opção | Caminho para o `leai.yml`. |

```bash
# Consultar objetos alterados nos últimos 15 dias
uv run leai changes -d 15

# Filtrar por schema
uv run leai changes -d 30 -u C_ERGON
```

---

## 📁 Estrutura de Pastas Gerada

```text
meu_projeto/
├── leai.yml
├── raw/                      <-- Snapshots puros em JSON extraídos do Oracle
│   └── C_ERGON/
│       ├── tables/
│       ├── views/
│       ├── synonyms/
│       └── code_objects/
├── annotations/              <-- Regras de negócio em YAML (editáveis)
│   └── C_ERGON/
│       ├── tables/
│       └── code_objects/
└── docs/                     <-- Markdown final para LLM, RAG e leitura humana
    └── C_ERGON/
        ├── tables/
        ├── dossiers/         <-- Dossiês de impacto gerados pelo leai trace
        └── code_objects/
```

---

## 🧪 Testes Automatizados

Para rodar a suíte completa de testes unitários:

```bash
uv run python -m unittest discover tests
```
