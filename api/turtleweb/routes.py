"""The /api/* endpoints.

Every endpoint is a plain `def`, never `async def`: the engine is sync, and FastAPI runs `def`
endpoints in a threadpool, whereas an `async def` calling a sync engine would block the event loop.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Report that the process is up, without querying the database.

    Postgres on the VPS can refuse connections after a reboot; a health check that queried would
    turn that into a restart loop instead of a single failed request.
    """
    return {"status": "ok"}
