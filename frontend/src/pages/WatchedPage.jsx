import { useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { watchedApi } from "../api/watched";
import { favoritesApi } from "../api/favorites";
import { watchlistApi } from "../api/watchlist";
import { ratingsApi } from "../api/ratings";
import { moviesApi } from "../api/movies";
import { useToast } from "../components/Toast";
import SkeletonCard from "../components/SkeletonCard";
import EmptyState from "../components/EmptyState";
import MovieModal from "../components/MovieModal";

const GRID = "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8 gap-4";

const SORT_OPTIONS = [
  { value: "date_desc", label: "Recente" },
  { value: "date_asc", label: "Vechi" },
  { value: "title_asc", label: "A–Z" },
];

export default function WatchedPage() {
  const { showToast, ToastContainer } = useToast();
  const queryClient = useQueryClient();
  const [selectedMovie, setSelectedMovie] = useState(null);
  const [sortBy, setSortBy] = useState("date_desc");

  const { data: watched = [], isLoading, refetch } = useQuery({
    queryKey: ["watched"],
    queryFn: () => watchedApi.getAll().then((r) => r.data),
  });
  const { data: favorites = [], refetch: refetchFavorites } = useQuery({
    queryKey: ["favorites"],
    queryFn: () => favoritesApi.getAll().then((r) => r.data),
  });
  const { data: watchlist = [], refetch: refetchWatchlist } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.getAll().then((r) => r.data),
  });
  const { data: ratings = [] } = useQuery({
    queryKey: ["ratings"],
    queryFn: () => ratingsApi.getAll().then((r) => r.data),
  });

  const sorted = [...watched].sort((a, b) => {
    switch (sortBy) {
      case "date_desc": return new Date(b.watched_at) - new Date(a.watched_at);
      case "date_asc":  return new Date(a.watched_at) - new Date(b.watched_at);
      case "title_asc": return a.title.localeCompare(b.title);
      default: return 0;
    }
  });

  const handleUnmark = useCallback(async (movie) => {
    try {
      await watchedApi.unmark(movie.movie_id);
      refetch();
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      showToast("Eliminat din vizionate", "success");
    } catch { showToast("Eroare", "error"); }
  }, [refetch, queryClient, showToast]);

  const handleFavoriteToggle = useCallback(async (movie, favoriteId) => {
    try {
      if (favoriteId) { await favoritesApi.remove(favoriteId); showToast("Eliminat din favorite", "success"); }
      else { await favoritesApi.add({ movie_id: movie.movie_id, tmdb_id: movie.tmdb_id, title: movie.title, genres: movie.genres, poster_url: movie.poster_url }); showToast("Adăugat la favorite", "success"); }
      refetchFavorites();
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    } catch (err) { showToast(err.response?.data?.detail || "Eroare", "error"); }
  }, [refetchFavorites, queryClient, showToast]);

  const handleWatchlistToggle = useCallback(async (movie, watchlistId) => {
    try {
      if (watchlistId) { await watchlistApi.remove(watchlistId); showToast("Eliminat din watchlist", "success"); }
      else { await watchlistApi.add({ movie_id: movie.movie_id, tmdb_id: movie.tmdb_id, title: movie.title, genres: movie.genres, poster_url: movie.poster_url }); showToast("Adăugat la watchlist", "success"); }
      refetchWatchlist();
    } catch (err) { showToast(err.response?.data?.detail || "Eroare", "error"); }
  }, [refetchWatchlist, showToast]);

  const handleCardClick = useCallback(async (movie) => {
    if (!movie.overview && movie.tmdb_id) {
      try { const full = await moviesApi.getById(movie.movie_id).then((r) => r.data); setSelectedMovie(full); }
      catch { setSelectedMovie(movie); }
    } else { setSelectedMovie(movie); }
  }, []);

  const itemToMovie = (item) => ({
    movie_id: item.movie_id,
    tmdb_id: item.tmdb_id,
    title: item.title,
    genres: item.genres,
    poster_url: item.poster_url,
  });

  return (
    <div className="max-w-screen-xl mx-auto px-5 py-8 space-y-6">

      {isLoading ? (
        <div className={GRID}>{Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}</div>
      ) : watched.length === 0 ? (
        <EmptyState title="Niciun film vizionat" message="Marchează filme ca văzute din orice pagină." />
      ) : (
        <>
          <div className="flex items-center gap-3">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-sm text-zinc-300 focus:outline-none focus:border-zinc-600"
            >
              {SORT_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
            </select>
            <span className="text-xs text-zinc-600 ml-auto">{watched.length} filme</span>
          </div>

          <div className={GRID}>
            {sorted.map((item) => (
              <div key={item.id} className="group flex flex-col">
                <div
                  className="relative aspect-[2/3] overflow-hidden rounded-lg bg-zinc-900 cursor-pointer"
                  onClick={() => handleCardClick(itemToMovie(item))}
                >
                  <img
                    src={item.poster_url || "/assets/no-poster.png"}
                    alt={item.title}
                    className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                    onError={(e) => { e.target.src = "/assets/no-poster.png"; }}
                  />
                  {/* Badge "Văzut" */}
                  <div className="absolute top-2 left-2 bg-black/70 backdrop-blur-sm text-green-400 text-xs font-semibold px-1.5 py-0.5 rounded">
                    ✓
                  </div>
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex flex-col justify-end p-2.5">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleUnmark(itemToMovie(item)); }}
                      className="w-full py-1.5 rounded text-xs font-medium bg-white/15 text-white hover:bg-white/25 backdrop-blur-sm transition-colors"
                    >
                      Marchează nevăzut
                    </button>
                  </div>
                </div>
                <div className="mt-2 px-0.5 cursor-pointer" onClick={() => handleCardClick(itemToMovie(item))}>
                  <p className="text-sm text-zinc-300 leading-snug line-clamp-2 group-hover:text-zinc-100 transition-colors">
                    {item.title}
                  </p>
                  {item.genres && (
                    <p className="text-xs text-zinc-600 mt-0.5">
                      {item.genres.split("|").slice(0, 2).join(" · ")}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {selectedMovie && (
        <MovieModal
          movie={selectedMovie}
          onClose={() => setSelectedMovie(null)}
          onFavoriteToggle={handleFavoriteToggle}
          onWatchlistToggle={handleWatchlistToggle}
          onCardClick={handleCardClick}
          favorites={favorites}
          watchlist={watchlist}
          ratings={ratings}
          watched={watched}
        />
      )}
      <ToastContainer />
    </div>
  );
}
