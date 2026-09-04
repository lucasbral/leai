# Extração, Compilação e Análise de Impacto

Esta seção detalha os comandos responsáveis pelo pipeline principal de engenharia reversa e análise de dados do LEAI.

---

## 1. `leai` (ou `leai generate`)

Executa o pipeline completo de ponta a ponta: extração do Oracle, geração de anotações e compilação final da documentação.

```bash
leai
# ou com arquivo de configuração customizado:
leai --config ./meu-leai.yml
```

---

## 2. `leai extract`

Conecta ao banco de dados Oracle configurado em `dsn` e extrai todas as definições DDL e metadados de catálogo dos schemas indicados.

```bash
leai extract
```

### Argumentos e Opções:
* `--schema <NOME>`: Extrai apenas um schema específico, ignorando a lista do `leai.yml`.
* `--types <LISTA>`: Sobrescreve os tipos de objetos a extrair (ex: `--types tables,views`).

Os arquivos gerados são salvos no diretório configurado em `rawPath` (padrão: `./raw/<SCHEMA>.json`).

---

## 3. `leai annotate`

Cria ou atualiza os arquivos de anotação de negócio em formato YAML sob `./annotations/<SCHEMA>.yml`.

```bash
leai annotate
```

> [!NOTE]
> Este comando é completamente não-destrutivo. Ele lê os metadados brutos gerados pela extração e combina com as anotações já existentes. Descrições já redigidas manualmente nunca serão apagadas.

---

## 4. `leai enrich`

Utiliza o provedor de IA configurado para sugerir descrições automáticas para tabelas e colunas que ainda não foram documentadas nos arquivos YAML.

```bash
leai enrich
# ou para um schema específico:
leai enrich --schema RH
```

---

## 5. `leai compile`

Lê os dados brutos de `./raw/` e as anotações de `./annotations/`, gerando arquivos Markdown organizados por schema sob o diretório `docPath` (padrão: `./docs/<SCHEMA>/`).

```bash
leai compile
```

Cada arquivo gerado inclui:
* **YAML Frontmatter:** Identificação do schema, tabela, tags de negócio e links de relacionamento.
* **Tabela de Colunas:** Tipos, anulabilidade, valores padrão e descrições.
* **Diagrama Mermaid:** Relacionamentos de chave primária e estrangeira e dependências.

---

## 6. `leai trace <OBJETO>`

Realiza a análise de impacto e rastreamento de linhagem em profundidade para qualquer objeto do banco.

```bash
leai trace NOME_DO_OBJETO
```

### Opções:
* `--depth <N>`: Profundidade máxima de exploração de dependências na árvore (padrão: `2`).
* `--schema <NOME>`: Especifica o schema do objeto quando houver ambiguidade.
* `--format <text|mermaid|json>`: Define o formato de saída no terminal.

#### Exemplo:
```bash
leai trace TB_PEDIDOS --depth 3 --format mermaid
```
