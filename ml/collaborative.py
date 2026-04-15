import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CollaborativeRecommender:
    def __init__(self, random_state=42):
        self.random_state = random_state
        self.ratings = None
        # Sparse user-movie matrices (păstrate pentru tune_weights.py + fallback)
        self.user_matrix_raw = None          # ratinguri originale — pentru weighted average scoring
        self.user_matrix_normalized = None   # mean-centered + L2 — pentru cosine similarity (fallback)
        # SVD latent factor model (principal) — O(k) la inferență vs O(n_users) pentru neighborhood
        self.item_factors = None             # (n_movies, k) — factori latenti per film
        self.cf_movie_id_to_idx: dict = {}
        self._idx_to_movie_id: dict = {}

    def load_ratings(self, ratings: pd.DataFrame) -> None:
        """
        Încarcă ratingurile fără a antrena niciun model.
        Apelat înaintea build_user_matrix().
        """
        self.ratings = ratings.copy()

    def build_user_matrix(self) -> None:
        """
        Construiește matricea user-movie sparse din ratingurile MovieLens și
        calculează descompunerea SVD (Truncated SVD, k=50 factori latenti).

        Matrici sparse (păstrate pentru fallback și tune_weights.py):
        - user_matrix_raw: ratinguri originale (0.5–5.0)
        - user_matrix_normalized: mean-centered + L2 norm (Adjusted Cosine)

        SVD (principal):
        - Descompune R ≈ U Σ Vᵀ → item_factors = Vᵀ.T * Σ (n_movies × k)
        - La inferență: user_vec = medie ponderată a item_factors pt. filmele ratinguite
          predicted_scores = item_factors @ user_vec  → O(n_movies * k), nu O(n_users)
        - Mult mai scalabil decât neighborhood CF la dataset-uri mari.

        Apelat o singură dată după load_ratings(), în thread separat la startup.
        """
        if self.ratings is None or self.ratings.empty:
            logger.warning("build_user_matrix: ratings DataFrame absent sau gol — CF dezactivat.")
            return

        from scipy.sparse import csr_matrix
        from sklearn.preprocessing import normalize

        all_user_ids = self.ratings["userId"].unique()
        all_movie_ids = self.ratings["movieId"].unique()

        user_id_to_idx = {int(uid): i for i, uid in enumerate(all_user_ids)}
        self.cf_movie_id_to_idx = {int(mid): i for i, mid in enumerate(all_movie_ids)}
        self._idx_to_movie_id = {i: int(mid) for mid, i in self.cf_movie_id_to_idx.items()}

        rows = self.ratings["userId"].map(user_id_to_idx).values
        cols = self.ratings["movieId"].map(self.cf_movie_id_to_idx).values

        n_users = len(all_user_ids)
        n_movies = len(all_movie_ids)

        # Matrice raw — ratinguri originale
        raw_data = self.ratings["rating"].values.astype(np.float32)
        self.user_matrix_raw = csr_matrix((raw_data, (rows, cols)), shape=(n_users, n_movies))

        # Mean-center per user: elimină bias-ul userilor care dau mereu 4-5
        user_means_series = self.ratings.groupby("userId")["rating"].transform("mean")
        centered_data = (self.ratings["rating"].values - user_means_series.values).astype(np.float32)
        centered_matrix = csr_matrix((centered_data, (rows, cols)), shape=(n_users, n_movies))
        self.user_matrix_normalized = normalize(centered_matrix, norm="l2", copy=True)

        logger.info(
            "CF user matrix: %d useri, %d filme (raw + mean-centered Adjusted Cosine).",
            n_users, n_movies,
        )

        # --- SVD Truncated (k=50 factori latenti) ---
        # svds() din scipy.sparse.linalg e eficient pe matrici sparse mari.
        # k=50: compromis bun între calitate și viteză (< 100 în general suficient).
        # Returnează valorile singulare în ordine CRESCĂTOARE — inversăm pentru
        # a păstra cei mai semnificativi factori primii (convenție standard).
        try:
            from scipy.sparse.linalg import svds
            k = min(50, min(n_users, n_movies) - 1)
            U, sigma, Vt = svds(self.user_matrix_raw.astype(np.float64), k=k)

            # Reordonare descrescătoare după valorile singulare
            order = np.argsort(sigma)[::-1]
            sigma = sigma[order]
            Vt = Vt[order, :]

            # item_factors (n_movies, k): absorb sigma în factori item pentru dot product simplu
            self.item_factors = (Vt.T * sigma).astype(np.float32)
            logger.info(
                "CF SVD: descompunere completă (%d useri × %d filme → k=%d factori latenti).",
                n_users, n_movies, k,
            )
        except Exception as exc:
            logger.warning("CF SVD eșuat (%s) — se va folosi neighborhood CF ca fallback.", exc)
            self.item_factors = None

    def get_cf_scores_for_ratings(self, user_ratings: dict, top_k: int = 100) -> dict:
        """
        Estimează scoruri CF pentru filmele din dataset.

        Dacă SVD e disponibil (cazul normal): proiectează ratingurile userului
        în spațiul latent și calculează predicted scores pentru toate filmele.
        Complexitate O(n_movies * k) — mult mai rapidă decât neighborhood O(n_users).

        Dacă SVD nu e disponibil (fallback): Adjusted Cosine Similarity pe vecinătate.

        user_ratings: {movie_id: rating} — ratingurile utilizatorului app
        Returns: {movie_id: cf_score}
        """
        if not user_ratings:
            return {}

        if self.item_factors is not None:
            return self._svd_scores(user_ratings)

        # Fallback: neighborhood CF cu Adjusted Cosine
        if self.user_matrix_normalized is None:
            return {}
        return self._neighborhood_scores(user_ratings, top_k)

    # ------------------------------------------------------------------
    # Metode private
    # ------------------------------------------------------------------

    def _svd_scores(self, user_ratings: dict) -> dict:
        """
        Predicție CF via SVD fold-in.

        Construiește vectorul latent al userului ca medie ponderată (mean-centered)
        a factorilor item pentru filmele ratinguite, apoi face dot product cu toți
        factorii item pentru a obține scoruri de predicție.

        Mean-centering înainte de ponderat — același principiu ca Adjusted Cosine:
        un user care dă mereu 4-5 nu va domina prin bias, ci prin preferințe reale.
        """
        overlap = {
            int(mid): float(r)
            for mid, r in user_ratings.items()
            if int(mid) in self.cf_movie_id_to_idx
        }
        if not overlap:
            return {}

        k = self.item_factors.shape[1]
        user_mean = float(np.mean(list(overlap.values())))

        user_vec = np.zeros(k, dtype=np.float32)
        total_weight = 0.0
        for mid, rating in overlap.items():
            idx = self.cf_movie_id_to_idx[mid]
            w = abs(rating - user_mean)
            signed_w = rating - user_mean
            user_vec += signed_w * self.item_factors[idx]
            total_weight += w

        if total_weight < 1e-10:
            # Toate ratingurile identice — folosim media necentrată
            user_vec = np.zeros(k, dtype=np.float32)
            for mid in overlap:
                user_vec += self.item_factors[self.cf_movie_id_to_idx[mid]]
            user_vec /= len(overlap)
        else:
            user_vec /= total_weight

        # Predicted scores pentru toate filmele: dot product cu factori item
        scores = self.item_factors @ user_vec  # (n_movies,)

        rated_indices = {self.cf_movie_id_to_idx[mid] for mid in overlap}
        result: dict = {}
        for idx, score in enumerate(scores):
            if idx not in rated_indices and score > 0:
                mid = self._idx_to_movie_id.get(idx)
                if mid is not None:
                    result[mid] = float(score)

        return result

    def _neighborhood_scores(self, user_ratings: dict, top_k: int) -> dict:
        """
        Fallback: Adjusted Cosine Similarity pe vecinătate (user-based neighborhood CF).
        Folosit doar dacă SVD nu e disponibil.
        """
        from scipy.sparse import csr_matrix
        from sklearn.preprocessing import normalize

        n_movies = self.user_matrix_normalized.shape[1]

        overlap = {
            int(mid): float(r)
            for mid, r in user_ratings.items()
            if int(mid) in self.cf_movie_id_to_idx
        }
        if not overlap:
            return {}

        user_mean = float(np.mean(list(overlap.values())))
        cols = [self.cf_movie_id_to_idx[mid] for mid in overlap]
        vals = [r - user_mean for r in overlap.values()]

        new_user_vec = csr_matrix(
            (vals, ([0] * len(cols), cols)), shape=(1, n_movies)
        )
        new_user_norm = normalize(new_user_vec, norm="l2")

        sims = np.asarray(
            new_user_norm.dot(self.user_matrix_normalized.T).todense()
        ).flatten()

        top_k_actual = min(top_k, len(sims))
        top_k_idx = np.argpartition(sims, -top_k_actual)[-top_k_actual:]
        top_k_sims = sims[top_k_idx]

        positive = top_k_sims > 0
        if not positive.any():
            return {}

        top_k_idx = top_k_idx[positive]
        top_k_sims = top_k_sims[positive]

        user_sub = self.user_matrix_raw[top_k_idx]
        weighted_sum = np.asarray(user_sub.T.dot(top_k_sims)).flatten()
        rated_mask = (user_sub > 0).astype(np.float32)
        weighted_count = np.asarray(rated_mask.T.dot(top_k_sims)).flatten()

        with np.errstate(divide="ignore", invalid="ignore"):
            avg_scores = np.where(weighted_count > 0, weighted_sum / weighted_count, 0.0)

        result: dict = {}
        for idx in np.nonzero(avg_scores)[0]:
            mid = self._idx_to_movie_id.get(int(idx))
            if mid is not None:
                result[mid] = float(avg_scores[idx])

        return result
