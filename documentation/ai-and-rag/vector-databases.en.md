# Vector Databases & RAG Integration

Markdown files compiled by `leai compile` are intentionally structured to serve as clean knowledge artifacts for enterprise **RAG (Retrieval-Augmented Generation)** systems.

---

## 💎 Anatomy of a RAG-Optimized Document

Every compiled file in `./docs/<SCHEMA>/` features structured metadata headers:

```markdown
---
schema: HR
table: EMPLOYEES_TB
type: TABLE
columns: 14
primary_key: [EMPLOYEE_ID]
foreign_keys:
  - column: DEPARTMENT_ID
    references: DEPARTMENTS(ID)
tags:
  - human-resources
  - payroll
---

# Table: EMPLOYEES_TB

Maintains active staff records, compensation tiers, and organizational units.

## Columns
...
```

### Why this format maximizes embedding accuracy:
* **YAML Frontmatter:** Feeds structured metadata directly into vector stores (`metadata={"schema": "HR", "type": "TABLE"}`).
* **Metadata Pre-Filtering:** Run precise SQL/vector hybrid queries (`where={"schema": "FINANCE"}`) before semantic similarity calculation.
* **Semantic Chunk Boundaries:** Distinct markdown sections (`## Columns`, `## Relationships`, `## Triggers`) make header-based chunking straightforward and coherent.

---

## 🚀 Ingestion Pipeline with Python & Chroma / LangChain

```python
from pathlib import Path
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# 1. Split LEAI generated markdown by semantic headers
headers_to_split_on = [
    ("#", "Entity"),
    ("##", "Section"),
]
splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

documents = []
for file_path in Path("./docs").glob("**/*.md"):
    content = file_path.read_text(encoding="utf-8")
    chunks = splitter.split_text(content)
    for chunk in chunks:
        chunk.metadata["source"] = str(file_path)
        documents.append(chunk)

# 2. Ingest into Chroma vector database
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_db = Chroma.from_documents(documents, embeddings, persist_directory="./chroma_db")

print(f"Success! {len(documents)} chunks indexed for semantic search.")
```

---

## 🗄️ Recommended Vector Engines

* **pgvector (PostgreSQL):** Best fit if your team already operates a PostgreSQL database.
* **ChromaDB / Qdrant:** Outstanding for embedded, local, and low-latency deployments.
* **Pinecone / Weaviate:** Great choices for managed cloud deployments and massive scale.
