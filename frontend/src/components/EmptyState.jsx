export default function EmptyState({ title, message, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
      <h3 className="text-base font-medium text-zinc-300 mb-2">{title}</h3>
      {message && <p className="text-sm text-zinc-600 max-w-xs mb-6">{message}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 text-sm rounded-lg transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
