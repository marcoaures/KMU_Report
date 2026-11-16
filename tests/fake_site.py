"""A tiny local web server used by the tests instead of real websites."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Tuple, Union

Page = Union[str, Tuple[int, str], Tuple[int, str, Dict[str, str]]]


class FakeSite:
    """Serve ``pages`` (path -> body | (status, body) | (status, body, headers))."""

    def __init__(self, pages: Dict[str, Page], default_status: int = 404):
        self.pages = pages
        self.hits: list[str] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                site.hits.append(self.path)
                page = site.pages.get(self.path.split("?")[0])
                if page is None:
                    status, body, headers = default_status, "not found", {}
                elif isinstance(page, str):
                    status, body, headers = 200, page, {}
                else:
                    status, body = page[0], page[1]
                    headers = page[2] if len(page) > 2 else {}
                data = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(status)
                ctype = headers.pop("Content-Type", None) if headers else None
                if ctype is None:
                    path = self.path.split("?")[0]
                    ctype = ("text/css" if path.endswith(".css")
                             else "application/xml" if path.endswith(".xml")
                             else "text/plain" if path.endswith(".txt")
                             else "text/html; charset=utf-8")
                self.send_header("Content-Type", ctype)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.domain = f"127.0.0.1:{self.port}"
        self.base = f"http://{self.domain}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
