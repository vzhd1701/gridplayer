"""The few calls of Crowdin's API the pipeline makes.

Crowdin keeps a .ts string's text as it is in the file, escaped (`&lt;p&gt;`),
and its `context` as "Qt context[\\ncomment]\\nfile:line"."""

import re
import time
from dataclasses import dataclass
from xml.sax.saxutils import unescape as _xml_unescape

from scripts.translations.pipeline.ts_file import escape

API = "https://api.crowdin.com/api/v2"
PAGE = 500

_ENTITIES = {"&quot;": '"', "&apos;": "'"}
_LOCATION = re.compile(r".+:\d+$")


def unescape(text: str) -> str:
    return _xml_unescape(text, _ENTITIES)


@dataclass(frozen=True)
class CrowdinString:
    id: int
    key: tuple[str, str, str]


@dataclass(frozen=True)
class Translation:
    id: int
    string_id: int
    text: str
    provider: str | None


def string_key(text: str, context: str) -> tuple[str, str, str]:
    lines = context.split("\n")
    rest = [line for line in lines[1:] if not _LOCATION.match(line)]
    return lines[0], unescape(text), "\n".join(rest)


class Crowdin:
    def __init__(self, token: str, project_id: str, session=None):
        import requests  # noqa: PLC0415

        self.project = f"{API}/projects/{project_id}"
        self.http = session or requests.Session()
        self.http.headers["Authorization"] = f"Bearer {token}"

    @classmethod
    def from_identity(cls, path):
        import yaml  # noqa: PLC0415

        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cls(cfg["api_token"], str(cfg["project_id"]))

    def _call(self, method: str, path: str, **kwargs):
        import requests  # noqa: PLC0415

        for attempt in range(4):
            try:
                r = self.http.request(
                    method, f"{self.project}{path}", timeout=90, **kwargs
                )
            except requests.RequestException as e:
                # a write may have landed: asking again could make two
                if method != "GET" or attempt == 3:
                    raise RuntimeError(f"Crowdin: {e}") from e
                time.sleep(2**attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2**attempt)
                continue
            return r
        return r

    def get(self, path: str, **params) -> dict:
        r = self._call("GET", path, params=params)
        r.raise_for_status()
        return r.json()

    def pages(self, path: str, **params) -> list[dict]:
        out, offset = [], 0
        while True:
            data = self.get(path, limit=PAGE, offset=offset, **params)["data"]
            out.extend(item["data"] for item in data)
            if len(data) < PAGE:
                return out
            offset += PAGE

    def source_file_id(self, path: str = "/en_US.ts") -> int:
        for f in self.pages("/files"):
            if f["path"] == path:
                return f["id"]
        raise LookupError(f"{path} is not on Crowdin")

    def strings(self, file_id: int) -> list[CrowdinString]:
        return [
            CrowdinString(s["id"], string_key(s["text"], s["context"]))
            for s in self.pages("/strings", fileId=file_id)
        ]

    def top_translations(
        self, language: str, file_id: int, approved_only: bool
    ) -> list[Translation]:
        """One per string: its approved one, or the one leading."""
        params = {"fileId": file_id}
        if approved_only:
            params["approvedOnly"] = 1
        return [
            Translation(
                id=t["translationId"],
                string_id=t["stringId"],
                text=unescape(t["text"]),
                provider=t.get("provider"),
            )
            for t in self.pages(f"/languages/{language}/translations", **params)
        ]

    def translation_ids(self, string_id: int, language: str) -> set[int]:
        """Every translation a string has in a language, approved or not."""
        return {
            t["id"]
            for t in self.pages(
                "/translations", stringId=string_id, languageId=language
            )
        }

    def add_ai_translation(self, string_id: int, language: str, text: str) -> int:
        r = self._call(
            "POST",
            "/translations",
            json={
                "stringId": string_id,
                "languageId": language,
                "text": escape(text),
                "provider": "ai",
                "isPreTranslated": True,
                # not in the translation memory until someone checks it
                "addToTm": False,
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Crowdin {r.status_code}: {r.text[:300]}")
        return r.json()["data"]["id"]

    # -- screenshots

    def upload_storage(self, path) -> int:
        r = self.http.post(
            f"{API}/storages",
            data=path.read_bytes(),
            headers={"Crowdin-API-FileName": path.name, "Content-Type": "image/png"},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["data"]["id"]

    def screenshots(self) -> dict[str, int]:
        return {s["name"]: s["id"] for s in self.pages("/screenshots")}

    def put_screenshot(self, name: str, storage_id: int, existing: int | None) -> int:
        if existing is None:
            r = self._call(
                "POST", "/screenshots", json={"storageId": storage_id, "name": name}
            )
        else:
            r = self._call(
                "PUT",
                f"/screenshots/{existing}",
                json={"storageId": storage_id, "name": name, "usePreviousTags": False},
            )
        r.raise_for_status()
        return r.json()["data"]["id"]

    def replace_tags(
        self, screenshot_id: int, tags: list[tuple[int, list[int]]]
    ) -> None:
        if tags:
            body = [
                {
                    "stringId": string_id,
                    "position": {"x": x, "y": y, "width": w, "height": h},
                }
                for string_id, (x, y, w, h) in tags
            ]
        else:
            # none found: Crowdin's own reading of the picture
            body = {"autoTag": True}
        r = self._call("PUT", f"/screenshots/{screenshot_id}/tags", json=body)
        r.raise_for_status()

    def delete_screenshot(self, screenshot_id: int) -> None:
        self._call("DELETE", f"/screenshots/{screenshot_id}").raise_for_status()
