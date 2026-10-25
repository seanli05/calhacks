"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Header } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { TryActions } from "@/components/landing/TryActions";
import { useTryLinks } from "@/components/landing/useTryLinks";
import { useLang, useStrings } from "@/lib/i18n";

import styles from "./ExampleTour.module.css";

/**
 * Snapshots of the demo case page (fixture steps 0, 2, 3, 4, 6), saved per language
 * in public/landing/example/. Recapture them if the case page changes.
 */
const SHOTS = [0, 2, 3, 4, 6];
const SLIDE_MS = 6500;
const SHOT_LANGS = ["en", "es", "fa"];

/**
 * "See an example": the product shown as a tour that plays by itself, instead of a
 * live dashboard to click around. A clear way back home sits at the top.
 */
export function ExampleTour() {
  const t = useStrings().landing;
  const { lang } = useLang();
  const links = useTryLinks();
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);

  const total = SHOTS.length;
  const shotLang = SHOT_LANGS.includes(lang) ? lang : "en";
  const last = index === total - 1;

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setPlaying(false);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const id = setTimeout(() => setIndex((i) => (i + 1) % total), SLIDE_MS);
    return () => clearTimeout(id);
  }, [index, playing, total]);

  const go = (i: number) => setIndex((i + total) % total);

  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <Header />
      </div>
      <main className={styles.wrap}>
        <Link href="/" className={styles.back}>
          <span className={styles.backArrow} aria-hidden="true">
            <Icon name="arrow" size={16} />
          </span>
          {t.example.back}
        </Link>

        <div className={styles.layout}>
          <section className={styles.side}>
            <h1 className={styles.title}>{t.example.title}</h1>
            <p className={styles.sub}>{t.example.sub}</p>

            <ol className={styles.steps}>
              {t.example.slides.map((slide, i) => (
                <li key={i}>
                  <button
                    type="button"
                    className={`${styles.step} ${i === index ? styles.active : ""} ${i < index ? styles.seen : ""}`}
                    onClick={() => go(i)}
                    aria-current={i === index ? "step" : undefined}
                  >
                    <span className={styles.stepTitle}>{slide.title}</span>
                    {i === index && <span className={styles.stepBody}>{slide.body}</span>}
                    {i === index && (
                      <span className={styles.track} aria-hidden="true">
                        <span
                          key={`${index}-${playing}`}
                          className={styles.fill}
                          style={{
                            animationDuration: `${SLIDE_MS}ms`,
                            animationPlayState: playing ? "running" : "paused",
                          }}
                        />
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ol>

            <div className={styles.controls}>
              <button type="button" onClick={() => go(index - 1)} aria-label={t.example.prev}>
                <span className={styles.flip}>
                  <Icon name="arrow" size={18} />
                </span>
              </button>
              <button type="button" className={styles.play} onClick={() => setPlaying((p) => !p)}>
                {playing ? t.example.pause : t.example.play}
              </button>
              <button type="button" onClick={() => go(index + 1)} aria-label={t.example.next}>
                <Icon name="arrow" size={18} />
              </button>
              <span className={styles.count}>{t.example.step(index + 1, total)}</span>
            </div>

            {last && (
              <div className={styles.done}>
                <p>{t.example.done}</p>
                <TryActions links={links} qrSize={96} scan={false} example={false} />
              </div>
            )}
          </section>

          <figure className={styles.frame}>
            <div className={styles.chrome} aria-hidden="true">
              <i />
              <i />
              <i />
            </div>
            <div className={styles.shots}>
              {SHOTS.map((shot, i) => (
                // eslint-disable-next-line @next/next/no-img-element -- static snapshots; next/image adds nothing here
                <img
                  key={shot}
                  src={`/landing/example/${shotLang}-${shot}.jpg`}
                  alt={i === index ? `${t.example.alt}: ${t.example.slides[i].title}` : ""}
                  className={`${styles.shot} ${i === index ? styles.shown : ""}`}
                  width={1440}
                  height={900}
                />
              ))}
            </div>
          </figure>
        </div>
      </main>
    </div>
  );
}
