import type { Metadata } from "next";
import { IBM_Plex_Mono, Instrument_Sans, Vazirmatn } from "next/font/google";

import { FixtureBar } from "@/components/FixtureBar";
import { LanguageProvider } from "@/lib/i18n";

import "./globals.css";

const sans = Instrument_Sans({
  subsets: ["latin", "latin-ext"],
  variable: "--font-sans",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

// Dari's script; Instrument Sans has no Arabic-script glyphs, so this is its fallback.
const dari = Vazirmatn({
  subsets: ["arabic"],
  variable: "--font-dari",
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: "[App]",
  description: "Immigration letters, explained in your language. We call the agency and wait on hold for you.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${sans.variable} ${mono.variable} ${dari.variable}`}>
      <body>
        <LanguageProvider>
          {children}
          <FixtureBar />
        </LanguageProvider>
      </body>
    </html>
  );
}
