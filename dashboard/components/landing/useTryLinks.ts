"use client";

import { api } from "@/lib/api/client";
import { usePoll } from "@/lib/api/hooks";
import { waLink } from "@/lib/whatsapp";

export interface TryLinks {
  /** wa.me link with the sandbox join message prefilled; null until config loads. */
  join: string | null;
  joinMessage: string | null;
  /** The seeded user's newest case, or their case list. */
  demoHref: string | null;
}

/** Where the landing CTAs point. Config and the demo user change rarely, so poll slowly. */
export function useTryLinks(): TryLinks {
  const config = usePoll(() => api.config(), "config", 60_000).data;
  const demo = usePoll(() => api.demo(), "demo", 10_000).data;
  return {
    join: config ? waLink(config.whatsapp_number, config.sandbox_join_message ?? "") : null,
    joinMessage: config?.sandbox_join_message ?? null,
    demoHref: demo ? (demo.case_id ? `/u/${demo.user_id}/cases/${demo.case_id}` : `/u/${demo.user_id}`) : null,
  };
}
