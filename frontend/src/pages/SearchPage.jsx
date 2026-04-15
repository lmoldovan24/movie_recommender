import { useState, useCallback, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { moviesApi } from "../api/movies";
import { recommendationsApi } from "../api/recommendations";
import { favoritesApi } from "../api/favorites";
import { watchlistApi } from "../api/watchlist";
import { ratingsApi } from "../api/ratings";
import { watchedApi } from "../api/watched";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../components/Toast";
import MovieGrid from "../components/MovieGrid";
import HorizontalRow from "../components/HorizontalRow";
import MovieModal from "../components/MovieModal";

const SECTION = "text-xs font-semibold text-zinc-500 uppercase tracking-widest";

function useDebounceValue(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export default function SearchPage() {
  const { isAuthenticated } = useAuth();
  const { showToast, ToastContainer } = useToast();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState(() => searchParams.get("q") ?? "");
  const [selectedMovie, setSelectedMovie] = useState(null);
  const debouncedQuery = useDebounceValue(query, 300);

  const { data: favorites = [], refetch: refetchFavorites } = useQuery({
    queryKey: ["favorites"],
    queryFn: () => favoritesApi.getAll().then((r) => r.data),
    enabled: isAuthenticated,
  });
  const { data: watchlist = [], refetch: refetchWatchlist } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.getAll().then((r) => r.data),
    enabled: isAuthenticated,
  });
  const { data: ratings = [] } = useQuery({
    queryKey: ["ratings"],
    queryFn: () => ratingsApi.getAll().then((r) => r.data),
    enabled: isAuthenticated,
  });
  const { data: watched = [] } = useQuery({
    queryKey: ["watched"],
    queryFn: () => watchedApi.getAll().then((r) => r.data),
    enabled: isAuthenticated,
  });

  const { data: results = [], isLoading } = useQuery({
    queryKey: ["search", debouncedQuery],
    queryFn: () => moviesApi.search(debouncedQuery).then((r) => r.data),
    enabled: debouncedQuery.length >= 2,
  });

  // Primer rezultat — baza pentru "Similare"
  const topResult = results[0] ?? null;

  const { data: similar = [], isLoading: loadingSimilar } = useQuery({
    queryKey: ["picks", "search", topResult?.movie_id],
    queryFn: () => recommendationsApi.getPicks([topResult.movie_id]).then((r) => r.data),
    enabled: !!topResult,
    staleTime: 1000 * 60 * 5,
  });

  // Similare fără filmele deja afișate în rezultate
  const resultIds = new Set(results.map((m) => m.movie_id));
  const filteredSimilar = similar.filter((m) => !resultIds.has(m.movie_id));

  const handleFavoriteToggle = useCallback(async (movie, favoriteId) => {
    if (!isAuthenticated) { showToast("Trebuie să fii autentificat", "info"); return; }
    try {
      if (favoriteId) { await favoritesApi.remove(favoriteId); showToast("Eliminat din favorite", "success"); }
      else { await favoritesApi.add({ movie_id: movie.movie_id, tmdb_id: movie.tmdb_id, title: movie.title, genres: movie.genres, poster_url: movie.poster_url }); showToast("Adăugat la favorite", "success"); }
      refetchFavorites();
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    } catch (err) { showToast(err.response?.data?.detail || "Eroare", "error"); }
  }, [isAuthenticated, refetchFavorites, queryClient, showToast]);

  const handleWatchlistToggle = useCallback(async (movie, watchlistId) => {
    if (!isAuthenticated) { showToast("Trebuie să fii autentificat", "info"); return; }
    try {
      if (watchlistId) { await watchlistApi.remove(watchlistId); showToast("Eliminat din watchlist", "success"); }
      else { await watchlistApi.add({ movie_id: movie.movie_id, tmdb_id: movie.tmdb_id, title: movie.title, genres: movie.genres, poster_url: movie.poster_url }); showToast("Adăugat la watchlist", "success"); }
      refetchWatchlist();
    } catch (err) { showToast(err.response?.data?.detail || "Eroare", "error"); }
  }, [isAuthenticated, refetchWatchlist, showToast]);

  const handleCardClick = useCallback(async (movie) => {
    if (!movie.overview && movie.tmdb_id) {
      try { const full = await moviesApi.getById(movie.movie_id).then((r) => r.data); setSelectedMovie(full); }
      catch { setSelectedMovie(movie); }
    } else { setSelectedMovie(movie); }
  }, []);

  const rowProps = { favorites, watchlist, onFavoriteToggle: handleFavoriteToggle, onWatchlistToggle: handleWatchlistToggle, onCardClick: handleCardClick };

  return (
    <div className="max-w-screen-xl mx-auto px-5 py-8 space-y-8">

      {/* Search input */}
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Caută după titlu…"
          autoFocus
          className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors"
        />
        {query && (
          <button
            onClick={() => setQuery("")}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400 transition-colors text-lg leading-none"
            aria-label="Șterge"
          >
            ×
          </button>
        )}
      </div>

      {debouncedQuery.length >= 2 ? (
        <>
          {/* Rezultate */}
          {!isLoading && results.length > 0 && (
            <p className="text-xs text-zinc-600">{results.length} rezultate pentru „{debouncedQuery}"</p>
          )}
          <MovieGrid
            movies={results}
            isLoading={isLoading}
            favorites={favorites}
            watchlist={watchlist}
            onFavoriteToggle={handleFavoriteToggle}
            onWatchlistToggle={handleWatchlistToggle}
            onCardClick={handleCardClick}
            emptyTitle="Niciun rezultat exact"
          />

          {/* Similare — apare când există un prim rezultat */}
          {!isLoading && topResult && (
            <div className="pt-2 border-t border-zinc-800/60">
              <HorizontalRow
                title={`Similare cu ${topResult.title}`}
                movies={filteredSimilar}
                isLoading={loadingSimilar}
                {...rowProps}
              />
            </div>
          )}

          {/* Când nu există rezultate exacte dar avem similare din fallback */}
          {!isLoading && results.length === 0 && (
            <p className="text-xs text-zinc-500 -mt-4">
              Arătăm rezultate aproximative pentru „{debouncedQuery}"
            </p>
          )}
        </>
      ) : (
        <div className="py-24 text-center">
          <p className="text-sm text-zinc-600">Scrie cel puțin 2 caractere</p>
        </div>
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
