import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from backend.limiter import limiter
from backend.schemas import MovieOut
from backend.services.recommender import RecommenderService
from backend.services.tmdb import enrich_movies

router = APIRouter(prefix="/movies", tags=["movies"])


def _row_to_movie_out(row: dict) -> dict:
    return {
        "movie_id": int(row.get("movie_id", row.get("movieId", 0))),
        "tmdb_id": int(row["tmdb_id"]) if row.get("tmdb_id") else None,
        "title": str(row.get("title", "")),
        "genres": str(row.get("genres", "")),
        "poster_url": row.get("poster_url"),
        "overview": row.get("overview"),
        "vote_average": row.get("vote_average"),
        "release_year": row.get("release_year"),
        "similarity_score": row.get("similarity_score"),
        "trailer_key": row.get("trailer_key"),
        "reason": row.get("reason"),
    }


def _parse_tmdb_id(row) -> Optional[int]:
    """Helper pentru parsarea tmdbId dintr-un rând de DataFrame."""
    try:
        val = row.get("tmdbId")
        if val and str(val) not in ("nan", "None", ""):
            return int(val)
    except (ValueError, TypeError):
        pass
    return None


def _safe_tmdb_val(val) -> Optional[int]:
    """Parsează tmdbId dintr-o valoare scalară (numpy float, NaN, None, string)."""
    try:
        if val and str(val) not in ("nan", "None", ""):
            return int(val)
    except (ValueError, TypeError):
        pass
    return None


def _filter_enriched(enriched: list, min_with_poster: int = 5) -> list:
    """
    Returnează filmele cu poster dacă există suficiente (≥ min_with_poster).
    Fallback la toate filmele dacă TMDB e indisponibil — e mai bine să arăți
    un card fără imagine decât o pagină goală.
    """
    with_poster = [_row_to_movie_out(m) for m in enriched if m.get("poster_url")]
    if len(with_poster) >= min_with_poster:
        return with_poster
    return [_row_to_movie_out(m) for m in enriched]


# IMPORTANT: ordinea rutelor contează — /genres, /popular, /search ÎNAINTEA /{movie_id}

@router.get("/popular", response_model=list[MovieOut])
@limiter.limit("30/minute")
async def get_popular(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    seed: Optional[int] = Query(None, description="Seed aleatoriu pentru variație"),
):
    """Returnează filme populare. Cu seed, samplez aleatoriu din top-150 pentru variație."""
    if not RecommenderService.is_ready():
        raise HTTPException(status_code=503, detail="Serviciul ML nu este gata încă")

    import numpy as np

    # _sorted_popular e pre-sortat la startup — fără sort O(N log N) per request
    pool = RecommenderService._sorted_popular.head(150)

    if seed is not None and len(pool) > limit * 3:
        rng = np.random.default_rng(seed)
        fetch_n = min(limit * 3, len(pool))
        scores = pool["popularity_score"].values.astype(float) + 1e-6
        probs = scores / scores.sum()
        chosen_idx = rng.choice(len(pool), size=fetch_n, replace=False, p=probs)
        top = pool.iloc[sorted(chosen_idx)]
    else:
        top = pool.head(limit * 3)

    tmdb_col = top["tmdbId"].tolist() if "tmdbId" in top.columns else [None] * len(top)
    movies = [
        {
            "movie_id": int(mid),
            "tmdb_id": _safe_tmdb_val(tmdb_val),
            "title": str(title),
            "genres": str(genres),
        }
        for mid, title, genres, tmdb_val in zip(
            top["movieId"].tolist(),
            top["title"].tolist(),
            top["genres"].tolist(),
            tmdb_col,
        )
    ]

    enriched = await enrich_movies(movies)
    with_poster = [_row_to_movie_out(m) for m in enriched if m.get("poster_url")]
    return with_poster[:limit]


@router.get("/genres", response_model=list[str])
@limiter.limit("60/minute")
def get_genres(request: Request):
    """Returnează lista tuturor genurilor disponibile."""
    if not RecommenderService.is_ready():
        raise HTTPException(status_code=503, detail="Serviciul ML nu este gata încă")

    # _genres_list e pre-calculat la startup — fără iterare O(N) per request
    return RecommenderService._genres_list


