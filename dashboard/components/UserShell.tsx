"use client";

import { useEffect } from "react";

import { api } from "@/lib/api/client";
import { usePoll } from "@/lib/api/hooks";
import { useLang } from "@/lib/i18n";

/** Wraps every /u/[userId] page: shows the dashboard in the user's language by default. */
export function UserShell({ userId, children }: { userId: string; children: React.ReactNode }) {
  const { adoptUserLanguage } = useLang();
  const user = usePoll(() => api.user(userId), userId, 30_000).data;

  useEffect(() => {
    if (user) adoptUserLanguage(user.language);
  }, [user, adoptUserLanguage]);

  return <>{children}</>;
}
