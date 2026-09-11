from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock

from leai.status import LiveStatusTicker, fmt_duration


class TestStatusTicker(unittest.TestCase):
    def test_fmt_duration(self):
        self.assertEqual(fmt_duration(0), "00:00")
        self.assertEqual(fmt_duration(9), "00:09")
        self.assertEqual(fmt_duration(53), "00:53")
        self.assertEqual(fmt_duration(65), "01:05")
        self.assertEqual(fmt_duration(3600), "60:00")

    def test_ticker_updates_periodically(self):
        mock_status = MagicMock()
        t0 = time.perf_counter()

        with LiveStatusTicker(
            mock_status,
            prefix="[SCHEMA (1/1)]",
            t0=t0,
            initial_msg="Extraindo Views...",
            interval=0.05,
        ) as ticker:
            # Let the ticker run in the background for ~0.2s
            time.sleep(0.2)
            ticker.update("Views Concluídas")
            time.sleep(0.1)

        # Ensure status.update was called multiple times by the background thread
        self.assertGreater(mock_status.update.call_count, 2)
        # Check that the call contains the updated message
        last_call_text = mock_status.update.call_args[0][0]
        self.assertIn("[SCHEMA (1/1)]", last_call_text)
        self.assertIn("Views Concluídas", last_call_text)

    def test_ticker_with_none_status(self):
        # Should not raise any errors when status is None
        with LiveStatusTicker(None, prefix="[SCHEMA (1/1)]", initial_msg="Test", interval=0.05) as ticker:
            ticker.update("Another message")

    def test_ticker_exception_in_status_update(self):
        # If status.update raises an exception, the ticker thread handles it gracefully
        mock_status = MagicMock()
        mock_status.update.side_effect = RuntimeError("Console detached")

        with LiveStatusTicker(mock_status, prefix="[SCHEMA]", initial_msg="Test", interval=0.05) as ticker:
            time.sleep(0.1)
            ticker.update("Fail safely")
