"""The services that translate: any of them takes the same prompt and gives
back the same JSON, so a run can go on with another when one runs out.

A prompt comes in two parts: `fixed` first, the same in many requests one
after another, which each service caches, then `varying`."""

import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TIMEOUT_S = 1200


class ProviderError(Exception):
    pass


class Provider:
    name = ""

    def __init__(self, model: str = "", **options):
        self.model = model
        self.options = options
        # what each request used, as far as the service says
        self.usage: list[dict] = []

    def usage_total(self) -> dict:
        total = {}
        for u in self.usage:
            for k, v in u.items():
                total[k] = total.get(k, 0) + (v or 0)
        return total

    @property
    def effort(self) -> str:
        return self.options.get("effort", "")

    @property
    def marker(self) -> str:
        marker = f"{self.name}/{self.model or 'default'}"
        return f"{marker}/{self.effort}" if self.effort else marker

    @property
    def stamp(self) -> str:
        """What marks a string this provider wrote or reviewed today."""
        return f"{self.marker} {datetime.date.today().isoformat()}"

    def run(self, fixed: str, varying: str, schema: dict) -> list[dict]:
        """The list the model gave under the schema's one key."""
        raise NotImplementedError


def _executable(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ProviderError(f"{name} is not on PATH")
    return path


def _run(cmd: list[str], stdin: str, cwd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            timeout=TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ProviderError(f"{cmd[0]} took longer than {TIMEOUT_S} s")


def _answer(data, schema: dict) -> list[dict]:
    key = schema["required"][0]
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise ProviderError(f"unexpected answer: {str(data)[:300]}")
    return data[key]


class ClaudeCli(Provider):
    """Claude Code in print mode, with no tools and none of this repo's
    settings: run from an empty folder. It caches the system prompt on its
    own, so the fixed part goes there, from a file: it is longer than a
    command line may be."""

    name = "claude"

    def run(self, fixed, varying, schema):
        cmd = [
            _executable("claude"),
            "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--tools", "",
            "--no-session-persistence",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--system-prompt-file", "system.txt",
        ]  # fmt: skip
        if self.model:
            cmd += ["--model", self.model]
        if self.effort:
            cmd += ["--effort", self.effort]

        with tempfile.TemporaryDirectory() as cwd:
            (Path(cwd) / "system.txt").write_text(fixed, encoding="utf-8")
            proc = _run(cmd, varying, cwd)

        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise ProviderError(
                f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[-500:]}"
            )
        u = out.get("usage") or {}
        self.usage.append(
            {
                "input": u.get("input_tokens"),
                "cache_write": u.get("cache_creation_input_tokens"),
                "cache_read": u.get("cache_read_input_tokens"),
                "output": u.get("output_tokens"),
                "cost_usd": out.get("total_cost_usd"),
            }
        )
        if out.get("is_error") or "structured_output" not in out:
            raise ProviderError(f"claude: {str(out.get('result'))[:500]}")
        return _answer(out["structured_output"], schema)


class CodexCli(Provider):
    """Codex in exec mode, read-only, in an empty folder. OpenAI caches the
    start of a prompt it has seen lately on its own."""

    name = "codex"

    def run(self, fixed, varying, schema):
        with tempfile.TemporaryDirectory() as cwd:
            schema_path = Path(cwd) / "schema.json"
            out_path = Path(cwd) / "out.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")

            cmd = [
                _executable("codex"),
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                "--output-schema", str(schema_path),
                "--output-last-message", str(out_path),
            ]  # fmt: skip
            if self.model:
                cmd += ["--model", self.model]
            if self.effort:
                cmd += ["--config", f'model_reasoning_effort="{self.effort}"']
            cmd.append("-")

            proc = _run(cmd, fixed + "\n\n" + varying, cwd)

            if proc.returncode != 0 or not out_path.exists():
                raise ProviderError(
                    f"codex exited {proc.returncode}: {(proc.stderr or proc.stdout)[-500:]}"
                )
            text = out_path.read_text(encoding="utf-8")

        try:
            return _answer(json.loads(text), schema)
        except json.JSONDecodeError:
            raise ProviderError(f"codex answered no JSON: {text[:300]}")


class OpenRouter(Provider):
    name = "openrouter"
    url = "https://openrouter.ai/api/v1/chat/completions"

    def run(self, fixed, varying, schema):
        import requests  # noqa: PLC0415 - only this provider needs it

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": fixed,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                },
                {"role": "user", "content": varying},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "translations",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        if self.effort:
            body["reasoning"] = {"effort": self.effort}
        body["usage"] = {"include": True}

        try:
            r = requests.post(
                self.url,
                headers={"Authorization": f"Bearer {_openrouter_key()}"},
                json=body,
                timeout=TIMEOUT_S,
            )
        except requests.RequestException as e:
            raise ProviderError(f"openrouter: {e}")
        if r.status_code != 200:
            raise ProviderError(f"openrouter {r.status_code}: {r.text[:500]}")

        try:
            data = r.json()
            u = data.get("usage") or {}
            details = u.get("prompt_tokens_details") or {}
            self.usage.append(
                {
                    "input": u.get("prompt_tokens"),
                    "cache_write": details.get("cache_write_tokens"),
                    "cache_read": details.get("cached_tokens"),
                    "output": u.get("completion_tokens"),
                    "cost_usd": u.get("cost"),
                }
            )
            content = data["choices"][0]["message"]["content"]
            return _answer(json.loads(content), schema)
        except (KeyError, IndexError, json.JSONDecodeError, TypeError):
            raise ProviderError(f"openrouter answered: {r.text[:500]}")


def _openrouter_key() -> str:
    if key := os.environ.get("OPENROUTER_API_KEY"):
        return key

    from scripts.translations.pipeline.config import LOCAL  # noqa: PLC0415

    path = LOCAL / "openrouter.yml"
    if path.exists():
        import yaml  # noqa: PLC0415

        key = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("api_key")
        if key:
            return key
    raise ProviderError(
        "no OpenRouter key: set OPENROUTER_API_KEY or .local/openrouter.yml"
    )


class Fake(Provider):
    """For tests: the English with the language's name in front. Keeps the
    requests it was given; a review gets `findings`."""

    name = "fake"

    def __init__(self, model: str = "", **options):
        super().__init__(model, **options)
        self.requests: list[tuple[str, str]] = []
        self.findings: list[dict] = []

    def run(self, fixed, varying, schema):
        self.requests.append((fixed, varying))
        if "findings" in schema["properties"]:
            return self.findings
        text = fixed + "\n" + varying
        strings = text.split("Strings (", 1)[1].split("\n", 1)[1]
        items = json.loads(strings.split("\n\nCode:", 1)[0])
        ask = text.split("Translate into ", 1)[1].split("\n", 1)[0]
        name, ids = ask.split(" the strings with these ids: ")
        wanted = set(ids.split(", "))
        return [
            {"id": i["id"], "text": f"[{name}] {i['text']}"}
            for i in items
            if i["id"] in wanted
        ]


PROVIDERS = {p.name: p for p in (ClaudeCli, CodexCli, OpenRouter, Fake)}


def make(name: str, settings: dict) -> Provider:
    if name not in PROVIDERS:
        raise SystemExit(f"Unknown provider {name!r}: {', '.join(PROVIDERS)}")
    options = dict(settings.get(name, {}))
    return PROVIDERS[name](**options)
