import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from leai.config import WikiJsConfig
from leai.wiki import execute_graphql, get_page_content, list_pages, search_pages


class TestWikiJsIntegration(unittest.TestCase):
    def setUp(self):
        self.config = WikiJsConfig(enabled=True, url="https://wiki.test.com", token="fake_token")

    @patch("urllib.request.urlopen")
    def test_execute_graphql_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": {"fake": "data"}}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        data = execute_graphql(self.config, "query { test }", {})
        self.assertEqual(data, {"fake": "data"})
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://wiki.test.com/graphql")
        self.assertEqual(req.headers["Authorization"], "Bearer fake_token")
        self.assertEqual(req.headers["Content-type"], "application/json")

    @patch("urllib.request.urlopen")
    def test_execute_graphql_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"errors": [{"message": "Syntax error"}]}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with self.assertRaises(RuntimeError) as ctx:
            execute_graphql(self.config, "query { error }", {})

        self.assertIn("GraphQL Error", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_execute_graphql_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://wiki.test.com/graphql",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b"Invalid token"),
        )

        with self.assertRaises(RuntimeError) as ctx:
            execute_graphql(self.config, "query { error }", {})

        self.assertIn("HTTP Error 401", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_execute_graphql_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(RuntimeError) as ctx:
            execute_graphql(self.config, "query { error }", {})

        self.assertIn("Network Error", str(ctx.exception))

    def test_execute_graphql_missing_config(self):
        empty_config = WikiJsConfig(enabled=True, url="", token="")
        with self.assertRaises(ValueError):
            execute_graphql(empty_config, "query { test }", {})

    @patch("leai.wiki.execute_graphql")
    def test_search_pages(self, mock_execute):
        mock_execute.return_value = {
            "pages": {"search": {"results": [{"id": 1, "title": "Test Page", "path": "/test", "description": "A test page"}]}}
        }
        results = search_pages(self.config, "Test")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test Page")
        mock_execute.assert_called_once()

    @patch("leai.wiki.execute_graphql")
    def test_search_pages_empty(self, mock_execute):
        mock_execute.return_value = {"pages": {"search": {"results": []}}}
        results = search_pages(self.config, "Unknown")
        self.assertEqual(len(results), 0)

    @patch("leai.wiki.execute_graphql")
    def test_list_pages(self, mock_execute):
        mock_execute.return_value = {
            "pages": {
                "list": [
                    {"id": 1, "path": "rh/ferias", "title": "Política de Férias", "description": "Regras de férias"},
                    {"id": 2, "path": "vendas/politica", "title": "Política de Vendas", "description": "Comissões"},
                ]
            }
        }
        pages = list_pages(self.config, refresh=True)
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["path"], "rh/ferias")

    @patch("leai.wiki.execute_graphql")
    def test_list_pages_cached(self, mock_execute):
        mock_execute.return_value = {"pages": {"list": [{"id": 1, "path": "rh/ferias", "title": "Política de Férias"}]}}
        pages1 = list_pages(self.config, refresh=True)
        self.assertEqual(len(pages1), 1)
        mock_execute.assert_called_once()

    @patch("leai.wiki.execute_graphql")
    def test_get_page_content(self, mock_execute):
        mock_execute.return_value = {"pages": {"singleByPath": {"content": "# Test Content"}}}
        content = get_page_content(self.config, "/test")
        self.assertEqual(content, "# Test Content")

    @patch("leai.wiki.execute_graphql")
    def test_get_page_content_not_found(self, mock_execute):
        mock_execute.return_value = {"pages": {"singleByPath": None}}
        content = get_page_content(self.config, "/unknown")
        self.assertEqual(content, "Page not found.")


if __name__ == "__main__":
    unittest.main()
