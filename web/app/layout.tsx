import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SCOUT.AI — Football Intelligence",
  description: "Next.js + FastAPI scouting dashboard POC",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
