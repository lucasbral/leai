# Extração, Compilação e Análise de Impacto

Esta seção detalha os comandos responsáveis pelo pipeline principal de engenharia reversa, análise de impacto e compilação de documentos do LEAI.

---

## 1. `leai` (ou `leai generate`)

Executa o pipeline completo de ponta a ponta: extração do Oracle, geração de anotações e compilação final da documentação em Markdown.

```bash
leai
# ou com parâmetros específicos:
leai -s HR -t tables -t packages --depth 2 --rag-json
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho para o arquivo de configuração. |
| `-s`, `--schemas TEXT` | Opção | Do config | Especifica um ou mais schemas alvo. |
| `-t`, `--object-types TEXT` | Opção | Do config | Filtra categorias de objetos (ex: `tables`, `views`, `packages`). |
| `--with-traces / --no-traces` | Flag | `True` | Inclui grafos de linhagem e avaliação de risco Mermaid. |
| `--rag-json / --rag` | Flag | `False` | Exporta chunks estruturados em JSON para bancos vetoriais. |
| `-d`, `--depth INT` | Opção | `1` | Profundidade de exploração na árvore de dependências. |
| `--seaweed` | Flag | `False` | Utiliza bucket S3/SeaweedFS remoto. |
| `--no-cache` | Flag | `False` | Modo 100% remoto: não salva snapshots no disco local. |
| `--force-upload` | Flag | `False` | Força reenvio de snapshots para o storage ignorando cache SHA-256. |

---

## 2. `leai extract`

Conecta ao banco de dados Oracle configurado em `dsn` e extrai todas as definições DDL e metadados de catálogo dos schemas indicados.

```bash
leai extract
# Extração incremental dos últimos 30 dias:
leai extract --days 30
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho para o arquivo `leai.yml`. |
| `-s`, `--schemas TEXT` | Opção | Do config | Extrai apenas os schemas indicados. |
| `-t`, `--object-types TEXT` | Opção | Do config | Filtra tipos de objetos (ex: `-t tables -t views`). |
| `-d`, `--days INT` | Opção | `None` | **Extração Incremental:** Extrai apenas objetos modificados nos últimos N dias via `LAST_DDL_TIME`. |
| `--seaweed` | Flag | `False` | Envia os snapshots JSON diretamente para o bucket S3. |
| `--no-cache` | Flag | `False` | Não grava snapshots no diretório local `rawPath`. |
| `--force-upload` | Flag | `False` | Força o upload de todos os arquivos para o storage. |

---

## 3. `leai annotate`

Cria ou atualiza os arquivos de anotação de negócio em formato YAML sob `./annotations/<SCHEMA>.yml`.

```bash
leai annotate
```

> [!NOTE]
> Este comando é totalmente não-destrutivo. Ele combina os metadados extraídos com as anotações existentes, garantindo que descrições e regras já escritas manualmente nunca sejam sobrescritas.

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho para o `leai.yml`. |
| `-s`, `--schemas TEXT` | Opção | Do config | Sincroniza schemas específicos. |
| `-t`, `--object-types TEXT` | Opção | Do config | Filtra tipos de objetos a sincronizar. |
| `--seaweed` | Flag | `False` | Sincroniza anotações diretamente no storage remoto. |
| `--no-cache` | Flag | `False` | Opera em modo remoto puro sem salvar no disco. |

> [!TIP]
> Também é possível executar `/annotate` dentro da sessão interativa do copilot (`leai chat`), com suporte aos modificadores `/annotate --seaweed` (ou `-W`) e `/annotate --no-cache` para sincronização remota sem sair do terminal.

---

## 4. `leai doc <OBJECT>`

Abre o editor interativo de documentação no próprio terminal para um objeto específico (tabela, view, pacote, etc.).

```bash
leai doc TB_FUNCIONARIOS
leai doc PKG_FOLHA_PAGTO
```

Permite editar descrições de negócio e comentários de colunas diretamente pelo teclado, salvando no YAML local e permitindo recompilar a documentação Markdown imediatamente. Também pode ser chamado no chat interativo via `/doc <OBJECT>`.

---

## 5. `leai enrich`

Utiliza o provedor de IA configurado para analisar DDLs e sugerir descrições automáticas para tabelas e colunas não documentadas.

```bash
leai enrich
# Forçar regeneração para um objeto específico:
leai enrich -o TB_CLIENTES --overwrite -p gemini
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-o`, `--object-name TEXT` | Opção | `None` | Nome do objeto específico a ser enriquecido. |
| `-w`, `--overwrite` | Flag | `False` | Força a reescrita de anotações já existentes. |
| `-p`, `--provider TEXT` | Opção | Do config | Provedor de IA a ser utilizado. |
| `-m`, `--model TEXT` | Opção | Do config | Modelo de IA específico. |
| `-s`, `--schemas TEXT` | Opção | Do config | Filtra por schemas específicos. |
| `-t`, `--object-types TEXT` | Opção | Do config | Filtra categorias de objetos. |
| `--seaweed` | Flag | `False` | Lê e grava anotações diretamente no S3. |
| `--no-cache` | Flag | `False` | Não grava cópias em disco local. |

---

## 6. `leai compile`

Lê os snapshots brutos de `./raw/` e as anotações de `./annotations/`, gerando os arquivos Markdown e diagramas Mermaid sob `docPath`.

```bash
leai compile --depth 2 --rag-json
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `-c`, `--config PATH` | Opção | `leai.yml` | Caminho do arquivo de configuração. |
| `-o`, `--object-name TEXT` | Opção | `None` | Recompila apenas um objeto individual. |
| `-s`, `--schemas TEXT` | Opção | Do config | Schemas a compilar. |
| `-t`, `--object-types TEXT` | Opção | Do config | Categorias de objetos. |
| `--with-traces / --no-traces` | Flag | `True` | Inclui diagramas de linhagem Mermaid. |
| `--rag-json / --rag` | Flag | `False` | Exporta chunks JSON para bancos vetoriais. |
| `-d`, `--depth INT` | Opção | `1` | Profundidade da árvore de dependências. |
| `--seaweed` | Flag | `False` | Utiliza dados do bucket S3. |
| `--no-cache` | Flag | `False` | Não grava arquivos no disco local. |

---

## 7. `leai trace <OBJECT>`

Realiza análise de impacto e rastreamento de linhagem upstream e downstream com cálculo de risco.

```bash
leai trace TB_CONTRATOS --depth 3 --offline --output ./dossier.md
```

### Parâmetros e Opções:

| Parâmetro / Flag | Tipo | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `OBJECT` | Argumento | **Obrigatório** | Nome do objeto a ser rastreado. |
| `-d`, `--depth INT` | Opção | `1` | Profundidade máxima na árvore de dependências. |
| `-s`, `--schema TEXT` | Opção | `None` | Schema do objeto quando houver ambiguidade. |
| `--offline` | Flag | `False` | **Modo Offline:** Rastreia localmente a partir de `raw/` sem conectar ao Oracle. |
| `-o`, `--output PATH` | Opção | `None` | Salva o dossiê em Markdown no arquivo especificado. |
| `--rag-json / --rag` | Flag | `False` | Exporta chunks JSON para RAG. |
| `--seaweed` | Flag | `False` | Resolve metadados diretamente do bucket S3. |
| `--no-cache` | Flag | `False` | Opera 100% remoto. |
