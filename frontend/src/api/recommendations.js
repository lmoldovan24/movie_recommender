import client from "./client";

export const recommendationsApi = {
  getPicks: (movieIds, genre = null) =>
    client.get("/recommendations/picks", {
      params: {
        movie_ids: movieIds.join(","),
        ...(genre ? { genre } : {}),
      },
    }),

  getPersonal: (seed) =>
    client.get("/recommendations/personal", { params: seed != null ? { seed } : {} }),
};
