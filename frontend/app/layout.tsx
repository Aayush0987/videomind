import type { Metadata } from "next";
import { Saira_Condensed, Source_Sans_3 } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

// Condensed grotesque for chapter titles + timecodes; a comfortable humanist
// sans for summaries and answers (§16.2).
const condensed = Saira_Condensed({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-condensed",
});

const sans = Source_Sans_3({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "VideoMind",
  description:
    "Paste a YouTube link, get topic chapters and grounded Q&A with clickable timestamp citations.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${condensed.variable} ${sans.variable}`}>
      <body className="min-h-screen bg-ground font-sans text-paper antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
