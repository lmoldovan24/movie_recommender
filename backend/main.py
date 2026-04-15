import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import settings
from backend.database import engine, SessionLocal
from backend.limiter import limiter
from backend.models import Base, WatchedMovie, RefreshToken, LoginAttempt
from backend.routers import auth, movies, recommendations, favorites, watchlist, ratings, watched, users
from backend.services.recommender import RecommenderService
from backend.services.tmdb import preload_cache, enrich_movies

logger = logging.getLogger(__name__)


async def _repair_watched_entries():
    """Repară watched entries cu titlu=ID sau fără poster."""
    if not RecommenderService.is_ready():
        logger.warning("repair_watched_entries: RecommenderService nu e gata, skip.")
        return

    db = SessionLocal()
    try:
        rows = db.query(WatchedMovie).all()
        if not rows:
            return

        changed = []
        for r in rows:
            bad_title = not r.title or r.title == str(r.movie_id)
            if bad_title or not r.tmdb_id or not r.poster_url:
                info = RecommenderService.get_movie_info(r.movie_id)
                if info:
                    if bad_title:
                        r.title = info["title"]
                    if not r.genres:
                        r.genres = info["genres"]
                    if not r.tmdb_id:
                        r.tmdb_id = info["tmdb_id"]
                    changed.append(r)

        if changed:
            db.commit()

        need_poster = [r for r in rows if r.tmdb_id and not r.poster_url]
        if need_poster:
            payload = [
                {"movie_id": r.movie_id, "tmdb_id": r.tmdb_id, "title": r.title, "genres": r.genres}
                for r in need_poster
            ]
            enriched = await enrich_movies(payload)
            enrich_map = {e["movie_id"]: e for e in enriched}
            for r in need_poster:
                data = enrich_map.get(r.movie_id)
                if data and data.get("poster_url"):
                    r.poster_url = data["poster_url"]
            db.commit()

    except Exception as e:
        logger.error(f"repair_watched_entries eroare: {e}")
    finally:
        db.close()


def _cleanup_expired_tokens():
    """
    Șterge RefreshToken-uri expirate și LoginAttempt-uri mai vechi de 24h.
    Previne creșterea nelimitată a tabelelor.
    Rulat sincron în asyncio.to_thread().
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        deleted_tokens = (
            db.query(RefreshToken)
            .filter(RefreshToken.expires_at < now)
            .delete(synchronize_session=False)
        )
        deleted_attempts = (
            db.query(LoginAttempt)
            .filter(LoginAttempt.attempted_at < now - timedelta(hours=24))
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted_tokens or deleted_attempts:
            logger.info(
                f"Cleanup: {deleted_tokens} refresh tokens expirate, "
                f"{deleted_attempts} login attempts șterse."
            )
    except Exception as e:
        logger.error(f"cleanup_expired_tokens eroare: {e}")
        db.rollback()
    finally:
        db.close()


async def _periodic_cleanup():
    """
    Cleanup periodic (la fiecare 24h) al token-urilor expirate și login attempts.
    Previne creșterea nelimitată a tabelelor pe servere cu uptime lung.
    """
    while True:
        await asyncio.sleep(86400)  # 24h
        try:
            await asyncio.to_thread(_cleanup_expired_tokens)
        except Exception as e:
            logger.error(f"periodic_cleanup eroare: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Creare tabele
    await asyncio.to_thread(Base.metadata.create_all, engine)

    # 2. Inițializare ML — nu blochează event loop-ul
    await asyncio.to_thread(RecommenderService.initialize)

    # 3. Cache TMDB din disc
    await asyncio.to_thread(preload_cache)

    # 4. Cleanup token-uri expirate la startup
    await asyncio.to_thread(_cleanup_expired_tokens)

    # 5. Repair watched entries rulează în background — nu blochează startup-ul
    repair_task = asyncio.create_task(_repair_watched_entries())

    # 6. Cleanup periodic — rulează la fiecare 24h pe durata vieții serverului
    cleanup_task = asyncio.create_task(_periodic_cleanup())

    yield

    # Oprire graceful la shutdown
    cleanup_task.cancel()
    repair_task.cancel()


app = FastAPI(
    title="CineRec API",
    description="API pentru sistemul de recomandare filme CineRec",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — originile vin din config, nu hardcodate
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' https://image.tmdb.org data:; "
        # frame-src necesar pentru embed-uri YouTube (trailers)
        "frame-src https://www.youtube.com https://www.youtube-nocookie.com; "
        "media-src 'none'; "
        "object-src 'none'; "
        "frame-ancestors 'none';"
    )
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


# Routers
app.include_router(auth.router)
app.include_router(movies.router)
app.include_router(recommendations.router)
app.include_router(favorites.router)
app.include_router(watchlist.router)
app.include_router(ratings.router)
app.include_router(watched.router)
app.include_router(users.router)


# Health check
@app.get("/health", tags=["system"])
async def health():
    return {
        "status": "ready" if RecommenderService.is_ready() else "loading"
    }
