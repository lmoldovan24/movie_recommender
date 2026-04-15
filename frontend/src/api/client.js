import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const client = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true, // trimite cookie-urile httpOnly automat cu fiecare request
});

// Mutex simplu — previne refresh-uri paralele
let isRefreshing = false;
let failedQueue = [];

function processQueue(error) {
  failedQueue.forEach((prom) => {
    if (error) prom.reject(error);
    else prom.resolve();
  });
  failedQueue = [];
}

// Interceptor response — refresh automat la 401
// Nu mai e nevoie de request interceptor: cookie-urile sunt trimise automat de browser
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Dacă nu e 401 sau e deja retry, nu încercăm refresh
    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Nu facem refresh pe endpoint-urile de auth
    if (
      originalRequest.url?.includes("/auth/login") ||
      originalRequest.url?.includes("/auth/register") ||
      originalRequest.url?.includes("/auth/refresh")
    ) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      // Adaugă request-ul în coadă până termină refresh-ul curent
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      })
        .then(() => client(originalRequest))
        .catch((err) => Promise.reject(err));
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      // Refresh fără body — cookie-ul refresh_token e trimis automat
      await axios.post(`${BASE_URL}/auth/refresh`, {}, { withCredentials: true });
      processQueue(null);
      // Cookie-ul nou e setat de server; browser-ul îl trimite automat la retry
      return client(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError);
      window.dispatchEvent(new CustomEvent("auth:session-expired"));
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export default client;
