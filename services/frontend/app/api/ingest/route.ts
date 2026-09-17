import { NextRequest } from "next/server";

const INGEST_URL = process.env.INGEST_API_URL || "http://localhost:8001";

export async function POST(req: NextRequest) {
  const formData = await req.formData();

  let upstream: Response;
  try {
    upstream = await fetch(`${INGEST_URL}/ingest`, {
      method: "POST",
      body:   formData,
    });
  } catch {
    return Response.json(
      { error: "Service d'ingestion inaccessible" },
      { status: 503 }
    );
  }

  const data = await upstream.json();
  return Response.json(data, { status: upstream.status });
}
