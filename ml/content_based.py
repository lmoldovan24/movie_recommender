import hashlib
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)

# Model SBERT compact: 22M parametri, ~80MB download, 384-dim, rapid pe CPU
_SBERT_MODEL = "all-MiniLM-L6-v2"
_CACHE_DIR = Path("data")


class ContentBasedRecommender:
    def __init__(self, max_features: int = 5000, use_sbert: bool = True):
        """
        Args:
            max_features: numărul maxim de features TF-IDF.
            use_sbert:    dacă True, calculează embeddings SBERT (all-MiniLM-L6-v2)
                          și le combină cu TF-IDF pentru înțelegere semantică.
                          Embeddings-urile sunt cache-uite pe disk după prima rulare.
        """
        self.max_features = max_features
        self.use_sbert = use_sbert
        self.movie_features = None
        self.vectorizer = None
        self.tfidf_matrix = None
        # Nu se stochează cosine_sim NxN în memorie (~700MB).
        # Se calculează la cerere doar pentru filmele relevante.
        self.movie_id_to_idx: dict = {}
        # SBERT embeddings (n_movies × 384) — None dacă use_sbert=False sau la eroare
        self.sbert_matrix: np.ndarray | None = None

    def fit(self, movie_features: pd.DataFrame) -> None:
        self.movie_features = movie_features.copy()

        # --- TF-IDF ---
        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=self.max_features)
        self.tfidf_matrix = self.vectorizer.fit_transform(
            self.movie_features["content_text"].fillna("")
        )

        self.movie_id_to_idx = {
            int(movie_id): idx for idx, movie_id in enumerate(self.movie_features["movieId"])
        }

        logger.info(
            "CB: TF-IDF antrenat (%d filme, max_features=%d).",
            len(self.movie_features), self.max_features,
        )

        # --- SBERT (opțional) ---
        if self.use_sbert:
            self._fit_sbert()

    def _fit_sbert(self) -> None:
        """
        Calculează embeddings semantice SBERT pentru content_text al fiecărui film.

        Cache pe disk (data/sbert_cache_<hash>.npy):
          - Hash MD5 al primelor 10K caractere din content concatenat identifică
            dataset-ul fără a hasha tot fișierul (costisitor la 62K filme).
          - La restart ulterior: embeddings se încarcă în <1s în loc de 5-15 min re-encodare.

        Modelul all-MiniLM-L6-v2:
          - 384-dim embeddings, ~80MB download unic
          - Captează semantică: "thriller psihologic" ≈ "horror psihologic"
            (imposibil pentru TF-IDF care tratează fiecare cuvânt independent)
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning(
                "sentence-transformers nu este instalat — SBERT dezactivat. "
                "Rulați: pip install sentence-transformers"
            )
            return

        texts = self.movie_features["content_text"].fillna("").tolist()

        # Cache key bazat pe conținut (primele 10K caractere sunt suficiente)
        sample = "".join(texts)[:10_000]
        cache_hash = hashlib.md5(sample.encode()).hexdigest()[:16]
        cache_path = _CACHE_DIR / f"sbert_cache_{cache_hash}.npy"

        if cache_path.exists():
            try:
                self.sbert_matrix = np.load(str(cache_path))
                logger.info(
                    "CB SBERT: embeddings încărcate din cache %s %s.",
                    cache_path.name, self.sbert_matrix.shape,
                )
                return
            except Exception as exc:
                logger.warning("CB SBERT: cache corupt (%s) — re-calculez.", exc)

        logger.info("CB SBERT: calculez embeddings pentru %d filme (prima rulare)...", len(texts))
        try:
            model = SentenceTransformer(_SBERT_MODEL)
            embeddings = model.encode(
                texts,
                batch_size=256,
                show_progress_bar=True,
                convert_to_numpy=True,
            )
            self.sbert_matrix = embeddings.astype(np.float32)
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            np.save(str(cache_path), self.sbert_matrix)
            logger.info(
                "CB SBERT: %d embeddings calculate și salvate în %s.",
                len(texts), cache_path.name,
            )
        except Exception as exc:
            logger.error("CB SBERT: eroare la encodare (%s) — SBERT dezactivat.", exc)
            self.sbert_matrix = None
