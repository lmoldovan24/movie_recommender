import { useQuery } from "@tanstack/react-query";
import { usersApi } from "../api/users";
import { useAuth } from "../contexts/AuthContext";

const COLORS = [
  "#6366f1","#ec4899","#22c55e","#f59e0b","#8b5cf6",
  "#06b6d4","#f97316","#ef4444","#14b8a6","#84cc16",
];

function GenreBar({ genre, count, max, color }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-zinc-400 w-24 shrink-0 truncate">{genre}</span>
      <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs text-zinc-600 w-5 text-right">{count}</span>
    </div>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-zinc-900 rounded-xl p-5 flex flex-col gap-1">
      <span className="text-3xl font-bold text-zinc-100 tracking-tight">{value}</span>
      <span className="text-sm text-zinc-400">{label}</span>
      {sub && <span className="text-xs text-zinc-600 mt-0.5">{sub}</span>}
    </div>
  );
}

export default function ProfilePage() {
  const { user, logout } = useAuth();

  const { data: stats, isLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: () => usersApi.getStats().then((r) => r.data),
    staleTime: 0,
  });

  const maxGenreCount = stats?.top_genres?.[0]?.count ?? 1;

  return (
    <div className="max-w-2xl mx-auto px-5 py-8 space-y-8">

      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center text-lg font-semibold text-zinc-300 select-none">
          {user?.username?.[0]?.toUpperCase() ?? "?"}
        </div>
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">{user?.username}</h1>
          <p className="text-sm text-zinc-500">{user?.email}</p>
        </div>
        <button
          onClick={() => logout()}
          className="ml-auto text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Deconectare
        </button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 animate-pulse">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-zinc-900 rounded-xl h-24" />
          ))}
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Favorite" value={stats?.favorites_count ?? 0} />
            <StatCard label="Vizionate" value={stats?.watched_count ?? 0} />
            <StatCard label="Note date" value={stats?.total_ratings ?? 0} />
            <StatCard
              label="Medie"
              value={stats?.avg_rating > 0 ? `${stats.avg_rating}` : "—"}
              sub={stats?.avg_rating > 0 ? "din 5" : null}
            />
          </div>

          {/* Top genuri */}
          {stats?.top_genres?.length > 0 && (
            <div className="bg-zinc-900 rounded-xl p-6 space-y-3">
              <p className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-5">
                Genuri preferate
              </p>
              {stats.top_genres.map((g, i) => (
                <GenreBar
                  key={g.genre}
                  genre={g.genre}
                  count={g.count}
                  max={maxGenreCount}
                  color={COLORS[i % COLORS.length]}
                />
              ))}
            </div>
          )}

          {stats?.top_genres?.length === 0 && (
            <p className="text-sm text-zinc-600 text-center py-12">
              Adaugă filme la favorite pentru a vedea statisticile tale.
            </p>
          )}
        </>
      )}
    </div>
  );
}
