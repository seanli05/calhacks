"use client";

import { useEffect, useState } from "react";

import styles from "./Mascot.module.css";

/** Hellos in the three languages we speak, shown whatever the page language is. */
const HELLOS = ["Hola!", "Hi!", "سلام!"];

/**
 * Avocado, our helper: a friendly face so the page greets people instead of selling
 * them a problem. `wave` adds the waving arm and the cycling hello bubble.
 */
export function Mascot({ size = 150, wave = false }: { size?: number; wave?: boolean }) {
  const [hello, setHello] = useState(0);

  useEffect(() => {
    if (!wave || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => setHello((i) => (i + 1) % HELLOS.length), 1800);
    return () => clearInterval(id);
  }, [wave]);

  return (
    <div className={`${styles.mascot} ${wave ? styles.bob : ""}`} style={{ width: size }} aria-hidden="true">
      {wave && (
        // <bdi> keeps Dari right-to-left inside the bubble without flipping where the bubble sits.
        <span key={hello} className={styles.hello}>
          <bdi>{HELLOS[hello]}</bdi>
        </span>
      )}
      <svg viewBox="0 0 160 184" width={size} height={size * 1.15}>
        {/* feet */}
        <ellipse cx="64" cy="174" rx="12" ry="6" fill="#0e3b2c" />
        <ellipse cx="96" cy="174" rx="12" ry="6" fill="#0e3b2c" />
        {/* resting arm */}
        <path d="M37 108 Q22 116 25 132" stroke="#0e3b2c" strokeWidth="5" strokeLinecap="round" fill="none" />
        {/* waving arm */}
        <g className={wave ? styles.arm : undefined}>
          <path d="M123 104 Q142 92 146 72" stroke="#0e3b2c" strokeWidth="5" strokeLinecap="round" fill="none" />
          <circle cx="146" cy="68" r="6" fill="#3f7d3b" stroke="#0e3b2c" strokeWidth="3" />
        </g>
        {/* skin */}
        <path
          d="M80 8 C50 8 38 40 34 72 C28 112 30 168 80 168 C130 168 132 112 126 72 C122 40 110 8 80 8 Z"
          fill="#3f7d3b"
          stroke="#0e3b2c"
          strokeWidth="4"
        />
        {/* flesh */}
        <path
          d="M80 20 C58 20 49 46 46 74 C41 110 45 156 80 156 C115 156 119 110 114 74 C111 46 102 20 80 20 Z"
          fill="#e3f6b9"
        />
        {/* pit */}
        <circle cx="80" cy="114" r="25" fill="#9a6a43" />
        <ellipse cx="72" cy="104" rx="7" ry="5" fill="#b98962" />
        {/* face */}
        <circle cx="68" cy="70" r="4.5" fill="#0f1a14" />
        <circle cx="92" cy="70" r="4.5" fill="#0f1a14" />
        <path d="M70 81 Q80 90 90 81" stroke="#0f1a14" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        <ellipse cx="58" cy="80" rx="6" ry="4" fill="#ffb9a8" opacity="0.8" />
        <ellipse cx="102" cy="80" rx="6" ry="4" fill="#ffb9a8" opacity="0.8" />
      </svg>
    </div>
  );
}
