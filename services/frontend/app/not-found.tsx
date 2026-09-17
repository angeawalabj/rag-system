export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-950">
      <div className="text-center font-mono">
        <p className="text-5xl font-bold text-green-400 mb-4">404</p>
        <p className="text-gray-400 text-sm mb-6">Page introuvable</p>
        <a
          href="/chat"
          className="text-xs text-gray-500 hover:text-gray-300 border border-gray-800 rounded px-4 py-2 transition-colors"
        >
          ← Retour au chat
        </a>
      </div>
    </div>
  );
}
