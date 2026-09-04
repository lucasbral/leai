# Utilitários, Diagnóstico e Governança

Esta seção cobre comandos essenciais para diagnóstico de ambiente, inicialização e auditoria de alterações no banco de dados.

---

## 1. `leai init`

Inicializa um diretório de documentação criando o arquivo de modelo `leai.yml`.

```bash
leai init
```

* Se já existir um arquivo `leai.yml`, o comando avisa e não o sobrescreve sem confirmação.
* Gera modelos detalhados de configuração de conexão e exemplos de filtros.

---

## 2. `leai doctor` (ou `leai check`)

Executa uma bateria de testes preventivos para garantir que seu ambiente está 100% pronto para o LEAI.

```bash
leai doctor
```

### O que o `doctor` valida:
* **Conectividade:** Consegue estabelecer conexão TCP com o Oracle no host e porta indicados?
* **Permissões de Dicionário:** O usuário possui privilégio de leitura nas views `ALL_TABLES`, `ALL_TAB_COLUMNS`, `ALL_CONSTRAINTS`, `ALL_SOURCE` e `ALL_SYNONYMS`?
* **Diretórios Locais:** Os caminhos para `rawPath`, `annotationsPath` e `docPath` existem e possuem permissão de escrita?
* **Chaves de API de IA:** Alguma chave de LLM está configurada para uso nos comandos `ask`, `chat` e `enrich`?

---

## 3. `leai changes`

Analisa a evolução do banco comparando o snapshot atual de extração (`./raw/`) com execuções anteriores, detectando *schema drift*.

```bash
leai changes
```

### Relatório de Modificações:
* Tabelas, colunas ou views **criadas**.
* Objetos ou colunas **removidas**.
* Alterações em tipos de dados ou precisão (ex: `NUMBER(10)` alterado para `NUMBER(12)`).
* Procedures ou triggers com assinaturas ou código fonte modificados.
