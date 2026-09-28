import json
import re
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from leai.config import WikiJsConfig

# In-memory cache for page listing to ensure fast autocomplete in TUI
_PAGES_CACHE: dict[str, Any] = {"data": [], "timestamp": 0.0, "url": ""}
_CACHE_TTL_SECONDS: float = 60.0


def execute_graphql(
    config: WikiJsConfig,
    query: str,
    variables: dict | None = None,
    raise_on_error: bool = True,
) -> dict[str, Any]:
    if not config.url or not config.token:
        raise ValueError("Wiki.js URL and Token must be configured.")

    headers = {
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
        "User-Agent": "LEAI-Copilot",
    }
    endpoint = f"{config.url.rstrip('/')}/graphql"
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")

    ssl_context = None
    if not getattr(config, "ssl_verify", True):
        ssl_context = ssl._create_unverified_context()

    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP Error {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network Error: {exc.reason}") from exc

    if "errors" in data and raise_on_error:
        raise RuntimeError(f"GraphQL Error: {data['errors']}")
    if raise_on_error:
        return data.get("data", {})
    return data


def list_pages(config: WikiJsConfig, refresh: bool = False) -> list[dict[str, Any]]:
    """Fetches all pages in the Wiki.js instance with in-memory caching."""
    global _PAGES_CACHE
    now = time.time()
    if (
        not refresh
        and _PAGES_CACHE["data"]
        and _PAGES_CACHE.get("url") == config.url
        and (now - _PAGES_CACHE["timestamp"]) < _CACHE_TTL_SECONDS
    ):
        return _PAGES_CACHE["data"]

    gql = """
    query {
      pages {
        list {
          id
          path
          title
          description
          locale
        }
      }
    }
    """
    try:
        data = execute_graphql(config, gql, raise_on_error=False)
        data_body = data.get("data", data) if isinstance(data, dict) else {}
        pages = data_body.get("pages", {}).get("list", [])
        if isinstance(pages, list):
            _PAGES_CACHE = {"data": pages, "timestamp": now, "url": config.url}
            return pages
    except Exception:
        pass
    return _PAGES_CACHE.get("data", [])


def search_pages(config: WikiJsConfig, query: str) -> list[dict[str, Any]]:
    """Searches pages in Wiki.js using full-text search with automatic fallback strategies."""
    gql = """
    query ($query: String!) {
      pages {
        search(query: $query) {
          results { id title description path locale }
        }
      }
    }
    """
    clean_q = query.strip()
    data = execute_graphql(config, gql, {"query": clean_q}, raise_on_error=False)
    data_body = data.get("data", data) if isinstance(data, dict) else {}
    results = data_body.get("pages", {}).get("search", {}).get("results", []) if isinstance(data_body, dict) else []

    if results:
        return results

    # Fallback 1: If query has slashes/underscores (e.g. APLICAÇÕES_/SGP_/conceitos), search individual words
    words = [w for w in re.split(r"[\W_]+", clean_q) if len(w) > 2]
    if words:
        fallback_query = " ".join(words)
        if fallback_query.lower() != clean_q.lower():
            data = execute_graphql(config, gql, {"query": fallback_query}, raise_on_error=False)
            data_body = data.get("data", data) if isinstance(data, dict) else {}
            results = data_body.get("pages", {}).get("search", {}).get("results", []) if isinstance(data_body, dict) else []
            if results:
                return results

    # Fallback 2: Search in-memory page list
    all_pages = list_pages(config)
    matching = []
    q_lower = clean_q.lower()
    for p in all_pages:
        p_path = (p.get("path") or "").lower()
        p_title = (p.get("title") or "").lower()
        if q_lower in p_path or q_lower in p_title or any(w.lower() in p_path or w.lower() in p_title for w in words):
            matching.append(p)

    return matching[:10]


def get_page_content(config: WikiJsConfig, path: str, locale: str | None = None) -> str:
    """Fetches Markdown content of a Wiki.js page using singleByPath(path, locale)."""
    raw_path = path.strip().strip("/")
    target_locale = locale or getattr(config, "locale", "en") or "en"

    # Check if path starts with locale prefix (e.g. "pt/aplicacoes/sgp" or "en/...")
    parts = raw_path.split("/", 1)
    if len(parts) == 2 and len(parts[0]) in (2, 5) and parts[0].isalpha():
        target_locale = parts[0]
        raw_path = parts[1]

    gql = """
    query ($path: String!, $locale: String!) {
      pages {
        singleByPath(path: $path, locale: $locale) {
          id
          path
          title
          locale
          content
        }
      }
    }
    """

    locales_to_try = [target_locale]
    for alt_loc in ["en", "pt", "pt-br"]:
        if alt_loc not in locales_to_try:
            locales_to_try.append(alt_loc)

    for loc in locales_to_try:
        try:
            data = execute_graphql(config, gql, {"path": raw_path, "locale": loc}, raise_on_error=False)
            # Check for permission error
            errors = data.get("errors", []) if isinstance(data, dict) else []
            for err in errors:
                msg = err.get("message", "")
                code = err.get("extensions", {}).get("exception", {}).get("code")
                if code == 6013 or "not authorized" in msg.lower() or "forbidden" in msg.lower():
                    return (
                        f"[Permissão Negada]: O token de API do Wiki.js não possui permissão de leitura "
                        f"para o caminho '{raw_path}' (Locale: {loc}). Libere a permissão para esse caminho "
                        "no painel de Administração > Grupos/Permissões do Wiki.js."
                    )
            data_body = data.get("data", data) if isinstance(data, dict) else {}
            page = data_body.get("pages", {}).get("singleByPath") if isinstance(data_body, dict) else None
            if page and isinstance(page, dict) and page.get("content"):
                return page["content"]
        except Exception:
            continue

    # Fallback: check list_pages to find matching path case-insensitively
    try:
        all_pages = list_pages(config)
        for p in all_pages:
            p_path = p.get("path", "")
            p_loc = p.get("locale") or target_locale
            if p_path.lower() == raw_path.lower() or p_path.lower().endswith(raw_path.lower()):
                data = execute_graphql(config, gql, {"path": p_path, "locale": p_loc}, raise_on_error=False)
                data_body = data.get("data", data) if isinstance(data, dict) else {}
                page = data_body.get("pages", {}).get("singleByPath")
                if page and isinstance(page, dict) and page.get("content"):
                    return page["content"]
    except Exception:
        pass

    return "Page not found."
