# -*- coding: utf-8 -*-
"""
Google Indexing API client using only Python standard library.
Sends URL_UPDATED notifications so Google indexes pages faster.
Supports service account JSON file path or GOOGLE_INDEXING_SA_JSON env var.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

INDEXING_API_URL = "https://indexing.googleapis.com/v3/urlNotifications:publish"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/indexing"
BASE_URL = "https://hotfeedlive.store"


def _b64url(data):
    """Base64url encode bytes without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _find_openssl():
    """Find openssl binary across Linux/macOS/Windows (including VS Git)."""
    found = shutil.which("openssl")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Git\usr\bin\openssl.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\TeamFoundation\Team Explorer\Git\usr\bin\openssl.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _sign_rs256(message_bytes, private_key_pem):
    """Sign with RS256 using cryptography if installed, else openssl CLI."""
    private_key_pem = private_key_pem.replace("\\n", "\n")
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
        return key.sign(message_bytes, padding.PKCS1v15(), hashes.SHA256())
    except ImportError:
        pass

    openssl_bin = _find_openssl()
    if not openssl_bin:
        raise RuntimeError("Neither python cryptography nor openssl binary is available.")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", encoding="utf-8", delete=False) as kf:
        kf.write(private_key_pem)
        kf_path = kf.name
    try:
        proc = subprocess.run(
            [openssl_bin, "dgst", "-sha256", "-sign", kf_path],
            input=message_bytes,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"openssl sign failed: {proc.stderr.decode('utf-8', errors='replace')}")
        return proc.stdout
    finally:
        if os.path.exists(kf_path):
            os.unlink(kf_path)


def _create_jwt(service_account_info):
    """Create a signed JWT for Google OAuth2."""
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": service_account_info["client_email"],
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }

    segments = _b64url(json.dumps(header).encode("utf-8")) + "." + _b64url(json.dumps(payload).encode("utf-8"))
    signature = _sign_rs256(segments.encode("utf-8"), service_account_info["private_key"])
    return segments + "." + _b64url(signature)


def _get_access_token(service_account_info):
    """Exchange JWT for an access token."""
    jwt = _create_jwt(service_account_info)
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt,
    }).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())["access_token"]


def notify_url_updated(access_token, url):
    """Send a URL_UPDATED notification to Google Indexing API."""
    body = json.dumps({"url": url, "type": "URL_UPDATED"}).encode("utf-8")
    req = urllib.request.Request(INDEXING_API_URL, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        status = result.get("urlNotificationMetadata", {}).get("latestUpdate", {}).get("type", "OK")
        print(f"  [OK] {url} -> {status}")
        return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"  [ERR] {url} -> HTTP {e.code}: {err_body[:240]}")
        return False


def load_service_account(source=None):
    """Load service account dict from file path or GOOGLE_INDEXING_SA_JSON env var."""
    if source and os.path.exists(source):
        with open(source, "r", encoding="utf-8") as f:
            return json.load(f)

    raw_env = os.environ.get("GOOGLE_INDEXING_SA_JSON", "").lstrip("\ufeff").strip()
    if raw_env:
        if raw_env.startswith("{"):
            return json.loads(raw_env)
        if os.path.exists(raw_env):
            with open(raw_env, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        raise ValueError("GOOGLE_INDEXING_SA_JSON is set but does not start with '{' (invalid JSON).")

    return None


def get_default_urls(repo_dir=None):
    """Build priority URLs from trends.json / archives without exceeding daily quota."""
    if repo_dir is None:
        repo_dir = os.path.dirname(os.path.abspath(__file__))

    urls = [f"{BASE_URL}/", f"{BASE_URL}/archive.html"]
    trends_path = os.path.join(repo_dir, "trends.json")
    if os.path.exists(trends_path):
        try:
            with open(trends_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            iso = data.get("updated_at_iso", "")
            if len(iso) >= 13 and "T" in iso:
                date_part = iso[:10]
                hour_part = iso[11:13]
                urls.append(f"{BASE_URL}/archive.html?date={date_part}")
                urls.append(f"{BASE_URL}/archive.html?date={date_part}&hour={hour_part}")
        except Exception:
            pass
    return urls


def submit_urls(sa_source, urls):
    """Submit a list of URLs to Google Indexing API."""
    sa_info = load_service_account(sa_source)
    if sa_info is None:
        print("[SKIP] GOOGLE_INDEXING_SA_JSON not configured.")
        return 0

    print(f"[*] Authenticating as {sa_info['client_email']}...")
    token = _get_access_token(sa_info)
    print("[OK] Access token obtained")

    success = 0
    for url in urls:
        if notify_url_updated(token, url):
            success += 1

    print(f"[OK] Submitted {success}/{len(urls)} URLs to Google Indexing API")
    if len(urls) > 0 and success == 0:
        raise RuntimeError("All Google Indexing API URL submissions failed.")
    return success


if __name__ == "__main__":
    sa_arg = None
    url_args = []
    args = sys.argv[1:]
    if args and (args[0].endswith(".json") or args[0] == "--env"):
        sa_arg = None if args[0] == "--env" else args[0]
        url_args = args[1:]
    else:
        url_args = args

    target_urls = url_args if url_args else get_default_urls()
    submit_urls(sa_arg, target_urls)
