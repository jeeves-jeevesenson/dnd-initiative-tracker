#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import socket
import threading
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]


class LanRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path == "/lan":
            # Serve the LAN page with placeholder replaced
            file_path = REPO_ROOT / "assets/web/lan/index.html"
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                # Replace the placeholder values with undefined for the smoke test
                content = content.replace(b"__LAN_BASE_URL__", b"undefined")
                content = content.replace(b"__PUSH_PUBLIC_KEY__", b"undefined")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception:
                pass  # Fall through to default handler
        self.path = path if path else "/"
        return super().do_GET()


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server() -> tuple[ThreadingHTTPServer, int]:
    port = _find_open_port()
    handler = partial(LanRequestHandler, directory=str(REPO_ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def main() -> int:
    server, port = start_server()
    page_errors: list[str] = []

    with contextlib.ExitStack() as stack:
        stack.callback(server.shutdown)
        stack.callback(server.server_close)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()

            def _on_page_error(error: Exception) -> None:
                page_errors.append(str(error))

            page.on("pageerror", _on_page_error)
            page.goto(f"http://127.0.0.1:{port}/lan", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.documentElement.dataset.lanBoot === 'true'",
                timeout=15000,
            )

    if page_errors:
        message = "\n".join(page_errors)
        raise SystemExit(f"Page errors detected:\n{message}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
