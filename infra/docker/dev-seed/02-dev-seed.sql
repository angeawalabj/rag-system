-- ─────────────────────────────────────────────────────────────────────────────
-- Dev seed — données de développement uniquement
-- Exécuté après 01-schema.sql par docker-entrypoint-initdb.d/seed/
-- ─────────────────────────────────────────────────────────────────────────────

-- Document de test pré-ingéré (statut completed, pas de vrai vecteur dans Qdrant)
INSERT INTO documents (filename, source_type, collection, status, chunk_count, file_size_bytes, ingested_at)
VALUES
  ('rapport-q1-2026.pdf', 'pdf', 'finance',   'completed', 12, 204800,  NOW() - INTERVAL '1 hour'),
  ('architecture.md',     'md',  'tech',       'completed', 4,  8192,   NOW() - INTERVAL '30 minutes'),
  ('notes.txt',           'txt', 'documents',  'pending',   NULL, 1024,  NULL)
ON CONFLICT DO NOTHING;
