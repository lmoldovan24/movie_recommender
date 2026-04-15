from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.limiter import limiter
from backend.models import User, Watchlist, Favorite
from backend.schemas import WatchlistCreate, WatchlistOut, FavoriteOut

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistOut])
@limiter.limit("60/minute")
def get_watchlist(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returnează toate filmele din watchlist-ul utilizatorului curent."""
    return db.query(Watchlist).filter(Watchlist.user_id == current_user.id).all()


@router.post("", response_model=WatchlistOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def add_to_watchlist(
    request: Request,
    data: WatchlistCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adaugă un film la watchlist. Returnează 409 dacă există deja."""
    existing = db.query(Watchlist).filter(
        Watchlist.user_id == current_user.id,
        Watchlist.movie_id == data.movie_id,
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Filmul este deja în watchlist",
        )

    item = Watchlist(
        user_id=current_user.id,
        movie_id=data.movie_id,
        tmdb_id=data.tmdb_id,
        title=data.title,
        genres=data.genres,
        poster_url=data.poster_url,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{watchlist_id}", status_code=status.HTTP_200_OK)
@limiter.limit("60/minute")
def remove_from_watchlist(
    request: Request,
    watchlist_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Șterge un film din watchlist după ID-ul înregistrării."""
    item = db.query(Watchlist).filter(
        Watchlist.id == watchlist_id,
        Watchlist.user_id == current_user.id,
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Înregistrarea nu există sau nu îți aparține",
        )

    db.delete(item)
    db.commit()
    return {"detail": "Șters din watchlist"}


@router.post("/{watchlist_id}/seen", response_model=FavoriteOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def mark_as_seen(
    request: Request,
    watchlist_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Marchează un film ca văzut — îl mută din watchlist în favorite.
    Dacă filmul e deja în favorite, nu creează duplicat — doar șterge din watchlist.
    """
    item = db.query(Watchlist).filter(
        Watchlist.id == watchlist_id,
        Watchlist.user_id == current_user.id,
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Înregistrarea nu există sau nu îți aparține",
        )

    # Verifică existența în favorite ÎNAINTE de INSERT
    existing_favorite = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.movie_id == item.movie_id,
    ).first()

    if existing_favorite:
        db.delete(item)
        db.commit()
        db.refresh(existing_favorite)
        return existing_favorite

    favorite = Favorite(
        user_id=current_user.id,
        movie_id=item.movie_id,
        tmdb_id=item.tmdb_id,
        title=item.title,
        genres=item.genres,
        poster_url=item.poster_url,
    )
    db.add(favorite)
    db.delete(item)
    db.commit()
    db.refresh(favorite)
    return favorite
