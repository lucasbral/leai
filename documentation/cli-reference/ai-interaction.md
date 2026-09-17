# Interação com IA (ask, chat, models)

O LEAI transforma seu catálogo Oracle em uma base de conhecimento interativa capaz de responder dúvidas complexas de engenharia e regras de negócio no terminal.

---

## 1. `leai ask <PERGUNTA>`

Permite fazer perguntas pontuais em linguagem natural sobre qualquer aspecto do banco de dados com injeção cirúrgica de contexto.

```bash
leai ask "Como funciona a regra de rescisão na procedure CALC_RESCISAO e quais tabelas ela consulta?" -p gemini
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `QUESTION` | Argumento | **Obrigatório** | Pergunta técnica ou funcional sobre o banco de dados. |
| `-p`, `--provider TEXT` | Opção | Do config | Provedor de IA (`openai`, `gemini`, `claude`, `deepseek`, `ollama`, etc.). |
| `-m`, `--model TEXT` | Opção | Do config | Modelo de IA a utilizar. |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho para o arquivo `leai.yml`. |
| `--seaweed` | Flag | `False` | Consulta metadados direto do bucket S3. |
| `--no-cache` | Flag | `False` | Opera em modo 100% remoto sem arquivos locais. |

---

## 2. `leai chat`

Inicia um console interativo avançado no terminal com tema Catppuccin Mocha, histórico persistente de conversa, autocompletar contextual dinâmico, streaming de raciocínio (*reasoning tokens*) e execução autônoma de ferramentas com feedback visual em tempo real.

```bash
# Iniciar console no terminal:
leai chat -p gemini -m gemini-2.0-flash

# Iniciar com modelo local via Ollama:
leai chat -p ollama -m qwen2.5-coder:7b

# Iniciar e abrir diretamente no navegador (Web Chat Studio):
leai chat --web
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Opção | Do config | Provedor de IA ativo (`gemini`, `openai`, `claude`, `ollama`, etc.). |
| `-m`, `--model TEXT` | Opção | Do config | Modelo de IA a utilizar. |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho do arquivo de configuração. |
| `-w`, `--web` | Flag | `False` | Inicia o servidor Web Studio e abre o chat no navegador. |
| `--seaweed` | Flag | `False` | Utiliza snapshots do storage S3. |
| `--no-cache` | Flag | `False` | Modo 100% em memória. |

---

### ✨ Recursos do Terminal Moderno (TUI):

* **🏷️ Autocompletar Inteligente com Prefixos:**
  * Digite `@` para autocompletar nomes de tabelas, packages, procedures e views do catálogo Oracle com ícones descritivos (`📋` Tabela, `📦` Package, `⚙️` Procedure, `👁️` View, `⚡` Trigger, `🔢` Sequence, `🔗` Synonym).
  * Digite `#` para referenciar termos de negócio e regras de domínio registradas no glossário (`glossary.yml`).
  * Digite `/` para listar e autocompletar comandos de barra (*slash commands*) disponíveis.
* **🧠 Streaming de Pensamentos (*Reasoning Traces*):**
  * Suporte a modelos de raciocínio (ex: DeepSeek-R1, Gemini 2.0 Flash Thinking, Qwen 2.5).
  * Exibe uma caixa colapsável com o fluxo de pensamento do modelo em tempo real antes da resposta final.
  * Use o comando `/thoughts on` ou `/thoughts off` para alternar a exibição.
* **⚡ Cards Visuais de Execução de Ferramentas:**
  * Durante as rodadas de investigação, exibe spinners animados e cronômetro em tempo real para cada ferramenta acionada (`⚡ search_database_objects (0.34s)`).
* **📊 Barra de Status Inferior Dinâmica:**
  * Exibe permanentemente no rodapé do terminal o provedor e modelo ativos, o schema conectado, o status de visualização de pensamentos (`thoughts:on/off`) e atalho de ajuda (`help:/?`).
* **⌨️ Teclas de Atalho e Edição Multilinha:**
  * `Enter`: Envia a mensagem para a IA.
  * `Alt+Enter` ou `Ctrl+J`: Insere uma quebra de linha para digitar consultas SQL e prompts longos sem disparar o envio.
  * `Ctrl+C` ou `Ctrl+D`: Cancela a edição ou sai da sessão.

