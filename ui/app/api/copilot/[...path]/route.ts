import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import nodePath from "path";

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8765";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params;
  const path = resolvedParams.path ? resolvedParams.path.join("/") : "";
  const search = req.nextUrl.search;
  const targetUrl = `${BACKEND_URL}/api/copilot/${path}${search}`;

  try {
    const isPdfRequest = path.includes("raw-pdf") || (req.headers.get("accept") || "").includes("pdf");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), isPdfRequest ? 15000 : 4000);

    const clientAccept = isPdfRequest ? "application/pdf, */*" : (req.headers.get("accept") || "application/json");

    const backendRes = await fetch(targetUrl, {
      method: "GET",
      headers: {
        "Accept": clientAccept,
      },
      signal: controller.signal,
    });
    clearTimeout(timeout);

    const contentType = backendRes.headers.get("content-type") || "";

    if (contentType.includes("application/pdf") || contentType.includes("octet-stream") || isPdfRequest) {
      const arrayBuffer = await backendRes.arrayBuffer();
      return new NextResponse(arrayBuffer, {
        status: backendRes.status,
        headers: {
          "Content-Type": contentType || "application/pdf",
          "Content-Disposition": backendRes.headers.get("content-disposition") || "inline",
          "Cache-Control": "public, max-age=3600",
        },
      });
    }

    const data = await backendRes.json();
    return NextResponse.json(data, { status: backendRes.status });
  } catch {
    if (path.includes("raw-pdf")) {
      const sessionId = req.nextUrl.searchParams.get("session_id") || "";
      const publicDir = nodePath.resolve(process.cwd(), "public");
      const uploadsDir = nodePath.resolve(process.cwd(), "..", "data", "uploads");

      const candidates = [
        nodePath.join(uploadsDir, `${sessionId}.pdf`),
        nodePath.join(uploadsDir, "INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf"),
        nodePath.join(publicDir, "INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf"),
        nodePath.join(uploadsDir, "demo-gst-fy23-24.pdf"),
        nodePath.join(publicDir, "sample_audited_financial_statements.pdf"),
      ];

      for (const cand of candidates) {
        if (fs.existsSync(cand)) {
          const fileBuf = fs.readFileSync(cand);
          return new NextResponse(fileBuf, {
            status: 200,
            headers: {
              "Content-Type": "application/pdf",
              "Content-Disposition": "inline",
              "Accept-Ranges": "bytes",
            },
          });
        }
      }
      return new NextResponse("PDF not found", { status: 404 });
    }
    // If backend is not running, return informative fallback rather than crashing
    return NextResponse.json(
      {
        session_id: "demo-gst-fy23-24",
        file_name: "INVESTOR_CORNER_1756730556104_570e54_1756730556104.pdf",
        status: "backend_offline",
        message:
          "FastAPI backend is offline. Start the backend with: .venv\\Scripts\\auditiq serve",
        active_rows: [],
        pdf_doc: null,
      },
      { status: 200 }
    );
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params;
  const path = resolvedParams.path ? resolvedParams.path.join("/") : "";
  const search = req.nextUrl.search;
  const targetUrl = `${BACKEND_URL}/api/copilot/${path}${search}`;

  try {
    const contentType = req.headers.get("content-type") || "";
    let body: any;

    if (contentType.includes("multipart/form-data")) {
      body = await req.formData();
    } else if (contentType.includes("application/json")) {
      body = JSON.stringify(await req.json());
    } else {
      body = await req.text();
    }

    const headers: Record<string, string> = {};
    if (contentType && !contentType.includes("multipart/form-data")) {
      headers["Content-Type"] = contentType;
    }

    const backendRes = await fetch(targetUrl, {
      method: "POST",
      headers,
      body,
    });

    const data = await backendRes.json();
    return NextResponse.json(data, { status: backendRes.status });
  } catch {
    return NextResponse.json(
      {
        error: "Backend server is offline or unreachable.",
        hint: "Start the Python FastAPI server in a separate terminal with: .venv\\Scripts\\auditiq serve",
      },
      { status: 503 }
    );
  }
}

