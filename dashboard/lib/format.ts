/** Date and time formatting through `Intl`, so every language works without string files. */

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * The `Intl` locale for a language code. Dari (`fa`) is Afghan Persian on the
 * Gregorian calendar ("۱۲ نومبر"), as USCIS's Dari pages write it; plain `fa` would
 * give Iranian Solar Hijri dates.
 */
export function intlLocale(lang: string): string {
  return lang === "fa" ? "fa-AF-u-ca-gregory" : lang;
}

/** "3 min ago", "hace 2 días", "now". Relative times only: no small clock text on video. */
export function relativeTime(iso: string, lang: string, now: number = Date.now()): string {
  const diff = new Date(iso).getTime() - now;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat(intlLocale(lang), { numeric: "auto", style: "short" });
  if (abs < MINUTE) return rtf.format(0, "second");
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

/** "Nov 12" for an ISO time or `YYYY-MM-DD` date. */
export function shortDate(value: string, lang: string): string {
  return new Intl.DateTimeFormat(intlLocale(lang), { month: "short", day: "numeric" }).format(new Date(value));
}

/** "8:30 AM" / "8:30" / "۸:۳۰ صبح" for an "HH:MM" local time. */
export function clockTime(hhmm: string, lang: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  if (lang === "fa") {
    // Afghan Dari names the part of the day instead of AM/PM.
    const part = h < 12 ? "صبح" : h < 17 ? "بعد از ظهر" : "شب";
    const digits = new Intl.NumberFormat(intlLocale(lang), { minimumIntegerDigits: 2 });
    return `${new Intl.NumberFormat(intlLocale(lang)).format(h % 12 || 12)}:${digits.format(m)} ${part}`;
  }
  return new Intl.DateTimeFormat(lang, { hour: "numeric", minute: "2-digit", timeZone: "UTC" }).format(
    new Date(Date.UTC(2000, 0, 1, h, m)),
  );
}

/** "12:34" for a duration in seconds. */
export function duration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
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
