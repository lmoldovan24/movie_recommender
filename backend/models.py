from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, Float,
    DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from backend.database import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    is_active = Column(Boolean, default=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    watchlist = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    ratings = relationship("UserRating", back_populates="user", cascade="all, delete-orphan")
    watched_movies = relationship("WatchedMovie", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    is_revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="refresh_tokens")


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, index=True)
    attempted_at = Column(DateTime(timezone=True), default=_now)
    success = Column(Boolean, default=False)


class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, nullable=False)
    tmdb_id = Column(Integer)
    title = Column(String)
    genres = Column(String)
    poster_url = Column(String)
    rating = Column(Float, default=0.0)
    added_at = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id"),
        Index("ix_favorites_user_id", "user_id"),
    )


class UserRating(Base):
    __tablename__ = "user_ratings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id = Column(Integer, nullable=False)
    rating = Column(Float, nullable=True)
    rated_at = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="ratings")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id"),
        Index("ix_user_ratings_user_id", "user_id"),
    )


class WatchedMovie(Base):
    __tablename__ = "watched_movies"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id = Column(Integer, nullable=False)
    tmdb_id = Column(Integer)
    title = Column(String)
    genres = Column(String)
    poster_url = Column(String)
    watched_at = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="watched_movies")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id"),
        Index("ix_watched_movies_user_id", "user_id"),
    )


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    movie_id = Column(Integer, nullable=False)
    tmdb_id = Column(Integer)
    title = Column(String)
    genres = Column(String)
    poster_url = Column(String)
    added_at = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="watchlist")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id"),
        Index("ix_watchlist_user_id", "user_id"),
    )