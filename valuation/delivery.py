"""Durable send claim and Telegram transport.

The claim lives on a dedicated Git branch. An uncertain POST keeps the claim in
`sending`, so an automatic retry cannot duplicate a channel document.
"""
from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

from .api import KST


class DeliveryError(RuntimeError):
    pass


class DuplicateDelivery(DeliveryError):
    def __init__(self, status):
        self.status = status
        super().__init__("existing durable delivery record: " + status)


class Ledger:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.repo = os.environ.get("GITHUB_REPOSITORY", "")
        self.token = os.environ.get("GITHUB_TOKEN", "")
        if not self.repo or not self.token:
            raise DeliveryError("GitHub repository/token unavailable for durable send ledger")
        self.base = f"https://api.github.com/repos/{self.repo}"
        self.branch = "valuation-delivery-ledger"

    def _api(self, method, path, **kwargs):
        try:
            response = self.session.request(method, self.base + path,
                headers={"Authorization": "Bearer " + self.token,
                         "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"}, timeout=15, **kwargs)
        except requests.RequestException:
            raise DeliveryError("GitHub ledger request failed") from None
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise DeliveryError(f"GitHub ledger HTTP {response.status_code}")
        return response.json()

    def ensure_branch(self):
        if self._api("GET", "/git/ref/heads/" + self.branch):
            return
        repository = self._api("GET", "")
        default = repository["default_branch"]
        ref = self._api("GET", "/git/ref/heads/" + default)
        self._api("POST", "/git/refs", json={"ref": "refs/heads/" + self.branch,
                                                "sha": ref["object"]["sha"]})

    def _path(self, key):
        return "/contents/valuation-sends/" + key + ".json"

    def read(self, key):
        payload = self._api("GET", self._path(key) + "?ref=" + self.branch)
        if payload is None:
            return None, None
        return json.loads(base64.b64decode(payload["content"])), payload["sha"]

    def write(self, key, value, sha=None):
        body = {"message": "valuation delivery: " + key + " " + value["status"],
                "branch": self.branch,
                "content": base64.b64encode(json.dumps(value, ensure_ascii=False,
                                                         sort_keys=True).encode()).decode()}
        if sha:
            body["sha"] = sha
        self._api("PUT", self._path(key), json=body)

    def claim(self, key, force=False):
        self.ensure_branch()
        previous, sha = self.read(key)
        if previous and not force:
            raise DuplicateDelivery(previous["status"])
        claim = {"status": "sending", "claimed_at": datetime.now(KST).isoformat(),
                 "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
                 "previous": previous}
        self.write(key, claim, sha)
        return claim

    def complete(self, key, claim, message_id):
        current, sha = self.read(key)
        if current is None or current.get("run_id") != claim["run_id"] or current.get("status") != "sending":
            raise DeliveryError("GitHub ledger claim changed before completion")
        current.update({"status": "sent", "sent_at": datetime.now(KST).isoformat(),
                        "telegram_message_id": message_id})
        self.write(key, current, sha)


class Telegram:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not self.token or not self.chat:
            raise DeliveryError("Telegram token/chat configuration missing")
        if self.chat != "@biyosi77":
            raise DeliveryError("TELEGRAM_CHAT_ID must be @biyosi77")
        self.base = "https://api.telegram.org/bot" + self.token + "/"

    def _call(self, method, data=None):
        try:
            response = self.session.post(self.base + method, data=data, timeout=(5, 20))
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise DeliveryError("Telegram response unavailable; delivery state is uncertain") from None
        if not payload.get("ok"):
            raise DeliveryError(f"Telegram {method} rejected: HTTP {response.status_code}")
        return payload["result"]

    def check_permission(self):
        bot = self._call("getMe")
        member = self._call("getChatMember", {"chat_id": self.chat, "user_id": bot["id"]})
        if member.get("status") not in ("administrator", "creator") or (
            member.get("status") == "administrator" and member.get("can_post_messages") is not True):
            raise DeliveryError("봇에게 채널 관리자 메시지 게시 권한이 없습니다")

    def send_document(self, file: Path, caption: str):
        # Only explicit 429 rate limits are retried. A lost POST response can
        # mean the document arrived; it remains `sending` for manual review.
        for attempt in range(3):
            try:
                with Path(file).open("rb") as handle:
                    response = self.session.post(self.base + "sendDocument",
                        data={"chat_id": self.chat, "caption": caption},
                        files={"document": (Path(file).name, handle,
                                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                        timeout=(5, 60))
                payload = response.json()
            except (requests.RequestException, ValueError):
                raise DeliveryError("Telegram document response unavailable; delivery state is uncertain") from None
            if payload.get("ok"):
                return payload["result"]["message_id"]
            if response.status_code == 429 and attempt < 2:
                time.sleep(min(int(payload.get("parameters", {}).get("retry_after", 3)), 30))
                continue
            raise DeliveryError(f"Telegram sendDocument rejected: HTTP {response.status_code}")
        raise DeliveryError("Telegram rate limit retries exhausted")

    def send_failure(self, day, slot, reason, uncertain=False):
        # Reason comes from internal fixed error classes; do not include URLs or credentials.
        tail = ("문서 전송 결과가 불확실합니다. GitHub 기록과 채널을 확인한 뒤 수동 재전송하세요."
                if uncertain else "정상 보고서는 전송하지 않았습니다.")
        self._call("sendMessage", {"chat_id": self.chat,
            "text": f"밸류에이션 실패 알림: {day} {slot} — {reason}. {tail}"})
