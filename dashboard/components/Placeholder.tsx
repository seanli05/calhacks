"use client";

import Link from "next/link";

import { FIXTURE_CASE_ID } from "@/lib/api/fixtures";

import { Header } from "./Header";

/** Stand-in for a page another agent is building. Delete it once no page uses it. */
export function Placeholder({ userId, title }: { userId?: string; title: string }) {
  return (
    <div style={{ maxWidth: 1880, margin: "0 auto", paddingInline: 20 }}>
      <Header userId={userId} />
      <main style={{ padding: "40px 0", display: "grid", gap: 12 }}>
        <h1 style={{ margin: 0 }}>{title}</h1>
        <p style={{ color: "var(--faint)", margin: 0 }}>Not built yet. See docs/specs/dashboard-build.md.</p>
        {userId && (
          <Link className="btn primary" style={{ justifySelf: "start" }} href={`/u/${userId}/cases/${FIXTURE_CASE_ID}`}>
            Open the case view →
          </Link>
        )}
      </main>
    </div>
  );
}
