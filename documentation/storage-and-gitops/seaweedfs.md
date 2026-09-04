# SeaweedFS & Object Storage S3 (`leai seaweed`)

O LEAI oferece suporte nativo e enterprise para persistência e compartilhamento de metadados em **Object Storage compatível com AWS S3**, com suporte de primeira classe ao **SeaweedFS**.

Isso permite que equipes inteiras compartilhem o mesmo catálogo técnico de metadados sem que cada desenvolvedor precise de acesso direto ao banco de dados Oracle de produção.

---

## 🏗️ Como Funciona o Armazenamento Distribuído

```mermaid
flowchart TD
    subgraph Local [Máquina do Desenvolvedor / CI-CD]
        CLI[LEAI CLI]
    end

    subgraph Remote [SeaweedFS / MinIO / AWS S3]
        BUCKET[(Bucket S3: leai)]
        RAW_REMOTE[raw/*.json]
        ANN_REMOTE[annotations/*.yml]
        BUCKET --> RAW_REMOTE & ANN_REMOTE
    end

    CLI -->|leai seaweed push| BUCKET
    BUCKET -->|leai seaweed pull| CLI
    CLI <-->|leai seaweed sync<br/>(Deduplicação SHA-256)| BUCKET
```

### Principais Benefícios:
* **Modo Zero-Cache (`no_cache: true` / `--no-cache`):** O LEAI pode operar 100% em memória ou lendo diretamente do S3 sem salvar arquivos na máquina local.
* **Sincronização Incremental por Hash SHA-256:** Somente arquivos cujo conteúdo mudou são trafegados pela rede.
* **Segurança e Isolamento:** Desenvolvedores podem rodar `leai ask`, `chat` ou `trace` localmente consumindo snapshots do S3 sem credenciais do banco Oracle.

---

## ⚡ Comandos do Grupo `seaweed`

### 1. `leai seaweed status`
Testa a conectividade com o endpoint S3, valida credenciais e relata a contagem de snapshots no bucket.

```bash
leai seaweed status
```

---

### 2. `leai seaweed push`
Envia todos os arquivos técnicos locais (`raw/`) e anotações (`annotations/`) para o bucket S3 remoto.

```bash
leai seaweed push
```

---

### 3. `leai seaweed pull`
Baixa os snapshots mais recentes do bucket remoto para os diretórios locais.

```bash
leai seaweed pull
```

---

### 4. `leai seaweed sync`
Executa uma sincronização inteligente bidirecional: calcula o hash SHA-256 de cada objeto e atualiza apenas os arquivos divergentes.

```bash
leai seaweed sync
```

---

## 🚩 Flags de SeaweedFS nos Comandos Principais

Você pode acionar o armazenamento remoto diretamente nos comandos habituais do LEAI através das seguintes flags:

* `--seaweed`: Ativa o uso do storage remoto para esta execução.
* `--no-cache`: Opera em modo remoto puro, sem gravar snapshots no disco local.
* `--force-upload`: Força o reenvio de todos os arquivos para o bucket S3, ignorando o cache SHA-256.

```bash
# Extrair do Oracle e enviar direto para o S3
leai extract --seaweed

# Rastrear linhagem lendo direto do S3 sem salvar no disco
leai trace TB_FATURAMENTO --seaweed --no-cache
```

---

## 🌐 Sincronização em Tempo Real no Web Studio (`leai serve`)

Quando o armazenamento SeaweedFS está configurado no `leai.yml`, o **LEAI Web Studio** (`leai serve` ou `/serve`) integra-se de forma transparente com o Object Storage:

* **Salvamento com Escrita Direta no S3:** Ao editar descrições de tabelas, regras de negócio ou comentários de colunas pela interface web, a rota `POST /api/annotations` persiste a alteração localmente e realiza o upload imediato para o bucket S3 remoto no prefixo `annotations/`.
* **Fallback Automático de Leitura Remota:** Ao inspecionar um objeto na rota `GET /api/object`, se a anotação YAML ainda não existir no disco local, o Web Studio tenta baixá-la dinamicamente do SeaweedFS e hidrata o cache local de maneira transparente.
* **Indicador Visual na Interface:** A barra de cabeçalho do Web Studio exibe a badge com o bucket conectado (`☁️ S3: <bucket>`) e as notificações de salvamento (*toasts*) confirmam o envio para o storage remoto.

---

## 💬 Comandos Interativos do Copilot (`/annotate`, `/update`, `/rule`)

Dentro da sessão interativa do assistente (`leai chat`):

