"""Generate only sandbox-local agent configuration. Contains no real credentials."""
import argparse
import json
from pathlib import Path


def configure(root: Path, model: str, responses: bool):
    def put(relative, text):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    def js(relative, value):
        put(relative, json.dumps(value, ensure_ascii=True, indent=2))
    model_info = {"id": model, "name": "Company internal model", "reasoning": False,
                  "input": ["text"], "contextWindow": 32768, "maxTokens": 8192,
                  "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                  "compat": {"supportsDeveloperRole": False, "supportsStore": False,
                             "supportsUsageInStreaming": False}}
    js("pi/models.json", {"providers": {"corp": {"baseUrl": "http://127.0.0.1:8765/v1",
       "api": "openai-completions", "apiKey": "sandbox-placeholder", "models": [model_info]}}})
    js("pi/settings.json", {"enableInstallTelemetry": False, "packages": [], "extensions": [],
        "skills": [], "prompts": [], "themes": [], "defaultProvider": "corp", "defaultModel": model})
    js("opencode/opencode.json", {"model": "corp/" + model, "small_model": "corp/" + model,
        "enabled_providers": ["corp"], "share": "disabled", "autoupdate": False,
        "plugin": [], "mcp": {}, "lsp": False, "formatter": False,
        "permission": {"*": "ask", "read": "allow", "edit": "ask", "bash": "deny",
                       "webfetch": "deny", "websearch": "deny", "external_directory": "deny"},
        "provider": {"corp": {"npm": "@ai-sdk/openai-compatible", "name": "Internal only",
            "options": {"baseURL": "http://127.0.0.1:8765/v1", "apiKey": "sandbox-placeholder"},
            "models": {model: {"name": "Internal only", "limit": {"context": 32768, "output": 8192}}}}}})
    put("codex/config.toml", f'''model = {json.dumps(model)}
model_provider = "corp"
approval_policy = "on-request"
sandbox_mode = "read-only"
web_search = "disabled"
check_for_update_on_startup = false
[model_providers.corp]
name = "Company internal model"
base_url = "http://127.0.0.1:8765/v1"
env_key = "CORP_SANDBOX_DUMMY_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
[features]
shell_tool = false
apply_patch_freeform = false
plugins = false
remote_plugin = false
plugin_sharing = false
skill_search = false
skill_mcp_dependency_install = false
workspace_dependencies = false
shell_snapshot = false
system_proxy_fallback = false
[analytics]
enabled = false
[feedback]
enabled = false
[otel]
exporter = "none"
metrics_exporter = "none"
log_user_prompt = false
[history]
persistence = "none"
''')
    js("dsh/profiles/web/package.json", {"private": True, "type": "module", "dsh": {
        "profile": {"bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app"]}}})
    put("dsh/profiles/web/cordis.yml", "[]\n")
    # Remove download, remote access, telemetry and command execution surfaces.
    disabled = ["session-telemetry-otel", "desktop-product-telemetry", "product-analytics",
                "deepseek-account", "llm-deepseek-account", "llm-deepseek",
                "api-remotes", "account-controller", "tool-plugin-manager",
                "web-search-deepseek", "web-fetch-http", "mcp-resources", "tool-pwsh",
                "tool-pwsh-persistent", "tool-bash", "tool-bash-persistent", "tool-cordis",
                "tool-subagent", "tool-subagent-fork", "tool-workflow", "tool-jobs", "tool-schedule"]
    patch = "".join(f"- id: {item}\n  disabled: true\n" for item in disabled)
    patch += f'''- id: llm-pi-ai
  config:
    providers:
      corp:
        apiKeyEnv: CORP_SANDBOX_DUMMY_KEY
        api: openai-completions
        baseURL: http://127.0.0.1:8765/v1
        models:
          - id: {json.dumps(model)}
            contextWindow: 32768
            maxTokens: 8192
            input: [text]
- id: agent-default-model
  config:
    provider: corp
    model: {json.dumps(model)}
'''
    put("dsh/profiles/web/cordis.patch.yml", patch)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--settings", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    a = p.parse_args()
    settings = json.loads(a.settings.read_text(encoding="utf-8-sig"))
    configure(a.root, settings["model"], settings.get("allow_responses", False))
