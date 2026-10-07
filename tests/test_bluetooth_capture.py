"""Behavioral checks for the read-only Bluetooth capture tool."""
import argparse
import asyncio
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import types
import unittest


spec = importlib.util.spec_from_file_location(
    "capture_bluetooth", Path(__file__).parents[1] / "tools/capture_bluetooth.py"
)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class Connection:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def receive_json(self):
        message = next(self.messages, None)
        if message is not None:
            return message
        await asyncio.sleep(1)

    async def send_json(self, message):
        self.sent.append(message)


class TestCapture(unittest.IsolatedAsyncioTestCase):
    async def run_capture(self, output, messages):
        connection = Connection(messages)
        session = Connection([])
        session.ws_connect = lambda *args, **kwargs: connection
        http = types.SimpleNamespace(
            ClientSession=lambda **kwargs: session,
            ClientTimeout=lambda **kwargs: None,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            await capture._capture(http, "https://ha.example", "private-token", output, 0.025)
        return connection

    async def test_read_only_requests_private_file_and_no_saved_token(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture.jsonl"
            connection = await self.run_capture(output, [
                {"type": "auth_required"}, {"type": "auth_ok"},
                {"id": 1, "type": "result", "success": True},
                {"id": 1, "type": "event", "event": {"add": []}},
                {"id": 2, "type": "result", "success": True},
            ])
            self.assertEqual([x["type"] for x in connection.sent], [
                "auth", "bluetooth/subscribe_scanner_details",
                "bluetooth/subscribe_advertisements",
            ])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            content = output.read_text()
            self.assertNotIn("private-token", content)
            self.assertEqual(len([json.loads(x) for x in content.splitlines()]), 3)

    async def test_existing_capture_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture.jsonl"
            output.write_text("keep this")
            with self.assertRaises(FileExistsError):
                await self.run_capture(output, [])
            self.assertEqual(output.read_text(), "keep this")

    async def test_authentication_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "authentication failed"):
                await self.run_capture(Path(directory) / "capture.jsonl", [
                    {"type": "auth_required"}, {"type": "auth_invalid"},
                ])

    async def test_rejected_subscription(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                await self.run_capture(Path(directory) / "capture.jsonl", [
                    {"type": "auth_required"}, {"type": "auth_ok"},
                    {"id": 1, "type": "result", "success": False},
                ])

    async def test_missing_acknowledgement_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "not acknowledged"):
                await self.run_capture(Path(directory) / "capture.jsonl", [
                    {"type": "auth_required"}, {"type": "auth_ok"},
                    {"id": 1, "type": "result", "success": True},
                ])

    def test_cli_rejects_unsafe_url_and_unbounded_duration(self):
        for url in ["https://user:secret@ha.example", "file:///config", "https://ha.example/?token=secret"]:
            with self.subTest(url=url), self.assertRaises(argparse.ArgumentTypeError):
                capture.validate_url(url)
        for value in ["0", "601", "-1"]:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                capture.duration(value)
        self.assertEqual(capture.validate_url("https://ha.example/"), "https://ha.example")
        self.assertEqual(capture.duration("600"), 600)
