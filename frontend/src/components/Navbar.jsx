import { useState, useRef, useEffect } from "react";
import { NavLink, Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export default function Navbar() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const inputRef = useRef(null);

  const links = [
    { to: "/", label: "Acasă", end: true },
    ...(isAuthenticated ? [
      { to: "/favorites", label: "Favorite", end: false },
      { to: "/watchlist", label: "Watchlist", end: false },
      { to: "/watched", label: "Vizionate", end: false },
    ] : []),
  ];

  useEffect(() => {
    if (searchOpen) inputRef.current?.focus();
  }, [searchOpen]);

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === "Escape") { setSearchOpen(false); setSearchQuery(""); }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (searchQuery.trim().length >= 2) {
      navigate(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
      setSearchOpen(false);
      setSearchQuery("");
    }
  };

  const handleSearchToggle = () => {
    if (searchOpen) {
      setSearchOpen(false);
      setSearchQuery("");
    } else {
      setSearchOpen(true);
    }
  };

  return (
    <header className="sticky top-0 z-40 bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800/50">
      <div className="max-w-screen-xl mx-auto px-5 flex items-center gap-6" style={{ height: 52 }}>
        <Link to="/" className="text-sm font-bold text-zinc-100 tracking-widest uppercase shrink-0">
          CineRec
        </Link>

        <nav className="flex items-center gap-0.5 flex-1">
          {links.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md text-sm transition-all ${
                  isActive
                    ? "text-zinc-100 bg-zinc-800"
                    : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/50"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Search + Profile */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Search bar */}
          <form onSubmit={handleSubmit} className="flex items-center gap-2">
            <div
              className={`overflow-hidden transition-all duration-200 ${
                searchOpen ? "w-48 sm:w-64 opacity-100" : "w-0 opacity-0"
              }`}
            >
              <input
                ref={inputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Caută filme…"
                className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
              />
            </div>
            <button
              type={searchOpen && searchQuery.length >= 2 ? "submit" : "button"}
              onClick={!searchOpen ? handleSearchToggle : undefined}
              className="w-8 h-8 flex items-center justify-center rounded-full text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-all"
              aria-label="Caută"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </button>
          </form>

          {/* Profile / Login */}
          {isAuthenticated ? (
            <Link to="/profile">
              <div className="w-8 h-8 rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-xs font-bold text-indigo-300 hover:bg-indigo-500/20 transition-colors">
                {user?.username?.[0]?.toUpperCase() ?? "?"}
              </div>
            </Link>
          ) : (
            <Link to="/login" className="text-sm text-zinc-500 hover:text-zinc-100 transition-colors">
              Conectare
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
