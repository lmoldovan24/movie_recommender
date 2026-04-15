from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.limiter import limiter
from backend.models import User, WatchedMovie
from backend.schemas import WatchedOut, WatchedCreate
from backend.services.recommender import RecommenderService
from backend.services.tmdb import enrich_movies

router = APIRouter(prefix="/watched", tags=["watched"])


@router.get("/", response_model=list[WatchedOut])
@limiter.limit("60/minute")
async def get_watched(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(WatchedMovie).filter(WatchedMovie.user_id == current_user.id).all()
    if not rows:
        return []

    # Pas 1: completează titlu/tmdb_id/genres din cache O(1) pentru orice entry incomplet.
    if RecommenderService.is_ready():
        needs_fix = [
            r for r in rows
            if not r.poster_url or not r.tmdb_id or r.title == str(r.movie_id)
        ]
        for r in needs_fix:
            info = RecommenderService.get_movie_info(r.movie_id)
            if info:
                if not r.tmdb_id and info["tmdb_id"]:
                    r.tmdb_id = info["tmdb_id"]
                if not r.title or r.title == str(r.movie_id):
                    r.title = info["title"]
                if not r.genres:
                    r.genres = info["genres"]
        if needs_fix:
            db.commit()

    # Pas 2: enrich poster prin TMDB pentru cele fără poster dar cu tmdb_id
    need_enrich = [r for r in rows if not r.poster_url and r.tmdb_id]
    if need_enrich:
        payload = [
            {"movie_id": r.movie_id, "tmdb_id": r.tmdb_id, "title": r.title, "genres": r.genres}
            for r in need_enrich
        ]
        enriched = await enrich_movies(payload)
        enrich_map = {e["movie_id"]: e for e in enriched}
        for r in need_enrich:
            data = enrich_map.get(r.movie_id)
            if data and data.get("poster_url"):
                r.poster_url = data["poster_url"]
        db.commit()

    return rows


@router.post("/{movie_id}", response_model=WatchedOut)
@limiter.limit("30/minute")
def mark_watched(
    request: Request,
    movie_id: int,
    body: WatchedCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(WatchedMovie).filter(
        WatchedMovie.user_id == current_user.id,
        WatchedMovie.movie_id == movie_id,
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Film deja marcat ca văzut")

    entry = WatchedMovie(
        user_id=current_user.id,
        movie_id=movie_id,
        tmdb_id=body.tmdb_id,
        title=body.title,
        genres=body.genres,
        poster_url=body.poster_url,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{movie_id}", status_code=204)
@limiter.limit("60/minute")
def unmark_watched(
    request: Request,
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.query(WatchedMovie).filter(
        WatchedMovie.user_id == current_user.id,
        WatchedMovie.movie_id == movie_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Film negăsit în istoricul vizionat")
    db.delete(entry)
    db.commit()
