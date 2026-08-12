"""Loopback-browser bridge for completing Plaid Link from the desktop client.

The bridge serves only on 127.0.0.1, exists for the Link session, and receives the
one-time public token. It never sends a Plaid access token to the browser or writes
banking payloads to the application log.
"""

from __future__ import annotations

import html
import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from core.plaid_connector import PlaidConnector


class PlaidDesktopLinkBridge:
    def __init__(self, connector: PlaidConnector, company_id: int, actor_id: int, *, mfa_verified: bool = False):
        self.connector = connector
        self.company_id = company_id
        self.actor_id = actor_id
        self.mfa_verified = mfa_verified
        self.link_token = connector.create_link_token(company_id, actor_id, mfa_verified=mfa_verified)["link_token"]
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.completed = threading.Event()
        self._server: Optional[ThreadingHTTPServer] = None

    def open(self) -> str:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, content_type: str, body: str) -> None:
                content = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", f"{content_type}; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def do_GET(self):  # noqa: N802
                if self.path != "/":
                    self._send(HTTPStatus.NOT_FOUND, "text/plain", "Not found")
                    return
                link_token = html.escape(bridge.link_token, quote=True)
                self._send(HTTPStatus.OK, "text/html", f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>FinAnalyzer | Connect bank</title>
<script src=\"https://cdn.plaid.com/link/v2/stable/link-initialize.js\"></script></head>
<body style=\"font-family:Segoe UI,Arial,sans-serif;background:#171717;color:#fff;padding:48px\">
<h1>Connect a financial institution</h1><p>Complete the secure consent flow in the Plaid window.</p>
<script>
const handler = Plaid.create({{
  token: \"{link_token}\",
  onSuccess: async (public_token, metadata) => {{
    const response = await fetch('/complete', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{public_token: public_token, institution: metadata.institution || {{}}}})}});
    const output = await response.json();
    document.body.innerHTML = output.ok
      ? '<h1>Bank connected.</h1><p>You may return to FinAnalyzer.</p>'
      : '<h1>Connection could not be completed.</h1><p>Return to FinAnalyzer and retry.</p>';
  }}
}});
handler.open();
</script></body></html>""")

            def do_POST(self):  # noqa: N802
                if self.path != "/complete":
                    self._send(HTTPStatus.NOT_FOUND, "application/json", '{"ok":false}')
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    bridge.result = bridge.connector.exchange_public_token(
                        bridge.company_id,
                        bridge.actor_id,
                        payload["public_token"],
                        payload.get("institution") or {},
                        mfa_verified=bridge.mfa_verified,
                    )
                    bridge.completed.set()
                    self._send(HTTPStatus.OK, "application/json", '{"ok":true}')
                except Exception:
                    bridge.error = "The bank connection could not be completed."
                    bridge.completed.set()
                    self._send(HTTPStatus.BAD_REQUEST, "application/json", '{"ok":false}')

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address
        url = f"http://{host}:{port}/"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        webbrowser.open(url)
        return url

    def close(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


__all__ = ["PlaidDesktopLinkBridge"]
