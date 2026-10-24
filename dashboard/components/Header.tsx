"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LANGUAGES, useLang, useStrings } from "@/lib/i18n";

import styles from "./Header.module.css";

/** Top bar for every page. `userId` turns on the user nav; `back` shows "← My cases". */
export function Header({ userId, back = false }: { userId?: string; back?: boolean }) {
  const t = useStrings().common;
  const pathname = usePathname();
  const casesHref = userId ? `/u/${userId}` : null;
  const memoryHref = userId ? `/u/${userId}/memory` : null;

  return (
    <header className={styles.top}>
      <Link href={casesHref ?? "/"} className={styles.brand}>
        <span className={styles.mark} aria-hidden="true" />
        <span className={styles.name}>{t.appName}</span>
      </Link>
      <nav className={styles.nav}>
        {casesHref && back && (
          <Link href={casesHref} className={styles.strong}>
            {t.nav.back}
          </Link>
        )}
        {casesHref && !back && (
          <Link href={casesHref} aria-current={pathname === casesHref ? "page" : undefined}>
            {t.nav.cases}
          </Link>
        )}
        {memoryHref && (
          <Link href={memoryHref} aria-current={pathname === memoryHref ? "page" : undefined}>
            {t.nav.memory}
          </Link>
        )}
        <LangSwitch />
      </nav>
    </header>
  );
}

export function LangSwitch() {
  const { lang, setLang } = useLang();
  const t = useStrings().common;
  return (
    <div className={styles.lang} role="group" aria-label={t.languageSwitch}>
      {LANGUAGES.map((l) => (
        <button
          key={l.code}
          type="button"
          aria-pressed={lang === l.code}
          onClick={() => setLang(l.code)}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
