import { useRef } from "react";
import MovieCard from "./MovieCard";
import SkeletonCard from "./SkeletonCard";

const SECTION = "text-xs font-semibold text-zinc-500 uppercase tracking-widest";

export default function HorizontalRow({
  title,
  movies = [],
  isLoading = false,
  favorites = [],
  watchlist = [],
  onFavoriteToggle,
  onWatchlistToggle,
  onCardClick,
  skeletonCount = 10,
}) {
  const rowRef = useRef(null);

  const scroll = (dir) => {
    rowRef.current?.scrollBy({ left: dir * 640, behavior: "smooth" });
  };

  const favMap = Object.fromEntries(favorites.map((f) => [f.movie_id, f.id]));
  const watchMap = Object.fromEntries(watchlist.map((w) => [w.movie_id, w.id]));

  // Ascunde filmele fără poster (date incomplete)
  const visibleMovies = movies.filter((m) => m.poster_url);

  if (!isLoading && visibleMovies.length === 0) return null;

  return (
    <section className="group/row">
      <div className="flex items-center justify-between mb-3">
        <p className={SECTION}>{title}</p>
        <div className="flex gap-1 opacity-0 group-hover/row:opacity-100 transition-opacity duration-150">
          <button
            onClick={() => scroll(-1)}
            className="w-6 h-6 rounded-full bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center text-zinc-400 hover:text-zinc-200 transition-colors text-base leading-none"
            aria-label="Înapoi"
          >
            ‹
          </button>
          <button
            onClick={() => scroll(1)}
            className="w-6 h-6 rounded-full bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center text-zinc-400 hover:text-zinc-200 transition-colors text-base leading-none"
            aria-label="Înainte"
          >
            ›
          </button>
        </div>
      </div>

      <div
        ref={rowRef}
        className="flex gap-3 overflow-x-auto pb-1"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        {isLoading
          ? Array.from({ length: skeletonCount }).map((_, i) => (
              <div key={i} className="w-32 sm:w-36 md:w-40 flex-shrink-0">
                <SkeletonCard />
              </div>
            ))
          : visibleMovies.map((movie) => (
              <div key={movie.movie_id} className="w-32 sm:w-36 md:w-40 flex-shrink-0">
                <MovieCard
                  movie={movie}
                  isFavorite={movie.movie_id in favMap}
                  isWatchlisted={movie.movie_id in watchMap}
                  favoriteId={favMap[movie.movie_id]}
                  watchlistId={watchMap[movie.movie_id]}
                  onFavoriteToggle={onFavoriteToggle}
                  onWatchlistToggle={onWatchlistToggle}
                  onCardClick={onCardClick}
                />
              </div>
            ))}
      </div>
    </section>
  );
}
