# Histórico de Versões (Changelog)

Todas as alterações notáveis no projeto **LEAI** são documentadas nesta página.

## [0.2.27] — 2026

### 🌐 Conclusão da Localização Integral e Padronização Canônica
* **Terminal Canônico 100% em Inglês por Padrão:** Varredura exaustiva e migração completa de todas as mensagens residuais em Português no CLI e TUI para o catálogo de internacionalização (`leai/i18n`), garantindo saída limpa em Inglês canônico por padrão e tradução instantânea em Português quando `language: "pt-BR"` estiver ativo.
* **Tabelas de Status Git e Indicadores do TUI:** A tabela `/git status` (propriedades, colunas, status de sincronização e avisos de commits à frente/atrás), mensagens de cópia inteligente e dicas de atalhos de clipboard foram 100% integradas ao motor i18n com suporte bilíngue.
* **Cabeçalhos de Documentação Markdown Bilíngues:** Geradores de documentação (`leai/docs.py`) agora produzem seções e títulos de Markdown (`## Overview`, `## Columns`, `## Primary Key`, `## Foreign Keys`, `## Business Rules`) de forma dinâmica no idioma ativo (`## Visão Geral`, `## Colunas`, `## Chave Primária`, etc. em `pt-BR`).
* **Web Studio Fallbacks e Telas de Carga:** As telas de carregamento do catálogo, mensagens de erro do SeaweedFS e botões de alternância da visualização de linhagem/Mermaid foram integrados ao dicionário i18n da interface Web.
* **Prevenção de Colisão e Limpeza de Imports:** Remoção de importações locais redundantes de `t` que causavam `UnboundLocalError` e renomeação de variáveis de iteração que colidiam com o símbolo de tradução.

---

## [0.2.26] — 2026

### 🌐 Arquitetura de Internacionalização (i18n) Completa (en-US / pt-BR)
* **Subsistema de i18n Nativo (`leai/i18n`):** Mecanismo de internacionalização tipado, leve e sem dependências externas, com catálogos completos para Inglês (`en-US`, padrão canônico) e Português do Brasil (`pt-BR`), suportando tags de estilização Rich e interpolação segura com fallback hierárquico.
* **Resolução Flexível por Precedência:** O idioma ativo pode ser determinado por: Flag CLI (`--lang` / `-L`) > Variável de ambiente (`LEAI_LANG` / `LEAI_LANGUAGE`) > Configuração (`language:` em `leai.yml`) > Fallback canônico (`en-US`).
* **Padronização do Terminal, TUI e Updater:** Migração de 100% das mensagens interativas do updater, avisos de sincronização do SeaweedFS/Git e comandos de barra do TUI (`/copy`, `/rule`, `/git`, `/init`) para o catálogo i18n, exibindo inglês por padrão ou português quando configurado.
* **Templates Bilíngues de Inicialização:** O comando `leai init --lang pt-BR` gera um arquivo `leai.yml` com comentários e exemplos em Português, enquanto `leai init` gera a versão padrão em Inglês.
* **Integração com o Studio Web:** Endpoints `/api/config` (GET e POST) sincronizam a preferência de idioma em tempo de execução, e o modal de configurações inclui um seletor visual com atualização dinâmica da UI.
* **Prompts de IA Bilíngues:** Os system prompts de enriquecimento de tabelas, objetos de código (procedures/packages/triggers) e o Copilot de RAG/Chat agora adaptam suas instruções com base no idioma do projeto, gerando regras e explicações em Português quando `language: "pt-BR"` estiver ativo, mantendo identificadores SQL técnicos intactos.

---

## [0.2.25] — 2026

### 🛡️ Correções no Reinício do Auto-Update
* **Resolução Robusta de Módulo no Reinício (`python -m leai`):** Substituição do comando de reinício baseado em `sys.argv` por `[sys.executable, "-m", "leai"] + sys.argv[1:]`. Isso elimina o erro `[Errno 2] No such file or directory` no Windows onde o launcher binário (`leai.exe` / `~/.local/bin/leai`) era passado como se fosse um arquivo de script `.py`.
* **Execução Síncrona em Primeiro Plano no Windows:** Substituição de `os.execv` por `subprocess.call` no Windows para manter a sessão no console do terminal ativa em primeiro plano sem liberar precocemente o prompt do PowerShell.

---

## [0.2.24] — 2026

### 🛡️ Correções & Estabilidade
* **Prevenção de Vazamento de Cursores Oracle:** Adicionados blocos `finally: cursor.close()` explícitos em `fetch_schema_metadata`, `fetch_focal_trace` e `fetch_available_schemas` em `leai/oracle.py`, garantindo fechamento determinístico de cursores mesmo em caso de erro.
* **Segurança na Área de Transferência (Clipboard):** Remoção de `shell=True` ao chamar `clip.exe` e substituição da interpolação de comandos no fallback do PowerShell por pipe direto via `stdin` (`$input | Set-Clipboard`), prevenindo potenciais falhas de escape de aspas ou injeção.
* **Correção de Closures em Loops:** Corrigido binding tardio de variáveis de loop em callbacks de progresso assíncronos/UI em `leai/web/server.py`, `leai/cli.py` e `leai/tui/session.py`.
* **Limpeza e Qualidade de Código:** Resolução de sobrescrita de variáveis de iteração em `leai/ai/tools.py` e simplificação da iteração de dicionários em `leai/workflows/__init__.py`.

