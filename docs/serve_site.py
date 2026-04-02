#!/usr/bin/env python3
"""Serve the static site locally. From repo root: python3 docs/serve_site.py"""

import http.server
import os
import pathlib
import socketserver
import threading
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent
PORT = 8765


def main() -> None:
    os.chdir(ROOT)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        url = f"http://127.0.0.1:{PORT}/"
        print(f"Serving {ROOT}")
        print(f"Open {url}")
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
