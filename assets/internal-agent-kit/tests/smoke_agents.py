"""Local mock-model compatibility test. No real credentials or company API used.

This does not prove absence of other network attempts. Prove isolation in the
generated network-disabled Sandbox as described in docs/ACCEPTANCE.zh-CN.md.
"""
import argparse
import http.cookiejar
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from configure import configure

requests_seen = []


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        body = json.dumps({"object": "list", "data": [{"id": "internal-model", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        obj = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests_seen.append({"path": self.path, "model": obj.get("model"), "tools": len(obj.get("tools", []))})
        chunks = [
            {"id": "chatcmpl-local", "object": "chat.completion.chunk", "created": 1, "model": "internal-model", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "INTERNAL_SMOKE_OK"}, "finish_reason": None}]},
            {"id": "chatcmpl-local", "object": "chat.completion.chunk", "created": 1, "model": "internal-model", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}},
        ]
        body = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def clean_env(home):
    env = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP", "COMSPEC", "PATHEXT", "PATH")}
    env.update(USERPROFILE=str(home), HOME=str(home), APPDATA=str(home / "appdata"),
               LOCALAPPDATA=str(home / "local"), PI_CODING_AGENT_DIR=str(home / "pi"),
               DSH_HOME=str(home / "dsh"), CODEX_HOME=str(home / "codex"),
               XDG_CONFIG_HOME=str(home / "config"), XDG_DATA_HOME=str(home / "data"),
               XDG_CACHE_HOME=str(home / "cache"), CORP_SANDBOX_DUMMY_KEY="sandbox-placeholder",
               PI_OFFLINE="1", PI_TELEMETRY="0", DSH_TELEMETRY_DISABLED="1",
               OPENCODE_DISABLE_AUTOUPDATE="1", OPENCODE_DISABLE_MODELS_FETCH="1",
               OPENCODE_DISABLE_PROJECT_CONFIG="1", OPENCODE_PURE="1", OTEL_SDK_DISABLED="true",
               OPENCODE_CONFIG=str(home / "opencode/opencode.json"))
    return env


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--agent", choices=("pi", "opencode", "deepseek", "codex"), required=True)
    a = p.parse_args()
    root = a.kit.resolve()
    vendor = root / "payload/vendor"
    if not vendor.exists(): vendor = root / "vendor"
    node = str(root / "payload/runtime/node/node.exe")
    mock = HTTPServer(("127.0.0.1", 8765), Mock)
    thread = threading.Thread(target=mock.serve_forever, daemon=True)
    thread.start()
    with tempfile.TemporaryDirectory(prefix="agent-smoke-") as folder:
        home = Path(folder)
        configure(home, "internal-model", False)
        env = clean_env(home)
        commands = {
            "pi": [node, str(vendor / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"),
                   "--offline", "--no-session", "--no-extensions", "--no-mcp", "--no-skills", "--no-prompt-templates", "--no-themes",
                   "--tools", "read,edit,write", "--provider", "corp", "--model", "internal-model", "-p", "Reply INTERNAL_SMOKE_OK"],
            "opencode": [str(root / "payload/runtime/opencode/opencode.exe"), "run", "--format", "json", "-m", "corp/internal-model", "Reply INTERNAL_SMOKE_OK"],
            "deepseek": [node, str(vendor / "node_modules/@deepseek-ai/dsh/lib/bin.js"), "web", "--host", "127.0.0.1", "--no-open"],
            "codex": [str(root / "payload/runtime/codex/codex.exe"), "features", "list"],
        }
        if a.agent == "deepseek":
            log_path = home / "startup.txt"
            with log_path.open("wb") as log:
                proc = subprocess.Popen(commands[a.agent], env=env, cwd=home, stdout=log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 25
                ok = False
                while time.monotonic() < deadline and proc.poll() is None:
                    text = log_path.read_text(encoding="utf-8", errors="replace")
                    match = re.search(r"http://127\.0\.0\.1:\d+/\?token=[A-Za-z0-9_-]+", text)
                    if match:
                        try:
                            response = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())).open(match[0], timeout=3)
                            page = response.read(65536)
                            ok = response.status == 200 and (b"<html" in page.lower() or b"<!doctype html" in page.lower())
                            if not ok: print('web_probe_status', response.status, 'content_type', response.headers.get('Content-Type'), 'prefix', repr(page[:160]))
                            if ok: break
                        except Exception as error:
                            print('web_probe_error', type(error).__name__, getattr(error, 'code', None))
                    time.sleep(0.25)
                running = proc.poll() is None
                if running: proc.terminate()
                proc.wait(timeout=15)
            output = log_path.read_text(encoding="utf-8", errors="replace")
            # Redact ephemeral local UI token from shareable evidence.
            output = re.sub(r"token=[A-Za-z0-9_-]+", "token=REDACTED", output)
            print(output[-10000:])
            print(json.dumps({"agent": a.agent, "web_startup": ok, "html_http_200": ok, "still_running": running}))
        else:
            result = subprocess.run(commands[a.agent], env=env, cwd=home, capture_output=True, timeout=75)
            output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            ok = result.returncode == 0 and (a.agent == "codex" or "INTERNAL_SMOKE_OK" in output)
            print(output[-6000:])
            print(json.dumps({"agent": a.agent, "ok": ok, "exit": result.returncode, "requests": requests_seen}))
    mock.shutdown()
    mock.server_close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
