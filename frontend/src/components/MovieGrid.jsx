import MovieCard from "./MovieCard";
import SkeletonCard from "./SkeletonCard";
import EmptyState from "./EmptyState";

const SKELETON_COUNT = 10;

export default function MovieGrid({
  movies = [],
  isLoading = false,
  favorites = [],
  watchlist = [],
  onFavoriteToggle,
  onWatchlistToggle,
  onCardClick,
  emptyIcon,
  emptyTitle,
  emptyMessage,
}) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8 gap-4">
        {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  const visibleMovies = movies.filter((m) => m.poster_url);

  if (!visibleMovies.length) {
    return (
      <EmptyState
        icon={emptyIcon}
        title={emptyTitle ?? "Niciun film găsit"}
        message={emptyMessage}
      />
    );
  }

  const favMap = Object.fromEntries(favorites.map((f) => [f.movie_id, f.id]));
  const watchMap = Object.fromEntries(watchlist.map((w) => [w.movie_id, w.id]));

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8 gap-4">
      {visibleMovies.map((movie) => (
        <MovieCard
          key={movie.movie_id}
          movie={movie}
          isFavorite={movie.movie_id in favMap}
          isWatchlisted={movie.movie_id in watchMap}
          favoriteId={favMap[movie.movie_id]}
          watchlistId={watchMap[movie.movie_id]}
          onFavoriteToggle={onFavoriteToggle}
          onWatchlistToggle={onWatchlistToggle}
          onCardClick={onCardClick}
        />
      ))}
    </div>
  );
}
