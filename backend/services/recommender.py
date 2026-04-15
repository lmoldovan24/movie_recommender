import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_init_lock = threading.Lock()

# Event în loc de bool pentru is_ready() — threading.Event.is_set() oferă garanții
# formale de vizibilitate a memoriei între thread-uri (memory barrier implicit),
# spre deosebire de citirea unui bool Python fără lock.
_init_event = threading.Event()

# ---------------------------------------------------------------------------
# Cache TTL per-user pentru get_personal()
# Evită re-calculul CF dot-product (O(n_users)) la request-uri rapide consecutive.
# Key: (signal_items, ratings_items, top_n, seed, exclude_items)
# TTL de 30s: suficient de scurt pentru a reflecta rating-uri noi, suficient de
# lung pentru a absorbi refresh-uri rapide / SSR double-fetch.
# ---------------------------------------------------------------------------
_personal_cache: dict = {}           # {key: (monotonic_ts, result)}
_personal_cache_lock = threading.Lock()
_PERSONAL_CACHE_TTL: float = 30.0    # secunde
_PERSONAL_CACHE_MAX: int = 500       # max intrări înainte de pruning


def _make_cache_key(
    signal: dict,
    user_ratings_dict: Optional[dict],
    top_n: int,
    liked_threshold: float,
    exclude_ids: Optional[set],
) -> str:
    """
    Construiește un cache key stabil ca SHA-256 hex string.

    SHA-256 în loc de tuple mare:
      - Evită alocarea unui tuple de sute de perechi (movie_id, rating) la fiecare request,
        chiar și pe cache hit — relevant pentru useri cu 500+ ratinguri.
      - Key mic (64 chars) → lookup O(1) mai rapid în dict față de hash(tuple_mare).
      - sha256 e stabil cross-process (spre deosebire de hash() Python cu seed aleatoriu).
    Risc de coliziune SHA-256: 1/2^256 — neglijabil.
    """
    parts = "|".join([
        repr(sorted(signal.items())),
        repr(sorted(user_ratings_dict.items()) if user_ratings_dict else []),
        str(top_n),
        str(liked_threshold),
        repr(sorted(exclude_ids) if exclude_ids else []),
    ])
    return hashlib.sha256(parts.encode()).hexdigest()


def _cache_get(key: str) -> Optional[list]:
    with _personal_cache_lock:
        entry = _personal_cache.get(key)
        if entry is None:
            return None
        ts, result = entry
        if time.monotonic() - ts < _PERSONAL_CACHE_TTL:
            return result
        del _personal_cache[key]   # expirat
    return None


