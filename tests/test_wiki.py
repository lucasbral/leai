import unittest
from unittest.mock import Mock, patch

from leai.config import WikiJsConfig
from leai.wiki import execute_graphql, get_page_content, search_pages


class TestWikiJsIntegration(unittest.TestCase):
    def setUp(self):
        self.config = WikiJsConfig(enabled=True, url="https://wiki.test.com", token="fake_token")

    @patch("leai.wiki.requests.post")
    def test_execute_graphql_success(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"fake": "data"}}
        mock_post.return_value = mock_response

        data = execute_graphql(self.config, "query { test }", {})
        self.assertEqual(data, {"fake": "data"})
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://wiki.test.com/graphql")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake_token")

    @patch("leai.wiki.requests.post")
    def test_execute_graphql_error(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"errors": [{"message": "Syntax error"}]}
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as ctx:
            execute_graphql(self.config, "query { error }", {})

        self.assertIn("GraphQL Error", str(ctx.exception))

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
