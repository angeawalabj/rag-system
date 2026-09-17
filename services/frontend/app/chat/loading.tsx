export default function ChatLoading() {
  return (
    <div className="flex h-screen flex-col bg-gray-950">
      {/* Header skeleton */}
      <div className="border-b border-gray-800 px-4 py-3 flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-gray-800 animate-pulse" />
        <div className="h-3 w-24 rounded bg-gray-800 animate-pulse" />
      </div>

      {/* Chat area skeleton */}
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center font-mono text-xs text-gray-700 animate-pulse">
          Chargement…
        </div>
      </div>

      {/* Input skeleton */}
      <div className="border-t border-gray-800 p-4">
        <div className="mx-auto max-w-3xl h-12 rounded-xl bg-gray-900 animate-pulse" />
      </div>
    </div>
  );
}
