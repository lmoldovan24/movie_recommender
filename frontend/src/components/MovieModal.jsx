import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { recommendationsApi } from "../api/recommendations";
import { ratingsApi } from "../api/ratings";
import { watchedApi } from "../api/watched";
import { useAuth } from "../contexts/AuthContext";
import StarRating from "./StarRating";
import SkeletonCard from "./SkeletonCard";
import MovieCard from "./MovieCard";
import clsx from "clsx";

const NO_POSTER = "/assets/no-poster.png";

export default function MovieModal({
  movie,
  onClose,
  onFavoriteToggle,
  onWatchlistToggle,
  favorites = [],
  watchlist = [],
  watched = [],
  ratings = [],
  onCardClick,
}) {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();

  const favMap = Object.fromEntries(favorites.map((f) => [f.movie_id, f]));
  const watchMap = Object.fromEntries(watchlist.map((w) => [w.movie_id, w.id]));
  const watchedSet = new Set(watched.map((w) => w.movie_id));
  const ratingEntry = ratings.find((r) => r.movie_id === movie.movie_id) ?? null;
  const isFavorite = movie.movie_id in favMap;
  const favEntry = favMap[movie.movie_id] ?? null;
  const isWatchlisted = movie.movie_id in watchMap;
  const isWatched = watchedSet.has(movie.movie_id);

  const [localRating, setLocalRating] = useState(ratingEntry?.rating ?? 0);
  const [ratingStatus, setRatingStatus] = useState(null);

  useEffect(() => {
    setLocalRating(ratingEntry?.rating ?? 0);
  }, [ratings, movie.movie_id]);

  useEffect(() => {
    const handleKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  const { data: similar = [], isLoading: loadingSimilar } = useQuery({
    queryKey: ["picks", movie.movie_id],
    queryFn: () => recommendationsApi.getPicks([movie.movie_id]).then((r) => r.data),
    staleTime: 1000 * 60 * 5,
  });

  const ratingMutation = useMutation({
    mutationFn: ({ movieId, payload }) => ratingsApi.upsert(movieId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ratings"] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      queryClient.invalidateQueries({ queryKey: ["watched"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      setRatingStatus("saved");
      setTimeout(() => setRatingStatus(null), 2000);
    },
    onError: () => {
      setRatingStatus("error");
      setTimeout(() => setRatingStatus(null), 2000);
    },
  });

  const handleRatingChange = (newRating) => {
    setLocalRating(newRating);
    setRatingStatus("saving");
    ratingMutation.mutate({
      movieId: movie.movie_id,
      payload: {
        rating: newRating,
        tmdb_id: movie.tmdb_id ?? null,
        title: movie.title ?? null,
        genres: movie.genres ?? null,
        poster_url: movie.poster_url ?? null,
      },
    });
  };

  const watchedMutation = useMutation({
    mutationFn: () => isWatched ? watchedApi.unmark(movie.movie_id) : watchedApi.mark(movie),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watched"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 w-8 h-8 bg-zinc-800 hover:bg-zinc-700 rounded-full flex items-center justify-center text-zinc-400 hover:text-zinc-200 transition-all text-lg leading-none"
          aria-label="Închide"
        >
          ×
        </button>

        {/* Trailer */}
        {movie.trailer_key && (
          <div className="w-full rounded-t-xl overflow-hidden bg-black">
            <iframe
              src={`https://www.youtube.com/embed/${movie.trailer_key}?rel=0`}
              title={`Trailer ${movie.title}`}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              className="w-full"
              style={{ aspectRatio: "16/9" }}
            />
          </div>
        )}

        {/* Main content */}
        <div className="flex flex-col sm:flex-row">
          {/* Poster */}
          {!movie.trailer_key && (
            <div className="sm:w-52 flex-shrink-0">
              <img
                src={movie.poster_url || NO_POSTER}
                alt={movie.title}
                className="w-full object-cover rounded-t-xl sm:rounded-l-xl sm:rounded-tr-none"
                style={{ maxHeight: "340px" }}
                onError={(e) => { e.target.src = NO_POSTER; }}
              />
            </div>
          )}

          {/* Info */}
          <div className="flex-1 p-6 flex flex-col gap-4">
            <div>
              <h2 className="text-xl font-semibold text-zinc-100 leading-tight mb-3">
                {movie.title}
              </h2>
              <div className="flex flex-wrap items-center gap-2">
                {movie.release_year && (
                  <span className="bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded text-xs">
                    {movie.release_year}
                  </span>
                )}
                {movie.genres?.split("|").map((g) => (
                  <span key={g} className="bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded text-xs">
                    {g}
                  </span>
                ))}
              </div>
            </div>

            {/* TMDB rating */}
            {movie.vote_average && (
              <div className="flex items-center gap-2">
                <span className="text-yellow-400 text-sm">★</span>
                <span className="text-sm text-zinc-300">{movie.vote_average.toFixed(1)}</span>
                <span className="text-xs text-zinc-600">/ 10 · TMDB</span>
              </div>
            )}

            {/* Overview */}
            {movie.overview ? (
              <p className="text-sm text-zinc-400 leading-relaxed">{movie.overview}</p>
            ) : (
              <p className="text-sm text-zinc-600 italic">Descriere indisponibilă.</p>
            )}

            {/* User rating */}
            {isAuthenticated && (
              <div className="bg-zinc-800/60 rounded-lg p-3 flex flex-col gap-2">
                <p className="text-xs text-zinc-500">
                  {localRating > 0 ? "Nota ta" : "Evaluează"}
                </p>
                <div className="flex items-center gap-3 flex-wrap">
                  <StarRating
                    rating={localRating}
                    onChange={handleRatingChange}
                    readonly={ratingMutation.isPending}
                    size="lg"
                  />
                  {ratingStatus === "saving" && (
                    <span className="text-xs text-zinc-500 animate-pulse w-full">Se salvează…</span>
                  )}
                  {ratingStatus === "saved" && (
                    <span className="text-xs text-green-500 w-full">Salvat</span>
                  )}
                  {ratingStatus === "error" && (
                    <span className="text-xs text-red-500 w-full">Eroare. Încearcă din nou.</span>
                  )}
                </div>
              </div>
            )}

            {/* Action buttons */}
            {isAuthenticated && (
              <div className="flex flex-wrap gap-2 mt-auto pt-1">
                <button
                  onClick={() => onFavoriteToggle(movie, isFavorite ? favEntry?.id : null)}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all",
                    isFavorite
                      ? "bg-red-500/20 text-red-400 ring-1 ring-red-500/30 hover:bg-red-500/30"
                      : "bg-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700"
                  )}
                >
                  {isFavorite ? "În favorite" : "Favorite"}
                </button>
                <button
                  onClick={() => onWatchlistToggle(movie, isWatchlisted ? watchMap[movie.movie_id] : null)}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all",
                    isWatchlisted
                      ? "bg-indigo-500/20 text-indigo-400 ring-1 ring-indigo-500/30 hover:bg-indigo-500/30"
                      : "bg-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700"
                  )}
                >
                  {isWatchlisted ? "În watchlist" : "Watchlist"}
                </button>
                <button
                  onClick={() => watchedMutation.mutate()}
                  disabled={watchedMutation.isPending}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50",
                    isWatched
                      ? "bg-green-500/20 text-green-400 ring-1 ring-green-500/30 hover:bg-green-500/30"
                      : "bg-zinc-800 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700"
                  )}
                >
                  {isWatched ? "Văzut" : "Marchează văzut"}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Similar movies */}
        <div className="px-6 pb-6 pt-4 border-t border-zinc-800">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-4">
            Similare
          </p>
          {loadingSimilar ? (
            <div className="grid grid-cols-5 gap-3">
              {Array.from({ length: 10 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : similar.length === 0 ? (
            <p className="text-sm text-zinc-600">Nu am găsit filme similare.</p>
          ) : (
            <div className="grid grid-cols-5 gap-3">
              {similar.slice(0, 10).map((m) => (
                <MovieCard
                  key={m.movie_id}
                  movie={m}
                  isFavorite={m.movie_id in favMap}
                  isWatchlisted={m.movie_id in watchMap}
                  favoriteId={favMap[m.movie_id]?.id}
                  watchlistId={watchMap[m.movie_id]}
                  onFavoriteToggle={onFavoriteToggle}
                  onWatchlistToggle={onWatchlistToggle}
                  onCardClick={onCardClick}
                  compact
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
