import re
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional


# --- Auth ---

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        if len(v) < 3:
            raise ValueError("Username trebuie să aibă minim 3 caractere")
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username poate conține doar litere, cifre și underscore (_)")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Parola trebuie să aibă minim 8 caractere")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Parola trebuie să conțină cel puțin o literă mare (A-Z)")
        if not re.search(r"[a-z]", v):
            raise ValueError("Parola trebuie să conțină cel puțin o literă mică (a-z)")
        if not re.search(r"\d", v):
            raise ValueError("Parola trebuie să conțină cel puțin o cifră (0-9)")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Răspuns la login/refresh — tokenurile sunt în httpOnly cookies, nu în body."""
    token_type: str = "bearer"
    user: Optional["UserOut"] = None

TokenResponse.model_rebuild()


# --- Movies ---

class MovieOut(BaseModel):
    movie_id: int
    tmdb_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    vote_average: Optional[float] = None
    release_year: Optional[int] = None
    similarity_score: Optional[float] = None
    trailer_key: Optional[str] = None
    reason: Optional[str] = None


# --- Favorites ---

class FavoriteCreate(BaseModel):
    movie_id: int
    tmdb_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    poster_url: Optional[str] = None


class FavoriteOut(BaseModel):
    id: int
    movie_id: int
    tmdb_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    poster_url: Optional[str] = None
    added_at: datetime
    user_rating: Optional[float] = None  # din UserRating, singura sursă de adevăr

    model_config = {"from_attributes": True}


# --- User Ratings ---

class UserRatingOut(BaseModel):
    id: int
    movie_id: int
    rating: Optional[float] = None
    rated_at: datetime

    model_config = {"from_attributes": True}


class UserRatingEnriched(BaseModel):
    id: int
    movie_id: int
    tmdb_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    poster_url: Optional[str] = None
    rating: Optional[float] = None
    rated_at: datetime

    model_config = {"from_attributes": True}


class UserRatingUpsert(BaseModel):
    rating: Optional[float] = None
    # Date film — folosite pentru auto-marcare ca văzut
    tmdb_id: Optional[int] = None
    title: Optional[str] = None
    genres: Optional[str] = None
    poster_url: Optional[str] = None

    @field_validator("rating")
    @classmethod
    def valid_rating(cls, v):
        if v is None:
            return v
        if not (0.5 <= v <= 5.0):
            raise ValueError("Rating trebuie să fie între 0.5 și 5.0")
        if round(v * 2) != v * 2:
            raise ValueError("Rating acceptă doar pași de 0.5 (ex: 1.0, 1.5, 2.0...)")
        return v


# --- Watched ---

class WatchedCreate(BaseModel):
    tmdb_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    poster_url: Optional[str] = None


class WatchedOut(BaseModel):
    id: int
    movie_id: int
    tmdb_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    poster_url: Optional[str] = None
    watched_at: datetime

    model_config = {"from_attributes": True}


# --- Stats ---

class GenreStat(BaseModel):
    genre: str
    count: int


class UserStatsOut(BaseModel):
    favorites_count: int
    total_ratings: int
    avg_rating: float
    watched_count: int
    top_genres: list[GenreStat]


# --- Watchlist ---

class WatchlistCreate(BaseModel):
    movie_id: int
    tmdb_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    poster_url: Optional[str] = None


class WatchlistOut(BaseModel):
    id: int
    movie_id: int
    tmdb_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    poster_url: Optional[str] = None
    added_at: datetime

    model_config = {"from_attributes": True}