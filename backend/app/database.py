from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

url = make_url(settings.DATABASE_URL)
connect_args = {}
engine_kwargs = {}

if url.drivername.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # Postgres (Cloud SQL / AlloyDB). pg8000 wants the Cloud SQL unix socket via
    # connect_args, not the URL query string — move it across if present.
    if "unix_sock" in url.query:
        q = dict(url.query)
        connect_args["unix_sock"] = q.pop("unix_sock")
        url = url.set(query=q)
    engine_kwargs = {"pool_pre_ping": True, "pool_recycle": 1800}

engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
