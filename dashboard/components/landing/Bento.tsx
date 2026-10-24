"use client";

import Link from "next/link";

import { Icon } from "@/components/Icon";
import { useStrings } from "@/lib/i18n";

import { ExplainVisual, HoldVisual, MemoryVisual, MenuVisual, PrepVisual, RingVisual, VerifyVisual } from "./BentoVisuals";
import type { TryLinks } from "./useTryLinks";
import styles from "./Bento.module.css";

interface TileProps {
  lead: string;
  rest: string;
  size: "big" | "small";
  /** Turns the tile into a link, with the corner arrow. */
  href?: string | null;
  label?: string;
  dark?: boolean;
  children: React.ReactNode;
}

/** One tile: a two-tone title (ink lead, muted rest) and a picture that bleeds off the bottom. */
function Tile({ lead, rest, size, href, label, dark = false, children }: TileProps) {
  const className = `${styles.tile} ${styles[size]} ${dark ? styles.dark : ""} ${href ? styles.link : ""}`;
  const body = (
    <>
      <h3 className={styles.title}>
        {lead}
        <span>{rest}</span>
      </h3>
      {href && (
        <span className={styles.arrow} aria-hidden="true">
          <Icon name="arrow" />
        </span>
      )}
      <div className={styles.visual} aria-hidden="true">
        {children}
      </div>
    </>
  );
  return href ? (
    <Link href={href} className={className} aria-label={label ? `${lead}${rest} · ${label}` : undefined}>
      {body}
    </Link>
  ) : (
    <article className={className}>{body}</article>
  );
}

/** Ramp-style grid: two big tiles, three small, two big. Each shows a piece of the product. */
export function Bento({ links }: { links: TryLinks }) {
  const t = useStrings().landing.bento;
  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>
        {t.title[0]} <span>{t.title[1]}</span>
      </h2>
      <div className={styles.grid}>
        <Tile {...t.explain} size="big">
          <ExplainVisual />
        </Tile>
        <Tile {...t.verify} size="big">
          <VerifyVisual />
        </Tile>
        <Tile {...t.menu} size="small">
          <MenuVisual />
        </Tile>
        <Tile {...t.hold} size="small">
          <HoldVisual />
        </Tile>
        <Tile {...t.ring} size="small" href={links.demoHref} label={t.ring.cta} dark>
          <RingVisual />
        </Tile>
        <Tile {...t.prep} size="big">
          <PrepVisual />
        </Tile>
        <Tile {...t.memory} size="big" href={links.memoryHref} label={t.memory.cta}>
          <MemoryVisual />
        </Tile>
      </div>
    </section>
  );
}
