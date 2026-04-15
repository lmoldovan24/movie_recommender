import { useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { favoritesApi } from "../api/favorites";
import { watchlistApi } from "../api/watchlist";
import { recommendationsApi } from "../api/recommendations";
import { moviesApi } from "../api/movies";
import { ratingsApi } from "../api/ratings";
import { watchedApi } from "../api/watched";
import { useToast } from "../components/Toast";
import SkeletonCard from "../components/SkeletonCard";
import EmptyState from "../components/EmptyState";
import MovieGrid from "../components/MovieGrid";
import MovieModal from "../components/MovieModal";
import clsx from "clsx";

const GRID = "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8 gap-4";
const SECTION = "text-xs font-semibold text-zinc-500 uppercase tracking-widest";

const SORT_OPTIONS_FAV = [
  { value: "date_desc", label: "Recente" },
  { value: "date_asc", label: "Vechi" },
  { value: "rating_desc", label: "Nota mea ↓" },
  { value: "rating_asc", label: "Nota mea ↑" },
  { value: "title_asc", label: "A–Z" },
];

const SORT_OPTIONS_NOTES = [
  { value: "rating_desc", label: "Rating ↓" },
  { value: "rating_asc", label: "Rating ↑" },
  { value: "date_desc", label: "Recente" },
  { value: "date_asc", label: "Vechi" },
  { value: "title_asc", label: "A–Z" },
];

const TABS = [
  { id: "favorites", label: "Favorite" },
  { id: "notes", label: "Note" },
  { id: "recommendations", label: "Recomandări" },
];

export default function FavoritesPage() {
  const { showToast, ToastContainer } = useToast();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("favorites");
  const [sortBy, setSortBy] = useState("date_desc");
  const [sortNotes, setSortNotes] = useState("rating_desc");
  const [filterGenre, setFilterGenre] = useState("");
  const [selectedMovie, setSelectedMovie] = useState(null);
  const [recSeed, setRecSeed] = useState(() => Math.floor(Math.random() * 1e9));

  const { data: favorites = [], isLoading: loadingFav, refetch: refetchFavorites } = useQuery({
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
  const { data: ratedMovies = [], isLoading: loadingNotes, refetch: refetchNotes } = useQuery({
    queryKey: ["ratings", "enriched"],
    queryFn: () => ratingsApi.getEnriched().then((r) => r.data),
    enabled: activeTab === "notes",
  });
  const { data: watched = [] } = useQuery({
    queryKey: ["watched"],
    queryFn: () => watchedApi.getAll().then((r) => r.data),
  });
  const { data: recommendations = [], isLoading: loadingRecs } = useQuery({
    queryKey: ["recommendations", "personal", recSeed],
    queryFn: () => recommendationsApi.getPersonal(recSeed).then((r) => r.data),
    enabled: activeTab === "recommendations" && favorites.length >= 3,
    staleTime: Infinity,
  });

  const availableGenres = [...new Set(favorites.flatMap((f) => (f.genres ? f.genres.split("|") : [])))].sort();
  const filteredFav = favorites
    .filter((f) => (filterGenre ? f.genres?.includes(filterGenre) : true))
    .sort((a, b) => {
      switch (sortBy) {
        case "date_desc": return new Date(b.added_at) - new Date(a.added_at);
        case "date_asc":  return new Date(a.added_at) - new Date(b.added_at);
        case "rating_desc": return (b.user_rating || 0) - (a.user_rating || 0);
        case "rating_asc":  return (a.user_rating || 0) - (b.user_rating || 0);
        case "title_asc": return a.title.localeCompare(b.title);
        default: return 0;
      }
    });

  const sortedNotes = [...ratedMovies]
    .filter((r) => r.rating != null)
    .sort((a, b) => {
      switch (sortNotes) {
        case "rating_desc": return (b.rating || 0) - (a.rating || 0);
        case "rating_asc":  return (a.rating || 0) - (b.rating || 0);
        case "date_desc":   return new Date(b.rated_at) - new Date(a.rated_at);
        case "date_asc":    return new Date(a.rated_at) - new Date(b.rated_at);
        case "title_asc":   return a.title.localeCompare(b.title);
        default: return 0;
      }
    });

  const handleRemoveFav = useCallback(async (movie, favoriteId) => {
    if (!favoriteId) return;
    try {
      await favoritesApi.remove(favoriteId);
      refetchFavorites();
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      showToast("Eliminat din favorite", "success");
    } catch { showToast("Eroare", "error"); }
  }, [refetchFavorites, queryClient, showToast]);

  const handleDeleteRating = useCallback(async (movieId) => {
    try {
      await ratingsApi.remove(movieId);
      refetchNotes();
      refetchFavorites();
      queryClient.invalidateQueries({ queryKey: ["ratings"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      showToast("Notă ștearsă", "success");
    } catch { showToast("Eroare", "error"); }
  }, [refetchNotes, refetchFavorites, queryClient, showToast]);

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

  const favToMovie = (fav) => ({ movie_id: fav.movie_id, tmdb_id: fav.tmdb_id, title: fav.title, genres: fav.genres, poster_url: fav.poster_url });
  const ratingToMovie = (r) => ({ movie_id: r.movie_id, tmdb_id: r.tmdb_id, title: r.title, genres: r.genres, poster_url: r.poster_url });

  return (
    <div className="max-w-screen-xl mx-auto px-5 py-8 space-y-8">

      {/* Tabs */}
      <div className="flex gap-1 bg-zinc-900 p-1 rounded-lg w-fit">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={clsx(
              "px-4 py-1.5 rounded text-sm font-medium transition-all",
              activeTab === tab.id
                ? "bg-zinc-700 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-300"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab: Favorite ── */}
      {activeTab === "favorites" && (
        <section>
          {favorites.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 mb-6">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-sm text-zinc-300 focus:outline-none focus:border-zinc-600"
              >
                {SORT_OPTIONS_FAV.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select>
              {availableGenres.length > 0 && (
                <select
                  value={filterGenre}
                  onChange={(e) => setFilterGenre(e.target.value)}
                  className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-sm text-zinc-300 focus:outline-none focus:border-zinc-600"
                >
                  <option value="">Toate genurile</option>
                  {availableGenres.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              )}
              <span className="text-xs text-zinc-600 ml-auto">{filteredFav.length} filme</span>
            </div>
          )}

          {loadingFav ? (
            <div className={GRID}>{Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}</div>
          ) : filteredFav.length === 0 ? (
            <EmptyState title="Niciun film în favorite" />
          ) : (
            <div className={GRID}>
              {filteredFav.map((fav) => (
                <div key={fav.id} className="group flex flex-col">
                  <div
                    className="relative aspect-[2/3] overflow-hidden rounded-lg bg-zinc-900 cursor-pointer"
                    onClick={() => handleCardClick(favToMovie(fav))}
                  >
                    <img
                      src={fav.poster_url || "/assets/no-poster.png"}
                      alt={fav.title}
                      className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                      onError={(e) => { e.target.src = "/assets/no-poster.png"; }}
                    />
                    {fav.user_rating > 0 && (
                      <div className="absolute top-2 right-2 bg-black/70 backdrop-blur-sm text-yellow-400 text-xs font-semibold px-1.5 py-0.5 rounded">
                        ★ {fav.user_rating.toFixed(1)}
                      </div>
                    )}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex flex-col justify-end p-2.5">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRemoveFav(fav, fav.id); }}
                        className="w-full py-1.5 rounded text-xs font-medium bg-white/15 text-white hover:bg-white/25 backdrop-blur-sm transition-colors"
                      >
                        Elimină
                      </button>
                    </div>
                  </div>
                  <div className="mt-2 px-0.5 cursor-pointer" onClick={() => handleCardClick(favToMovie(fav))}>
                    <p className="text-sm text-zinc-300 leading-snug line-clamp-2 group-hover:text-zinc-100 transition-colors">
                      {fav.title}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ── Tab: Note ── */}
      {activeTab === "notes" && (
        <section>
          {!loadingNotes && sortedNotes.length > 0 && (
            <div className="flex items-center gap-2 mb-6">
              <select
                value={sortNotes}
                onChange={(e) => setSortNotes(e.target.value)}
                className="px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded text-sm text-zinc-300 focus:outline-none focus:border-zinc-600"
              >
                {SORT_OPTIONS_NOTES.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select>
              <span className="text-xs text-zinc-600 ml-auto">{sortedNotes.length} filme notate</span>
            </div>
          )}

          {loadingNotes ? (
            <div className={GRID}>{Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}</div>
          ) : sortedNotes.length === 0 ? (
            <EmptyState title="Nicio notă dată" />
          ) : (
            <div className={GRID}>
              {sortedNotes.map((r) => (
                <div key={r.id} className="group flex flex-col">
                  <div
                    className="relative aspect-[2/3] overflow-hidden rounded-lg bg-zinc-900 cursor-pointer"
                    onClick={() => handleCardClick(ratingToMovie(r))}
                  >
                    <img
                      src={r.poster_url || "/assets/no-poster.png"}
                      alt={r.title}
                      className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                      onError={(e) => { e.target.src = "/assets/no-poster.png"; }}
                    />
                    <div className="absolute top-2 right-2 bg-black/70 backdrop-blur-sm text-yellow-400 text-xs font-semibold px-1.5 py-0.5 rounded">
                      ★ {r.rating?.toFixed(1)}
                    </div>
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex flex-col justify-end p-2.5">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteRating(r.movie_id); }}
                        className="w-full py-1.5 rounded text-xs font-medium bg-white/15 text-white hover:bg-white/25 backdrop-blur-sm transition-colors"
                      >
                        Șterge nota
                      </button>
                    </div>
                  </div>
                  <div className="mt-2 px-0.5 cursor-pointer" onClick={() => handleCardClick(ratingToMovie(r))}>
                    <p className="text-sm text-zinc-300 leading-snug line-clamp-2 group-hover:text-zinc-100 transition-colors">
                      {r.title}
                    </p>
                    {r.genres && (
                      <p className="text-xs text-zinc-600 mt-0.5">
                        {r.genres.split("|").slice(0, 2).join(" · ")}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ── Tab: Recomandări ── */}
      {activeTab === "recommendations" && (
        favorites.length < 3 ? (
          <EmptyState title="Prea puține favorite" message="Adaugă cel puțin 3 filme la favorite." />
        ) : (
          <section>
            <div className="flex items-center justify-between mb-6">
              <p className={SECTION}>Pe gustul tău</p>
              <button
                onClick={() => setRecSeed(Math.floor(Math.random() * 1e9))}
                disabled={loadingRecs}
                className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-40"
              >
                {loadingRecs ? "Se încarcă…" : "Regenerează"}
              </button>
            </div>
            <MovieGrid
              movies={recommendations}
              isLoading={loadingRecs}
              favorites={favorites}
              watchlist={watchlist}
              onFavoriteToggle={handleFavoriteToggle}
              onWatchlistToggle={handleWatchlistToggle}
              onCardClick={handleCardClick}
              emptyTitle="Nu am găsit recomandări"
            />
          </section>
        )
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
