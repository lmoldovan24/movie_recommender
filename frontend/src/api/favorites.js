import client from "./client";

// Cookie-urile httpOnly sunt trimise automat de browser cu fiecare request
export const favoritesApi = {
  getAll: () => client.get("/favorites/"),
  add: (movie) =>
    client.post("/favorites/", {
      movie_id: movie.movie_id,
      tmdb_id: movie.tmdb_id ?? null,
      title: movie.title,
      genres: movie.genres ?? null,
      poster_url: movie.poster_url ?? null,
    }),
  remove: (favoriteId) => client.delete(`/favorites/${favoriteId}`),
};