def _cache_set(key: str, result: list) -> None:
    with _personal_cache_lock:
        _personal_cache[key] = (time.monotonic(), result)
        if len(_personal_cache) > _PERSONAL_CACHE_MAX:
            # Curățăm intrările expirate; dacă nu sunt suficiente, eliminăm cele mai vechi
            now = time.monotonic()
            expired = [
                k for k, (ts, _) in _personal_cache.items()
                if now - ts >= _PERSONAL_CACHE_TTL
            ]
            for k in expired:
                del _personal_cache[k]
            # Dacă tot depășim limita, scoatem cele mai vechi 25%
            if len(_personal_cache) > _PERSONAL_CACHE_MAX:
                overflow = sorted(_personal_cache, key=lambda k: _personal_cache[k][0])
                for k in overflow[: _PERSONAL_CACHE_MAX // 4]:
                    del _personal_cache[k]


class RecommenderService:
    """
    Singleton wrapper peste modelele ML din ml/.
    Inițializat o singură dată la startup în lifespan (asyncio.to_thread).

    Responsabilități:
      - Orchestrează încărcarea datelor și antrenarea modelelor
      - Expune HybridRecommender prin metode de clasă simple
      - Menține cache-uri O(1) imutabile după startup

    Nu conține logică ML directă — aceasta trăiește în ml/hybrid.py,
    ml/content_based.py și ml/collaborative.py.

    Thread safety pentru is_ready():
      Folosim _init_event (threading.Event) în loc de un bool simplu.
      Event.is_set() oferă garanții formale de vizibilitate a memoriei (memory barrier)
      între thread-ul de inițializare și thread-urile de request — corect fără GIL.
    """

    # Modele ML
    hybrid_model = None           # HybridRecommender — logica de recomandare centrală

    # Date brute — păstrate pentru acces direct (ex: search pe titluri)
    movie_features: Optional[pd.DataFrame] = None

    # Cache-uri O(1) — pre-calculate la startup, imutabile după aceea
    _movie_by_id: dict = {}                       # movie_id → {title, genres, tmdb_id}
    _pop_map: dict = {}                            # movie_id → popularity_score [0,1]
    _all_movie_ids: list = []                      # IDs indexate în TF-IDF
    _genres_list: list = []                        # genuri sortate (GET /genres)
    _sorted_popular: Optional[pd.DataFrame] = None # popularity_df sortat desc, reset index

    @classmethod
    def initialize(cls):
        """
        Rulat cu asyncio.to_thread() în lifespan — NU blochează event loop-ul.
        Încarcă datele, antrenează modelele și construiește toate cache-urile.

        Atribuirea clasă se face ATOMIC la final: evită stare parțial inițializată
        vizibilă altor thread-uri în caz de eroare intermediară.
        Lock-ul previne dublă inițializare dacă to_thread() ar fi apelat concurent.
        """
        with _init_lock:
            if _init_event.is_set():
                logger.info("RecommenderService deja inițializat, skip.")
                return

            logger.info("RecommenderService: început inițializare ML...")

            try:
                from ml.preprocess import load_data, preprocess_movies_and_tags, build_popularity_scores
                from ml.collaborative import CollaborativeRecommender
                from ml.content_based import ContentBasedRecommender
                from ml.hybrid import HybridRecommender

                # --- Încărcare și preprocesare date ---
                ratings, movies, tags, links = load_data()
                movie_features = preprocess_movies_and_tags(movies, tags, links)
                popularity_df = build_popularity_scores(ratings, movie_features)

                # --- Collaborative Filtering ---
                collab = CollaborativeRecommender()
                collab.load_ratings(ratings)
                collab.build_user_matrix()
                logger.info("CF: user matrix construit (Adjusted Cosine, mean-centered pe overlap).")

                # --- Content-Based Filtering ---
                content = ContentBasedRecommender(use_sbert=True)
                content.fit(movie_features)
                logger.info(
                    "CB: antrenat (TF-IDF%s).",
                    " + SBERT" if content.sbert_matrix is not None else "",
                )

                # --- Cache metadate filme O(1) ---
                # Construcție vectorizată: evită iterrows() O(N) cu overhead Python per rând.
                # apply() pe coloana tmdbId gestionează NaN / valori non-numerice (ex: "nan", "").
                # zip() peste liste native e de 10–50× mai rapid decât iterrows() la 62K+ rânduri.
                def _safe_tmdb(val) -> Optional[int]:
                    try:
                        return int(val) if pd.notna(val) else None
                    except (ValueError, TypeError):
                        return None

                tmdb_series = movie_features["tmdbId"].apply(_safe_tmdb)

                movie_cache: dict = {
                    int(mid): {
                        "title": str(title),
                        "genres": str(genres),
                        "tmdb_id": tmdb,
                    }
                    for mid, title, genres, tmdb in zip(
                        movie_features["movieId"].tolist(),
                        movie_features["title"].tolist(),
                        movie_features["genres"].tolist(),
                        tmdb_series.tolist(),
                    )
                }

                # --- Cache-uri derivate ---
                pop_map: dict = popularity_df.set_index("movieId")["popularity_score"].to_dict()

                # IDs pre-filtrați la startup — evită verificarea content.movie_id_to_idx per request.
                # dict.fromkeys: deduplicare O(N) cu păstrarea ordinii inserției (Python 3.7+),
                # previne candidați duplicați în recomandări dacă movie_features are rânduri repetate.
                all_movie_ids: list = list(dict.fromkeys(
                    int(mid) for mid in movie_features["movieId"].tolist()
                    if int(mid) in content.movie_id_to_idx
                ))

                all_genres: set = set()
                for genres_str in movie_features["genres"].dropna():
                    for g in genres_str.split("|"):
                        g = g.strip()
                        if g and g != "(no genres listed)":
                            all_genres.add(g)
                genres_list: list = sorted(all_genres)

                # reset_index() — permite iloc/indexare pozițională corectă după filtrare
                sorted_popular: pd.DataFrame = (
                    popularity_df
                    .sort_values("popularity_score", ascending=False)
                    .reset_index(drop=True)
                    .copy()
                )

                # --- Ponderi hibride — din fișierul de tuning dacă există ---
                hybrid_weights = (0.55, 0.25, 0.20)   # default
                weights_path = Path("ml/best_weights.json")
                if weights_path.exists():
                    try:
                        import json as _json
                        _w = _json.loads(weights_path.read_text())
                        hybrid_weights = (float(_w["cb"]), float(_w["cf"]), float(_w["pop"]))
                        logger.info(
                            "Ponderi hibride încărcate din %s: CB=%.2f CF=%.2f POP=%.2f",
                            weights_path, *hybrid_weights,
                        )
                    except Exception as _e:
                        logger.warning("Nu s-au putut citi ponderile din %s: %s — folosesc default.", weights_path, _e)
                else:
                    logger.info("ml/best_weights.json absent — ponderi default: CB=0.55 CF=0.25 POP=0.20")

                # --- HybridRecommender — combinator central ---
                hybrid = HybridRecommender(
                    content_model=content,
                    collaborative_model=collab,
                    pop_map=pop_map,
                    movie_by_id=movie_cache,
                    all_movie_ids=all_movie_ids,
                    weights=hybrid_weights,
                )
                logger.info("HybridRecommender inițializat (CB + CF + Popularity).")

                # --- Atribuire atomică — starea clasă e consistentă sau deloc ---
                # _init_event.set() e ULTIMA operație: până la set(), is_ready() returnează
                # False → niciun request nu va vedea stare parțial inițializată.
                # Event.set() include un memory barrier → toate atribuirile de mai sus
                # sunt vizibile oricărui thread care observă is_set() == True.
                cls.movie_features = movie_features
                cls.hybrid_model = hybrid
                cls._movie_by_id = movie_cache
                cls._pop_map = pop_map
                cls._all_movie_ids = all_movie_ids
                cls._genres_list = genres_list
                cls._sorted_popular = sorted_popular
                _init_event.set()   # memory barrier — semnalează că inițializarea e completă

                logger.info(
                    "RecommenderService: inițializare completă. "
                    "%d filme indexate, %d genuri.",
                    len(movie_cache), len(genres_list),
                )

            except Exception as e:
                logger.error("RecommenderService: eroare la inițializare: %s", e)
                raise

    # ------------------------------------------------------------------
    # API public
    # ------------------------------------------------------------------

    @classmethod
    def is_ready(cls) -> bool:
        return _init_event.is_set()

    @classmethod
    def get_movie_info(cls, movie_id: int) -> Optional[dict]:
        """Lookup O(1) metadate film: title, genres, tmdb_id."""
        return cls._movie_by_id.get(movie_id)

    @classmethod
    def get_picks(
        cls,
        movie_ids: list,
        genre: Optional[str] = None,
        top_n: int = 10,
    ) -> list:
        """
        Recomandări content-based pentru utilizatori neautentificați.
        Delegă la HybridRecommender.get_content_picks().
        """
        if not _init_event.is_set() or not movie_ids:
            return []
        return cls.hybrid_model.get_content_picks(
            movie_ids=movie_ids,
            genre_filter=genre,
            top_n=top_n,
        )

    @classmethod
    def get_personal(
        cls,
        signal: dict,
        user_ratings_dict: Optional[dict] = None,
        top_n: int = 10,
        seed: Optional[int] = None,
        liked_threshold: float = 3.0,
        exclude_ids: Optional[set] = None,
    ) -> list:
        """
        Recomandări hibride personalizate pentru utilizatori autentificați.
        Delegă la HybridRecommender.recommend().

        Args:
            signal:            {movie_id: rating} filmele apreciate (rating ≥ 3.0).
                               Construcția signal-ului e responsabilitatea router-ului.
            user_ratings_dict: toate ratingurile din DB (pentru CF Adjusted Cosine).
            top_n:             număr de recomandări de returnat.
            seed:              seed numpy RNG pentru sampling reproductibil.
            liked_threshold:   prag rating pentru mesajul "reason".
            exclude_ids:       set suplimentar de movie_id-uri excluse din candidați
                               (toate filmele vizionate/favorite, inclusiv cele cu rating
                               prea mic pentru a intra în signal).
        """
        if not _init_event.is_set():
            return []

        # Request-urile cu seed explicit sunt pentru varietate per sesiune — nu le cacheăm.
        # Fiecare seed distinct ar crea o intrare separată în cache, umplând rapid _PERSONAL_CACHE_MAX
        # fără beneficiu real (seed-ul schimbă doar sampling-ul final, nu calculul ML costisitor).
        if seed is not None:
            return cls.hybrid_model.recommend(
                signal=signal,
                user_ratings_dict=user_ratings_dict,
                top_n=top_n,
                seed=seed,
                liked_threshold=liked_threshold,
                exclude_ids=exclude_ids,
            )

        # Cache key: SHA-256 hash al tuturor elementelor care influențează rezultatul.
        # Hash string (64 chars) în loc de tuple mare → lookup O(1) mai rapid,
        # mai puțin memorie per intrare, fără alocare costisitoare la useri cu mulți ratinguri.
        cache_key = _make_cache_key(signal, user_ratings_dict, top_n, liked_threshold, exclude_ids)
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug("get_personal: cache hit")
            return cached

        result = cls.hybrid_model.recommend(
            signal=signal,
            user_ratings_dict=user_ratings_dict,
            top_n=top_n,
            seed=None,
            liked_threshold=liked_threshold,
            exclude_ids=exclude_ids,
        )
        _cache_set(cache_key, result)
        return result

    @classmethod
    def get_popular_fallback(cls, exclude_ids: set, top_n: int = 30) -> list:
        """
        Filme populare diversificate filtrate de istoricul userului.
        Fallback când semnalul e insuficient pentru recomandări personalizate.

        Aplică genre diversity (max 4 per gen) pe top-ul de popularitate astfel
        că un user nou vede un mix de genuri, nu 10 filme de acțiune la rând.
        Evita cold start plictisitor cu liste monotone.

        Filtrare vectorizată (pandas boolean mask) — evită iterrows() O(N)
        cu overhead Python per rând, de 10–100× mai rapid la exclude_ids mari.
        """
        if not _init_event.is_set():
            return []

        from ml.hybrid import apply_genre_diversity

        # Luăm un pool mai mare pentru a da diversității șanse să funcționeze
        mask = ~cls._sorted_popular["movieId"].isin(exclude_ids)
        subset = cls._sorted_popular[mask].head(top_n * 4)

        results = []
        for movie_id_val, pop_val in zip(
            subset["movieId"].values,
            subset["popularity_score"].values,
        ):
            mid = int(movie_id_val)
            info = cls._movie_by_id.get(mid)
            if info is None:
                continue
            results.append({
                "movie_id": mid,
                "tmdb_id": info["tmdb_id"],
                "title": info["title"],
                "genres": info["genres"],
                "similarity_score": round(float(pop_val), 4),
                "reason": None,
            })

        # Diversificare gen: max 4 filme per gen, pool de top_n * 2
        diverse = apply_genre_diversity(results, max_per_genre=4, pool_size=top_n * 2)
        return diverse[:top_n]
