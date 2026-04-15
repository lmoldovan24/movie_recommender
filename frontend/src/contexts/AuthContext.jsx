import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const navigate = useNavigate();

  // Stocăm doar obiectul user (fără tokeni — aceștia sunt în httpOnly cookies)
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem("user");
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = !!user;

  // Logout — server revocă refresh token-ul din cookie, curăță cookies + state local
  const logout = useCallback(
    async (silent = false) => {
      if (!silent) {
        try {
          await client.post("/auth/logout");
        } catch {
          // Ignorăm erorile la logout — oricum curățăm local
        }
      }

      localStorage.removeItem("user");
      setUser(null);
      navigate("/login");
    },
    [navigate]
  );

  // Silent refresh la mount — verifică dacă sesiunea e validă folosind cookie-ul httpOnly
  const hasRefreshed = useRef(false);
  useEffect(() => {
    if (hasRefreshed.current) return;
    hasRefreshed.current = true;

    async function silentRefresh() {
      try {
        // Trimitem fără body — cookie-ul refresh_token e trimis automat de browser
        const response = await client.post("/auth/refresh");
        const { user: userData } = response.data;
        if (userData) {
          localStorage.setItem("user", JSON.stringify(userData));
          setUser(userData);
        }
      } catch {
        // Refresh token expirat sau absent — userul nu e autentificat
        localStorage.removeItem("user");
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    }

    silentRefresh();
  }, []);

  // Listener pentru event auth:session-expired emis din client.js
  useEffect(() => {
    function handleSessionExpired() {
      setUser(null);
      localStorage.removeItem("user");
      navigate("/login");
    }

    window.addEventListener("auth:session-expired", handleSessionExpired);
    return () => {
      window.removeEventListener("auth:session-expired", handleSessionExpired);
    };
  }, [navigate]);

  const login = useCallback(async (username, password) => {
    // Server setează httpOnly cookies; noi primim doar datele userului
    const response = await client.post("/auth/login", { username, password });
    const { user: userData } = response.data;

    localStorage.setItem("user", JSON.stringify(userData));
    setUser(userData);

    return userData;
  }, []);

  const register = useCallback(async (username, email, password) => {
    const response = await client.post("/auth/register", {
      username,
      email,
      password,
    });
    return response.data;
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoading,
        login,
        logout,
        register,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth trebuie folosit în interiorul AuthProvider");
  }
  return context;
}
