import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../components/Toast";
import clsx from "clsx";

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { showToast, ToastContainer } = useToast();

  const [mode, setMode] = useState("login");
  const [isLoading, setIsLoading] = useState(false);
  const [form, setForm] = useState({ username: "", email: "", password: "" });

  const next = searchParams.get("next") || "/";

  function handleChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setIsLoading(true);
    try {
      if (mode === "login") {
        await login(form.username, form.password);
        navigate(next, { replace: true });
      } else {
        await register(form.username, form.email, form.password);
        showToast("Cont creat! Te poți autentifica acum.", "success");
        setMode("login");
        setForm((prev) => ({ ...prev, email: "", password: "" }));
      }
    } catch (err) {
      const msg = err.response?.data?.detail || "A apărut o eroare. Încearcă din nou.";
      showToast(msg, "error");
    } finally {
      setIsLoading(false);
    }
  }

  const inputClass = "w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors";
  const labelClass = "block text-xs font-medium text-zinc-500 mb-1.5";

  return (
    <div className="flex-1 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm space-y-6">

        {/* Logo */}
        <div className="text-center">
          <Link to="/" className="text-xl font-semibold text-zinc-100 tracking-tight">
            CineRec
          </Link>
        </div>

        {/* Card */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-5">

          {/* Mode toggle */}
          <div className="flex gap-1 bg-zinc-950 p-1 rounded-lg">
            <button
              onClick={() => setMode("login")}
              className={clsx(
                "flex-1 py-1.5 rounded text-sm font-medium transition-all",
                mode === "login" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
              )}
            >
              Autentificare
            </button>
            <button
              onClick={() => setMode("register")}
              className={clsx(
                "flex-1 py-1.5 rounded text-sm font-medium transition-all",
                mode === "register" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
              )}
            >
              Cont nou
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className={labelClass}>Username</label>
              <input
                type="text"
                name="username"
                value={form.username}
                onChange={handleChange}
                required
                minLength={3}
                autoComplete="username"
                className={inputClass}
                placeholder="username"
              />
            </div>

            {mode === "register" && (
              <div>
                <label className={labelClass}>Email</label>
                <input
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={handleChange}
                  required
                  autoComplete="email"
                  className={inputClass}
                  placeholder="email@exemplu.com"
                />
              </div>
            )}

            <div>
              <label className={labelClass}>Parolă</label>
              <input
                type="password"
                name="password"
                value={form.password}
                onChange={handleChange}
                required
                minLength={8}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                className={inputClass}
                placeholder="Minim 8 caractere"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 bg-zinc-100 text-zinc-900 rounded-lg text-sm font-medium hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? "Se încarcă…" : mode === "login" ? "Autentifică-te" : "Creează cont"}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-zinc-600">
          <Link to="/" className="hover:text-zinc-400 transition-colors">
            ← Înapoi
          </Link>
        </p>
      </div>
      <ToastContainer />
    </div>
  );
}
