"""
ml/hybrid.py — HybridRecommender

Combinator central al sistemului CineRec:
  Content-Based (TF-IDF cosine) + Collaborative Filtering (neighborhood Adjusted Cosine)
  + Popularity (Bayesian average).

Blending adaptiv per request:
  - CF activ  (overlap ≥ _MIN_CF_NONZERO filme cu scor > 0): 55% CB + 25% CF + 20% POP
  - CF inactiv (overlap insuficient cu MovieLens):             80% CB + 20% POP

Expune două metode publice:
  - recommend()          → recomandări personalizate pentru useri autentificați
  - get_content_picks()  → recomandări content-only pentru useri neautentificați
"""

import logging
from collections import defaultdict
from typing import Optional

import numpy as np
from sklearn.metrics.pairwise import linear_kernel

logger = logging.getLogger(__name__)

# Număr minim de filme cu scor CF > 0 pentru activarea componentei CF în blending.
# Sub acest prag, overlap-ul cu MovieLens e prea slab: normalizarea min-max ar amplifica
# artificial câteva scoruri nesemnificative spre 1.0, distorsionând blending-ul 55/25/20.
_MIN_CF_NONZERO = 10

# Pragul minim de rating pentru ca un film să fie inclus în signal și în reason.
# Exportat pentru a fi importat de router — sincronizare garantată între layere.
LIKED_THRESHOLD: float = 3.0


