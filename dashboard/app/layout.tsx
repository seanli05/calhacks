import type { Metadata } from "next";
import { IBM_Plex_Mono, Instrument_Sans } from "next/font/google";

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

export const metadata: Metadata = {
  title: "[App]",
  description: "Immigration letters, explained in your language. We call the agency and wait on hold for you.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <LanguageProvider>
          {children}
          <FixtureBar />
        </LanguageProvider>
      </body>
    </html>
  );
}
