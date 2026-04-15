from collections import Counter

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.limiter import limiter
from backend.models import User, Favorite, UserRating, WatchedMovie
from backend.schemas import UserStatsOut, GenreStat

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/stats", response_model=UserStatsOut)
@limiter.limit("30/minute")
def get_stats(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    favorites = db.query(Favorite).filter(Favorite.user_id == current_user.id).all()
    user_ratings = db.query(UserRating).filter(UserRating.user_id == current_user.id).all()
    watched = db.query(WatchedMovie).filter(WatchedMovie.user_id == current_user.id).all()

    # Genuri preferate din favorite
    genres_counter: Counter = Counter()
    for f in favorites:
        if f.genres:
            for g in f.genres.split("|"):
                g = g.strip()
                if g and g != "(no genres listed)":
                    genres_counter[g] += 1

    # Medie ratinguri (doar cele cu stele setate)
    rated = [r.rating for r in user_ratings if r.rating is not None]
    avg_rating = round(sum(rated) / len(rated), 2) if rated else 0.0

    top_genres = [
        GenreStat(genre=g, count=c)
        for g, c in genres_counter.most_common(8)
    ]

    return UserStatsOut(
        favorites_count=len(favorites),
        total_ratings=len(user_ratings),
        avg_rating=avg_rating,
        watched_count=len(watched),
        top_genres=top_genres,
    )
