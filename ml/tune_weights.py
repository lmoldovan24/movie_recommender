"""
ml/tune_weights.py — Grid search pentru ponderile hibride CB/CF/POP

Evaluare offline pe MovieLens cu Precision@K și NDCG@K.

Strategie split:
  - Per user: ultimele 20% ratinguri (cronologic, după timestamp) = test set
  - Restul = train set (signal pentru recomandări)
  - Filme evaluate cu rating >= RELEVANT_THRESHOLD în test = "relevante"

Metrice:
  - Precision@K: câte din top-K recomandate sunt relevante
  - NDCG@K: Normalized Discounted Cumulative Gain — penalizează relevant results
    aflate pe poziții mai joase în top-K

Rulare:
  cd /path/to/movie_recommender
  python -m ml.tune_weights [--top-k 10] [--min-ratings 20] [--output ml/best_weights.json]

Output:
  ml/best_weights.json — {"cb": 0.55, "cf": 0.25, "pop": 0.20, "precision_at_k": 0.12, "ndcg_at_k": 0.15}
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Prag rating pentru a considera un film "relevant" în test set
RELEVANT_THRESHOLD = 4.0

# Grila de ponderi testate (cb, cf, pop) — sumă = 1.0 cu toleranță 0.01
_CB_VALUES  = [0.40, 0.50, 0.55, 0.60, 0.70, 0.80]
_CF_VALUES  = [0.00, 0.10, 0.15, 0.20, 0.25, 0.30]
_POP_VALUES = [0.10, 0.15, 0.20, 0.25, 0.30]


def _build_weight_grid() -> list:
    grid = []
    for cb, cf, pop in product(_CB_VALUES, _CF_VALUES, _POP_VALUES):
        if abs(cb + cf + pop - 1.0) < 0.011:
            grid.append((round(cb, 2), round(cf, 2), round(pop, 2)))
    return grid


def _precision_at_k(recommended: list, relevant: set, k: int) -> float:
    if not relevant or not recommended:
        return 0.0
    top_k = recommended[:k]
    hits = sum(1 for mid in top_k if mid in relevant)
    return hits / k


def _ndcg_at_k(recommended: list, relevant: set, k: int) -> float:
    if not relevant or not recommended:
        return 0.0
    top_k = recommended[:k]
    dcg = sum(
        1.0 / np.log2(i + 2)
        for i, mid in enumerate(top_k)
        if mid in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / np.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def _split_user_ratings(user_df: pd.DataFrame, test_fraction: float = 0.20):
    """Split cronologic: ultimele test_fraction ratinguri = test, restul = train."""
    user_df = user_df.sort_values("timestamp")
    n_test = max(1, int(len(user_df) * test_fraction))
    train = user_df.iloc[:-n_test]
    test = user_df.iloc[-n_test:]
    return train, test


def _compute_component_scores(
    content_model,
    collab_model,
    pop_map: dict,
    all_movie_ids: list,
    signal: dict,
    user_ratings_dict: dict,
) -> tuple:
    """
    Calculează vectorii de scoruri normalizate CB, CF, POP pentru toți candidații.

    Returns:
        (candidate_ids, cb_norm, cf_norm_or_none, pop_norm)
    """
    from sklearn.metrics.pairwise import linear_kernel

    # Candidați = toate filmele, mai puțin cele din signal
    fav_set = set(signal.keys())
    candidate_ids = [mid for mid in all_movie_ids if mid not in fav_set]
    if not candidate_ids:
        return [], [], None, []

    # --- CB scores (quadratic weighting) ---
    valid_inputs = [
        (mid, r) for mid, r in signal.items()
        if mid in content_model.movie_id_to_idx
    ]
    if not valid_inputs:
        return [], [], None, []

    ratings_arr = np.array([r for _, r in valid_inputs], dtype=float)
    ratings_sq = ratings_arr ** 2
    weights = ratings_sq / ratings_sq.sum()

    input_indices = [content_model.movie_id_to_idx[mid] for mid, _ in valid_inputs]
    candidate_indices = [content_model.movie_id_to_idx[mid] for mid in candidate_ids]

    input_vecs = content_model.tfidf_matrix[input_indices]
    cand_vecs = content_model.tfidf_matrix[candidate_indices]
    sim_matrix = linear_kernel(cand_vecs, input_vecs)
    tfidf_scores = (sim_matrix * weights).sum(axis=1)  # (n_cands,)

    # Blend TF-IDF + SBERT identic cu HybridRecommender._content_scores()
    # — grid search evaluează astfel același sistem care rulează în producție.
    sbert_matrix = getattr(content_model, "sbert_matrix", None)
    if sbert_matrix is not None:
        input_embs = sbert_matrix[input_indices].astype(np.float32)
        cand_embs = sbert_matrix[candidate_indices].astype(np.float32)

        input_norms = np.linalg.norm(input_embs, axis=1, keepdims=True)
        cand_norms = np.linalg.norm(cand_embs, axis=1, keepdims=True)
        input_norms[input_norms < 1e-10] = 1.0
        cand_norms[cand_norms < 1e-10] = 1.0

        sbert_sim = (cand_embs / cand_norms) @ (input_embs / input_norms).T  # (n_cands, n_inputs)
        sbert_scores = (sbert_sim * weights).sum(axis=1)
        cb_scores = (0.55 * tfidf_scores + 0.45 * sbert_scores).tolist()
    else:
        cb_scores = tfidf_scores.tolist()

    # --- POP scores ---
    pop_scores = [pop_map.get(mid, 0.0) for mid in candidate_ids]

    # _minmax definit înainte de prima utilizare (fix: era definit după apel → NameError)
    def _minmax(scores):
        arr = np.array(scores, dtype=float)
        mn, mx = arr.min(), arr.max()
        if mx == mn:
            return [0.0] * len(scores)
        return ((arr - mn) / (mx - mn)).tolist()

    # --- CF scores ---
    cf_norm = None
    if user_ratings_dict and len(user_ratings_dict) >= 3 and collab_model.user_matrix_normalized is not None:
        cf_raw = collab_model.get_cf_scores_for_ratings(user_ratings=user_ratings_dict, top_k=150)
        if cf_raw:
            cf_list = [cf_raw.get(mid, 0.0) for mid in candidate_ids]
            n_nonzero = sum(1 for v in cf_list if v > 0)
            if n_nonzero >= 10:
                cf_norm = _minmax(cf_list)

    return (
        candidate_ids,
        _minmax(cb_scores),
        cf_norm,
        _minmax(pop_scores),
    )


def evaluate_weights(
    cb_norm: list,
    cf_norm,
    pop_norm: list,
    candidate_ids: list,
    relevant_ids: set,
    weights: tuple,
    top_k: int,
) -> tuple:
    """Calculează Precision@K și NDCG@K pentru o combinație de ponderi."""
    w_cb, w_cf, w_pop = weights

    if cf_norm is not None:
        scores = [
            w_cb * cb + w_cf * cf + w_pop * pop
            for cb, cf, pop in zip(cb_norm, cf_norm, pop_norm)
        ]
    else:
        total = w_cb + w_pop
        if total == 0:
            return 0.0, 0.0
        fb_cb = w_cb / total
        fb_pop = w_pop / total
        scores = [fb_cb * cb + fb_pop * pop for cb, pop in zip(cb_norm, pop_norm)]

    # Top-K candidați după scor
    top_k_ids = [
        candidate_ids[i]
        for i in np.argsort(scores)[::-1][:top_k]
    ]

    p = _precision_at_k(top_k_ids, relevant_ids, top_k)
    n = _ndcg_at_k(top_k_ids, relevant_ids, top_k)
    return p, n


def main():
    parser = argparse.ArgumentParser(description="Tunează ponderile hibride CB/CF/POP")
    parser.add_argument("--top-k", type=int, default=10, help="K pentru Precision@K și NDCG@K")
    parser.add_argument("--min-ratings", type=int, default=20, help="Număr minim ratinguri per user pentru evaluare")
    parser.add_argument("--max-users", type=int, default=500, help="Număr maxim useri evaluați (pentru viteză)")
    parser.add_argument("--output", type=str, default="ml/best_weights.json", help="Fișier output JSON")
    parser.add_argument("--metric", choices=["precision", "ndcg"], default="ndcg", help="Metrica de optimizat")
    args = parser.parse_args()

    # --- Încărcare date și modele ---
    logger.info("Încărcare date...")
    from ml.preprocess import load_data, preprocess_movies_and_tags, build_popularity_scores
    from ml.collaborative import CollaborativeRecommender
    from ml.content_based import ContentBasedRecommender

    ratings_full, movies, tags, links = load_data()

    # Adăugăm timestamp în ratings pentru split cronologic
    ratings_with_ts = pd.read_csv("data/ratings.csv", usecols=["userId", "movieId", "rating", "timestamp"])
    ratings_with_ts["userId"] = ratings_with_ts["userId"].astype(int)
    ratings_with_ts["movieId"] = ratings_with_ts["movieId"].astype(int)

    movie_features = preprocess_movies_and_tags(movies, tags, links)
    popularity_df = build_popularity_scores(ratings_full, movie_features)
    pop_map = popularity_df.set_index("movieId")["popularity_score"].to_dict()

    logger.info("Antrenare modele CB și CF...")
    content = ContentBasedRecommender()
    content.fit(movie_features)

    collab = CollaborativeRecommender()
    collab.load_ratings(ratings_full)
    collab.build_user_matrix()

    all_movie_ids = list(dict.fromkeys(
        int(mid) for mid in movie_features["movieId"].tolist()
        if int(mid) in content.movie_id_to_idx
    ))

    # --- Selectăm useri cu suficiente ratinguri ---
    user_counts = ratings_with_ts.groupby("userId").size()
    eligible_users = user_counts[user_counts >= args.min_ratings].index.tolist()
    np.random.seed(42)
    np.random.shuffle(eligible_users)
    eval_users = eligible_users[:args.max_users]
    logger.info("Evaluare pe %d useri (din %d eligibili)", len(eval_users), len(eligible_users))

    # --- Grid search ---
    weight_grid = _build_weight_grid()
    logger.info("Grilă: %d combinații de ponderi", len(weight_grid))

    # Acumulatori per combinație de ponderi
    precision_totals = {w: 0.0 for w in weight_grid}
    ndcg_totals = {w: 0.0 for w in weight_grid}
    n_evaluated = 0

    for i, user_id in enumerate(eval_users):
        user_df = ratings_with_ts[ratings_with_ts["userId"] == user_id]
        train_df, test_df = _split_user_ratings(user_df)

        if len(train_df) < 3:
            continue

        # Relevante = filme din test cu rating >= RELEVANT_THRESHOLD
        relevant_ids = set(
            test_df[test_df["rating"] >= RELEVANT_THRESHOLD]["movieId"].astype(int).tolist()
        )
        if not relevant_ids:
            continue

        # Signal = filme din train cu rating >= 3.0 (la fel ca în recommend())
        signal = {
            int(row.movieId): float(row.rating)
            for row in train_df[train_df["rating"] >= 3.0].itertuples()
        }
        if len(signal) < 3:
            continue

        user_ratings_dict = {int(row.movieId): float(row.rating) for row in train_df.itertuples()}

        # Pre-calculăm scorurile o singură dată per user
        candidate_ids, cb_norm, cf_norm, pop_norm = _compute_component_scores(
            content_model=content,
            collab_model=collab,
            pop_map=pop_map,
            all_movie_ids=all_movie_ids,
            signal=signal,
            user_ratings_dict=user_ratings_dict,
        )
        if not candidate_ids:
            continue

        # Evaluăm toate combinațiile de ponderi
        for w in weight_grid:
            p, n = evaluate_weights(cb_norm, cf_norm, pop_norm, candidate_ids, relevant_ids, w, args.top_k)
            precision_totals[w] += p
            ndcg_totals[w] += n

        n_evaluated += 1
        if (i + 1) % 50 == 0:
            logger.info("  Progres: %d/%d useri evaluați (%d valizi)", i + 1, len(eval_users), n_evaluated)

    if n_evaluated == 0:
        logger.error("Niciun user valid evaluat. Verificați --min-ratings.")
        sys.exit(1)

    logger.info("Evaluare completă: %d useri valizi", n_evaluated)

    # --- Alegem cea mai bună combinație ---
    if args.metric == "ndcg":
        totals = ndcg_totals
        metric_name = f"ndcg_at_{args.top_k}"
    else:
        totals = precision_totals
        metric_name = f"precision_at_{args.top_k}"

    best_weights = max(totals, key=lambda w: totals[w])
    best_score = totals[best_weights] / n_evaluated

    # Top 5 combinații pentru context
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    logger.info("Top 5 combinații (%s):", metric_name)
    for w, total in ranked[:5]:
        avg = total / n_evaluated
        p_avg = precision_totals[w] / n_evaluated
        n_avg = ndcg_totals[w] / n_evaluated
        logger.info("  CB=%.2f CF=%.2f POP=%.2f → Precision@%d=%.4f NDCG@%d=%.4f",
                    w[0], w[1], w[2], args.top_k, p_avg, args.top_k, n_avg)

    result = {
        "cb": best_weights[0],
        "cf": best_weights[1],
        "pop": best_weights[2],
        f"precision_at_{args.top_k}": round(precision_totals[best_weights] / n_evaluated, 4),
        f"ndcg_at_{args.top_k}": round(ndcg_totals[best_weights] / n_evaluated, 4),
        "n_users_evaluated": n_evaluated,
        "optimized_metric": metric_name,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    logger.info(
        "Cele mai bune ponderi: CB=%.2f CF=%.2f POP=%.2f (%s=%.4f) → salvat în %s",
        best_weights[0], best_weights[1], best_weights[2],
        metric_name, best_score, output_path,
    )


if __name__ == "__main__":
    main()
