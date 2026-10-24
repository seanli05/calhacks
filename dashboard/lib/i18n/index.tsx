"use client";

/**
 * UI labels per language. Adding a language: copy `strings/en/` to
 * `strings/<code>/`, translate, and register it in `STRINGS` and `LANGUAGES`.
 * Text that comes from data (feed, checklist, facts) is translated by the API,
 * not here.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { caseView as enCase } from "./strings/en/case";
import { casesPage as enCases } from "./strings/en/cases";
import { common as enCommon } from "./strings/en/common";
import { landing as enLanding } from "./strings/en/landing";
import { memoryPage as enMemory } from "./strings/en/memory";
import { caseView as esCase } from "./strings/es/case";
import { casesPage as esCases } from "./strings/es/cases";
import { common as esCommon } from "./strings/es/common";
import { landing as esLanding } from "./strings/es/landing";
import { memoryPage as esMemory } from "./strings/es/memory";

const STRINGS = {
  en: { common: enCommon, case: enCase, cases: enCases, memory: enMemory, landing: enLanding },
  es: { common: esCommon, case: esCase, cases: esCases, memory: esMemory, landing: esLanding },
};

export type Strings = (typeof STRINGS)["en"];

/** Languages the switch offers, as shown on the button. */
export const LANGUAGES: { code: string; label: string }[] = [
  { code: "es", label: "ES" },
  { code: "en", label: "EN" },
];

const STORAGE_KEY = "dashboard.lang";

interface LangContextValue {
  /** The language the UI is shown in. */
  lang: string;
  setLang: (lang: string) => void;
  /** Use the user's language unless the viewer already picked one with the switch. */
  adoptUserLanguage: (lang: string | null) => void;
}

const LangContext = createContext<LangContextValue | null>(null);

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState("es");
  const [picked, setPicked] = useState(false);

  useEffect(() => {
    const stored = readStored();
    if (stored) {
      setLangState(stored);
      setPicked(true);
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: string) => {
    setLangState(next);
    setPicked(true);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage can be blocked; the switch still works for this page view.
    }
  }, []);

  const adoptUserLanguage = useCallback(
    (userLang: string | null) => {
      if (!picked && userLang) setLangState(userLang);
    },
    [picked],
  );

  const value = useMemo(() => ({ lang, setLang, adoptUserLanguage }), [lang, setLang, adoptUserLanguage]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangContextValue {
  const value = useContext(LangContext);
  if (!value) throw new Error("useLang must be used inside LanguageProvider");
  return value;
}

/** UI labels for one language, falling back to English. */
export function stringsFor(lang: string): Strings {
  return (STRINGS as Record<string, Strings>)[lang] ?? STRINGS.en;
}

/** UI labels for the current language, falling back to English. */
export function useStrings(): Strings {
  return stringsFor(useLang().lang);
}