class HybridRecommender:
    """
    Sistem de recomandare hibrid: Content-Based + Collaborative Filtering + Popularity.

    Parametri constructor:
        content_model       — ContentBasedRecommender (fitted), furnizează tfidf_matrix
        collaborative_model — CollaborativeRecommender (built), furnizează CF scores
        pop_map             — {movie_id: popularity_score [0,1]} pre-calculat la startup
        movie_by_id         — {movie_id: {title, genres, tmdb_id}} cache O(1)
        all_movie_ids       — lista de movie IDs indexate în TF-IDF (pre-filtrați)
        weights             — (cb, cf, pop) ponderi pentru blending complet (CF activ).
                              Suma trebuie să fie 1.0. Default: (0.55, 0.25, 0.20).
                              Fallback fără CF folosește (cb+cf, pop) rebalansate automat.

    Coupling cu ContentBasedRecommender:
        Această clasă accesează direct două atribute publice ale content_model:
          - content_model.tfidf_matrix   (scipy sparse CSR, shape n_movies × n_features)
          - content_model.movie_id_to_idx ({movie_id: row_index})
        Dacă ContentBasedRecommender redenumește aceste atribute, HybridRecommender
        se va sparge la runtime. Tratați-le ca parte din interfața contractuală a clasei.
    """

    def __init__(
        self,
        content_model,
        collaborative_model,
        pop_map: dict,
        movie_by_id: dict,
        all_movie_ids: list,
        weights: tuple = (0.55, 0.25, 0.20),
    ):
        self.content_model = content_model
        self.collaborative_model = collaborative_model
        self.pop_map = pop_map
        self.movie_by_id = movie_by_id
        self.all_movie_ids = all_movie_ids
        self.weights = weights  # (cb, cf, pop) — tunat via ml/tune_weights.py

    # ------------------------------------------------------------------
    # API public
    # ------------------------------------------------------------------

    def recommend(
        self,
        signal: dict,
        user_ratings_dict: Optional[dict] = None,
        top_n: int = 10,
        seed: Optional[int] = None,
        liked_threshold: float = 3.0,
        exclude_ids: Optional[set] = None,
    ) -> list:
        """
        Recomandări personalizate (hibrid) pentru un user autentificat.

        Args:
            signal:            {movie_id: rating} — filmele apreciate (rating ≥ 3.0).
                               Construcția signal-ului e responsabilitatea router-ului.
            user_ratings_dict: toate ratingurile userului din DB (pentru CF Adjusted Cosine).
            top_n:             număr de recomandări de returnat.
            seed:              seed numpy RNG pentru sampling reproductibil per sesiune.
            liked_threshold:   prag rating pentru a genera mesajul "reason".
            exclude_ids:       set suplimentar de movie_id-uri excluse din candidați
                               (filme vizionate fără rating sau cu rating < 3.0 care nu
                               sunt în signal dar nu trebuie recomandate).

        Returns:
            list[dict] sortat descrescător după similarity_score, max top_n elemente.
        """
        if len(signal) < 3:
            return []

        content = self.content_model

        # Setul complet de filme de exclus: signal + exclude_ids suplimentar
        fav_set = set(signal.keys())
        if exclude_ids:
            fav_set = fav_set | exclude_ids

        # Doar filmele din signal care sunt indexate în TF-IDF
        valid_inputs = [
            (mid, r) for mid, r in signal.items()
            if mid in content.movie_id_to_idx
        ]
        if not valid_inputs:
            return []

        # Candidați = toate filmele indexate, mai puțin toate filmele excluse
        candidate_ids = [mid for mid in self.all_movie_ids if mid not in fav_set]
        if not candidate_ids:
            return []

        # --- Scoruri Content-Based (quadratic weighting) ---
        sim_matrix, content_scores = self._content_scores(valid_inputs, candidate_ids)

        # --- Scoruri Popularity ---
        pop_scores = np.array(
            [self.pop_map.get(mid, 0.0) for mid in candidate_ids], dtype=float
        )

        # --- Normalizare min-max independentă per componentă ---
        content_norm = self._normalize(content_scores.tolist())
        pop_norm = self._normalize(pop_scores.tolist())

        # --- Scoruri CF (condiționate de overlap MovieLens) ---
        cf_norm = self._compute_cf_norm(candidate_ids, user_ratings_dict)

        # --- Blending ---
        w_cb, w_cf, w_pop = self.weights
        if cf_norm is not None:
            # Hybrid complet cu ponderile configurate (tunat via ml/tune_weights.py)
            final_scores = [
                w_cb * cs + w_cf * cfs + w_pop * ps
                for cs, cfs, ps in zip(content_norm, cf_norm, pop_norm)
            ]
            logger.debug("Hybrid blend: %.0f%% CB + %.0f%% CF + %.0f%% POP", w_cb*100, w_cf*100, w_pop*100)
        else:
            # Fallback fără CF: rebalansăm CB și POP proporțional (ignorăm w_cf)
            total = w_cb + w_pop
            fb_cb = w_cb / total
            fb_pop = w_pop / total
            final_scores = [
                fb_cb * cs + fb_pop * ps
                for cs, ps in zip(content_norm, pop_norm)
            ]
            logger.debug("Hybrid blend (CF inactiv): %.0f%% CB + %.0f%% POP", fb_cb*100, fb_pop*100)

        # --- Construire rezultate cu reason ---
        results = self._build_results(
            candidate_ids, final_scores, sim_matrix, valid_inputs, liked_threshold
        )
        results.sort(key=lambda x: x["similarity_score"], reverse=True)

        # --- Diversitate gen + sampling ponderat ---
        pool = apply_genre_diversity(results, max_per_genre=3, pool_size=top_n * 3)

        if len(pool) <= top_n:
            return pool

        rng = np.random.default_rng(seed)
        pool_scores = np.array([r["similarity_score"] for r in pool], dtype=float)
        pool_scores = np.maximum(pool_scores, 1e-6)   # evită zero-weights
        probs = pool_scores / pool_scores.sum()
        chosen_indices = rng.choice(len(pool), size=top_n, replace=False, p=probs)
        chosen = [pool[i] for i in sorted(chosen_indices)]
        chosen.sort(key=lambda x: x["similarity_score"], reverse=True)
        return chosen

    def get_content_picks(
        self,
        movie_ids: list,
        genre_filter: Optional[str] = None,
        top_n: int = 10,
    ) -> list:
        """
        Recomandări content-based pure — fără user history.
        Folosit pentru /picks (useri neautentificați) și filme similare.

        Strategie similaritate: max(cosine față de oricare film din movie_ids).
        max > mean pentru input-uri diverse: un film foarte similar cu CEL PUȚIN
        unul din input-uri e relevant, chiar dacă e disimilar față de restul.

        Diversitate gen: aplică apply_genre_diversity(max_per_genre=3) identic cu
        recommend() — evită că rezultatele să fie dominate de un singur gen.

        Args:
            movie_ids:    lista de MovieLens IDs de referință.
            genre_filter: dacă e setat, restricționează candidații la genul dat.
            top_n:        număr de rezultate de returnat.
        """
        content = self.content_model
        input_set = set(movie_ids)

        input_indices = [
            content.movie_id_to_idx[mid]
            for mid in movie_ids
            if mid in content.movie_id_to_idx
        ]
        if not input_indices:
            return []

        # Pool candidați — filtrat opțional pe gen via movie_by_id (O(1) per lookup)
        if genre_filter:
            genre_lower = genre_filter.lower()
            candidate_ids = [
                mid for mid in self.all_movie_ids
                if mid not in input_set
                and genre_lower in (
                    self.movie_by_id.get(mid, {}).get("genres", "") or ""
                ).lower()
            ]
        else:
            candidate_ids = [mid for mid in self.all_movie_ids if mid not in input_set]

        if not candidate_ids:
            return []

        candidate_indices = [content.movie_id_to_idx[mid] for mid in candidate_ids]

        input_vecs = content.tfidf_matrix[input_indices]
        cand_vecs = content.tfidf_matrix[candidate_indices]

        sim_matrix = linear_kernel(cand_vecs, input_vecs)   # (n_cand, n_inputs) TF-IDF
        tfidf_scores = sim_matrix.max(axis=1)               # max similarity per candidat

        # Blend TF-IDF + SBERT identic cu _content_scores() — aceeași logică pentru useri autentificați
        if content.sbert_matrix is not None:
            input_embs = content.sbert_matrix[input_indices].astype(np.float32)
            cand_embs = content.sbert_matrix[candidate_indices].astype(np.float32)

            input_norms = np.linalg.norm(input_embs, axis=1, keepdims=True)
            cand_norms = np.linalg.norm(cand_embs, axis=1, keepdims=True)
            input_norms[input_norms < 1e-10] = 1.0
            cand_norms[cand_norms < 1e-10] = 1.0

            sbert_sim = (cand_embs / cand_norms) @ (input_embs / input_norms).T  # (n_cand, n_inputs)
            sbert_scores = sbert_sim.max(axis=1)             # max semantic similarity per candidat
            raw_scores = 0.55 * tfidf_scores + 0.45 * sbert_scores
            logger.debug("get_content_picks: 55%% TF-IDF + 45%% SBERT")
        else:
            raw_scores = tfidf_scores

        normalized = self._normalize(raw_scores.tolist())

        # Determină "de ce" — filmul input cel mai similar cu fiecare candidat
        input_ids_valid = [mid for mid in movie_ids if mid in content.movie_id_to_idx]
        best_input_local = sim_matrix.argmax(axis=1)

        results = []
        for i, (mid, score) in enumerate(zip(candidate_ids, normalized)):
            info = self.movie_by_id.get(mid)
            if info is None:
                continue

            reason = None
            local_idx = int(best_input_local[i])
            if local_idx < len(input_ids_valid):
                best_info = self.movie_by_id.get(input_ids_valid[local_idx])
                if best_info:
                    reason = f"Asemănător cu: {best_info['title']}"

            results.append({
                "movie_id": mid,
                "tmdb_id": info["tmdb_id"],
                "title": info["title"],
                "genres": info["genres"],
                "similarity_score": round(score, 4),
                "reason": reason,
            })

        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        diverse = apply_genre_diversity(results, max_per_genre=3, pool_size=top_n * 3)
        return diverse[:top_n]

    # ------------------------------------------------------------------
    # Metode private
    # ------------------------------------------------------------------

    def _content_scores(self, valid_inputs: list, candidate_ids: list):
        """
        Calculează scorurile content-based cu quadratic weighting.

        Quadratic weighting: rating² / Σrating²
        Efect: un film cu 5★ contribuie de 2.78× mai mult decât unul cu 3★
        (25/9 ≈ 2.78) față de 1.67× cu weighting liniar.

        Dacă SBERT e disponibil (content_model.sbert_matrix nu e None), blendăm:
          final_content = 0.55 * TF-IDF_score + 0.45 * SBERT_score
        TF-IDF: precis pe cuvinte cheie (genuri, taguri specifice)
        SBERT: captează semantică ("thriller psihologic" ≈ "horror psihologic")

        Returns: (sim_matrix, content_scores_array)
            sim_matrix: (n_candidates, n_inputs) — TF-IDF, pentru extragerea reason-ului
            content_scores: (n_candidates,) — scoruri brute înaintea normalizării
        """
        content = self.content_model

        ratings_arr = np.array([r for _, r in valid_inputs], dtype=float)
        ratings_sq = ratings_arr ** 2
        weights = ratings_sq / ratings_sq.sum()   # sum > 0 garantat (rating ≥ 3.0)

        input_indices = [content.movie_id_to_idx[mid] for mid, _ in valid_inputs]
        candidate_indices = [content.movie_id_to_idx[mid] for mid in candidate_ids]

        input_vecs = content.tfidf_matrix[input_indices]
        cand_vecs = content.tfidf_matrix[candidate_indices]

        sim_matrix = linear_kernel(cand_vecs, input_vecs)       # (n_cand, n_inputs)
        tfidf_scores = (sim_matrix * weights).sum(axis=1)       # (n_cand,)

        # Blend TF-IDF + SBERT dacă embeddings-urile sunt disponibile
        if content.sbert_matrix is not None:
            sbert_scores = self._sbert_scores(input_indices, candidate_indices, weights)
            content_scores = 0.55 * tfidf_scores + 0.45 * sbert_scores
            logger.debug("Content scores: 55%% TF-IDF + 45%% SBERT")
        else:
            content_scores = tfidf_scores

        return sim_matrix, content_scores

    def _sbert_scores(
        self,
        input_indices: list,
        candidate_indices: list,
        weights: np.ndarray,
    ) -> np.ndarray:
        """
        Scoruri de similaritate semantică via SBERT embeddings.

        Folosește cosine similarity pe embeddings dense (L2-normalizate → dot product = cosine).
        Aplică aceleași quadratic weights ca TF-IDF pentru consistență.

        Returns: (n_candidates,) array de scoruri semantice [0, 1]
        """
        sbert = self.content_model.sbert_matrix

        input_embs = sbert[input_indices].astype(np.float32)    # (n_inputs, d)
        cand_embs = sbert[candidate_indices].astype(np.float32) # (n_cands, d)

        # L2 normalizare pentru cosine similarity via dot product
        input_norms = np.linalg.norm(input_embs, axis=1, keepdims=True)
        cand_norms = np.linalg.norm(cand_embs, axis=1, keepdims=True)
        input_norms[input_norms < 1e-10] = 1.0
        cand_norms[cand_norms < 1e-10] = 1.0

        input_embs_norm = input_embs / input_norms
        cand_embs_norm = cand_embs / cand_norms

        # (n_cands, n_inputs) cosine similarity matrix
        sbert_sim = cand_embs_norm @ input_embs_norm.T
        return (sbert_sim * weights).sum(axis=1)  # (n_cands,)

    def _compute_cf_norm(
        self,
        candidate_ids: list,
        user_ratings_dict: Optional[dict],
    ) -> Optional[list]:
        """
        Calculează scoruri CF normalizate pentru lista de candidați.
        Returnează None dacă CF e inactiv.

        CF e inactiv dacă:
          - user_ratings_dict e None/gol sau < 3 ratinguri
          - modelul CF nu e disponibil (nu s-a inițializat)
          - overlap cu MovieLens produce < _MIN_CF_NONZERO filme cu scor > 0
            (overlap slab → normalizarea min-max ar amplifica artificial scoruri minore)
        """
        if (
            not user_ratings_dict
            or len(user_ratings_dict) < 3
            or self.collaborative_model is None
            or self.collaborative_model.user_matrix_normalized is None
        ):
            return None

        cf_raw = self.collaborative_model.get_cf_scores_for_ratings(
            user_ratings=user_ratings_dict,
            top_k=150,
        )
        if not cf_raw:
            return None

        cf_scores_list = [cf_raw.get(mid, 0.0) for mid in candidate_ids]
        n_nonzero = sum(1 for v in cf_scores_list if v > 0)

        if n_nonzero < _MIN_CF_NONZERO:
            logger.debug(
                "CF insuficient: %d scoruri non-zero (minim %d) — folosesc fallback CB+POP",
                n_nonzero, _MIN_CF_NONZERO,
            )
            return None

        logger.info("CF activ: %d filme cu scor CF > 0", n_nonzero)
        return self._normalize(cf_scores_list)

    def _build_results(
        self,
        candidate_ids: list,
        final_scores: list,
        sim_matrix,
        valid_inputs: list,
        liked_threshold: float,
    ) -> list:
        """
        Construiește lista de dicts rezultat cu metadate film și reason.

        reason e generat doar dacă filmul favorit de referință are rating ≥ liked_threshold,
        pentru a evita mesaje de tipul "recomandat pentru că ți-a plăcut X" când X are 1★.
        """
        best_input_local = sim_matrix.argmax(axis=1)
        input_title_map = {
            mid: self.movie_by_id[mid]["title"]
            for mid, _ in valid_inputs
            if mid in self.movie_by_id
        }

        results = []
        for i, (mid, score) in enumerate(zip(candidate_ids, final_scores)):
            info = self.movie_by_id.get(mid)
            if info is None:
                continue

            best_fav_mid, best_fav_rating = valid_inputs[int(best_input_local[i])]
            best_title = input_title_map.get(best_fav_mid, "")
            reason = (
                f"Recomandat pentru că ți-a plăcut: {best_title}"
                if best_title and best_fav_rating >= liked_threshold
                else None
            )

            results.append({
                "movie_id": mid,
                "tmdb_id": info["tmdb_id"],
                "title": info["title"],
                "genres": info["genres"],
                "similarity_score": round(score, 4),
                "reason": reason,
            })

        return results

    @staticmethod
    def _normalize(scores: list) -> list:
        """
        Min-max normalizare la [0, 1].
        Guards: listă goală → [], toate egale → [0.0, ...].
        """
        if not scores:
            return []
        arr = np.array(scores, dtype=float)
        mn, mx = arr.min(), arr.max()
        if mx == mn:
            return [0.0] * len(scores)
        return ((arr - mn) / (mx - mn)).tolist()


