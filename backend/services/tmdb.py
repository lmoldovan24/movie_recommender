import asyncio
import json
import logging
import os
from typing import Optional

import requests

from backend.config import settings

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
CACHE_FILE = "tmdb_cache.json"

# Cache în memorie — încărcat o singură dată la pornire
_memory_cache: dict = {}
_cache_dirty = False  # marcăm că avem date noi de salvat

# Semaphore: max 10 request-uri TMDB concurente (evităm rate-limit)
_semaphore = asyncio.Semaphore(10)
_save_lock = asyncio.Lock()


def _load_disk_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_disk_cache_sync(data: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except IOError as e:
        logger.warning(f"Nu am putut salva cache TMDB: {e}")


def preload_cache():
    """Apelat o singură dată la startup — încarcă tot cache-ul de pe disc în memorie."""
    global _memory_cache
    _memory_cache = _load_disk_cache()
    logger.info(f"TMDB cache încărcat: {len(_memory_cache)} intrări")


def _fetch_tmdb_sync(tmdb_id: int) -> Optional[dict]:
    """Fetch sincron — rulat cu asyncio.to_thread()."""
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {
        "api_key": settings.TMDB_API_KEY,
        "language": "en-US",
        "append_to_response": "videos",
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            poster_path = data.get("poster_path")

            trailer_key = None
            videos = data.get("videos", {}).get("results", [])
            for v in videos:
                if v.get("site") == "YouTube" and v.get("type") == "Trailer" and v.get("official"):
                    trailer_key = v["key"]
                    break
            if trailer_key is None:
                for v in videos:
                    if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                        trailer_key = v["key"]
                        break

            return {
                "tmdb_id": tmdb_id,
                "poster_url": f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None,
                "overview": data.get("overview"),
                "vote_average": data.get("vote_average"),
                "release_year": int(data["release_date"][:4]) if data.get("release_date") else None,
                "trailer_key": trailer_key,
            }
        elif response.status_code == 404:
            return None
        else:
            logger.warning(f"TMDB: status {response.status_code} pentru tmdb_id={tmdb_id}")
            return None
    except requests.RequestException as e:
        logger.warning(f"TMDB: eroare request pentru tmdb_id={tmdb_id}: {e}")
        return None


async def get_movie_details(tmdb_id: int) -> Optional[dict]:
    """
    Returnează detalii TMDB pentru un film.
    Verifică cache memorie mai întâi, altfel fetch concurent cu semaphore.
    """
    global _cache_dirty
    cache_key = str(tmdb_id)

    # Cache hit — instant
    if cache_key in _memory_cache:
        return _memory_cache[cache_key]

    # Cache miss — fetch concurent, limitat de semaphore
    async with _semaphore:
        # Verificăm din nou după ce am intrat (alt coroutine putea să îl fi fetch-uit deja)
        if cache_key in _memory_cache:
            return _memory_cache[cache_key]

        result = await asyncio.to_thread(_fetch_tmdb_sync, tmdb_id)

        if result:
            _memory_cache[cache_key] = result
            _cache_dirty = True

        return result


async def flush_cache():
    """Salvează cache-ul pe disc dacă are modificări. Apelat după un batch de enrichment."""
    global _cache_dirty
    if not _cache_dirty:
        return
    async with _save_lock:
        if not _cache_dirty:
            return
        await asyncio.to_thread(_save_disk_cache_sync, _memory_cache)
        _cache_dirty = False


async def enrich_movies(movies: list[dict]) -> list[dict]:
    """
    Adaugă poster_url, overview, vote_average, release_year la o listă de filme.
    Toate request-urile TMDB rulează CONCURENT (asyncio.gather).
    """
    async def enrich_one(movie: dict) -> dict:
        tmdb_id = movie.get("tmdb_id")
        if tmdb_id:
            details = await get_movie_details(tmdb_id)
            if details:
                return {**movie, **details}
        return movie

    enriched = await asyncio.gather(*[enrich_one(m) for m in movies])

    # Salvăm cache-ul în background după batch
    asyncio.create_task(flush_cache())

    return list(enriched)
