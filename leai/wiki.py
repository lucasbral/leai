import json
import urllib.error
import urllib.request
from typing import Any

from leai.config import WikiJsConfig


def execute_graphql(config: WikiJsConfig, query: str, variables: dict) -> dict[str, Any]:
    if not config.url or not config.token:
        raise ValueError("Wiki.js URL and Token must be configured.")

    headers = {
        "Authorization": f"Bearer {config.token}",
        "Content-Type": "application/json",
        "User-Agent": "LEAI-Copilot",
    }
    endpoint = f"{config.url.rstrip('/')}/graphql"
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")

    req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP Error {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network Error: {exc.reason}") from exc

    if "errors" in data:
        raise RuntimeError(f"GraphQL Error: {data['errors']}")
    return data.get("data", {})


def search_pages(config: WikiJsConfig, query: str) -> list[dict[str, Any]]:
    gql = """
    query ($query: String!) {
      pages {
        search(query: $query) {
          results { id title description path }
        }
      }
    }
    """
    data = execute_graphql(config, gql, {"query": query})

    try:
        results = data.get("pages", {}).get("search", {}).get("results", [])
        return results if results else []
    except AttributeError:
        return []


def get_page_content(config: WikiJsConfig, path: str) -> str:
    gql = """
    query ($path: String!) {
      pages {
        singleByPath(path: $path) { content }
      }
    }
    """
    data = execute_graphql(config, gql, {"path": path})

    try:
        page = data.get("pages", {}).get("singleByPath")
        return page.get("content", "") if page else "Page not found."
    except AttributeError:
        return "Page not found."
