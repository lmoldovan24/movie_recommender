from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.limiter import limiter
from backend.models import User, Favorite, UserRating
from backend.schemas import FavoriteCreate, FavoriteOut

router = APIRouter(prefix="/favorites", tags=["favorites"])


def _enrich_with_rating(favorites: list, db: Session, user_id: int) -> list:
    """Îmbogățește lista de favorite cu ratingul din UserRating (singura sursă de adevăr)."""
    movie_ids = [f.movie_id for f in favorites]
    ratings_map = {}
    if movie_ids:
        rows = db.query(UserRating).filter(
            UserRating.user_id == user_id,
            UserRating.movie_id.in_(movie_ids),
            UserRating.rating.isnot(None),
        ).all()
        ratings_map = {r.movie_id: r.rating for r in rows}

    results = []
    for f in favorites:
        results.append({
            "id": f.id,
            "movie_id": f.movie_id,
            "tmdb_id": f.tmdb_id,
            "title": f.title,
            "genres": f.genres,
            "poster_url": f.poster_url,
            "added_at": f.added_at,
            "user_rating": ratings_map.get(f.movie_id),
        })
    return results


@router.get("/", response_model=list[FavoriteOut])
@limiter.limit("60/minute")
def get_favorites(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    favorites = db.query(Favorite).filter(Favorite.user_id == current_user.id).all()
    return _enrich_with_rating(favorites, db, current_user.id)


@router.post("/", response_model=FavoriteOut)
@limiter.limit("30/minute")
def add_favorite(
    request: Request,
    body: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.movie_id == body.movie_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Film deja în favorite")

    fav = Favorite(
        user_id=current_user.id,
        movie_id=body.movie_id,
        tmdb_id=body.tmdb_id,
        title=body.title,
        genres=body.genres,
        poster_url=body.poster_url,
    )
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return _enrich_with_rating([fav], db, current_user.id)[0]


@router.delete("/{favorite_id}", status_code=204)
@limiter.limit("60/minute")
def remove_favorite(
    request: Request,
    favorite_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fav = db.query(Favorite).filter(
        Favorite.id == favorite_id,
        Favorite.user_id == current_user.id,
    ).first()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorit negăsit")
    db.delete(fav)
    db.commit()