---

## [0.2.23] — 2026

### 🌟 Adicionado & Aprimorado
* **Configurações Granulares de IA no `leai.yml`:** Suporte a `temperature` e `timeout` configuráveis tanto globalmente quanto sobrescritos individualmente por provedor em `ai.providers.<nome>`.
* **Controle de Limites Operacionais de Agentes:** Adicionados os parâmetros `max_history_turns` (janela de histórico do chat), `max_agent_iterations` (máximo de passos/tools do agente principal) e `max_subagent_iterations` (máximo de iterações para subagentes especialistas).
* **Presets de Modelos Locais:** Adicionado suporte nativo aos provedores `local` (LM Studio, vLLM em `http://localhost:1234/v1` com `qwen2.5`) e `custom` (`http://localhost:8000/v1`), além de atualizar o modelo padrão do `ollama` para `qwen2.5-coder:latest`.
* **Documentação Expandida:** Atualização completa do `leai.example.yml`, `README.md` e páginas de documentação MkDocs cobrindo todas as configurações de LLMs e modelos locais.

---

## [0.2.22] — 2026

### 🌟 Adicionado
* **Mecanismo de Atualização Automática Interativa (Auto-Update PyPI):** O comando interativo raiz `leai` agora verifica automaticamente no PyPI (`https://pypi.org/pypi/leai/json`) se há uma versão mais recente disponível (com timeout rápido de 2s e modo não-bloqueante/fail-safe).
* **Detecção Inteligente do Gerenciador de Instalação:** Identifica se o LEAI está rodando via `uv tool` (`uv tool upgrade leai`) ou `pip` tradicional (`pip install --upgrade leai`), além de proteger ambientes de desenvolvimento locais (`editable`).
* **Interface de Atualização Amigável:** Painel Rich formatado exibindo versão atual, nova versão, destaques de lançamento e link do changelog, com prompt interativo `[Y/n]` e reinício automático do processo via `os.execv`.
* **Controles de Desativação:** Opção `--no-update-check` na CLI, variável de ambiente `LEAI_NO_UPDATE_CHECK=1` e chave `update_check: false` no `leai.yml` para ambientes de CI/CD e automações.
* **Script de Instalação Automatizado do Windows (`install.ps1`):** Instalador unificado com instalação do `uv`, Ollama, download do modelo `qwen2.5-coder`, instalação do LEAI CLI e geração automática de ambiente de trabalho e `leai.yml`.

---

## [0.2.21] — 2026

### 🌟 Adicionado
* **Operação 100% Remota de IA e Agentes via SeaweedFS S3:** Todas as ferramentas de banco de dados (`DATABASE_TOOLS_DEFINITIONS`), subagentes e workflows agora operam diretamente com o SeaweedFS S3, dispensando a necessidade de metadados técnicos ou anotações locais em disco (`raw/`, `annotations/`, `docs/`).
* **Fallback Remoto no `lookup_business_term`:** Acesso instantâneo a termos de negócio, regras organizacionais e filtros SQL canônicos diretamente do bucket (`annotations/glossary.yml`).
* **Enriquecimento Remoto de Schemas e Colunas:** `get_table_schema`, `search_column_comments` e `search_database_objects` recuperam anotações de negócio, regras, tags e descrições humanas de colunas gravadas no S3 para Tabelas, Views e Materialized Views.
* **Busca Semântica Remota:** `search_business_documentation` agora varre o catálogo de anotações persistido no S3 via `list_annotated_objects()` quando não há anotações locais.
* **Dossiês e RAG Remotos:** `build_rag_context` consulta anotações remotas do SeaweedFS para montagem de dossiês focais.
* **Comandos CLI Integrados ao Storage:** `leai agent run` e `leai workflow run` agora suportam `--seaweed` (`-W`) e `--no-cache`, carregando automaticamente metadados técnicos diretamente do SeaweedFS.

---

## [0.2.20] — 2026

### 🌟 Adicionado
* **Sincronização Direta de Regras Universais com SeaweedFS no Web Studio:** O painel Web Studio (`leai serve` / `/serve`) agora carrega, salva e exclui regras de negócio diretamente no bucket SeaweedFS S3 (`annotations/glossary.yml`), eliminando arquivos sujos locais.
* **Feedback Visual de Sincronização no Web Studio:** Botão "Atualizar" com animação de rotação (spin) durante o carregamento e notificação toast informativa com contagem de regras sincronizadas.
* **Indicadores de Progresso em Tempo Real no `leai update` e `/update`:** Visualização dinâmica detalhada a cada etapa (extração de tabelas, views, pacotes e envio para S3) com contadores `[atual/total]` e medição precisa de tempo decorrido por schema e tempo total.
* **Habilitação de Versionamento Nativo S3 no SeaweedFS:** Suporte a versionamento nativo (`Status: Enabled`) para retenção e auditoria contínua de histórico de alterações de metadados e anotações no bucket remoto.

