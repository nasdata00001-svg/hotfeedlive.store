# -*- coding: utf-8 -*-
"""
TREND PULSE - Production-ready Self-Contained Server
- Built-in 1-hour cron scheduler
- Static Web Hosting + Real-time REST API
- Zero external package dependencies (Standard Python 3)
"""

import http.server
import socketserver
import threading
import time
import json
import os
import sys

from collector import collect_all

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRENDS_FILE = os.path.join(BASE_DIR, "trends.json")
REFRESH_LOCK = threading.Lock()

def run_collector_task():
    """Background task to fetch and save trends"""
    with REFRESH_LOCK:
        try:
            print(f"[*] [CRON] Starting 1-hour automated trend collection at {time.strftime('%Y-%m-%d %H:%M:%S')}...")
            data = collect_all()
            with open(TRENDS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            trends_js_file = os.path.join(BASE_DIR, "trends_data.js")
            with open(trends_js_file, "w", encoding="utf-8") as f:
                f.write("window.INITIAL_TRENDS = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n")

            print(f"[OK] [CRON] Trend data successfully refreshed and saved to {TRENDS_FILE} and {trends_js_file}")
            return data
        except Exception as e:
            print(f"[!] [CRON] Error during collection: {e}", file=sys.stderr)
            return None

def scheduler_daemon():
    """Loops every 3600 seconds (1 hour)"""
    while True:
        time.sleep(3600)
        run_collector_task()

class TrendRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        # API: /api/trends
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

        # Default static file serving
        return super().do_GET()

    def do_POST(self):
        # API: /api/refresh (manual trigger)
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
    # If trends.json does not exist, run initial collection
    if not os.path.exists(TRENDS_FILE):
        print("[*] Initial trends.json not found. Running first collection...")
        run_collector_task()

    # Start 1-hour cron thread
    cron_thread = threading.Thread(target=scheduler_daemon, daemon=True)
    cron_thread.start()
    print("[OK] Background 1-hour scheduler daemon started successfully.")

    # Start HTTP server
    handler = TrendRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"=== TREND PULSE Server running at: http://localhost:{PORT} ===")
        print(f"=== 1-hour Automated Trend Scheduler: Active ===")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")

if __name__ == "__main__":
    main()
