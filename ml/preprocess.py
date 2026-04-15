import re
import pandas as pd


def normalize_text(text: str) -> str:
    if pd.isna(text):
        return ""
    text = str(text).lower()
    text = text.replace("|", " ")
    text = re.sub(r"\b(19|20)\d{2}\b", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)   # cratima dispare — recuperăm genurile cu cratime
    text = text.replace("sci fi", "scifi")
    text = text.replace("film noir", "filmnoir")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_data(
    ratings_path="data/ratings.csv",
    movies_path="data/movies.csv",
    tags_path="data/tags.csv",
    links_path="data/links.csv"
):
    ratings = pd.read_csv(ratings_path, usecols=["userId", "movieId", "rating"])
    movies = pd.read_csv(movies_path, usecols=["movieId", "title", "genres"])
    tags = pd.read_csv(tags_path, usecols=["userId", "movieId", "tag"])
    links = pd.read_csv(links_path, usecols=["movieId", "imdbId", "tmdbId"])

    ratings = ratings.dropna(subset=["userId", "movieId", "rating"]).copy()
    movies = movies.dropna(subset=["movieId", "title", "genres"]).copy()
    tags = tags.dropna(subset=["movieId", "tag"]).copy()
    links = links.dropna(subset=["movieId"]).copy()

    ratings["userId"] = ratings["userId"].astype(int)
    ratings["movieId"] = ratings["movieId"].astype(int)

    movies["movieId"] = movies["movieId"].astype(int)
    tags["movieId"] = tags["movieId"].astype(int)
    links["movieId"] = links["movieId"].astype(int)

    return ratings, movies, tags, links


def preprocess_movies_and_tags(movies: pd.DataFrame, tags: pd.DataFrame, links: pd.DataFrame, include_title=True):
    movies = movies.copy()
    tags = tags.copy()
    links = links.copy()

    movies["genres_clean"] = movies["genres"].fillna("").apply(normalize_text)
    movies["title_clean"] = movies["title"].fillna("").apply(normalize_text)
    tags["tag_clean"] = tags["tag"].fillna("").apply(normalize_text)

    grouped_tags = (
        tags.groupby("movieId")["tag_clean"]
        .apply(lambda x: " ".join(x.astype(str)))
        .reset_index()
        .rename(columns={"tag_clean": "tags"})
    )

    movie_features = movies.merge(grouped_tags, on="movieId", how="left")
    movie_features = movie_features.merge(links, on="movieId", how="left")
    movie_features["tags"] = movie_features["tags"].fillna("")

    if include_title:
        movie_features["content_text"] = (
            movie_features["title_clean"] + " " +
            movie_features["genres_clean"] + " " +
            movie_features["tags"]
        ).str.strip()
    else:
        movie_features["content_text"] = (
            movie_features["genres_clean"] + " " +
            movie_features["tags"]
        ).str.strip()

    return movie_features


def build_popularity_scores(ratings: pd.DataFrame, movie_features: pd.DataFrame) -> pd.DataFrame:
    stats = (
        ratings.groupby("movieId")["rating"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "avg_rating", "count": "rating_count"})
    )

    # Bayesian average: (v/(v+m)) * R + (m/(v+m)) * C
    # v = numărul de ratinguri al filmului
    # m = pragul minim (percentila 25 a numărului de ratinguri) — filmele cu sub m ratinguri
    #     sunt trase spre media globală C, evitând ca un film cu 1 rating de 5.0
    #     să bată filme cu mii de ratinguri de 4.5
    # R = media filmului, C = media globală a TUTUROR ratingurilor (nu mean-of-means)
    # Folosim ratings["rating"].mean() și nu stats["avg_rating"].mean() pentru că
    # mean-of-means supraevaluează filmele cu puține ratinguri față de media adevărată.
    m = stats["rating_count"].quantile(0.25)
    C = ratings["rating"].mean()

    stats["popularity_score"] = (
        (stats["rating_count"] / (stats["rating_count"] + m)) * stats["avg_rating"] +
        (m / (stats["rating_count"] + m)) * C
    )

    # Normalizare la [0, 1] pentru a putea fi folosit în blending
    min_score = stats["popularity_score"].min()
    max_score = stats["popularity_score"].max()
    if max_score > min_score:
        stats["popularity_score"] = (stats["popularity_score"] - min_score) / (max_score - min_score)
    else:
        stats["popularity_score"] = 0.0

    popularity_df = movie_features.merge(stats, on="movieId", how="left")
    popularity_df["avg_rating"] = popularity_df["avg_rating"].fillna(0)
    popularity_df["rating_count"] = popularity_df["rating_count"].fillna(0)
    popularity_df["popularity_score"] = popularity_df["popularity_score"].fillna(0)

    return popularity_df