import { useState, useCallback, useMemo } from "react";
import { useQuery, useQueries, useQueryClient } from "@tanstack/react-query";
import { moviesApi } from "../api/movies";
import { recommendationsApi } from "../api/recommendations";
import { favoritesApi } from "../api/favorites";
import { watchlistApi } from "../api/watchlist";
import { ratingsApi } from "../api/ratings";
import { watchedApi } from "../api/watched";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../components/Toast";
import GenreSelector from "../components/GenreSelector";
import HorizontalRow from "../components/HorizontalRow";
import MovieCard from "../components/MovieCard";
import SkeletonCard from "../components/SkeletonCard";
import MovieModal from "../components/MovieModal";

// LCG seeded RNG — for consistent shuffle per session
function seededRng(seed) {
  let s = (seed % 2147483647) || 1;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

const SECTION = "text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-4";

export default function HomePage() {
  const { isAuthenticated } = useAuth();
  const { showToast, ToastContainer } = useToast();
  const queryClient = useQueryClient();
  const [selectedGenre, setSelectedGenre] = useState(null);
  const [selectedMovie, setSelectedMovie] = useState(null);
  const [homeSeed] = useState(() => Math.floor(Math.random() * 1e9));

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data: genres = [] } = useQuery({
    queryKey: ["genres"],
    queryFn: () => moviesApi.getGenres().then((r) => r.data),
  });
  const { data: genreMovies = [], isLoading: loadingGenre } = useQuery({
    queryKey: ["movies", "genre", selectedGenre],
    queryFn: () => moviesApi.getByGenre(selectedGenre, 200, homeSeed).then((r) => r.data),
    enabled: !!selectedGenre,
  });
  const { data: favorites = [], isSuccess: favoritesLoaded, refetch: refetchFavorites } = useQuery({
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
  const { data: popularMovies = [], isLoading: loadingPopular } = useQuery({
    queryKey: ["movies", "popular", homeSeed],
    queryFn: () => moviesApi.getPopular(30, homeSeed).then((r) => r.data),
    staleTime: Infinity,
  });

  const hasEnoughFavorites = isAuthenticated && favoritesLoaded && favorites.length >= 3;
  const { data: personalRecs = [], isLoading: loadingPersonal } = useQuery({
    queryKey: ["recommendations", "personal", homeSeed],
    queryFn: () => recommendationsApi.getPersonal(homeSeed).then((r) => r.data),
    enabled: hasEnoughFavorites,
    staleTime: Infinity,
  });

  // ── "Pentru că ți-a plăcut X" rows ──────────────────────────────────────
  // Sursă: filme cu rating ≥ 4 stele; titlul vine din favorites sau watched
  const movieLookup = useMemo(() => {
    const map = {};
    favorites.forEach((f) => { map[f.movie_id] = { movie_id: f.movie_id, title: f.title, poster_url: f.poster_url, genres: f.genres }; });
    watched.forEach((w) => { if (!map[w.movie_id]) map[w.movie_id] = { movie_id: w.movie_id, title: w.title, poster_url: w.poster_url, genres: w.genres }; });
    return map;
  }, [favorites, watched]);

  const becausePicks = useMemo(() => {
    const highRated = ratings
      .filter((r) => r.rating >= 4)
      .map((r) => movieLookup[r.movie_id])
      .filter(Boolean);
    if (!highRated.length) return [];
    const rng = seededRng(homeSeed);
    const shuffled = [...highRated].sort(() => rng() - 0.5);
    return shuffled.slice(0, Math.min(2, highRated.length));
  }, [ratings, movieLookup, homeSeed]);

  const becauseQueries = useQueries({
    queries: becausePicks.map((fav) => ({
      queryKey: ["picks", fav.movie_id, homeSeed],
      queryFn: () => recommendationsApi.getPicks([fav.movie_id]).then((r) => r.data),
      staleTime: Infinity,
      enabled: isAuthenticated,
    })),
  });

  // ── "Pentru că ai văzut X" rows ──────────────────────────────────────────
  // Pick 1-2 random watched movies each session (seed diferit față de becausePicks)
  const watchedPicks = useMemo(() => {
    if (!watched.length) return [];
    const rng = seededRng(homeSeed + 1); // seed diferit ca să nu coincidă cu favoritele
    const shuffled = [...watched].sort(() => rng() - 0.5);
    return shuffled.slice(0, Math.min(2, watched.length));
  }, [watched, homeSeed]);

  const watchedQueries = useQueries({
    queries: watchedPicks.map((w) => ({
      queryKey: ["picks", "watched", w.movie_id, homeSeed],
      queryFn: () => recommendationsApi.getPicks([w.movie_id]).then((r) => r.data),
      staleTime: Infinity,
      enabled: isAuthenticated,
    })),
  });

  // ── Handlers ─────────────────────────────────────────────────────────────
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

  // ── Deduplicare globală — niciun film nu apare în două rânduri ──────────
  const becauseData = becauseQueries.map((q) => q?.data ?? []);
  const watchedData = watchedQueries.map((q) => q?.data ?? []);

  const deduped = useMemo(() => {
    const seen = new Set();
    const take = (movies) => {
      const fresh = movies.filter((m) => m?.movie_id && !seen.has(m.movie_id));
      fresh.forEach((m) => seen.add(m.movie_id));
      return fresh;
    };

    const mainRow   = take(hasEnoughFavorites ? personalRecs : popularMovies);
    const genreRow  = take(genreMovies);
    const becauseRows = becauseData.map((movies) => take(movies));
    const popularRow  = take(popularMovies);
    const watchedRows = watchedData.map((movies) => take(movies));

    return { mainRow, genreRow, becauseRows, popularRow, watchedRows };
  }, [
    personalRecs, popularMovies, genreMovies,
    becauseData, watchedData, hasEnoughFavorites,
  ]);

  const favMap = useMemo(() => Object.fromEntries(favorites.map((f) => [f.movie_id, f.id])), [favorites]);
  const watchMap = useMemo(() => Object.fromEntries(watchlist.map((w) => [w.movie_id, w.id])), [watchlist]);

  const rowProps = {
    favorites,
    watchlist,
    onFavoriteToggle: handleFavoriteToggle,
    onWatchlistToggle: handleWatchlistToggle,
    onCardClick: handleCardClick,
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-screen-xl mx-auto px-5 py-8 space-y-10">

      {/* Genre selector */}
      <section>
        <p className={SECTION}>Explorează după gen</p>
        <GenreSelector
          genres={genres}
          selected={selectedGenre}
          onSelect={(genre) => setSelectedGenre(genre)}
        />
      </section>

      {/* Genre grid */}
      {selectedGenre && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">
              {selectedGenre}
            </p>
            <span className="text-xs text-zinc-600">
              {loadingGenre ? "…" : `${genreMovies.length} filme`}
            </span>
          </div>
          {loadingGenre ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8 gap-4">
              {Array.from({ length: 12 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8 gap-4">
              {genreMovies.map((movie) => (
                <MovieCard
                  key={movie.movie_id}
                  movie={movie}
                  isFavorite={movie.movie_id in favMap}
                  isWatchlisted={movie.movie_id in watchMap}
                  favoriteId={favMap[movie.movie_id]}
                  watchlistId={watchMap[movie.movie_id]}
                  onFavoriteToggle={handleFavoriteToggle}
                  onWatchlistToggle={handleWatchlistToggle}
                  onCardClick={handleCardClick}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Popular / Personal */}
      <HorizontalRow
        title={hasEnoughFavorites ? "Pentru tine" : "Popular"}
        movies={deduped.mainRow}
        isLoading={hasEnoughFavorites ? loadingPersonal : loadingPopular}
        {...rowProps}
      />

      {/* "Pentru că ți-a plăcut X" rows — Popular intercalat după primul */}
      {isAuthenticated && becausePicks.map((fav, i) => {
        const shortTitle = fav.title.length > 40 ? fav.title.slice(0, 38) + "…" : fav.title;
        return (
          <div key={`because-fav-${fav.movie_id}`}>
            <HorizontalRow
              title={`Pentru că ți-a plăcut ${shortTitle}`}
              movies={deduped.becauseRows[i] ?? []}
              isLoading={becauseQueries[i]?.isLoading ?? false}
              {...rowProps}
            />
            {i === 0 && (
              <div className="mt-10">
                <HorizontalRow
                  title="Popular"
                  movies={deduped.popularRow}
                  isLoading={loadingPopular}
                  {...rowProps}
                />
              </div>
            )}
          </div>
        );
      })}

      {/* "Pentru că ai văzut X" rows */}
      {isAuthenticated && watchedPicks.map((w, i) => {
        const shortTitle = w.title.length > 40 ? w.title.slice(0, 38) + "…" : w.title;
        return (
          <HorizontalRow
            key={`because-watched-${w.movie_id}`}
            title={`Pentru că ai văzut ${shortTitle}`}
            movies={deduped.watchedRows[i] ?? []}
            isLoading={watchedQueries[i]?.isLoading ?? false}
            {...rowProps}
          />
        );
      })}

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
