import type { Localized } from "./api/types";

/**
 * The English to show muted under a `Localized` text, or null when it would just
 * repeat the line above: the UI is in English, or no translation exists yet.
 */
export function englishBelow(value: Localized, lang: string): string | null {
  return lang !== "en" && value.en !== value.text ? value.en : null;
}
