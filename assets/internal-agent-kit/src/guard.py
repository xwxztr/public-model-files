"""Restricted model relay. Python standard library only; no proxy, DNS or redirects.

The host process accepts data-only mailbox messages, never commands or URLs.
Run bridge mode ONLY in the network-disabled sandbox. See SECURITY.md.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import getpass
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

MAX_REQUEST = 4 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
ID = re.compile(r"[0-9a-f]{32}\Z")
PRIVATE = tuple(ipaddress.ip_network(s) for s in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode(value: str, limit: int) -> bytes:
    if not isinstance(value, str) or len(value) > ((limit + 2) // 3) * 4:
        raise ValueError("encoded body too large")
    data = base64.b64decode(value, validate=True)
    if len(data) > limit:
        raise ValueError("body too large")
    return data


def json_load(data: bytes):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError("duplicate JSON key")
            obj[k] = v
        return obj
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")))


def safe_read(path: Path, limit: int) -> bytes:
    """Reject final-component reparse points and links without following them.

    Parent is a dedicated, pre-created host-owned mapped directory, never a path
    supplied in a request. Hard-linked files are rejected too.
    """
    if os.name == "nt":
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        handle = create(str(path), 0x80000000, 1 | 2 | 4, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "cannot open mailbox entry")
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
            raise
    else:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        info = os.fstat(f.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                getattr(info, "st_file_attributes", 0) & 0x400 or info.st_size > limit):
            raise ValueError("unsafe mailbox file")
        data = f.read(limit + 1)
        if len(data) > limit:
            raise ValueError("mailbox entry too large")
        return data


def write_new(path: Path, obj: dict):
    # O_EXCL fails if the sandbox pre-created a symlink, junction or target file.
    data = json.dumps(obj, ensure_ascii=True, allow_nan=False).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def check_directory(path: Path):
    # All ancestors must be trusted: disallow junctions/reparse points throughout.
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("mailbox path contains a link or reparse point")


class Policy:
    def __init__(self, config: dict):
        self.url = urlsplit(config["base_url"])
        if (self.url.scheme != "https" or not self.url.hostname or self.url.username is not None
                or self.url.password is not None or self.url.query or self.url.fragment
                or self.url.path not in ("", "/", "/v1", "/v1/")):
            raise ValueError("base_url must be an HTTPS origin optionally ending /v1")
        self.ip = str(ipaddress.IPv4Address(config["pinned_ip"]))
        if not any(ipaddress.ip_address(self.ip) in n for n in PRIVATE):
            raise ValueError("pinned_ip must be RFC1918 IPv4; public, loopback and metadata IPs denied")
        self.port = self.url.port or 443
        if not 1 <= self.port <= 65535:
            raise ValueError("invalid port")
        self.model = config["model"]
        if not isinstance(self.model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", self.model) or "REPLACE" in self.model:
            raise ValueError("provide an internal model ID")
        self.routes = {"/v1/chat/completions"}
        if config.get("allow_responses", False) is True:
            self.routes.add("/v1/responses")
        self.request_limit = int(config.get("max_request_bytes", MAX_REQUEST))
        self.response_limit = int(config.get("max_response_bytes", MAX_RESPONSE))
        self.timeout = int(config.get("timeout_seconds", 180))
        self.budget = int(config.get("max_requests_per_session", 500))
        if not (1 <= self.request_limit <= MAX_REQUEST and 1 <= self.response_limit <= MAX_RESPONSE
                and 1 <= self.timeout <= 300 and 1 <= self.budget <= 5000):
            raise ValueError("invalid resource limits")
        self.ca_file = config.get("ca_file")
        self.key_env = config.get("api_key_env", "CORP_LLM_API_KEY")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.key_env):
            raise ValueError("invalid key environment name")

    def validate(self, method: str, path: str, body: bytes) -> bytes:
        if method != "POST" or path not in self.routes:
            raise ValueError("method or route denied")
        if len(body) > self.request_limit:
            raise ValueError("request too large")
        obj = json_load(body)
        if not isinstance(obj, dict) or obj.get("model") != self.model:
            raise ValueError("model denied")
        # No server-side tools that could give the upstream Internet access.
        tools = obj.get("tools", [])
        allowed_tools = {"function", "custom"} if path == "/v1/responses" else {"function"}
        if not isinstance(tools, list) or any(not isinstance(t, dict) or t.get("type") not in allowed_tools for t in tools):
            raise ValueError("only client-side function tools are permitted")
        if any(k in obj for k in ("previous_response_id", "conversation", "background")):
            raise ValueError("server-side conversation/background state denied")
        def visit(value):
            if isinstance(value, dict):
                if any(k in value for k in ("image_url", "file_url", "file_id", "input_audio")):
                    raise ValueError("remote media and uploaded file references denied")
                if value.get("type") in ("input_image", "input_file", "image", "audio", "video"):
                    raise ValueError("only text content permitted")
                for v in value.values():
                    visit(v)
            elif isinstance(value, list):
                for v in value:
                    visit(v)
        visit(obj)
        obj["store"] = False
        return json.dumps(obj, ensure_ascii=True, allow_nan=False).encode()


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, policy: Policy):
        self.deadline = time.monotonic() + policy.timeout
        super().__init__(policy.url.hostname, policy.port, timeout=policy.timeout,
                         context=ssl.create_default_context(cafile=policy.ca_file))
        self.pinned_ip = policy.ip

    def connect(self):
        # No getaddrinfo: neither proxy env vars nor the OS DNS resolver is used.
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(self.remaining())
        try:
            raw.connect((self.pinned_ip, self.port))
            raw.settimeout(self.remaining())
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
            self.tls_socket = self.sock
        except BaseException:
            raw.close()
            raise

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("upstream deadline")
        return remaining


def upstream(policy: Policy, key: str, body: bytes, path: str) -> dict:
    connection = PinnedHTTPS(policy)
    try:
        connection.connect()
        connection.tls_socket.settimeout(connection.remaining())
        connection.request("POST", path, body, {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Accept-Encoding": "identity",
        })
        connection.tls_socket.settimeout(connection.remaining())
        response = connection.getresponse()
        # http.client does not follow redirects. Never send a Location header back.
        if 300 <= response.status < 400:
            raise ValueError("upstream redirect denied")
        if not 200 <= response.status < 300:
            return error_result(response.status, "upstream_rejected_request")
        chunks, size = [], 0
        while True:
            remaining = connection.remaining()
            # response.fp owns the socket once an HTTP/1.0 response closes it.
            connection.tls_socket.settimeout(remaining)
            chunk = response.read1(min(65536, policy.response_limit - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > policy.response_limit:
                raise ValueError("upstream response too large")
            chunks.append(chunk)
        content_type = response.getheader("Content-Type", "application/json").split(";", 1)[0].lower()
        if content_type not in ("application/json", "text/event-stream"):
            raise ValueError("upstream content type denied")
        return {"status": response.status, "content_type": content_type, "body": encode(b"".join(chunks))}
    finally:
        connection.close()


def error_result(status: int, code: str) -> dict:
    return {"status": status, "content_type": "application/json",
            "body": encode(json.dumps({"error": {"message": code, "type": "relay_error"}}).encode())}


def process_request(policy: Policy, key: str, msg: dict, transport=upstream) -> dict:
    try:
        if not isinstance(msg, dict) or set(msg) != {"method", "path", "body"}:
            raise ValueError("unexpected request fields")
        body = policy.validate(msg["method"], msg["path"], decode(msg["body"], policy.request_limit))
    except (ValueError, TypeError, KeyError, RecursionError):
        return error_result(403, "policy_denied")
    try:
        return transport(policy, key, body, msg["path"])
    except Exception:
        # Do not expose key, URL, certificates, payload or upstream exceptions.
        return error_result(502, "upstream_failed_or_denied")


def serve_host(config_path: Path, exchange: Path):
    policy = Policy(json_load(config_path.read_bytes()))
    check_directory(exchange)
    key = os.environ.pop(policy.key_env, "") or getpass.getpass("Internal API key (hidden; not saved): ")
    if not key or any(ord(c) < 32 or ord(c) > 126 for c in key):
        raise ValueError("invalid API key")
    print("Host relay ready. Only the pinned private HTTPS endpoint is reachable through this relay.", flush=True)
    processed = 0
    while processed < policy.budget:
        # Sequential: at most one API request at a time, no unbounded worker pool.
        with os.scandir(exchange) as entries:
            batch = []
            for entry in entries:
                if len(batch) >= 32:
                    break
                if entry.name.endswith(".req") and ID.fullmatch(entry.name[:-4]):
                    batch.append(entry.name)
        for name in batch:
            rid = name[:-4]
            request = exchange / name
            reply = exchange / (rid + ".res")
            try:
                data = safe_read(request, policy.request_limit * 2 + 2048)
                msg = json_load(data)
            except (OSError, ValueError, RecursionError):
                # Malformed entries never reach the network.
                msg = None
            try:
                request.unlink(missing_ok=True)
            except OSError:
                continue
            if reply.exists():
                continue
            result = process_request(policy, key, msg)
            try:
                write_new(reply, result)
            except OSError:
                pass
            processed += 1
            print(f"request={processed} status={result['status']}", flush=True)
            if processed >= policy.budget:
                break
        time.sleep(0.10)
    print("Session request budget reached. Relay stopped.", flush=True)


class Bridge(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    exchange: Path
    model: str
    allow_responses: bool = False
    wait_seconds: int = 200

    def log_message(self, *args):
        pass

    def send_result(self, result):
        body = decode(result["body"], MAX_RESPONSE)
        self.send_response(int(result["status"]))
        self.send_header("Content-Type", result["content_type"])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/v1/models" or self.headers.get("Origin"):
            return self.send_result(error_result(403, "route_denied"))
        data = {"object": "list", "data": [{"id": self.model, "object": "model", "owned_by": "internal"}]}
        self.send_result({"status": 200, "content_type": "application/json", "body": encode(json.dumps(data).encode())})

    def do_POST(self):
        routes = {"/v1/chat/completions"} | ({"/v1/responses"} if self.allow_responses else set())
        if (self.path not in routes or self.headers.get("Origin") or self.headers.get("Transfer-Encoding")
                or len(self.headers.get_all("Content-Length", [])) != 1):
            return self.send_result(error_result(403, "route_or_framing_denied"))
        rid = uuid.uuid4().hex
        request, reply = self.exchange / (rid + ".req"), self.exchange / (rid + ".res")
        temporary = self.exchange / (rid + ".tmp")
        try:
            length = int(self.headers["Content-Length"])
            if not 1 <= length <= MAX_REQUEST:
                raise ValueError("length denied")
            self.connection.settimeout(15)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("incomplete body")
            write_new(temporary, {"method": "POST", "path": self.path, "body": encode(body)})
            os.rename(temporary, request)
            deadline = time.monotonic() + self.wait_seconds
            while time.monotonic() < deadline:
                try:
                    # Host .res is written exclusively; may be incomplete briefly.
                    result = json_load(safe_read(reply, MAX_RESPONSE * 2 + 2048))
                    if (not isinstance(result, dict) or set(result) != {"status", "content_type", "body"}
                            or type(result["status"]) is not int or not 200 <= result["status"] <= 599
                            or result["content_type"] not in ("application/json", "text/event-stream")):
                        raise ValueError("invalid relay response")
                    decode(result["body"], MAX_RESPONSE)
                    break
                except (FileNotFoundError, ValueError):
                    time.sleep(0.10)
            else:
                result = error_result(504, "relay_timeout")
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            result = error_result(400, "invalid_request_or_mailbox")
        finally:
            for path in (temporary, request, reply):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        self.send_result(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("host", "bridge"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--exchange", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "host":
            serve_host(args.config, args.exchange)
        else:
            settings = json_load(args.config.read_bytes())
            check_directory(args.exchange)
            Bridge.exchange, Bridge.model = args.exchange, settings["model"]
            Bridge.allow_responses = settings.get("allow_responses", False) is True
            Bridge.wait_seconds = min(320, max(20, int(settings.get("relay_wait_seconds", 200))))
            HTTPServer(("127.0.0.1", 8765), Bridge).serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception:
        print("Relay refused to start or stopped. Check local configuration and certificate trust.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
