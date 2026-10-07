#!/usr/bin/env python3
"""Capture HA Bluetooth observations privately. No radio commands are sent."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit


def validate_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise argparse.ArgumentTypeError("Use an http:// or https:// Home Assistant URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("Do not include credentials, query parameters or fragments in the URL")
    return value.rstrip("/")


def duration(value):
    seconds = int(value)
    if not 1 <= seconds <= 600:
        raise argparse.ArgumentTypeError("Duration must be between 1 and 600 seconds")
    return seconds


async def capture(url, token, output, seconds):
    import aiohttp

    try:
        await _capture(aiohttp, url, token, output, seconds)
    except aiohttp.ClientError:
        raise RuntimeError("Home Assistant connection failed") from None


async def _capture(aiohttp, url, token, output, seconds):
    # Refuse overwrites and make the capture owner-readable only from creation.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    events = 0
    with os.fdopen(fd, "w") as stream:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.ws_connect(url + "/api/websocket", heartbeat=20) as ws:
                greeting = await asyncio.wait_for(ws.receive_json(), 15)
                if greeting.get("type") != "auth_required":
                    raise RuntimeError("Unexpected Home Assistant authentication greeting")
                await ws.send_json({"type": "auth", "access_token": token})
                if (await asyncio.wait_for(ws.receive_json(), 15)).get("type") != "auth_ok":
                    raise RuntimeError("Home Assistant authentication failed")
                for request_id, command in enumerate((
                    "bluetooth/subscribe_scanner_details",
                    "bluetooth/subscribe_advertisements",
                ), 1):
                    await ws.send_json({"id": request_id, "type": command})
                pending = {1, 2}
                loop = asyncio.get_running_loop()
                deadline = loop.time() + seconds
                while loop.time() < deadline:
                    try:
                        message = await asyncio.wait_for(ws.receive_json(), deadline - loop.time())
                    except asyncio.TimeoutError:
                        break
                    if message.get("type") == "result":
                        if not message.get("success"):
                            raise RuntimeError("Home Assistant rejected the Bluetooth subscription")
                        pending.discard(message.get("id"))
                        if not pending:
                            print("Capturing Bluetooth observations; no transmit actions are called.", flush=True)
                    if message.get("type") == "event":
                        events += 1
                    stream.write(json.dumps({
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "message": message,
                    }) + "\n")
                    stream.flush()
                if pending:
                    raise RuntimeError("Bluetooth subscriptions were not acknowledged before the deadline")
    print(f"Saved {events} event messages to {output}. Keep this file private.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, type=validate_url)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=duration, default=60)
    args = parser.parse_args()
    token = os.environ.get("HA_TOKEN", "").strip()
    if not token:
        parser.error("Supply a Home Assistant administrator access token in HA_TOKEN")
    try:
        asyncio.run(capture(args.url, token, args.output, args.seconds))
    except KeyboardInterrupt:
        print("Capture stopped; partial output retained.", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ImportError, ValueError, asyncio.TimeoutError) as error:
        # Exception details may include URLs or remote data. Do not print credentials or payloads.
        print(f"Capture failed ({type(error).__name__}); check connectivity, authentication, aiohttp and the output path.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
