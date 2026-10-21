from starlette.responses import JSONResponse
from app.core.config import settings
from app.core.deployment_guard import is_public_deployment


class RequestLimitsMiddleware:
    """Enforce real streaming body limits before multipart parsing/spooling."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if is_public_deployment() and "/simulate" in scope["path"]:
            return await JSONResponse({"detail":"Simulation endpoints are disabled in published deployments."},409)(scope, receive, send)
        limit = settings.MAX_UPLOAD_BYTES + 1024 * 1024 if "/knowledge/upload" in scope["path"] else 1024 * 1024
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail":"Invalid content length."}, 400)(scope, receive, send)
        if declared > limit:
            return await JSONResponse({"detail":"Request body is too large."}, 413)(scope, receive, send)
        chunks, total = [], 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body = event.get("body", b"")
            total += len(body)
            if total > limit:
                return await JSONResponse({"detail":"Request body is too large."}, 413)(scope, receive, send)
            chunks.append(body)
            if not event.get("more_body", False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type":"http.request", "body":b"".join(chunks), "more_body":False}
        await self.app(scope, replay, send)
