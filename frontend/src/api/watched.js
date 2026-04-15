import client from "./client";

// Cookie-urile httpOnly sunt trimise automat de browser cu fiecare request
export const watchedApi = {
  getAll: () => client.get("/watched/"),
  mark: (movie) =>
    client.post(`/watched/${movie.movie_id}`, {
      tmdb_id: movie.tmdb_id ?? null,
      title: movie.title,
      genres: movie.genres ?? null,
      poster_url: movie.poster_url ?? null,
    }),
  unmark: (movieId) => client.delete(`/watched/${movieId}`),
};
