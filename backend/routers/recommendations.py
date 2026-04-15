import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.limiter import limiter
from backend.models import User, Favorite, UserRating, WatchedMovie
from backend.schemas import MovieOut
from backend.services.recommender import RecommenderService
from backend.services.tmdb import enrich_movies
from ml.hybrid import LIKED_THRESHOLD

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _to_movie_out(m: dict) -> dict:
    return {
        "movie_id": m.get("movie_id", 0),
        "tmdb_id": m.get("tmdb_id"),
        "title": m.get("title", ""),
        "genres": m.get("genres"),
        "poster_url": m.get("poster_url"),
        "overview": m.get("overview"),
        "vote_average": m.get("vote_average"),
        "release_year": m.get("release_year"),
        "similarity_score": m.get("similarity_score"),
        "trailer_key": m.get("trailer_key"),
        "reason": m.get("reason"),
    }


def _filter_enriched(enriched: list, min_with_poster: int = 5) -> list:
    """
    Filtrare cu fallback reziliență la TMDB downtime.

    Strategia: returnăm preferabil filmele cu poster. Dacă TMDB e indisponibil
    și mai puțin de min_with_poster filme au poster, returnăm toate — e mai bine
    să arăți un card fără imagine decât o pagină goală.
    """
    with_poster = [_to_movie_out(m) for m in enriched if m.get("poster_url")]
    if len(with_poster) >= min_with_poster:
        return with_poster
    # TMDB probabil indisponibil — returnăm toate, frontend-ul gestionează lipsa posterului
    return [_to_movie_out(m) for m in enriched]


@router.get("/picks", response_model=list[MovieOut])
@limiter.limit("30/minute")
async def get_picks(
    request: Request,
    movie_ids: str = Query(..., description="Lista de MovieLens IDs separați prin virgulă (max 10)"),
    genre: Optional[str] = Query(None, description="Filtrare opțională după gen"),
):
    """
    Recomandări content-based pentru utilizatori neautentificați.
    Primește 1–10 movie_ids și returnează filme similare (max similarity).
    """
    if not RecommenderService.is_ready():
        raise HTTPException(status_code=503, detail="Serviciul ML nu este gata încă")

    try:
        ids = [int(x.strip()) for x in movie_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="movie_ids trebuie să fie numere întregi separate prin virgulă",
        )

    if not ids:
        raise HTTPException(status_code=422, detail="Cel puțin un movie_id este necesar")

    if len(ids) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 movie_ids permise")

    picks = await asyncio.to_thread(
        RecommenderService.get_picks, movie_ids=ids, genre=genre, top_n=25
    )
    if not picks:
        return []

    enriched = await enrich_movies(picks)
    return _filter_enriched(enriched)


@router.get("/personal", response_model=list[MovieOut])
@limiter.limit("20/minute")
async def get_personal(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    seed: Optional[int] = Query(None, description="Seed aleatoriu pentru diversitate"),
):
    """
    Recomandări personalizate hibride (CB + CF + Popularity) pentru utilizatori autentificați.

    Construcția signal-ului:
      - Favorite fără rating → rating implicit 3.0 (adăugat înseamnă că îi place)
      - Favorite cu rating ≥ 3.0 → incluse cu ratingul real
      - Favorite cu rating < 3.0 → excluse (nu-i place)
      - Vizionate cu rating ≥ 3.0 → incluse (ia max față de eventual rating din favorite)
      - Vizionate fără rating → excluse (semnal incert)

    Dacă semnalul total < 3 filme → fallback la filme populare neatinse de user.
    """
    if not RecommenderService.is_ready():
        raise HTTPException(status_code=503, detail="Serviciul ML nu este gata încă")

    # Singura sursă de adevăr pentru ratinguri
    user_ratings_rows = (
        db.query(UserRating)
        .filter(UserRating.user_id == current_user.id)
        .all()
    )
    rating_map = {r.movie_id: r.rating for r in user_ratings_rows if r.rating is not None}

    favorites = db.query(Favorite).filter(Favorite.user_id == current_user.id).all()
    watched = db.query(WatchedMovie).filter(WatchedMovie.user_id == current_user.id).all()

    # --- Construcție signal ---
    signal: dict = {}

    for f in favorites:
        r = rating_map.get(f.movie_id)
        if r is None:
            signal[f.movie_id] = LIKED_THRESHOLD   # adăugat la favorite → implicit îi place
        elif r >= LIKED_THRESHOLD:
            signal[f.movie_id] = float(r)
        # r < LIKED_THRESHOLD → exclus intenționat (nu-i place)

    for w in watched:
        r = rating_map.get(w.movie_id)
        if r is not None and r >= LIKED_THRESHOLD:
            # Dacă filmul e și în favorite, păstrăm greutatea mai mare
            signal[w.movie_id] = max(signal.get(w.movie_id, 0.0), float(r))

    # --- Fallback: semnal insuficient → filme populare neatinse ---
    if len(signal) < 3:
        exclude_ids = {f.movie_id for f in favorites} | {w.movie_id for w in watched}
        popular = await asyncio.to_thread(
            RecommenderService.get_popular_fallback, exclude_ids=exclude_ids, top_n=30
        )
        if not popular:
            return []
        enriched = await enrich_movies(popular)
        return _filter_enriched(enriched)

    # --- Recomandări hibride ---
    # exclude_ids = toate filmele cu care userul a interacționat, indiferent de rating.
    # Filmele din signal sunt deja excluse de HybridRecommender prin fav_set,
    # dar watched fără rating sau cu rating < 3.0 NU sunt în signal — le excludem explicit
    # pentru a nu recomanda filme pe care userul le-a văzut și eventual nu i-au plăcut.
    exclude_ids = {f.movie_id for f in favorites} | {w.movie_id for w in watched}

    recs = await asyncio.to_thread(
        RecommenderService.get_personal,
        signal=signal,
        user_ratings_dict=rating_map,
        top_n=30,
        seed=seed,
        liked_threshold=LIKED_THRESHOLD,
        exclude_ids=exclude_ids,
    )

    if not recs:
        return []

    enriched = await enrich_movies(recs)
    return _filter_enriched(enriched)
