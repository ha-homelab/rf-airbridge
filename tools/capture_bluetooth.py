#!/usr/bin/env python3
"""Capture HA Bluetooth observations privately. No radio commands are sent."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import ssl
import sys
from urllib.parse import urlsplit


def _check_verified_keys(connection):
    """Inspect the chain already verified on this connection, including its anchor."""
    from cryptography import x509
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, rsa

    get_chain = getattr(connection, "get_verified_chain", None)
    if not callable(get_chain):
        # CPython 3.12 exposes the verified chain on the underlying SSL object.
        get_chain = getattr(getattr(connection, "_sslobj", None), "get_verified_chain", None)
    if not callable(get_chain):
        raise ssl.SSLError("TLS runtime does not expose its verified certificate chain")
    chain = get_chain()
    if not isinstance(chain, list) or not chain:
        raise ssl.SSLError("TLS peer has no verified certificate chain")
    for certificate in chain:
        if isinstance(certificate, bytes):
            der = certificate
        else:
            encode = getattr(certificate, "public_bytes", None)
            pem = encode() if callable(encode) else None
            if not isinstance(pem, str):
                raise ssl.SSLError("TLS runtime returned an unsupported certificate format")
            der = ssl.PEM_cert_to_DER_cert(pem)
        try:
            key = x509.load_der_x509_certificate(der).public_key()
        except (ValueError, UnsupportedAlgorithm):
            raise ssl.SSLError("TLS certificate public key cannot be verified") from None
        if isinstance(key, rsa.RSAPublicKey):
            accepted = key.public_numbers().n.bit_length() >= 2048
        elif isinstance(key, ec.EllipticCurvePublicKey):
            accepted = key.key_size >= 224
        elif isinstance(key, dsa.DSAPublicKey):
            parameters = key.public_numbers().parameter_numbers
            accepted = parameters.p.bit_length() >= 2048 and parameters.q.bit_length() >= 224
        else:
            accepted = isinstance(key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey))
        if not accepted:
            raise ssl.SSLError("TLS certificate key is below the supported security minimum")


class _VerifiedTLS(ssl.SSLObject):
    def do_handshake(self):
        super().do_handshake()
        _check_verified_keys(self)


def verified_context():
    """Preserve default trust/hostname checks and check exact keys before HTTP."""
    context = ssl.create_default_context()
    context.minimum_version = max(context.minimum_version, ssl.TLSVersion.TLSv1_2)
    if context.security_level < 2:
        selected = [cipher["name"] for cipher in context.get_ciphers()
                    if cipher["protocol"] != "TLSv1.3"]
        context.set_ciphers(":".join([*selected, "@SECLEVEL=2"]))
    context.set_alpn_protocols(["http/1.1"])
    context.sslobject_class = _VerifiedTLS
    return context


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
        connector = aiohttp.TCPConnector(ssl=verified_context())
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                         connector=connector, trust_env=False) as session:
            async with session.ws_connect(url + "/api/websocket", heartbeat=20) as ws:
                if urlsplit(url).scheme == "https" and ws.get_extra_info("ssl_object") is None:
                    raise RuntimeError("Home Assistant HTTPS redirect lost TLS protection")
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
