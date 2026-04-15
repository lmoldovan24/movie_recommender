import clsx from "clsx";
import { useAuth } from "../contexts/AuthContext";

const NO_POSTER = "/assets/no-poster.png";

export default function MovieCard({
  movie,
  isFavorite = false,
  isWatchlisted = false,
  onFavoriteToggle,
  onWatchlistToggle,
  onCardClick,
  favoriteId = null,
  watchlistId = null,
  showRating = false,
  rating = 0,
  compact = false,
}) {
  const { isAuthenticated } = useAuth();
  const year = movie.release_year ?? "";
  const genre = movie.genres?.split("|")[0] ?? "";

  return (
    <div className="group flex flex-col">
      {/* Poster */}
      <div
        className="relative aspect-[2/3] overflow-hidden rounded-lg bg-zinc-900 cursor-pointer"
        onClick={() => onCardClick?.(movie)}
      >
        <img
          src={movie.poster_url || NO_POSTER}
          alt={movie.title}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
          onError={(e) => { e.target.src = NO_POSTER; }}
        />

        {/* Hover overlay */}
        {isAuthenticated && !compact && (
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex flex-col justify-end p-2.5 gap-1.5">
            <div className="flex gap-1.5">
              {onFavoriteToggle && (
                <button
                  onClick={(e) => { e.stopPropagation(); onFavoriteToggle(movie, isFavorite ? favoriteId : null); }}
                  className={clsx(
                    "flex-1 py-1.5 rounded text-xs font-medium transition-colors",
                    isFavorite
                      ? "bg-red-500 text-white"
                      : "bg-white/15 text-white hover:bg-white/25 backdrop-blur-sm"
                  )}
                >
                  {isFavorite ? "❤ Favorit" : "+ Favorite"}
                </button>
              )}
              {onWatchlistToggle && (
                <button
                  onClick={(e) => { e.stopPropagation(); onWatchlistToggle(movie, isWatchlisted ? watchlistId : null); }}
                  className={clsx(
                    "flex-1 py-1.5 rounded text-xs font-medium transition-colors",
                    isWatchlisted
                      ? "bg-indigo-500 text-white"
                      : "bg-white/15 text-white hover:bg-white/25 backdrop-blur-sm"
                  )}
                >
                  {isWatchlisted ? "✓ Watchlist" : "+ Watchlist"}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Rating badge */}
        {showRating && rating > 0 && (
          <div className="absolute top-2 right-2 bg-black/70 backdrop-blur-sm text-yellow-400 text-xs font-semibold px-1.5 py-0.5 rounded">
            ★ {rating.toFixed(1)}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="mt-2 px-0.5 cursor-pointer" onClick={() => onCardClick?.(movie)}>
        <p className="text-sm text-zinc-300 leading-snug line-clamp-2 group-hover:text-zinc-100 transition-colors">
          {movie.title}
        </p>
        {!compact && (year || genre) && (
          <p className="text-xs text-zinc-600 mt-0.5">
            {[year, genre].filter(Boolean).join(" · ")}
          </p>
        )}
      </div>
    </div>
  );
}
