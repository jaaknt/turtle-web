"""The FastAPI app factory: lifespan, router and the SPA static mount."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from turtleweb.db import make_engine
from turtleweb.ledger import LedgerError
from turtleweb.routes import router
from turtleweb.settings import Settings

# Missing paths under these stay 404. api/: an unknown endpoint is an error, not a page.
# assets/: after a deploy, a tab opened on the previous release asks for chunks that are gone; a
# real 404 makes its dynamic import fail cleanly, and the frontend reloads (src/staleChunks.ts),
# where index.html served as JavaScript would fail with a confusing MIME-type error instead.
_NO_FALLBACK = ("api/", "assets/")


class SpaStaticFiles(StaticFiles):
    """Serve web/dist; unknown page paths get index.html so deep links like /chart/AAPL.US work."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Return the file at `path`, or index.html when it is missing and not under api/ or assets/.

        Args:
            path: Request path relative to the mount, without a leading slash.
            scope: The ASGI scope of the request.
        """
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith(_NO_FALLBACK):
                raise
            return await super().get_response("index.html", scope)


async def _ledger_error(request: Request, exc: Exception) -> JSONResponse:
    """A loud 500 naming the ticker whose bars are missing, rather than a bare Internal Server Error.

    Only LedgerError is surfaced: its message holds a symbol and a date, nothing internal.
    """
    return JSONResponse(status_code=500, content={"detail": str(exc)})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app.

    Startup never touches the database: the engine connects lazily, so after a VPS reboot the
    first request once Postgres recovers simply succeeds, instead of the app exhausting systemd's
    restart limit.

    Args:
        settings: Configuration; defaults to the environment. Tests and the OpenAPI export pass
            their own, so they can build the app without a database.
    """
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings)
        app.state.engine = engine
        app.state.settings = settings
        app.state.symbols = None  # a routes.SymbolCache, loaded on first use
        yield
        engine.dispose()

    app = FastAPI(title="turtle-web", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_exception_handler(LedgerError, _ledger_error)
    app.include_router(router, prefix="/api")
    if settings.static_dir:
        app.mount("/", SpaStaticFiles(directory=settings.static_dir, html=True), name="spa")  # last: it matches every path
    return app
