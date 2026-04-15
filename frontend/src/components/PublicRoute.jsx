import { Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function PublicRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();

  // Așteptăm să se termine silent refresh
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Dacă e deja autentificat, redirect la home — nu poate accesa /login
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return children;
}
