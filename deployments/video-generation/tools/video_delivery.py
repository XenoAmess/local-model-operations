"""Record full HTTP response completion, without buffering media or claiming client checksum verification."""

import asyncio
import time


class DeliveryAudit:
    def __init__(self, app, store):
        self.app, self.store = app, store

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        parts = path.strip("/").split("/")
        if (scope.get("type") != "http" or scope.get("method") != "GET"
                or len(parts) != 4 or parts[:2] != ["v1", "videos"] or parts[-1] != "content"):
            return await self.app(scope, receive, send)
        code, expected, sent, finished = 0, None, 0, False
        started = time.time()

        async def audit_send(message):
            nonlocal code, expected, sent, finished
            if message["type"] == "http.response.start":
                code = message["status"]
                headers = dict(message.get("headers", []))
                if b"content-length" in headers:
                    expected = int(headers[b"content-length"])
            await send(message)
            if message["type"] == "http.response.body":
                sent += len(message.get("body", b""))
                if not message.get("more_body", False):
                    finished = True
        try:
            await self.app(scope, receive, audit_send)
        finally:
            if code in (200, 206):
                await asyncio.to_thread(self.store.event, "content_delivery_complete" if finished and code == 200 and sent == expected
                                        else "content_delivery_incomplete", job=parts[2], bytes_sent=sent,
                                        expected_bytes=expected, http_status=code, started_at=started,
                                        completed_at=time.time(), remote=(scope.get("client") or [None])[0],
                                        client_checksum_verified=False)
