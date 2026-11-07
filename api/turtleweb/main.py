"""The FastAPI app factory: lifespan, router and the SPA static mount."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from turtleweb.db import make_engine
from turtleweb.routes import router
from turtleweb.settings import Settings


class SpaStaticFiles(StaticFiles):
    """Serve web/dist; unknown non-API paths get index.html so deep links like /chart/AAPL.US work."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Return the file at `path`, or index.html when it is missing and not under api/.

        Args:
            path: Request path relative to the mount, without a leading slash.
            scope: The ASGI scope of the request.
        """
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


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
        app.state.symbols = None  # loaded on first /api/symbols request, see Step 4
        yield
        engine.dispose()

    app = FastAPI(title="turtle-web", lifespan=lifespan)
    app.include_router(router, prefix="/api")
    if settings.static_dir:
        app.mount("/", SpaStaticFiles(directory=settings.static_dir, html=True), name="spa")  # last: it matches every path
    return app
