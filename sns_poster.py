# -*- coding: utf-8 -*-
"""
Automated hourly SNS poster for HOTFEED LIVE (standard Python 3 only).
Posts TOP 10 trends + og-image.png to:
1. Telegram Channel (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)
2. X / Twitter (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SITE_URL = "https://hotfeedlive.store"


def load_top_keywords(repo_dir, limit=10):
    trends_path = os.path.join(repo_dir, "trends.json")
    if not os.path.exists(trends_path):
        raise FileNotFoundError(f"trends.json not found at {trends_path}")

    with open(trends_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("platforms", {}).get("all", {}).get("items", [])
    if not items:
        items = []
        for k, pinfo in data.get("platforms", {}).items():
            if k == "all" or not isinstance(pinfo, dict):
                continue
            items.extend((pinfo.get("items") or [])[:3])

    keywords = []
    seen = set()
    for it in items:
        kw = (it.get("keyword") or "").strip()
        if kw and kw not in seen:
            seen.add(kw)
            keywords.append(kw)
        if len(keywords) >= limit:
            break

    updated = data.get("updated_at", "")
    return updated, keywords


def build_post_text(updated, keywords, max_chars=None):
    lines = [f"🔥 HOTFEED LIVE 실시간 검색어 TOP {len(keywords)} ({updated} KST)", ""]
    for i, kw in enumerate(keywords, 1):
        lines.append(f"{i}. {kw}")
    lines.append("")
    lines.append(f"📊 전체 보기: {SITE_URL}")
    text = "\n".join(lines)
    if max_chars and len(text) > max_chars:
        # Trim to top 5 if exceeding tweet limit
        short_lines = [f"🔥 실시간 검색어 TOP 5 ({updated} KST)", ""]
        for i, kw in enumerate(keywords[:5], 1):
            short_lines.append(f"{i}. {kw}")
        short_lines.append(f"\n📊 {SITE_URL}")
        text = "\n".join(short_lines)[:max_chars]
    return text


def post_telegram(repo_dir, updated, keywords):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("[SKIP] Telegram credentials not configured.")
        return False

    caption = build_post_text(updated, keywords)
    png_path = os.path.join(repo_dir, "og-image.png")

    if os.path.exists(png_path):
        boundary = f"----HotFeedBoundary{secrets.token_hex(8)}"
        with open(png_path, "rb") as pf:
            img_bytes = pf.read()

        parts = []
        for name, val in [("chat_id", chat_id), ("caption", caption)]:
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n{val}\r\n'.encode("utf-8")
            )
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="og-image.png"\r\n'
            f"Content-Type: image/png\r\n\r\n".encode("utf-8")
            + img_bytes
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendPhoto", data=body, method="POST"
        )
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    else:
        payload = json.dumps({"chat_id": chat_id, "text": caption}).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST"
        )
        req.add_header("Content-Type", "application/json")

    try:
        resp = urllib.request.urlopen(req, timeout=20)
        res = json.loads(resp.read())
        print("[OK] Telegram post sent:", res.get("ok"))
        return bool(res.get("ok"))
    except urllib.error.HTTPError as e:
        print(f"[ERR] Telegram failed ({e.code}): {e.read().decode('utf-8', errors='replace')[:200]}", file=sys.stderr)
        return False


def _pct(s):
    return urllib.parse.quote(str(s), safe="")


def _oauth1_header(method, url, consumer_key, consumer_secret, token, token_secret):
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    param_str = "&".join(f"{_pct(k)}={_pct(oauth_params[k])}" for k in sorted(oauth_params))
    base_str = f"{method.upper()}&{_pct(url)}&{_pct(param_str)}"
    signing_key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(
        hmac.new(signing_key.encode("utf-8"), base_str.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    oauth_params["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(oauth_params[k])}"' for k in sorted(oauth_params))


def post_x(updated, keywords):
    api_key = os.environ.get("X_API_KEY", "").strip()
    api_secret = os.environ.get("X_API_SECRET", "").strip()
    access_token = os.environ.get("X_ACCESS_TOKEN", "").strip()
    access_secret = os.environ.get("X_ACCESS_SECRET", "").strip()

    if not all([api_key, api_secret, access_token, access_secret]):
        print("[SKIP] X (Twitter) credentials not configured.")
        return False

    tweet_url = "https://api.x.com/2/tweets"
    text = build_post_text(updated, keywords, max_chars=275)
    body = json.dumps({"text": text}).encode("utf-8")
    auth_header = _oauth1_header("POST", tweet_url, api_key, api_secret, access_token, access_secret)

    req = urllib.request.Request(tweet_url, data=body, method="POST")
    req.add_header("Authorization", auth_header)
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        res = json.loads(resp.read())
        print("[OK] X post sent:", res.get("data", {}).get("id"))
        return True
    except urllib.error.HTTPError as e:
        print(f"[ERR] X post failed ({e.code}): {e.read().decode('utf-8', errors='replace')[:200]}", file=sys.stderr)
        return False


if __name__ == "__main__":
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    updated, keywords = load_top_keywords(repo_dir)
    if not keywords:
        print("[!] No keywords to post.")
        sys.exit(0)
    post_telegram(repo_dir, updated, keywords)
    post_x(updated, keywords)
