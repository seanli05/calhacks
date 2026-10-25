import { DATA_MODE } from "@/lib/api/client";
import { FIXTURE_USER_ID } from "@/lib/api/fixtures";

export type DemoUser = { label: string; href: string };

/**
 * The demo's two accounts, for the landing page's "Already have a dashboard?". Each is
 * set in dashboard/.env.local as a user ID (`user_…`) or a full dashboard URL. The IDs
 * survive the demo reset (`app.db.reset --keep-users`), so fixed values are safe. An
 * unset account is left out. Fixtures mode falls back to the fixture user so the menu
 * can be previewed without the backend.
 *
 * The env names are written out in full: Next.js only inlines literal
 * `process.env.NEXT_PUBLIC_…` references into the browser bundle.
 */
export function demoUsers(): DemoUser[] {
  const accounts = [
    { label: "Mariam · دری", value: process.env.NEXT_PUBLIC_MARIAM_HOST_DASHBOARD },
    { label: "Ana · English", value: process.env.NEXT_PUBLIC_ANA_HOST_DASHBOARD },
  ];
  const users = accounts.flatMap(({ label, value }) => {
    const href = dashboardHref(value?.trim() ?? "");
    return href ? [{ label, href }] : [];
  });
  if (users.length === 0 && DATA_MODE === "fixtures") return [{ label: "Demo", href: `/u/${FIXTURE_USER_ID}` }];
  return users;
}

/** A user ID becomes its "My cases" page; a URL or path is used as is. */
function dashboardHref(value: string): string | null {
  if (value.startsWith("user_")) return `/u/${value}`;
  if (value.startsWith("http://") || value.startsWith("https://") || value.startsWith("/")) return value;
  return null;
}
