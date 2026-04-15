import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.limiter import limiter
from backend.models import User, UserRating, WatchedMovie, Favorite
from backend.schemas import UserRatingOut, UserRatingUpsert, UserRatingEnriched
from backend.services.recommender import RecommenderService
from backend.services.tmdb import enrich_movies

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ratings", tags=["ratings"])


@router.get("/", response_model=list[UserRatingOut])
@limiter.limit("60/minute")
def get_ratings(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(UserRating).filter(UserRating.user_id == current_user.id).all()


@router.get("/enriched", response_model=list[UserRatingEnriched])
@limiter.limit("30/minute")
async def get_ratings_enriched(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returnează toate ratingurile userului cu detalii complete despre fiecare film."""
    rows = db.query(UserRating).filter(UserRating.user_id == current_user.id).all()
    if not rows:
        return []

    movies_payload = []
    rating_meta = {}  # movie_id → {id, rating, rated_at}

    for r in rows:
        rating_meta[r.movie_id] = {
            "id": r.id,
            "rating": r.rating,
            "rated_at": r.rated_at,
        }
        # Lookup O(1) în loc de scan O(n) al DataFrame-ului la fiecare iterație
        info = RecommenderService.get_movie_info(r.movie_id)
        if info:
            entry = {
                "movie_id": r.movie_id,
                "tmdb_id": info["tmdb_id"],
                "title": info["title"],
                "genres": info["genres"],
            }
        else:
            entry = {"movie_id": r.movie_id, "tmdb_id": None, "title": str(r.movie_id), "genres": None}
        movies_payload.append(entry)

    enriched = await enrich_movies(movies_payload)

    results = []
    for m in enriched:
        mid = m["movie_id"]
        meta = rating_meta.get(mid, {})
        results.append({
            "id": meta.get("id", 0),
            "movie_id": mid,
            "tmdb_id": m.get("tmdb_id"),
            "title": m.get("title", ""),
            "genres": m.get("genres"),
            "poster_url": m.get("poster_url"),
            "rating": meta.get("rating"),
            "rated_at": meta.get("rated_at"),
        })

    return results


@router.put("/{movie_id}", response_model=UserRatingOut)
@limiter.limit("30/minute")
def upsert_rating(
    request: Request,
    movie_id: int,
    body: UserRatingUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(UserRating).filter(
        UserRating.user_id == current_user.id,
        UserRating.movie_id == movie_id,
    ).first()

    if existing:
        if body.rating is not None:
            existing.rating = body.rating
    else:
        existing = UserRating(
            user_id=current_user.id,
            movie_id=movie_id,
            rating=body.rating,
        )
        db.add(existing)

    # Marchează automat ca văzut dacă nu e deja.
    # Interogarea se face ÎNAINTE de commit — vedem starea DB-ului comis,
    # nu starea pending. Adăugăm WatchedMovie în aceeași sesiune și facem
    # un singur commit atomic: fie ambele operații reușesc, fie niciuna.
    already_watched = db.query(WatchedMovie).filter(
        WatchedMovie.user_id == current_user.id,
        WatchedMovie.movie_id == movie_id,
    ).first()

    if not already_watched:
        fav = db.query(Favorite).filter(
            Favorite.user_id == current_user.id,
            Favorite.movie_id == movie_id,
        ).first()

        # Prioritate: date din request → favorite → dataset
        title = body.title or str(movie_id)
        genres = body.genres
        tmdb_id = body.tmdb_id
        poster_url = body.poster_url

        if fav and not poster_url:
            title = title or fav.title
            genres = genres or fav.genres
            tmdb_id = tmdb_id or fav.tmdb_id
            poster_url = fav.poster_url

        if not poster_url:
            info = RecommenderService.get_movie_info(movie_id)
            if info:
                title = title or info["title"]
                genres = genres or info["genres"]
                tmdb_id = tmdb_id or info["tmdb_id"]

        db.add(WatchedMovie(
            user_id=current_user.id,
            movie_id=movie_id,
            tmdb_id=tmdb_id,
            title=title,
            genres=genres,
            poster_url=poster_url,
        ))

    try:
        db.commit()
    except OperationalError as e:
        db.rollback()
        logger.error("upsert_rating: DB locked după timeout: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Baza de date momentan indisponibilă — încearcă din nou în câteva secunde.",
        )
    db.refresh(existing)
    return existing


@router.delete("/{movie_id}", status_code=204)
@limiter.limit("60/minute")
def delete_rating(
    request: Request,
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Șterge ratingul unui film.

    WatchedMovie NU este ștearsă intenționat: a vedea un film și a-l evalua sunt
    concepte independente. Un film poate fi "văzut" fără rating (marcat manual via
    POST /watched/{id} sau prin adăugarea unui rating ulterior șters). Ștergerea
    automată a watched-ului la delete-rating ar distruge starea "am văzut filmul"
    setată independent de user.
    """
    entry = db.query(UserRating).filter(
        UserRating.user_id == current_user.id,
        UserRating.movie_id == movie_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Rating negăsit")
    db.delete(entry)
    db.commit()