# ------------------------------------------------------------------
# Helpers standalone (exportate pentru testabilitate independentă)
# ------------------------------------------------------------------

def apply_genre_diversity(
    results: list,
    max_per_genre: int,
    pool_size: int,
) -> list:
    """
    Construiește un pool diversificat din rezultatele sortate descrescător.

    Strategia multi-label: un film e acceptat în pool-ul principal dacă NICIUN
    gen al său nu a atins limita max_per_genre. Contorizăm TOATE genurile filmului,
    nu doar primul (fix față de versiunea anterioară care trata "Action|Drama" ca
    pur Action, ignorând complet Drama).

    Exemplu: dacă max_per_genre=3 și avem deja 3 filme Action, un film Action|Drama
    va fi pus în overflow — indiferent de poziția genului în string.

    Filmele din overflow completează pool-ul dacă e nevoie pentru a atinge pool_size.

    Args:
        results:       lista sortată descrescător după scor.
        max_per_genre: număr maxim de filme per gen în pool-ul principal.
        pool_size:     dimensiunea totală țintă a pool-ului (înainte de sampling).
    """
    genre_counts: dict = defaultdict(int)
    primary_pool: list = []
    overflow: list = []

    for r in results:
        genres_str = r.get("genres", "") or ""
        all_genres = [g.strip() for g in genres_str.split("|") if g.strip()] or ["Unknown"]

        # Acceptăm filmul doar dacă niciun gen al lui nu e la limită
        if max(genre_counts[g] for g in all_genres) < max_per_genre:
            primary_pool.append(r)
            for g in all_genres:
                genre_counts[g] += 1
        else:
            overflow.append(r)

        if len(primary_pool) >= pool_size:
            break

    # Completăm cu overflow dacă pool-ul principal e sub pool_size
    remaining = pool_size - len(primary_pool)
    if remaining > 0:
        primary_pool.extend(overflow[:remaining])

    return primary_pool
