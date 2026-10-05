"""Tiny localhost JSON-RPC bridge that delegates TLS to curl.

Some macOS/OpenSSL combinations intermittently fail against StudioNet with
BAD_RECORD_MAC while the system curl transport remains healthy. This bridge
changes no RPC payloads or responses; it only provides a stable local HTTP
hop for live integration tests.
"""

import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


UPSTREAM = "https://studio.genlayer.com/api"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        payload = self.rfile.read(length)
        result = subprocess.run(
            [
                "curl", "-fsS", "--retry", "5", "--retry-all-errors",
                "-X", "POST", UPSTREAM,
                "-H", "content-type: application/json",
                "--data-binary", "@-",
            ],
            input=payload,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            self.send_response(502)
            body = b'{"jsonrpc":"2.0","error":{"code":-32098,"message":"upstream transport failed"},"id":null}'
        else:
            self.send_response(200)
            body = result.stdout
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 4133), Handler).serve_forever()
