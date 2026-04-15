import client from "./client";

export const authApi = {
  register: (username, email, password) =>
    client.post("/auth/register", { username, email, password }),

  login: (username, password) =>
    client.post("/auth/login", { username, password }),

  // Fără body — cookie-ul refresh_token e trimis automat de browser
  refresh: () => client.post("/auth/refresh"),

  // Fără body — server citește și revocă cookie-ul refresh_token
  logout: () => client.post("/auth/logout"),
};
