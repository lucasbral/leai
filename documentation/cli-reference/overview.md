# Visão Geral do CLI

O LEAI fornece uma interface de linha de comando completa, construída com Typer e estilizada com Rich para tabelas, árvores hierárquicas e barras de progresso animadas.

---

## 🧭 Tabela Completa de Comandos

| Comando | Grupo | Descrição Resumida |
| :--- | :--- | :--- |
| **`leai`** (ou `generate`) | Pipeline | Executa as 3 etapas completas: `extract`, `annotate` e `compile`. |
| **`leai extract`** | Pipeline | Extrai DDLs e metadados técnicos do Oracle para snapshots JSON brutos. |
| **`leai annotate`** | Pipeline | Gera/atualiza stubs YAML de anotações sem sobrescrever notas manuais. |
| **`leai compile`** | Pipeline | Compila metadados e anotações em Markdown e diagramas Mermaid. |
| **`leai doc <OBJ>`** | Documentação | Abre o editor interativo no terminal para documentar um objeto específico. |
| **`leai trace <OBJ>`** | Análise | Rastreia a linhagem upstream e dependentes downstream com cálculo de risco. |
| **`leai enrich`** | IA / LLM | Preenche automaticamente anotações vazias no YAML utilizando IA. |
| **`leai ask <PERGUNTA>`** | IA / LLM | Responde perguntas pontuais sobre o schema no terminal utilizando LLMs. |
| **`leai chat`** | IA / LLM | Inicia uma sessão de chat interativo com raciocínio autônomo e ferramentas. |
| **`leai models`** | IA / LLM | Lista, testa a conectividade e mede a latência dos provedores de IA configurados. |
| **`leai serve`** | Web Studio | Inicia o servidor local do LEAI Web Documentation & Annotation Studio. |
| **`leai agent`** | Subagentes | Gerencia subagentes especializados (`list`, `run`). |
| **`leai workflow`** | Automação | Executa workflows multi-etapas (`impact-analysis`, `safe-refactor`). |
| **`leai rule`** | Regras | Gerencia glossário e regras canônicas de negócio (`list`, `add`, `show`). |
| **`leai git`** | Versionamento | Operações GitOps para sincronizar documentação (`status`, `pull`, `sync`). |
| **`leai seaweed`** | Storage | Gerencia persistência em Object Storage S3/SeaweedFS (`status`, `push`, `pull`, `sync`). |
| **`leai changes`** | Governança | Detecta modificações e drift no banco via `LAST_DDL_TIME`. |
| **`leai doctor`** (ou `check`) | Diagnóstico | Valida conectividade Oracle, permissões no catálogo e dependências. |
| **`leai init`** | Configuração | Cria um arquivo de configuração inicial `leai.yml` pronto para uso. |

---

## ⚙️ Opções Globais Comuns

* `-c`, `--config PATH`: Especifica um arquivo de configuração customizado (Padrão: `leai.yml`).
* `--seaweed`: Ativa o uso de Object Storage remoto SeaweedFS/S3 para a operação.
* `--no-cache`: Opera 100% remoto, sem salvar snapshots no disco local.
* `--help`: Exibe instruções detalhadas e lista de argumentos de qualquer comando.
* `--version`: Exibe a versão instalada do LEAI.
