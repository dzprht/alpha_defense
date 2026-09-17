"""Request identity, body-size enforcement, and baseline response headers."""

from __future__ import annotations

from typing import cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from alpha_defense.transport.http.v1.errors import PROBLEM_MEDIA_TYPE

MUTATING_METHODS = {"POST", "PUT", "PATCH"}


class RequestContextMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        allowed_hosts: tuple[str, ...],
    ) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes
        self._allowed_hosts = frozenset(host.lower() for host in allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _canonical_request_id(_header(scope, b"x-request-id")) or str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        host = _host_name(_header(scope, b"host"))
        if host is None or host not in self._allowed_hosts:
            await self._reject(scope, send, request_id, 400, "invalid_host")
            return
        limited_receive = receive
        content_length = _content_length(scope)
        if content_length is None and _header(scope, b"content-length") is not None:
            await self._reject(scope, send, request_id, 400, "invalid_content_length")
            return
        if content_length is not None and content_length > self._max_body_bytes:
            await self._reject(scope, send, request_id, 413, "payload_too_large")
            return
        if scope.get("method") in MUTATING_METHODS:
            messages, too_large = await _buffer_body(receive, self._max_body_bytes)
            if too_large:
                await self._reject(scope, send, request_id, 413, "payload_too_large")
                return
            limited_receive = _replay(messages)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", ()))
                headers.extend(
                    (
                        (b"x-request-id", request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                    )
                )
                message["headers"] = headers
            await send(message)

        await self._app(scope, limited_receive, send_with_headers)

    async def _reject(
        self,
        scope: Scope,
        send: Send,
        request_id: str,
        status: int,
        code: str,
    ) -> None:
        path = str(scope.get("path", "/"))
        detail = (
            "Размер тела запроса превышает допустимый предел."
            if status == 413
            else (
                "Заголовок Host не разрешен."
                if code == "invalid_host"
                else "Заголовок Content-Length некорректен."
            )
        )
        response = JSONResponse(
            status_code=status,
            media_type=PROBLEM_MEDIA_TYPE,
            content={
                "type": f"urn:alpha-defense:problem:{code}",
                "title": "Слишком большой запрос" if status == 413 else "Некорректный запрос",
                "status": status,
                "detail": detail,
                "instance": path,
                "code": code,
                "request_id": request_id,
                "retryable": False,
            },
            headers={
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            },
        )
        await response(scope, _empty_receive, send)


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", ()):  # headers are normalized to lowercase by ASGI
        if key == name:
            return cast(bytes, value).decode("latin-1")
    return None


def _canonical_request_id(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    canonical = str(parsed)
    return canonical if value == canonical else None


def _host_name(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return urlsplit(f"//{value}").hostname
    except ValueError:
        return None


def _content_length(scope: Scope) -> int | None:
    value = _header(scope, b"content-length")
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


async def _buffer_body(receive: Receive, limit: int) -> tuple[list[Message], bool]:
    messages: list[Message] = []
    size = 0
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] != "http.request":
            return messages, False
        size += len(message.get("body", b""))
        if size > limit:
            return messages, True
        if not message.get("more_body", False):
            return messages, False


def _replay(messages: list[Message]) -> Receive:
    index = 0

    async def receive() -> Message:
        nonlocal index
        if index < len(messages):
            message = messages[index]
            index += 1
            return message
        return {"type": "http.disconnect"}

    return receive


async def _empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}
