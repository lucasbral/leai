# Integração com Bancos Vetoriais e RAG

Os arquivos Markdown gerados pelo comando `leai compile` foram especificamente desenhados para servir de base de conhecimento para sistemas de **RAG (Retrieval-Augmented Generation)**.

---

## 💎 Anatomia de um Documento Otimizado para RAG

Cada arquivo gerado em `./docs/<SCHEMA>/` possui a seguinte estrutura:

```markdown
---
schema: ERGON
table: TB_FUNCIONARIOS
type: TABLE
columns: 14
primary_key: [ID_FUNC]
foreign_keys:
  - column: ID_SETOR
    references: TB_SETORES(ID)
tags:
  - recursos-humanos
  - folha-pagamento
---

# Tabela: TB_FUNCIONARIOS

Armazena o registro de empregados ativos, dados contratuais e vínculos setoriais.

## Colunas
...
```

### Por que esse formato é ideal para embeddings?
* **YAML Frontmatter:** Permite alimentar os metadados do documento no banco vetorial (`metadata={"schema": "ERGON", "type": "TABLE"}`).
* **Filtros por Metadados:** Você pode consultar a base vetorial aplicando filtros exatos (`where={"schema": "FINANCEIRO"}`) antes da busca por similaridade semântica.
* **Hierarquia Limpa:** Sessões bem delimitadas (`## Colunas`, `## Relacionamentos`, `## Triggers`) facilitam o particionamento em chunks lógicos.

---

## 🚀 Exemplo de Ingestão com Python e LangChain / Chroma

```python
from pathlib import Path
from langchain_community.document_loaders import DirectoryLoader, UnstructuredMarkdownLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# 1. Carregar os documentos gerados pelo LEAI
headers_to_split_on = [
    ("#", "Entity"),
    ("##", "Section"),
]
markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

docs = []
for md_file in Path("./docs").glob("**/*.md"):
    text = md_file.read_text(encoding="utf-8")
    chunks = markdown_splitter.split_text(text)
    for chunk in chunks:
        chunk.metadata["source"] = str(md_file)
        docs.append(chunk)

# 2. Criar o índice vetorial no Chroma
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_db = Chroma.from_documents(docs, embeddings, persist_directory="./chroma_db")

print(f"Sucesso! {len(docs)} chunks indexados para busca semântica.")
```

---

## 🗄️ Bancos Vetoriais Recomendados

* **pgvector (PostgreSQL):** Ideal se sua equipe já possui infraestrutura PostgreSQL.
* **ChromaDB / Qdrant:** Excelentes para uso local, rápido e embutido.
* **Pinecone / Weaviate:** Ideais para pipelines serverless e escalabilidade massiva.
