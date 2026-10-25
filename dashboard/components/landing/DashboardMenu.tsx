"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { Icon } from "@/components/Icon";
import type { DemoUser } from "@/lib/demoUsers";
import { useStrings } from "@/lib/i18n";

import styles from "./DashboardMenu.module.css";

/**
 * "Already have a dashboard?" in the landing page's top bar: a small menu with one
 * link per demo account (lib/demoUsers.ts). Hidden when there are none.
 */
export function DashboardMenu({ users }: { users: DemoUser[] }) {
  const t = useStrings().landing;
  const ref = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    // <details> stays open on its own; close it when someone clicks elsewhere.
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) ref.current.open = false;
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  if (users.length === 0) return null;
  return (
    <details ref={ref} className={styles.menu}>
      <summary>{t.dashboards.prompt}</summary>
      <div className={styles.list}>
        {users.map((user) => (
          <Link key={user.userId} href={`/u/${user.userId}`} className={styles.account}>
            <span dir="auto">{user.label}</span>
            <Icon name="arrow" size={15} />
          </Link>
        ))}
      </div>
    </details>
  );
}
