# Histórico de Versões (Changelog)

Todas as alterações notáveis no projeto **LEAI** são documentadas nesta página.

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