* **/update [horas|dias] [--seaweed|-W] [--compile|-C]:** Extrai cirurgicamente objetos alterados recentemente no Oracle, atualiza as anotações, mescla com o schema consolidado, sincroniza o `glossary.yml` e envia os deltas ao SeaweedFS.
* **/annotate [--seaweed|-W] [--no-cache]:** Gera stubs de documentação para todas as tabelas e views do catálogo, sincroniza o `glossary.yml` e faz o upload síncrono para o SeaweedFS. Com `--no-cache`, a operação é feita sem persistir no disco local.
* **/rule [list|add|del|find]:** Gerencia o glossário corporativo e sincroniza diretamente com o bucket SeaweedFS.
* **/doc &lt;OBJECT&gt;:** Abre o editor TUI no terminal para anotação ágil. Suas alterações são salvas estritamente no disco local (`annotations/`), permitindo revisão e testes locais antes de serem sincronizadas via `leai seaweed push` ou Web Studio.

---

## 📖 Gestão e Sincronização do Glossário (`annotations/glossary.yml`)

O LEAI trata o glossário de negócio (`annotations/glossary.yml`) como parte integrante do repositório central no SeaweedFS:

* **Sincronização Contínua**: Toda inclusão via `leai rule add` (ou `/rule add`) e exclusão via `leai rule del` (ou `/rule del`) é enviada de forma síncrona para a chave `annotations/glossary.yml` no S3 quando o storage está ativo.
* **Mesclagem Não Destrutiva Inteligente**: Durante `leai update` ou `leai annotate`, o LEAI une os termos do arquivo local com o do bucket remoto:
  * **Prioridade para o Bucket**: Se o mesmo termo tiver definições divergentes, a versão remota do SeaweedFS é preservada para salvaguardar regras de negócio institucionais já auditadas.
  * **União de Metadados**: Tags, tabelas relacionadas e exemplos de uso são combinados sem duplicidade.
* **Resiliência do Agente de IA**: Caso o LEAI esteja rodando em contêineres ou com `--no-cache`, a ferramenta de busca de termos de negócio (`lookup_business_term`) carrega o `glossary.yml` diretamente do SeaweedFS de maneira transparente.

---

## 🧹 Políticas de Ciclo de Vida (S3 Lifecycle Rules) para `annotations/`

No S3 e no SeaweedFS, o versionamento de objetos é configurado a **nível de bucket**. Não é possível desativar o versionamento para apenas um prefixo ou subpasta específica.

No entanto, como as anotações de negócio em `annotations/*.yml` sofrem frequentes edições no Web Studio ou no editor de terminal, manter dezenas de versões históricas pode consumir espaço desnecessário no SeaweedFS — especialmente quando o controle de versão principal já é mantido via Git (`leai git`).

### Como Configurar a Limpeza de Versões Antigas no SeaweedFS

A solução padrão S3 é aplicar uma **Lifecycle Configuration** com a regra `NoncurrentVersionExpiration`, restringindo o escopo ao prefixo `annotations/`. Dessa forma, versões antigas são expiradas automaticamente após o período desejado (por exemplo, 1 dia).

#### 1. Crie o arquivo de política `lifecycle-annotations.json`:

```json
{
  "Rules": [
    {
      "ID": "PurgeOldAnnotationVersions",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "annotations/"
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 1
      }
    }
  ]
}
```

#### 2. Aplique a configuração no SeaweedFS via AWS CLI:

```bash
aws s3api put-bucket-lifecycle-configuration \
  --endpoint-url http://storage.empresa.com:8333 \
  --bucket leai-metadata \
  --lifecycle-configuration file://lifecycle-annotations.json
```

#### 3. Verifique as regras ativas:

```bash
aws s3api get-bucket-lifecycle-configuration \
  --endpoint-url http://storage.empresa.com:8333 \
  --bucket leai-metadata
```

Com essa regra, o SeaweedFS mantém sempre a versão atual da anotação disponível para o Web Studio e expira as versões não-atuais automaticamente.

---

## ⚙️ Configuração no `leai.yml`

```yaml
storage:
  seaweedfs:
    enabled: true                                  # Se true, os comandos usam S3 automaticamente
    endpoint_url: "http://storage.empresa.com:8333" # Endpoint do gateway S3
    bucket: "leai-metadata"                        # Nome do bucket
    access_key: "${SEAWEEDFS_ACCESS_KEY}"
    secret_key: "${SEAWEEDFS_SECRET_KEY}"
    region_name: "us-east-1"
    raw_prefix: "raw"                              # Prefixo para snapshots JSON
    annotations_prefix: "annotations"              # Prefixo para anotações YAML
    auto_create_bucket: true                       # Cria o bucket se não existir
    no_cache: false                                # Opera em disco ou 100% remoto
    incremental: true                              # Deduplicação SHA-256
```
