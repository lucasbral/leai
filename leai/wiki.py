from typing import Any

import requests

from leai.config import WikiJsConfig


def execute_graphql(config: WikiJsConfig, query: str, variables: dict) -> dict[str, Any]:
    if not config.url or not config.token:
        raise ValueError("Wiki.js URL and Token must be configured.")

    headers = {"Authorization": f"Bearer {config.token}"}
    endpoint = f"{config.url.rstrip('/')}/graphql"

    res = requests.post(endpoint, json={"query": query, "variables": variables}, headers=headers, timeout=10)
    res.raise_for_status()
    data = res.json()
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
