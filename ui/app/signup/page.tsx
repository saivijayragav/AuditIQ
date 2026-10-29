"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Scale, Lock, Mail, User, Building, ArrowRight, AlertCircle, ArrowLeft, Sparkles } from "lucide-react";
import { signUp } from "@/lib/auth-client";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [firmName, setFirmName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await signUp.email({
        email,
        password,
        name: `${name} (${firmName || "Chartered Accountants"})`,
      });

      if (res?.error) {
        setError(res.error.message || "Failed to register account.");
      } else {
        router.push("/workspace");
      }
    } catch {
      // In dev fallback
      router.push("/workspace");
    } finally {
      setLoading(false);
    }
  };

  const handleDemoEnroll = () => {
    setName("CA J. Swaminathan");
    setFirmName("Swaminathan & Co., Chartered Accountants");
    setEmail("partner@swaminathan-ca.in");
    setPassword("Audit2026!Secure");
    router.push("/workspace");
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "#F4F1EA",
        padding: "1.5rem",
      }}
    >
      <div style={{ width: "100%", maxWidth: "460px", marginBottom: "1rem" }}>
        <Link
          href="/"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            color: "#38483F",
            fontSize: "0.825rem",
            textDecoration: "none",
            fontFamily: "var(--font-mono, monospace)",
            fontWeight: 600,
          }}
        >
          <ArrowLeft size={14} />
          <span>Return to AuditIQ Overview</span>
        </Link>
      </div>

      <div
        style={{
          width: "100%",
          maxWidth: "460px",
          backgroundColor: "#FAF8F3",
          borderRadius: "6px",
          border: "1px solid #D8D2C4",
          padding: "2.5rem 2.25rem",
          boxShadow: "0 4px 20px rgba(15, 56, 42, 0.08)",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "4px",
              backgroundColor: "#0F382A",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 2px 6px rgba(15, 56, 42, 0.2)",
              marginBottom: "1rem",
            }}
          >
            <Scale size={24} color="#FAF8F3" />
          </div>
          <h1
            style={{
              fontSize: "1.6rem",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: "#0F382A",
              fontFamily: 'var(--font-serif, "Iowan Old Style", Georgia, serif)',
              margin: 0,
            }}
          >
            CA Practice Enrollment
          </h1>
          <p
            style={{
              color: "#38483F",
              fontSize: "0.825rem",
              marginTop: "0.35rem",
              fontFamily: "var(--font-mono, monospace)",
            }}
          >
            Provision Statutory Working Paper Workspace
          </p>
        </div>

        {error && (
          <div
            style={{
              backgroundColor: "rgba(185, 28, 28, 0.08)",
              border: "1px solid rgba(185, 28, 28, 0.3)",
              color: "#B91C1C",
              borderRadius: "4px",
              padding: "0.75rem",
              fontSize: "0.8rem",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              marginBottom: "1.25rem",
              fontFamily: "var(--font-mono, monospace)",
            }}
          >
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.1rem" }}>
          <div>
            <label
              style={{
                display: "block",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "#0F382A",
                marginBottom: "0.35rem",
                fontFamily: "var(--font-mono, monospace)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              Auditor Full Name (FCA / ACA)
            </label>
            <div style={{ position: "relative" }}>
              <User
                size={15}
                color="#5D6E64"
                style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)" }}
              />
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="CA J. Swaminathan"
                style={{
                  width: "100%",
                  padding: "0.7rem 0.75rem 0.7rem 2.4rem",
                  borderRadius: "4px",
                  border: "1px solid #D8D2C4",
                  backgroundColor: "#FFFFFF",
                  color: "#14221B",
                  fontSize: "0.875rem",
                  outline: "none",
                }}
              />
            </div>
          </div>

          <div>
            <label
              style={{
                display: "block",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "#0F382A",
                marginBottom: "0.35rem",
                fontFamily: "var(--font-mono, monospace)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              Chartered Accountancy Firm Name
            </label>
            <div style={{ position: "relative" }}>
              <Building
                size={15}
                color="#5D6E64"
                style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)" }}
              />
              <input
                type="text"
                required
                value={firmName}
                onChange={(e) => setFirmName(e.target.value)}
                placeholder="Swaminathan & Co., Chartered Accountants"
                style={{
                  width: "100%",
                  padding: "0.7rem 0.75rem 0.7rem 2.4rem",
                  borderRadius: "4px",
                  border: "1px solid #D8D2C4",
                  backgroundColor: "#FFFFFF",
                  color: "#14221B",
                  fontSize: "0.875rem",
                  outline: "none",
                }}
              />
            </div>
          </div>

          <div>
            <label
              style={{
                display: "block",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "#0F382A",
                marginBottom: "0.35rem",
                fontFamily: "var(--font-mono, monospace)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              Firm Official Email
            </label>
            <div style={{ position: "relative" }}>
              <Mail
                size={15}
                color="#5D6E64"
                style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)" }}
              />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="partner@swaminathan-ca.in"
                style={{
                  width: "100%",
                  padding: "0.7rem 0.75rem 0.7rem 2.4rem",
                  borderRadius: "4px",
                  border: "1px solid #D8D2C4",
                  backgroundColor: "#FFFFFF",
                  color: "#14221B",
                  fontSize: "0.875rem",
                  outline: "none",
                  fontFamily: "var(--font-mono, monospace)",
                }}
              />
            </div>
          </div>

          <div>
            <label
              style={{
                display: "block",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "#0F382A",
                marginBottom: "0.35rem",
                fontFamily: "var(--font-mono, monospace)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              Password
            </label>
            <div style={{ position: "relative" }}>
              <Lock
                size={15}
                color="#5D6E64"
                style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)" }}
              />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                style={{
                  width: "100%",
                  padding: "0.7rem 0.75rem 0.7rem 2.4rem",
                  borderRadius: "4px",
                  border: "1px solid #D8D2C4",
                  backgroundColor: "#FFFFFF",
                  color: "#14221B",
                  fontSize: "0.875rem",
                  outline: "none",
                  fontFamily: "var(--font-mono, monospace)",
                }}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "0.85rem",
              borderRadius: "4px",
              backgroundColor: "#0F382A",
              color: "#FFFFFF",
              fontWeight: 700,
              fontSize: "0.925rem",
              border: "1px solid #0F382A",
              cursor: loading ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              marginTop: "0.5rem",
              fontFamily: 'var(--font-serif, "Iowan Old Style", Georgia, serif)',
              boxShadow: "0 2px 6px rgba(15, 56, 42, 0.2)",
              transition: "transform 0.15s ease",
            }}
          >
            {loading ? "Registering Practice..." : "Register Firm & Open Working Paper"}
            <ArrowRight size={16} />
          </button>
        </form>

        <div style={{ margin: "1.5rem 0", display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{ flex: 1, height: "1px", backgroundColor: "#D8D2C4" }} />
          <span style={{ fontSize: "0.685rem", color: "#5D6E64", textTransform: "uppercase", fontFamily: "var(--font-mono, monospace)", letterSpacing: "0.04em" }}>
            Instant Testing
          </span>
          <div style={{ flex: 1, height: "1px", backgroundColor: "#D8D2C4" }} />
        </div>

        <button
          onClick={handleDemoEnroll}
          type="button"
          style={{
            width: "100%",
            padding: "0.75rem",
            borderRadius: "4px",
            backgroundColor: "rgba(21, 128, 61, 0.08)",
            border: "1px solid rgba(21, 128, 61, 0.35)",
            color: "#15803D",
            fontWeight: 700,
            fontSize: "0.825rem",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px",
            fontFamily: "var(--font-mono, monospace)",
            transition: "all 0.15s ease",
          }}
        >
          <Sparkles size={14} />
          <span>1-Click Practice Enrollment (FCA Demo Practice)</span>
        </button>

        <div style={{ textAlign: "center", marginTop: "1.75rem", fontSize: "0.825rem", color: "#38483F" }}>
          Already have an auditor account?{" "}
          <Link href="/login" style={{ color: "#0F382A", fontWeight: 700, textDecoration: "none" }}>
            Sign In →
          </Link>
        </div>
      </div>
    </div>
  );
}
