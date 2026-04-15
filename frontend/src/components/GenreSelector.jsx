import clsx from "clsx";

export default function GenreSelector({ genres = [], selected, onSelect }) {
  return (
    <div className="flex flex-wrap gap-2">
      {genres.map((genre) => (
        <button
          key={genre}
          onClick={() => onSelect(genre === selected ? null : genre)}
          className={clsx(
            "px-3 py-1.5 rounded-full text-sm transition-all duration-150",
            genre === selected
              ? "bg-zinc-100 text-zinc-900 font-medium"
              : "bg-zinc-800/70 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
          )}
        >
          {genre}
        </button>
      ))}
    </div>
  );
}
