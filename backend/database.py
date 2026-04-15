from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "check_same_thread": False,  # necesar pentru SQLite cu FastAPI async
        "timeout": 30,               # așteaptă până la 30s dacă DB e locked (writer concurent)
                                     # previne OperationalError: database is locked la load
    },
)


# WAL mode pentru SQLite: permite citiri concurente în timp ce se face o scriere,
# elimină lock-ul global care blochează readers pe durata unui write.
# Fără WAL, un singur writer blochează toate request-urile simultane.
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # mai rapid, safe cu WAL
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
