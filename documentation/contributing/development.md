# Guia de Desenvolvimento e Testes

Agradecemos o interesse em contribuir com o **LEAI**! Este guia explica como configurar o ambiente local de desenvolvimento, executar testes unitários e garantir os padrões de qualidade de código.

---

## 🛠️ Configuração do Ambiente

Recomendamos o uso do [uv](https://github.com/astral-sh/uv) para gerenciamento rápido do ambiente virtual:

```bash
# 1. Clonar o repositório
git clone https://github.com/lucasbral/leai.git
cd leai

# 2. Criar o ambiente virtual e instalar dependências de desenvolvimento e documentação
uv sync --all-extras
```

Se preferir `pip`:
```bash
python -m venv .venv
source .venv/bin/activate  # No Windows: .venv\Scripts\activate
pip install -e ".[dev,docs]"
```

---

## 🧪 Executando a Suíte de Testes

O LEAI possui cobertura abrangente de testes unitários com `unittest` e `pytest`:

```bash
# Executar testes com relatório de cobertura
uv run coverage run -m unittest discover tests
uv run coverage report -m
```

Ou com `pytest`:
```bash
uv run pytest
```

---

## 🧹 Formatação e Linting

Utilizamos o **Ruff** para análise estática e formatação de código:

```bash
# Verificar problemas de lint
uv run ruff check .

# Corrigir automaticamente problemas identificados
uv run ruff check --fix .

# Formatar o código
uv run ruff format .
```

---

## 📚 Visualizando a Documentação Localmente

Para iniciar o servidor local de documentação com recarregamento em tempo real (hot-reload):

```bash
uv run mkdocs serve
```

Acesse [http://localhost:8000](http://localhost:8000) no seu navegador para navegar pelas páginas em Português e Inglês.
