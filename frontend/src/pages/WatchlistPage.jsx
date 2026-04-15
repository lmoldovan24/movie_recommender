import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { watchlistApi } from "../api/watchlist";
import { favoritesApi } from "../api/favorites";
import { moviesApi } from "../api/movies";
import { ratingsApi } from "../api/ratings";
import { watchedApi } from "../api/watched";
import { useToast } from "../components/Toast";
import SkeletonCard from "../components/SkeletonCard";
import EmptyState from "../components/EmptyState";
import MovieModal from "../components/MovieModal";
import { useNavigate } from "react-router-dom";

const GRID = "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8 gap-4";

export default function WatchlistPage() {
  const { showToast, ToastContainer } = useToast();
  const navigate = useNavigate();
  const [selectedMovie, setSelectedMovie] = useState(null);

  const { data: watchlist = [], isLoading, refetch } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.getAll().then((r) => r.data),
  });
  const { data: favorites = [], refetch: refetchFavorites } = useQuery({
    queryKey: ["favorites"],
    queryFn: () => favoritesApi.getAll().then((r) => r.data),
  });
  const { data: ratings = [] } = useQuery({
    queryKey: ["ratings"],
    queryFn: () => ratingsApi.getAll().then((r) => r.data),
  });
  const { data: watched = [] } = useQuery({
    queryKey: ["watched"],
    queryFn: () => watchedApi.getAll().then((r) => r.data),
  });

  const handleSeen = useCallback(async (item) => {
    try {
      await watchlistApi.markSeen(item.id);
      refetch();
      refetchFavorites();
      showToast(`„${item.title}" marcat ca văzut`, "success");
    } catch (err) { showToast(err.response?.data?.detail || "Eroare", "error"); }
  }, [refetch, refetchFavorites, showToast]);

  const handleRemove = useCallback(async (item) => {
    try { await watchlistApi.remove(item.id); refetch(); showToast("Eliminat din watchlist", "success"); }
    catch { showToast("Eroare", "error"); }
  }, [refetch, showToast]);

  const handleFavoriteToggle = useCallback(async (movie, favoriteId) => {
    try {
      if (favoriteId) { await favoritesApi.remove(favoriteId); showToast("Eliminat din favorite", "success"); }
      else { await favoritesApi.add({ movie_id: movie.movie_id, tmdb_id: movie.tmdb_id, title: movie.title, genres: movie.genres, poster_url: movie.poster_url }); showToast("Adăugat la favorite", "success"); }
      refetchFavorites();
    } catch (err) { showToast(err.response?.data?.detail || "Eroare", "error"); }
  }, [refetchFavorites, showToast]);

  const handleWatchlistToggle = useCallback(async (movie, watchlistId) => {
    try {
      if (watchlistId) { await watchlistApi.remove(watchlistId); refetch(); showToast("Eliminat din watchlist", "success"); }
    } catch (err) { showToast(err.response?.data?.detail || "Eroare", "error"); }
  }, [refetch, showToast]);

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
        <div className={GRID}>{Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}</div>
      ) : watchlist.length === 0 ? (
        <EmptyState
          title="Watchlist-ul tău e gol"
          action={{ label: "Descoperă filme", onClick: () => navigate("/") }}
        />
      ) : (
        <>
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">
            {watchlist.length} {watchlist.length === 1 ? "film" : "filme"} de văzut
          </p>
          <div className={GRID}>
            {watchlist.map((item) => (
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
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex flex-col justify-end p-2.5 gap-1.5">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleSeen(item); }}
                      className="w-full py-1.5 rounded text-xs font-medium bg-white/15 text-white hover:bg-white/25 backdrop-blur-sm transition-colors"
                    >
                      Am văzut
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRemove(item); }}
                      className="w-full py-1.5 rounded text-xs font-medium bg-white/10 text-zinc-300 hover:bg-white/20 backdrop-blur-sm transition-colors"
                    >
                      Elimină
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
