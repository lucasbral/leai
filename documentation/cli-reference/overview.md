# Visão Geral do CLI

O LEAI fornece uma interface de linha de comando poderosa e intuitiva, construída com Typer e estilizada com Rich para formatação de tabelas, barras de progresso e realce de sintaxe no terminal.

---

## 🧭 Tabela de Comandos

| Comando | Grupo | Descrição Resumida |
| :--- | :--- | :--- |
| **`leai`** (ou `generate`) | Pipeline | Executa as 3 etapas completas: `extract`, `annotate` e `compile`. |
| **`leai extract`** | Pipeline | Conecta ao Oracle e extrai DDLs e metadados técnicos para JSON. |
| **`leai annotate`** | Pipeline | Cria/atualiza stubs YAML de anotações de negócio sem sobrescrever notas manuais. |
| **`leai compile`** | Pipeline | Compila os metadados e anotações em Markdown e diagramas Mermaid. |
| **`leai trace <OBJ>`** | Análise | Rastreia a linhagem upstream e dependentes downstream com cálculo de risco. |
| **`leai enrich`** | IA / LLM | Preenche automaticamente anotações vazias no YAML utilizando IA. |
| **`leai ask <PERGUNTA>`** | IA / LLM | Responde perguntas pontuais sobre o schema no terminal utilizando LLMs. |
| **`leai chat`** | IA / LLM | Inicia uma sessão de chat interativo com raciocínio autônomo e ferramentas. |
| **`leai models`** | IA / LLM | Lista, testa a conectividade e mede a latência dos provedores de IA configurados. |
| **`leai changes`** | Governança | Detecta drift de schema comparando a extração atual com snapshots anteriores. |
| **`leai doctor`** (ou `check`) | Diagnóstico | Valida conectividade Oracle, permissões no catálogo e dependências. |
| **`leai init`** | Configuração | Cria um arquivo de configuração inicial `leai.yml` pronto para uso. |

---

## ⚙️ Opções Globais

* `--help`: Exibe instruções detalhadas e lista de argumentos de qualquer comando.
* `--version`: Exibe a versão instalada do LEAI.
