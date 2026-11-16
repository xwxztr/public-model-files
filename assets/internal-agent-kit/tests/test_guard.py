import base64
from concurrent.futures import ThreadPoolExecutor
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import guard
import configure

CONFIG = {"base_url": "https://llm.corp.example/v1", "pinned_ip": "10.20.30.40", "model": "internal-model"}


class PolicyTests(unittest.TestCase):
    def msg(self, obj=None, **kwargs):
        return {"method": "POST", "path": "/v1/chat/completions", "body": guard.encode(json.dumps(
            obj if obj is not None else {"model": "internal-model", "messages": []}).encode()), **kwargs}

    def test_accepts_private_networks(self):
        for ip in ("10.0.0.1", "172.16.0.1", "172.31.255.254", "192.168.1.1"):
            self.assertEqual(guard.Policy({**CONFIG, "pinned_ip": ip}).ip, ip)

    def test_denies_non_rfc1918(self):
        for ip in ("8.8.8.8", "127.0.0.1", "169.254.169.254", "100.64.0.1", "172.32.0.1", "::1", "0.0.0.0", "224.0.0.1"):
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                guard.Policy({**CONFIG, "pinned_ip": ip})

    def test_denies_ambiguous_base_urls(self):
        for url in ("http://corp/v1", "https://u:p@corp/v1", "https://corp/v1?target=x", "https://corp/a",
                    "https://corp/v1#x", "file:///secret", "https://corp//v1", "https://corp/v1/../a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                guard.Policy({**CONFIG, "base_url": url})

    def test_exact_route_allowlist(self):
        policy = guard.Policy(CONFIG)
        for method, route in [("GET", "/v1/chat/completions"), ("CONNECT", "x:443"),
                              ("POST", "https://evil/v1/chat/completions"), ("POST", "/v1/responses"),
                              ("POST", "/v1/chat/completions?url=x"), ("POST", "/v1/../files"),
                              ("POST", "/v1/chat%2fcompletions"), ("POST", "/v1/files")]:
            with self.subTest(route=route), self.assertRaises(ValueError):
                policy.validate(method, route, b'{"model":"internal-model"}')

    def test_denied_request_never_calls_transport(self):
        calls = []
        def transport(*a):
            calls.append(a)
            return {}
        for msg in [self.msg({"model": "external"}), self.msg(url="https://evil"), None,
                    {"method": "POST", "path": "/v1/chat/completions", "body": "###"}]:
            self.assertEqual(guard.process_request(guard.Policy(CONFIG), "SECRET", msg, transport)["status"], 403)
        self.assertEqual(calls, [])

    def test_injects_store_false_and_filters_fields(self):
        seen = []
        def transport(policy, key, body, route):
            seen.append((key, json.loads(body), route))
            return guard.error_result(200, "test")
        r = guard.process_request(guard.Policy(CONFIG), "SECRET", self.msg({"model": "internal-model", "store": True}), transport)
        self.assertEqual(r["status"], 200)
        self.assertEqual(seen, [("SECRET", {"model": "internal-model", "store": False}, "/v1/chat/completions")])

    def test_duplicate_json_and_nan_rejected(self):
        for body in (b'{"model":"internal-model","model":"other"}', b'{"model":"internal-model","n":NaN}'):
            msg = self.msg()
            msg["body"] = guard.encode(body)
            self.assertEqual(guard.process_request(guard.Policy(CONFIG), "k", msg)["status"], 403)

    def test_server_tools_remote_media_and_state_denied(self):
        fields = [{"tools": [{"type": "web_search"}]}, {"tools": [{"type": "mcp", "server_url": "https://evil"}]},
                  {"messages": [{"content": [{"image_url": {"url": "https://evil"}}]}]},
                  {"input": [{"type": "input_file", "file_id": "f"}]}, {"previous_response_id": "r"},
                  {"conversation": "c"}, {"background": False}, {"tools": "bad"}]
        for field in fields:
            with self.subTest(field=field):
                self.assertEqual(guard.process_request(guard.Policy(CONFIG), "k", self.msg({"model": "internal-model", **field}))["status"], 403)

    def test_functions_allowed_and_responses_custom_allowed(self):
        p = guard.Policy({**CONFIG, "allow_responses": True})
        p.validate("POST", "/v1/chat/completions", b'{"model":"internal-model","tools":[{"type":"function"}]}')
        p.validate("POST", "/v1/responses", b'{"model":"internal-model","tools":[{"type":"custom"}]}')

    def test_body_caps(self):
        p = guard.Policy({**CONFIG, "max_request_bytes": 10})
        self.assertEqual(guard.process_request(p, "k", self.msg())["status"], 403)
        with self.assertRaises(ValueError):
            guard.decode(guard.encode(b"abc"), 2)

    def test_transport_errors_are_redacted(self):
        def fail(*a):
            raise RuntimeError("SECRET PRIVATE_URL PROMPT")
        result = guard.process_request(guard.Policy(CONFIG), "SECRET", self.msg(), fail)
        self.assertEqual(result["status"], 502)
        self.assertNotIn(b"SECRET", guard.decode(result["body"], 1000))

    def test_pinned_tls_no_dns_no_proxy(self):
        calls = []
        class Raw:
            def settimeout(self, value): pass
            def connect(self, address): calls.append(address)
            def close(self): pass
        class Context:
            def wrap_socket(self, raw, server_hostname):
                calls.append(server_hostname)
                return raw
        with patch.object(guard.socket, "socket", return_value=Raw()), patch.object(guard.ssl, "create_default_context", return_value=Context()), patch.object(guard.socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")):
            c = guard.PinnedHTTPS(guard.Policy(CONFIG))
            c.connect()
        self.assertEqual(calls, [("10.20.30.40", 443), "llm.corp.example"])

    def test_default_tls_verifies_peer_and_hostname(self):
        context = guard.PinnedHTTPS(guard.Policy(CONFIG))._context
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_upstream_redirect_rejected_and_no_second_request(self):
        class Response:
            status = 307
        class Connection:
            def __init__(self, policy):
                self.tls_socket = self
                self.calls = []
            def connect(self): pass
            def remaining(self): return 1
            def settimeout(self, value): pass
            def request(self, *args): self.calls.append(args)
            def getresponse(self): return Response()
            def close(self): pass
        conn = Connection(None)
        with patch.object(guard, "PinnedHTTPS", return_value=conn):
            with self.assertRaises(ValueError):
                guard.upstream(guard.Policy(CONFIG), "SECRET", b"{}", "/v1/chat/completions")
        self.assertEqual(len(conn.calls), 1)

    def test_upstream_error_body_never_forwarded(self):
        class Response:
            status = 401
            def read1(self, size): raise AssertionError("private upstream error must not be read/forwarded")
        class Connection:
            def __init__(self): self.tls_socket = self
            def connect(self): pass
            def remaining(self): return 1
            def settimeout(self, value): pass
            def request(self, *args): pass
            def getresponse(self): return Response()
            def close(self): pass
        with patch.object(guard, "PinnedHTTPS", return_value=Connection()):
            result = guard.upstream(guard.Policy(CONFIG), "SECRET", b"{}", "/v1/chat/completions")
        self.assertEqual(result["status"], 401)
        self.assertNotIn(b"SECRET", guard.decode(result["body"], 1000))


class MailboxTests(unittest.TestCase):
    def test_exclusive_write_and_regular_read(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "message"
            guard.check_directory(Path(folder))
            guard.write_new(f, {"a": 1})
            self.assertEqual(guard.json_load(guard.safe_read(f, 100)), {"a": 1})
            with self.assertRaises(FileExistsError): guard.write_new(f, {"a": 2})
            with self.assertRaises(ValueError): guard.safe_read(f, 1)

    def test_hardlink_read_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            f, linked = Path(folder) / "secret", Path(folder) / "link"
            f.write_bytes(b"secret")
            os.link(f, linked)
            with self.assertRaises(ValueError): guard.safe_read(linked, 100)

    def test_symlink_read_and_write_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            f, linked = Path(folder) / "secret", Path(folder) / "link"
            f.write_bytes(b"secret")
            try:
                linked.symlink_to(f)
            except OSError:
                self.skipTest("Windows symlink privilege unavailable; hardlinks tested separately")
            with self.assertRaises((OSError, ValueError)): guard.safe_read(linked, 100)
            with self.assertRaises(FileExistsError): guard.write_new(linked, {"oops": 1})
            self.assertEqual(f.read_bytes(), b"secret")


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        handler = type("TestBridge", (guard.Bridge,), {"exchange": self.folder, "model": "internal-model", "wait_seconds": 2})
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, route, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        c.request(method, route, body, headers or {})
        r = c.getresponse()
        result = (r.status, r.read(), r.getheader("Content-Type"))
        c.close()
        return result

    def test_models_is_local_and_no_mailbox(self):
        status, body, _ = self.request("GET", "/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["data"][0]["id"], "internal-model")
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_foreign_origin_denied(self):
        self.assertEqual(self.request("GET", "/v1/models", headers={"Origin": "https://evil"})[0], 403)

    def test_bad_route_and_chunking_denied(self):
        self.assertEqual(self.request("POST", "/v1/files", b"{}")[0], 403)
        self.assertEqual(self.request("POST", "/v1/chat/completions", b"{}", {"Transfer-Encoding": "chunked"})[0], 403)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_mailbox_roundtrip_preserves_sse_and_hides_headers(self):
        sse = b'data: {"choices":[]}\n\ndata: [DONE]\n\n'
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.request, "POST", "/v1/chat/completions", b'{"model":"internal-model"}', {"Authorization": "Bearer HOST_SECRET_MUST_NOT_FORWARD"})
            deadline = time.monotonic() + 2
            requests = []
            while time.monotonic() < deadline:
                requests = list(self.folder.glob("*.req"))
                if requests: break
                time.sleep(0.01)
            self.assertEqual(len(requests), 1)
            msg = guard.json_load(guard.safe_read(requests[0], 1000))
            self.assertEqual(set(msg), {"method", "path", "body"})
            self.assertNotIn("HOST_SECRET", json.dumps(msg))
            guard.write_new(requests[0].with_suffix(".res"), {"status": 200, "content_type": "text/event-stream", "body": guard.encode(sse)})
            status, body, content_type = pending.result()
        self.assertEqual((status, body, content_type), (200, sse, "text/event-stream"))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_unavailable_host_fails_closed(self):
        self.assertEqual(self.request("POST", "/v1/chat/completions", b"{}")[0], 504)
        self.assertEqual(list(self.folder.iterdir()), [])


class ConfigurationTests(unittest.TestCase):
    def test_generated_configuration_contains_only_loopback_dummy_auth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            configure.configure(root, "internal-model", False)
            pi = json.loads((root / "pi/models.json").read_text())
            self.assertEqual(pi["providers"]["corp"]["baseUrl"], "http://127.0.0.1:8765/v1")
            oc = json.loads((root / "opencode/opencode.json").read_text())
            self.assertEqual(oc["share"], "disabled")
            self.assertEqual(oc["permission"]["bash"], "deny")
            import tomllib
            codex = tomllib.loads((root / "codex/config.toml").read_text())
            self.assertFalse(codex["analytics"]["enabled"])
            self.assertEqual(codex["otel"]["metrics_exporter"], "none")
            self.assertFalse(codex["features"]["shell_tool"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
