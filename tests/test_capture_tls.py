"""Real loopback HTTPS/WSS checks; all certificates and tokens are synthetic."""
import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import os
from pathlib import Path
import socket
import ssl
import tempfile
import types
import unittest
from unittest.mock import patch

from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


spec = importlib.util.spec_from_file_location(
    "capture_tls", Path(__file__).parents[1] / "tools/capture_bluetooth.py"
)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
TOKEN = "synthetic-capture-token"


def issue(name, key, issuer=None, issuer_key=None, ca=False):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(subject)
               .issuer_name(issuer.subject if issuer else subject)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(hours=1))
               .not_valid_after(now + timedelta(days=1))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), True)
               .add_extension(x509.KeyUsage(True, False, not ca, False, False,
                                            ca, ca, False, False), True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                   (issuer_key or key).public_key()), False))
    if not ca:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
        builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
    return builder.sign(issuer_key or key, hashes.SHA256())


def make_chain(directory, name, weak_part=None, bits=2048, elliptic=False):
    def key(part):
        if elliptic:
            return ec.generate_private_key(ec.SECP256R1())
        return rsa.generate_private_key(65537, bits if part == weak_part else 2048)

    root_key, intermediate_key, leaf_key = [key(part) for part in ("root", "intermediate", "leaf")]
    root = issue(name + " root", root_key, ca=True)
    intermediate = issue(name + " intermediate", intermediate_key, root, root_key, ca=True)
    leaf = issue("localhost", leaf_key, intermediate, intermediate_key)
    certfile, keyfile = directory / (name + ".pem"), directory / (name + ".key")
    # The verified trust anchor is deliberately absent from the server's chain.
    certfile.write_bytes(leaf.public_bytes(serialization.Encoding.PEM)
                         + intermediate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    keyfile.chmod(0o600)
    return root, certfile, keyfile


class TestNativeCaptureTLS(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="rf TLS fixtures ")
        cls.directory = Path(cls.temporary.name)
        cls.fixtures = {"rsa": make_chain(cls.directory, "rsa"),
                        "ec": make_chain(cls.directory, "ec", elliptic=True),
                        "untrusted": make_chain(cls.directory, "untrusted")}
        for part in ("root", "intermediate", "leaf"):
            for bits in (1024, 2047):
                name = f"{part}-{bits}"
                cls.fixtures[name] = make_chain(cls.directory, name, part, bits)
        cls.bundle = cls.directory / "trusted.pem"
        cls.bundle.write_bytes(b"".join(value[0].public_bytes(serialization.Encoding.PEM)
            for name, value in cls.fixtures.items() if name != "untrusted"))
        cls.empty_ca_directory = cls.directory / "empty"
        cls.empty_ca_directory.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    async def run_case(self, name, version, expected, wrong_host=False, redirect=False):
        root, certfile, keyfile = self.fixtures[name]
        state = {"requests": 0, "authenticated": False, "commands": [], "errors": []}

        async def handler(request):
            state["requests"] += 1
            state["tls"] = request.transport.get_extra_info("ssl_object")
            websocket = web.WebSocketResponse()
            await websocket.prepare(request)
            await websocket.send_json({"type": "auth_required"})
            try:
                auth = await websocket.receive_json(timeout=2)
                state["authenticated"] = auth.get("access_token") == TOKEN
                await websocket.send_json({"type": "auth_ok"})
                for _ in range(2):
                    command = await websocket.receive_json(timeout=2)
                    state["commands"].append(command["type"])
                    await websocket.send_json({"type": "result", "id": command["id"], "success": True})
                await websocket.send_json({"type": "event", "event": {"synthetic": True}})
                await websocket.receive(timeout=2)
            except (TypeError, ConnectionError) as error:
                # A rejected plaintext redirect closes before authentication.
                if not redirect or state["authenticated"]:
                    state["errors"].append(type(error).__name__)
            return websocket

        app = web.Application()
        app.router.add_get("/api/websocket", handler)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = context.maximum_version = version
        context.set_ciphers("DEFAULT:@SECLEVEL=0")  # Only synthetic server fixtures.
        context.load_cert_chain(certfile, keyfile)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        site = web.SockSite(runner, listener, ssl_context=context)
        await site.start()
        extra_runner = None
        try:
            def calibrate():
                oracle = ssl.create_default_context(cadata=root.public_bytes(serialization.Encoding.PEM).decode())
                oracle.minimum_version = ssl.TLSVersion.TLSv1_2
                oracle.maximum_version = version
                oracle.set_ciphers("DEFAULT:@SECLEVEL=0")
                with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
                    with oracle.wrap_socket(raw, server_hostname="localhost") as tls:
                        return tls.version()

            self.assertEqual(await asyncio.to_thread(calibrate),
                             "TLSv1.2" if version == ssl.TLSVersion.TLSv1_2 else "TLSv1.3")
            if redirect:
                plain_socket = socket.socket()
                plain_socket.bind(("127.0.0.1", 0))
                plain_socket.listen()
                plain_site = web.SockSite(runner, plain_socket)
                await plain_site.start()
                plain_port = plain_socket.getsockname()[1]
                redirect_app = web.Application()

                async def downgrade(request):
                    raise web.HTTPFound(f"http://localhost:{plain_port}/api/websocket")

                redirect_app.router.add_get("/api/websocket", downgrade)
                extra_runner = web.AppRunner(redirect_app, access_log=None)
                await extra_runner.setup()
                redirect_socket = socket.socket()
                redirect_socket.bind(("127.0.0.1", 0))
                redirect_socket.listen()
                port = redirect_socket.getsockname()[1]
                await web.SockSite(extra_runner, redirect_socket, ssl_context=context).start()
            with tempfile.TemporaryDirectory() as output_directory:
                output = Path(output_directory) / "capture.jsonl"
                env = {"SSL_CERT_FILE": str(self.bundle), "SSL_CERT_DIR": str(self.empty_ca_directory),
                       "https_proxy": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1"}
                with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
                    url = f"https://{'127.0.0.1' if wrong_host else 'localhost'}:{port}"
                    if expected:
                        await capture.capture(url, TOKEN, output, .05)
                    else:
                        with self.assertRaises(RuntimeError):
                            await capture.capture(url, TOKEN, output, .05)
                self.assertNotIn(TOKEN, output.read_text())
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(state["authenticated"], expected)
            self.assertEqual(state["requests"], 1 if expected or redirect else 0)
            self.assertEqual(len(state["commands"]), 2 if expected else 0)
            self.assertEqual(state["errors"], [])
        finally:
            if extra_runner:
                await extra_runner.cleanup()
            await runner.cleanup()

    async def test_exact_chain_minima_before_http_and_credentials(self):
        for name in self.fixtures:
            for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
                with self.subTest(chain=name, version=version.name):
                    await self.run_case(name, version, name in {"rsa", "ec"})

    async def test_hostname_verification_is_retained(self):
        await self.run_case("rsa", ssl.TLSVersion.TLSv1_3, False, wrong_host=True)

    async def test_plaintext_redirect_never_receives_token(self):
        await self.run_case("rsa", ssl.TLSVersion.TLSv1_3, False, redirect=True)


class TestCapturePolicy(unittest.TestCase):
    def test_ec_certificate_metadata_minimum(self):
        for curve, accepted in ((ec.SECP192R1(), False), (ec.SECP224R1(), True)):
            key = ec.generate_private_key(curve)
            certificate = issue("synthetic EC metadata", key, ca=True)
            der = certificate.public_bytes(serialization.Encoding.DER)
            connection = types.SimpleNamespace(get_verified_chain=lambda: [der])
            with self.subTest(bits=curve.key_size):
                if accepted:
                    capture._check_verified_keys(connection)
                else:
                    with self.assertRaises(ssl.SSLError):
                        capture._check_verified_keys(connection)

    def test_missing_or_empty_verified_chain_fails_closed(self):
        for connection in (object(), types.SimpleNamespace(get_verified_chain=lambda: [])):
            with self.subTest(connection=connection), self.assertRaises(ssl.SSLError):
                capture._check_verified_keys(connection)

    def test_stricter_floor_and_cipher_selection_are_preserved(self):
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384:@SECLEVEL=3")
        original = context.get_ciphers()
        with patch.object(capture.ssl, "create_default_context", return_value=context):
            result = capture.verified_context()
        self.assertEqual(result.minimum_version, ssl.TLSVersion.TLSv1_3)
        self.assertEqual(result.security_level, 3)
        self.assertEqual(result.get_ciphers(), original)

    def test_weaker_floor_is_raised_without_expanding_cipher_selection(self):
        context = ssl.create_default_context()
        context.set_ciphers("ECDHE-RSA-AES256-GCM-SHA384:@SECLEVEL=1")
        names = [cipher["name"] for cipher in context.get_ciphers()]
        with patch.object(capture.ssl, "create_default_context", return_value=context):
            result = capture.verified_context()
        self.assertGreaterEqual(result.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(result.security_level, 2)
        self.assertEqual([cipher["name"] for cipher in result.get_ciphers()], names)
