from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from leai.config import LeaiConfig
from leai.oracle import (
    _CATALOG_PREFIX_CACHE,
    _detect_catalog_prefix,
    _fetch_code_objects,
    _fetch_tables,
    fetch_focal_trace,
    fetch_schema_metadata,
)


class TestOracleOptimizations(unittest.TestCase):
    def setUp(self):
        _CATALOG_PREFIX_CACHE.clear()
        self.config = LeaiConfig(
            dsn="oracle://user:pass@localhost:1521/ORCL",
            schemas=["TEST_SCHEMA"],
        )

    def test_detect_catalog_prefix_caching(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.connection = mock_conn

        # First call executes query on dba_tables
        prefix1 = _detect_catalog_prefix(mock_cursor)
        self.assertEqual(prefix1, "dba")
        self.assertEqual(mock_cursor.execute.call_count, 1)

        # Second call with same connection uses cache without executing SQL
        prefix2 = _detect_catalog_prefix(mock_cursor)
        self.assertEqual(prefix2, "dba")
        self.assertEqual(mock_cursor.execute.call_count, 1)

    def test_fetch_code_objects_batching_eliminates_n_plus_one(self):
        mock_cursor = MagicMock()

        # 1. Objects query returns 3 procedures/packages
        mock_cursor.fetchall.side_effect = [
            [
                ("PKG_1", "PACKAGE BODY"),
                ("PRC_2", "PROCEDURE"),
                ("FN_3", "FUNCTION"),
            ],
            # 2. Single batched query to _source returns all code lines
            [
                ("PKG_1", "PACKAGE BODY", "PACKAGE BODY PKG_1 IS END;"),
                ("PRC_2", "PROCEDURE", "PROCEDURE PRC_2 IS BEGIN NULL; END;"),
                ("FN_3", "FUNCTION", "FUNCTION FN_3 RETURN NUMBER IS BEGIN RETURN 1; END;"),
            ],
        ]

        target_types = {"PACKAGE", "PACKAGE BODY", "PROCEDURE", "FUNCTION"}
        code_objs = _fetch_code_objects(mock_cursor, self.config, target_types, prefix="all")

        # Must have executed exactly 2 queries total: 1 for _objects, 1 for _source (NOT 1 + 3)
        self.assertEqual(mock_cursor.execute.call_count, 2)
        self.assertEqual(len(code_objs), 3)
        names = {co.name for co in code_objs}
        self.assertEqual(names, {"PKG_1", "PRC_2", "FN_3"})

    def test_fetch_tables_unfiltered_avoids_dynamic_in_clause(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [
            # 1. _tables query
            [("TBL_A", "Comment A"), ("TBL_B", "Comment B")],
            # 2. _tab_columns query (direct WHERE owner = :owner without IN chunking)
            [
                ("TBL_A", "ID", "NUMBER", 22, 10, 0, "N", None, None, None),
                ("TBL_B", "ID", "NUMBER", 22, 10, 0, "N", None, None, None),
            ],
            # 3. pks query
            [("TBL_A", "ID"), ("TBL_B", "ID")],
            # 4. fks query
            [],
        ]

        tables = _fetch_tables(mock_cursor, self.config, prefix="all")
        self.assertEqual(len(tables), 2)
        self.assertEqual(mock_cursor.execute.call_count, 4)

        # Verify that columns query did not use dynamic IN clause placeholders
        col_exec_sql = mock_cursor.execute.call_args_list[1][0][0]
        self.assertNotIn("IN (:t", col_exec_sql)
        self.assertIn("WHERE c.owner = :owner", col_exec_sql)

    @patch("leai.oracle.oracledb.connect")
    def test_fetch_schema_metadata_connection_reuse(self, mock_connect):
        existing_conn = MagicMock()
        mock_cursor = MagicMock()
        existing_conn.cursor.return_value = mock_cursor

        # Mock query outputs
        mock_cursor.fetchall.return_value = []

        cfg = self.config.model_copy()
        cfg.object_types = ["tables"]

        # Call with existing connection
        schema_meta = fetch_schema_metadata(cfg, schema_name="TEST_SCHEMA", connection=existing_conn)

        # connect() should NOT have been called
        mock_connect.assert_not_called()
        # existing connection should NOT have been closed
        existing_conn.close.assert_not_called()
        # cursor should have arraysize tuned to 1000
        self.assertEqual(mock_cursor.arraysize, 1000)
        self.assertEqual(schema_meta.schema_name, "TEST_SCHEMA")

    @patch("leai.oracle.oracledb.connect")
    def test_fetch_focal_trace_layer_batching_and_connection_reuse(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        cfg = self.config.model_copy()
        cfg.object_types = ["tables"]

        # 1. Discover focal object type -> TABLE
        # 2. Inside fetch_schema_metadata: _tables, _tab_columns, pks, fks, timestamps
        # 3. In layer 1 dependencies batch query
        # 4. In layer 1 FKs batch query
        # 5. In layer 1 Triggers batch query
        mock_cursor.fetchall.side_effect = [
            [("TABLE",)],  # discover type
            [("TBL_A", None)],  # _tables
            [("TBL_A", "ID", "NUMBER", 22, 10, 0, "N", None, None, None)],  # cols
            [("TBL_A", "ID")],  # pks
            [],  # fks
            [],  # timestamps
            [],  # dependencies for layer
            [],  # FKs for layer
            [],  # triggers for layer
        ]

        result = fetch_focal_trace(cfg, "TBL_A", schema_name="TEST_SCHEMA", max_depth=1)
        self.assertEqual(result.focal_name, "TBL_A")
        self.assertEqual(result.focal_type, "TABLE")
        # Ensure only 1 connection was created throughout the entire trace
        self.assertEqual(mock_connect.call_count, 1)
        # Connection properly closed at end
        mock_conn.close.assert_called_once()
