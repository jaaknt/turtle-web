"""The read-only connection pool."""

import sqlalchemy as sa

from turtleweb.settings import Settings


def make_engine(s: Settings) -> sa.Engine:
    """Build the read-only connection pool.

    The connect options repeat the turtle_web role's settings, so the demo database (where you
    connect as postgres) is read-only too. create_engine connects lazily: nothing here touches
    the database until the first query.

    Args:
        s: Settings holding the connection parameters.

    Returns:
        sa.Engine: A small pool; the dashboard has one user.
    """
    url = sa.URL.create(
        "postgresql+psycopg", username=s.db_user, password=s.db_password, host=s.db_host, port=s.db_port, database=s.db_name
    )
    return sa.create_engine(
        url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=10000 -c jit=off"},
    )
