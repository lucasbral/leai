# Development & Testing Guide

Thank you for contributing to **LEAI**! This document explains how to set up your local development workspace, run the test suite, and maintain code standards.

---

## 🛠️ Workspace Setup

We strongly recommend using [uv](https://github.com/astral-sh/uv) for fast, deterministic dependency management:

```bash
# 1. Clone the repository
git clone https://github.com/lucasbral/leai.git
cd leai

# 2. Synchronize virtual environment with development and documentation extras
uv sync --all-extras
```

Or using standard `pip`:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev,docs]"
```

---

## 🧪 Running the Test Suite

LEAI maintains high unit test coverage:

```bash
# Run tests with test coverage reporting
uv run coverage run -m unittest discover tests
uv run coverage report -m
```

Or via `pytest`:
```bash
uv run pytest
```

---

## 🧹 Code Quality & Linting

We enforce clean, idiomatic Python using **Ruff**:

```bash
# Run linter
uv run ruff check .

# Automatically apply fixes
uv run ruff check --fix .

# Format code
uv run ruff format .
```

---

## 📚 Previewing Documentation Locally

Launch the local documentation server with live-reloading:

```bash
uv run mkdocs serve
```

Navigate to [http://localhost:8000](http://localhost:8000) to browse both English and Portuguese documentation pages.
