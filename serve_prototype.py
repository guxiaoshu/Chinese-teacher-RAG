"""只对外提供 prototype_v2.html 这一个文件的最小静态服务。

比 `python -m http.server` 更安全：不会把项目根目录（含 .env 里的 API key）
暴露给局域网。仅 / 与 /prototype_v2.html 会返回该页面，其它路径一律 404。

启动：
    python serve_prototype.py
然后浏览器访问 http://<本机局域网IP>:8000/prototype_v2.html
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FILE = Path(__file__).resolve().parent / "prototype_v2.html"
PORT = 8000
ALLOWED = {"/", "/prototype_v2.html", "/index.html"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ALLOWED:
            try:
                data = FILE.read_bytes()
            except Exception:
                self.send_response(500)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    print(f"Serving {FILE.name} -> http://0.0.0.0:{PORT}/prototype_v2.html")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
