import client from "./client";

// Cookie-urile httpOnly sunt trimise automat de browser cu fiecare request
export const usersApi = {
  getStats: () => client.get("/users/me/stats"),
};
