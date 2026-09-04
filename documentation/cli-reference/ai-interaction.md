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

Inicia um console interativo no terminal no estilo Catppuccin Mocha com histórico de conversa, autocompletar e raciocínio autônomo com ferramentas in-memory.

```bash
# Iniciar console no terminal:
leai chat -p gemini -m gemini-2.0-flash

# Iniciar e abrir diretamente no navegador (Web Chat Studio):
leai chat --web
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-p`, `--provider TEXT` | Opção | Do config | Provedor de IA ativo. |
| `-m`, `--model TEXT` | Opção | Do config | Modelo de IA a utilizar. |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho do arquivo de configuração. |
| `-w`, `--web` | Flag | `False` | Inicia o servidor Web Studio e abre o chat no navegador. |
| `--seaweed` | Flag | `False` | Utiliza snapshots do storage S3. |
| `--no-cache` | Flag | `False` | Modo 100% em memória. |

### 📋 Comandos de Barra (Slash Commands) na Sessão Interativa:

| Comando | Categoria | Descrição |
| :--- | :--- | :--- |
| `/copy [all\|code\|N]` | Clipboard | Copia a última resposta ou bloco de código direto para a área de transferência do OS. |
| `/doc [obj]` | Documentação | Abre o editor interativo de documentação no terminal para a tabela ou pacote. |
| `/rule [list\|add\|find]` | Glossário | Gerencia regras de negócio globais e filtros canônicos de domínio. |
| `/enrich [obj]` | IA Studio | Auto-enriquece descrições e regras com IA. |
| `/compile [obj]` | Pipeline | Recompila a documentação Markdown em `docs/` (suporta objeto individual). |
| `/annotate [-W]` | Pipeline | Sincroniza stubs YAML em `annotations/` e/ou SeaweedFS. |
| `/extract [s\|d\|-W]` | Pipeline | Conecta ao Oracle e extrai snapshot técnico atualizado. |
| `/seaweed [status\|push\|pull\|sync]` | SeaweedFS | Gerencia status, push, pull e sincronização com Object Storage S3. |
| `/serve [port\|stop]` | Web Studio | Inicia o Web Studio no navegador com editor e diagramas em tempo real. |
| `/git [status\|pull\|sync]` | GitOps | Verifica status de commits, pull ou sincroniza metadados com Git/GitLab. |
| `/trace <obj>` | Linhagem | Executa raio-X de dependências e risco com diagramas Mermaid. |
| `/tables` | Inspeção | Lista tabelas do catálogo com contagem de colunas e PKs. |
| `/schema [s]` | Inspeção | Exibe visão panorâmica consolidada do schema. |
| `/changes [d]` | Inspeção | Inspeciona objetos modificados nos últimos N dias (Padrão: 7). |
| `/agent <role> <task>` | Multi-Agente | Executa subagentes especializados (`catalog`, `plsql`, `lineage`, `patch`, `doc`). |
| `/workflow <name> <obj>` | Workflows | Executa workflows autônomos multi-etapas (`impact`, `refactor`). |
| `/models [p]` | IA Config | Lista modelos disponíveis na API do provedor configurado. |
| `/model <p> [m]` | IA Config | Alterna de provedor e modelo de IA em tempo de execução. |
| `/audit [last\|session\|export]`| Auditoria | Inspeciona as chamadas de ferramentas da IA, latência e log da sessão. |
| `/tools` | Auditoria | Exibe as entradas e saídas detalhadas das ferramentas do último turno. |
| `/save [arquivo.md]` | Sessão | Exporta o histórico completo da conversa para arquivo Markdown. |
| `/doctor` (ou `/check`) | Diagnóstico | Executa diagnóstico preventivo completo no Oracle, IA, Storage e Git. |
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
