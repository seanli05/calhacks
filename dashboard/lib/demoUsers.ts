import { DATA_MODE } from "@/lib/api/client";
import { FIXTURE_USER_ID } from "@/lib/api/fixtures";

export type DemoUser = { label: string; userId: string };

/**
 * The demo's accounts, from NEXT_PUBLIC_DEMO_USERS ("Label:user_id,Label:user_id"), for the
 * landing page's "Already have a dashboard?". Their IDs survive the demo reset
 * (`app.db.reset --keep-users`), so a fixed list is safe. Fixtures mode falls back to the
 * fixture user so the link can be previewed without the backend.
 */
export function demoUsers(): DemoUser[] {
  const users = (process.env.NEXT_PUBLIC_DEMO_USERS ?? "")
    .split(",")
    .map((entry) => {
      const at = entry.lastIndexOf(":");
      return { label: entry.slice(0, at).trim(), userId: entry.slice(at + 1).trim() };
    })
    .filter((user) => user.label && user.userId.startsWith("user_"));
  if (users.length === 0 && DATA_MODE === "fixtures") return [{ label: "Demo", userId: FIXTURE_USER_ID }];
  return users;
}
