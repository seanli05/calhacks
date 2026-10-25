/** Date and time formatting through `Intl`, so every language works without string files. */

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * The `Intl` locale for a language code. Dari (`fa`) is Afghan Persian on the
 * Gregorian calendar ("۱۲ نومبر"), as USCIS's Dari pages write it; plain `fa` would
 * give Iranian Solar Hijri dates. Spanish is US Spanish, so times read "8:30 a.m."
 * like the letter's "8:30 AM", not 24-hour.
 */
export function intlLocale(lang: string): string {
  if (lang === "fa") return "fa-AF-u-ca-gregory";
  if (lang === "es") return "es-US";
  return lang;
}

/** A whole number in the language's digits: "19", "۱۹". */
export function formatNumber(value: number, lang: string, minDigits = 1): string {
  return new Intl.NumberFormat(intlLocale(lang), { minimumIntegerDigits: minDigits, useGrouping: false }).format(value);
}

/** "3 min ago", "hace 2 días", "now". Relative times only: no small clock text on video. */
export function relativeTime(iso: string, lang: string, now: number = Date.now()): string {
  const diff = new Date(iso).getTime() - now;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat(intlLocale(lang), { numeric: "auto", style: "short" });
  // `Intl` says the literary "اکنون"; Afghan Dari says "حالا", as the rest of the page does.
  if (abs < MINUTE) return lang === "fa" ? "حالا" : rtf.format(0, "second");
  if (abs < HOUR) return rtf.format(Math.round(diff / MINUTE), "minute");
  if (abs < DAY) return rtf.format(Math.round(diff / HOUR), "hour");
  return rtf.format(Math.round(diff / DAY), "day");
}

/** "Thursday, November 12" for a `YYYY-MM-DD` date, read as a calendar day (no timezone shift). */
export function longDate(date: string, lang: string): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Intl.DateTimeFormat(intlLocale(lang), {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(y, m - 1, d)));
}

/** "Nov 12" for an ISO time or `YYYY-MM-DD` date; Dari puts the day first ("۱۲ نومبر"), like `longDate`. */
export function shortDate(value: string, lang: string): string {
  const date = new Date(value);
  if (lang === "fa") {
    const parts = new Intl.DateTimeFormat(intlLocale(lang), { month: "long", day: "numeric" }).formatToParts(date);
    const part = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
    return `${part("day")} ${part("month")}`;
  }
  return new Intl.DateTimeFormat(intlLocale(lang), { month: "short", day: "numeric" }).format(date);
}

/** "8:30 AM" / "8:30" / "۸:۳۰ صبح" for an "HH:MM" local time. */
export function clockTime(hhmm: string, lang: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  if (lang === "fa") {
    // Afghan Dari names the part of the day instead of AM/PM.
    const part = h < 12 ? "صبح" : h < 17 ? "بعد از ظهر" : "شب";
    return `${formatNumber(h % 12 || 12, lang)}:${formatNumber(m, lang, 2)} ${part}`;
  }
  return new Intl.DateTimeFormat(intlLocale(lang), { hour: "numeric", minute: "2-digit", timeZone: "UTC" }).format(
    new Date(Date.UTC(2000, 0, 1, h, m)),
  );
}

/** "12:34" (or "۱۲:۳۴") for a duration in seconds. */
export function duration(seconds: number, lang: string): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${formatNumber(Math.floor(s / 60), lang, 2)}:${formatNumber(s % 60, lang, 2)}`;
}

/** Whole days from today until a `YYYY-MM-DD` date. */
export function daysUntil(date: string, now: number = Date.now()): number {
  const [y, m, d] = date.split("-").map(Number);
  const today = new Date(now);
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((Date.UTC(y, m - 1, d) - start) / DAY);
}

/** "uscis.gov" from "https://www.uscis.gov/contactcenter". */
export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
