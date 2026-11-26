# -*- coding: utf-8 -*-
"""
HOTFEED LIVE - Self-Contained Local/VPS Server
- Built-in 1-hour cron scheduler
- Static Web Hosting + Real-time REST API
- Zero external package dependencies (Standard Python 3)
"""

import datetime
import http.server
import json
import os
import socketserver
import sys
import threading
import time

from collector import KST, collect_all, save_trends

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRENDS_FILE = os.path.join(BASE_DIR, "trends.json")
REFRESH_LOCK = threading.Lock()


def run_collector_task():
    """Background task to fetch and save trends."""
    with REFRESH_LOCK:
        try:
            now_str = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
            print(f"[*] [CRON] Starting 1-hour automated trend collection at {now_str}...")
            data = collect_all()
            save_trends(data, BASE_DIR)
            return data
        except Exception as e:
            print(f"[!] [CRON] Error during collection: {e}", file=sys.stderr)
            return None


def scheduler_daemon():
    """Loops every 3600 seconds (1 hour)."""
    while True:
        time.sleep(3600)
        run_collector_task()


class TrendRequestHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript; charset=utf-8",
        ".mjs": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".xml": "application/xml; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/trends"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()

            if os.path.exists(TRENDS_FILE):
                with open(TRENDS_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                self.wfile.write(content.encode("utf-8"))
            else:
                data = run_collector_task()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return

        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/refresh":
            print("[*] Manual refresh triggered via API")
            data = run_collector_task()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "data": data}, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def main():
    if not os.path.exists(TRENDS_FILE):
        print("[*] Initial trends.json not found. Running first collection...")
        run_collector_task()

    cron_thread = threading.Thread(target=scheduler_daemon, daemon=True)
    cron_thread.start()
    print("[OK] Background 1-hour scheduler daemon started successfully.")

    handler = TrendRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"=== HOTFEED LIVE Server running at: http://localhost:{PORT} ===")
        print("=== 1-hour Automated Trend Scheduler: Active ===")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")


if __name__ == "__main__":
    main()
