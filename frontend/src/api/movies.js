import client from "./client";

export const moviesApi = {
  getGenres: () =>
    client.get("/movies/genres"),

  getByGenre: (genre, limit = 200, seed = null) =>
    client.get(`/movies/genre/${encodeURIComponent(genre)}`, {
      params: { limit, ...(seed != null ? { seed } : {}) },
    }),

  search: (q) =>
    client.get("/movies/search", { params: { q } }),

  getById: (movieId) =>
    client.get(`/movies/${movieId}`),

  getPopular: (limit = 20, seed = null) =>
    client.get("/movies/popular", { params: { limit, ...(seed != null ? { seed } : {}) } }),
};
