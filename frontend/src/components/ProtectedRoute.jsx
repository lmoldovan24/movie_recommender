import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  // Așteptăm să se termine silent refresh înainte să redirectăm
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-6 h-6 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    // Salvăm pagina curentă în ?next= pentru redirect după login
    return (
      <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
    );
  }

  return children;
}
