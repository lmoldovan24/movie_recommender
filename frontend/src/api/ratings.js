import client from "./client";

// Cookie-urile httpOnly sunt trimise automat de browser cu fiecare request
export const ratingsApi = {
  getAll: () => client.get("/ratings/"),
  getEnriched: () => client.get("/ratings/enriched"),
  upsert: (movieId, { rating, tmdb_id, title, genres, poster_url } = {}) =>
    client.put(`/ratings/${movieId}`, { rating, tmdb_id, title, genres, poster_url }),
  remove: (movieId) => client.delete(`/ratings/${movieId}`),
};