### ⚡ Correções
* **Contagem de Objetos Modificados:** Correção no cálculo de `count_schema_objects` para não retornar 1 objeto quando o schema estiver vazio (`max(1, total)` removido).
* **Limpeza de Regras Padrão:** Remoção de regras estáticas mockadas ("Estágio Probatório") na inicialização do Web Studio, garantindo que o catálogo permaneça limpo se não houver termos cadastrados.

---

## [0.2.19] — 2026

### 🌟 Adicionado
* **Comando `leai update` na CLI e `/update` no TUI:** Extração incremental cirúrgica de objetos modificados no Oracle em janelas de horas (`--hours`) ou dias (`--days`), mesclando metadados técnicos com a foto consolidada de schema e enviando deltas ao SeaweedFS.
* **Preservação e Mesclagem de Anotações do SeaweedFS:** Sincronização inteligente onde descrições, tags, regras de negócio e comentários de colunas existentes no SeaweedFS nunca são perdidos nem sobrescritos.
* **Sincronização Contínua do `GLOSSARY.yml` no SeaweedFS:** Sincronização automática e persistência em nuvem do glossário de negócio corporativo em `annotations/glossary.yml`.
* **Comandos `leai rule del` (CLI) e `/rule del` (TUI):** Exclusão de termos de negócio com remoção sincronizada no bucket SeaweedFS.
* **Mesclagem Não Destrutiva de Regras (`merge_glossaries`):** Priorização de definições centrais do SeaweedFS em divergências e união de tags e filtros canônicos.
* **Autocompletar no TUI:** Autocomplete aprimorado para `/update` e `/rule [list|add|del|find]`.

---

## [0.2.18] — 2026

### 🌟 Adicionado
* **Comando `leai doctor` na CLI:** Novo comando e alias oficial para `check`, executando diagnóstico preventivo do Oracle (`v$version`), permissões de catálogo, diretórios do pipeline, bucket S3 (SeaweedFS), conectividade do modelo de IA e status do GitOps.
* **Comandos `/doctor` e `/check` no TUI:** Diagnóstico completo executável diretamente dentro do terminal interativo (`leai chat`) com tabela formatada via Rich.
* **Documentação Atualizada:** Referências de comandos CLI e slash commands do TUI atualizados com `/doctor`, `/seaweed`, `/git`, `/rule`, `/agent` e `/workflow`.

---

## [0.2.17] — 2026

### 🌟 Adicionado
* **Sincronização com SeaweedFS S3 no Web Studio (`/serve`):** Edições de anotações feitas pelo navegador (`POST /api/annotations`) são sincronizadas diretamente com o bucket S3 em tempo real.
* **Fallback Remoto de Anotações no Web Studio:** O endpoint `GET /api/object` busca automaticamente a anotação no SeaweedFS caso o arquivo local não exista, criando o cache local de forma transparente.
* **Feedback Visual de S3 na Interface Web:** Indicador de status no cabeçalho (`☁️ S3: <bucket>`) e mensagem de confirmação no toast de salvamento.
* **Subcomando `/seaweed sync` no TUI:** Sincronização inteligente bidirecional (push + pull com hash SHA-256) agora executável diretamente dentro do terminal interativo.
* **Isolamento Local do `/doc`:** O editor de documentação do terminal salva única e exclusivamente no disco local, evitando envios acidentais para a nuvem.

### ⚡ Melhorias
* Suporte e documentação de políticas de ciclo de vida (Lifecycle Rules) para expiração de histórico não-corrente em `annotations/`.
* Autocompletion do terminal atualizado com `/seaweed sync` e modificadores `--seaweed`, `-W` e `--no-cache` no comando `/annotate`.

---

## [0.2.15] — 2026

### 🌟 Adicionado
* **Documentação Oficial no GitHub Pages:** Estrutura completa bilíngue (Português e Inglês) usando Material for MkDocs.
* **Agente Autônomo In-Memory:** Suporte aprimorado ao loop ReAct e compressão de PL/SQL no comando `leai chat`.
* **Suporte Multi-Provedor de IA:** Integrações REST leves com OpenAI, Gemini, Claude, DeepSeek, Qwen e Ollama.

### ⚡ Melhorias
* Rastreamento de linhagem multi-nível (`trace`) com cálculo automático de severidade de risco.
* Resolução recursiva de sinônimos públicos e privados (`PUBLIC SYNONYM`) e `@dblink`.
* Esqueletização cirúrgica de subprogramas PL/SQL para otimização de até 95% dos tokens.

---

## [0.2.0] — Primeiras Versões

* Extração técnica de catálogo Oracle em JSON.
* Camada editável e não-destrutiva de anotações em YAML.
* Compilação para Markdown com YAML Frontmatter e diagramas Mermaid.