@router.get("/search", response_model=list[MovieOut])
@limiter.limit("20/minute")
async def search_movies(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100, description="Termen de căutare (minim 2 caractere)"),
):
    """Caută filme după titlu — minim 2 caractere."""
    if not RecommenderService.is_ready():
        raise HTTPException(status_code=503, detail="Serviciul ML nu este gata încă")

    mf = RecommenderService.movie_features
    q_lower = q.lower().strip()

    # re.escape previne interpretarea caracterelor speciale din input (ex: '(', '*', '[')
    # ca metacaractere regex, eliminând erori re.error → HTTP 500.
    matches = mf[
        mf["title"].str.lower().str.contains(re.escape(q_lower), na=False)
    ].head(20)

    if matches.empty:
        # Fallback: căutare per cuvânt — fiecare cuvânt e escaped independent
        words = [w for w in q_lower.split() if len(w) >= 3]
        if words:
            pattern = "|".join(re.escape(w) for w in words)
            matches = mf[
                mf["title"].str.lower().str.contains(pattern, na=False)
            ].head(20)

    if matches.empty:
        return []

    # zip() peste liste native — evită overhead-ul Python per rând al iterrows()
    tmdb_col = matches["tmdbId"].tolist() if "tmdbId" in matches.columns else [None] * len(matches)
    movies = [
        {
            "movie_id": int(mid),
            "tmdb_id": _safe_tmdb_val(tmdb_val),
            "title": str(title),
            "genres": str(genres),
        }
        for mid, title, genres, tmdb_val in zip(
            matches["movieId"].tolist(),
            matches["title"].tolist(),
            matches["genres"].tolist(),
            tmdb_col,
        )
    ]

    enriched = await enrich_movies(movies)
    return _filter_enriched(enriched)


@router.get("/genre/{genre}", response_model=list[MovieOut])
@limiter.limit("10/minute")
async def get_movies_by_genre(
    request: Request,
    genre: str,
    limit: int = Query(default=200, ge=1, le=500),
    seed: Optional[int] = Query(None),
):
    """Returnează filme dintr-un gen specific. Cu seed, ordinea variază ușor la fiecare sesiune."""
    if not RecommenderService.is_ready():
        raise HTTPException(status_code=503, detail="Serviciul ML nu este gata încă")

    import numpy as np

    # _sorted_popular e pre-sortat la startup
    pop_df = RecommenderService._sorted_popular
    genre_lower = genre.lower()

    pool = pop_df[
        pop_df["genres"].str.lower().str.contains(re.escape(genre_lower), na=False)
    ].head(int(limit * 2))

    if pool.empty:
        raise HTTPException(status_code=404, detail=f"Niciun film găsit pentru genul '{genre}'")

    if seed is not None and len(pool) > limit:
        rng = np.random.default_rng(seed)
        scores = pool["popularity_score"].values.astype(float) + 1e-6
        probs = scores / scores.sum()
        chosen_idx = rng.choice(len(pool), size=min(limit, len(pool)), replace=False, p=probs)
        pool = pool.iloc[sorted(chosen_idx)]

    tmdb_col = pool["tmdbId"].tolist() if "tmdbId" in pool.columns else [None] * len(pool)
    movies = [
        {
            "movie_id": int(mid),
            "tmdb_id": _safe_tmdb_val(tmdb_val),
            "title": str(title),
            "genres": str(genres),
        }
        for mid, title, genres, tmdb_val in zip(
            pool["movieId"].tolist(),
            pool["title"].tolist(),
            pool["genres"].tolist(),
            tmdb_col,
        )
    ]

    enriched = await enrich_movies(movies)
    result = _filter_enriched(enriched)
    return result[:limit]


@router.get("/{movie_id}", response_model=MovieOut)
@limiter.limit("30/minute")
async def get_movie(request: Request, movie_id: int):
    """Returnează detalii pentru un film specific după MovieLens ID."""
    if not RecommenderService.is_ready():
        raise HTTPException(status_code=503, detail="Serviciul ML nu este gata încă")

    # Lookup O(1) via cache — fără scan O(N) al DataFrame-ului
    info = RecommenderService.get_movie_info(movie_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Film cu ID {movie_id} inexistent")

    movie = {
        "movie_id": movie_id,
        "tmdb_id": info["tmdb_id"],
        "title": info["title"],
        "genres": info["genres"],
    }

    enriched = await enrich_movies([movie])
    return _row_to_movie_out(enriched[0])