---

### 📋 Comandos de Barra (Slash Commands) na Sessão Interativa:

| Comando | Categoria | Descrição |
| :--- | :--- | :--- |
| `/tune [sql]` | Otimização | Analisa e otimiza queries SQL com diagnóstico de sargabilidade, FTS, índices e anti-patterns. |
| `/validate [sql]` | Validação | Valida conformidade e sintaxe estrita Oracle SQL/PL-SQL (detecta construções MySQL/PostgreSQL). |
| `/thoughts [on\|off]` | Raciocínio | Alterna a exibição em tempo real dos blocos de pensamento/raciocínio (*thinking trace*). |
| `/provider [nome]` | IA Config | Alterna o provedor de IA ativo com autocompletar dinâmico. |
| `/model <p> [m]` | IA Config | Alterna de provedor e modelo de IA em tempo de execução. |
| `/models [p]` | IA Config | Lista modelos disponíveis na API do provedor configurado. |
| `/workflow <name> <obj>` | Workflows | Executa workflows autônomos (`impact`, `refactor`, `reverse-procedure` / `reverse`). |
| `/agent <role> <task>` | Multi-Agente | Executa subagentes especializados (`catalog`, `plsql`, `lineage`, `patch`, `doc`). |
| `/trace <obj>` | Linhagem | Executa raio-X de dependências e risco com diagramas Mermaid. |
| `/copy [all\|code\|N]` | Clipboard | Copia a última resposta ou bloco de código direto para a área de transferência do OS. |
| `/doc [obj]` | Documentação | Abre o editor interativo de documentação no terminal para a tabela ou pacote. |
| `/rule [list\|add\|del\|find]` | Glossário | Gerencia regras de negócio globais, filtros canônicos e sincronização com SeaweedFS. |
| `/enrich [obj]` | IA Studio | Auto-enriquece descrições e regras com IA. |
| `/compile [obj]` | Pipeline | Recompila a documentação Markdown em `docs/` (suporta objeto individual). |
| `/annotate [-W]` | Pipeline | Sincroniza stubs YAML em `annotations/` e/ou SeaweedFS. |
| `/extract [s\|d\|-W]` | Pipeline | Conecta ao Oracle e extrai snapshot técnico atualizado. |
| `/update [h\|d\|-W]` | Pipeline | Atualização incremental rápida de objetos modificados, anotações e S3. |
| `/seaweed [status\|push\|pull\|sync]` | SeaweedFS | Gerencia status, push, pull e sincronização com Object Storage S3. |
| `/serve [port\|stop]` | Web Studio | Inicia o Web Studio no navegador com editor e diagramas em tempo real. |
| `/git [status\|pull\|sync]` | GitOps | Verifica status de commits, pull ou sincroniza metadados com Git/GitLab. |
| `/tables` | Inspeção | Lista tabelas do catálogo com contagem de colunas e PKs. |
| `/schema [s]` | Inspeção | Exibe visão panorâmica consolidada do schema. |
| `/changes [d]` | Inspeção | Inspeciona objetos modificados nos últimos N dias (Padrão: 7). |
| `/audit [last\|session\|export]`| Auditoria | Inspeciona as chamadas de ferramentas da IA, latência e log da sessão. |
| `/tools` | Auditoria | Exibe as entradas e saídas detalhadas das ferramentas do último turno. |
| `/save [arquivo.md]` | Sessão | Exporta o histórico completo da conversa para arquivo Markdown. |
| `/doctor` | Diagnóstico | Executa diagnóstico preventivo completo no Oracle, IA, Storage, Git e diretórios. |
| `/init` | Configuração | Inicializa ou atualiza o arquivo de configuração `leai.yml`. |
| `/clear` | Sessão | Limpa a memória conversacional e reinicia a tela. |
| `/exit`, `/quit` | Sessão | Encerra a sessão do copilot. |

---

## 3. `leai models`

Testa credenciais, exibe a lista de modelos suportados e afere a latência da conexão REST com os provedores configurados.

```bash
leai models -p gemini
leai models -p openai
```

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Opção | Todos | Filtra por um provedor específico. |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho do arquivo de configuração. |
