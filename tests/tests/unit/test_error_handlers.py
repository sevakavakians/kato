"""Guards for KATO's structured error handling.

Background: ``setup_error_handlers(app)`` used to be called from a startup
hook. Starlette builds its middleware stack on the first ``__call__`` -- which
is the lifespan scope -- and
``build_middleware_stack()`` copies ``app.exception_handlers`` into a fresh
dict. Anything registered after that point is silently ignored, so every
handler in ``kato/exceptions/handlers.py`` was dead in production and KATO
exceptions escaped as plain ``500 Internal Server Error``.

These tests pin both halves of the fix: that registration happens at import
time, and that the handlers behave as intended once registered.
"""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from kato.exceptions import KatoV2Exception, SessionNotFoundError, ValidationError
from kato.exceptions.handlers import setup_error_handlers


def test_handlers_are_registered_at_import_time():
    """The real app must carry its handlers before any startup hook runs.

    This is the regression guard: move ``setup_error_handlers(app)`` into
    ``_startup()`` (or the ``lifespan`` context manager) and this fails, because
    at import time the app's handler map would not yet contain them.
    """
    from kato.services.kato_fastapi import app

    assert KatoV2Exception in app.exception_handlers, (
        "KatoV2Exception handler missing -- it must be registered at module "
        "scope, not from a startup/lifespan hook (Starlette snapshots the "
        "handler map when it builds the middleware stack)."
    )
    assert Exception in app.exception_handlers, (
        "Catch-all Exception handler missing; unhandled errors would return a "
        "plain-text 500 and could leak a traceback."
    )


def _app_with_handlers() -> FastAPI:
    app = FastAPI()
    setup_error_handlers(app)

    @app.get("/session-missing")
    async def session_missing():
        raise SessionNotFoundError("nope")

    @app.get("/invalid")
    async def invalid():
        raise ValidationError(
            message="bad",
            field_name="strings",
            field_value=1,
            validation_rule="must be str",
        )

    @app.get("/http-404")
    async def http_404():
        raise HTTPException(status_code=404, detail="plain not found")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("unexpected")

    return app


def test_late_registration_is_ignored():
    """Document the failure mode the fix exists for.

    Registering from the lifespan context manager must NOT work: Starlette
    builds its middleware stack in ``__call__`` *before* it dispatches the
    lifespan scope, so ``build_middleware_stack()`` has already snapshotted an
    empty handler map by the time the lifespan body runs. If a future Starlette
    makes it work, this test tells us the guard above is no longer load-bearing.
    """
    @asynccontextmanager
    async def register_handlers_late(app: FastAPI):
        setup_error_handlers(app)
        yield

    # lifespan= is a constructor argument, so the app is built first and the
    # route registered after; routes resolve at request time, so that is fine.
    app = FastAPI(lifespan=register_handlers_late)

    @app.get("/boom")
    async def boom():
        raise KatoV2Exception("late", error_code="LATE")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert "error" not in response.text, (
        "Handlers registered from the lifespan unexpectedly fired; revisit "
        "test_handlers_are_registered_at_import_time."
    )


@pytest.mark.parametrize(
    "path,expected_status,expected_code",
    [
        ("/session-missing", 404, "SESSION_NOT_FOUND"),
        ("/invalid", 422, "VALIDATION_ERROR"),
    ],
)
def test_kato_exceptions_map_to_their_status(path, expected_status, expected_code):
    """KATO exceptions get their mapped status and a structured body."""
    with TestClient(_app_with_handlers(), raise_server_exceptions=False) as client:
        response = client.get(path)

    assert response.status_code == expected_status
    body = response.json()
    assert body["error"]["code"] == expected_code


def test_http_exception_keeps_fastapi_default_shape():
    """HTTPException responses stay flat ``{"detail": ...}``.

    ``setup_error_handlers`` deliberately leaves HTTPException and
    RequestValidationError on FastAPI's defaults: route handlers raise
    HTTPException throughout the codebase and clients depend on that shape.
    Taking them over is an API-visible change and is opt-in via
    ``include_http_handlers=True``.
    """
    with TestClient(_app_with_handlers(), raise_server_exceptions=False) as client:
        response = client.get("/http-404")

    assert response.status_code == 404
    assert response.json() == {"detail": "plain not found"}


def test_unexpected_exception_does_not_leak_detail():
    """The catch-all returns a generic message, not the exception text."""
    with TestClient(_app_with_handlers(), raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "unexpected" not in body["error"]["message"].lower() or \
        body["error"]["message"] == "An unexpected error occurred"


def test_opt_in_http_handlers_change_the_shape():
    """include_http_handlers=True switches HTTPException to the structured envelope."""
    app = FastAPI()
    setup_error_handlers(app, include_http_handlers=True)

    @app.get("/http-404")
    async def http_404():
        raise HTTPException(status_code=404, detail="plain not found")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/http-404")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
