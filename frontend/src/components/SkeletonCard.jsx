export default function SkeletonCard() {
  return (
    <div className="animate-pulse">
      <div className="bg-zinc-800 aspect-[2/3] w-full rounded-lg" />
      <div className="mt-2 space-y-1.5 px-0.5">
        <div className="h-3 bg-zinc-800 rounded w-4/5" />
        <div className="h-2.5 bg-zinc-800/60 rounded w-2/5" />
      </div>
    </div>
  );
}
