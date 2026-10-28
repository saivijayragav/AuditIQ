import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AuditIQ — Statutory Audit Intelligence & GST Copilot",
  description: "AI-grounded audit intelligence platform for Indian CA firms, GST reconciliation, SA 240 fraud detection, and Schedule III compliance.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </head>
      <body>{children}</body>
    </html>
  );
}

