import client from "./client";

export const watchlistApi = {
  getAll: () =>
    client.get("/watchlist"),

  add: (movie) =>
    client.post("/watchlist", movie),

  remove: (watchlistId) =>
    client.delete(`/watchlist/${watchlistId}`),

  markSeen: (watchlistId) =>
    client.post(`/watchlist/${watchlistId}/seen`),
};
