import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

const title = "SCOUT.AI — Football Decision Intelligence";
const description = "8개 유럽 리그를 연결하는 스카우팅, 영입 적합도, 스쿼드 플래닝 운영 시스템";

export function generateMetadata(): Metadata {
  const requestHeaders = headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const base = new URL(`${protocol}://${host}`);
  const image = new URL("/og.png", base).toString();

  return {
    metadataBase: base,
    title,
    description,
    applicationName: "SCOUT.AI",
    openGraph: {
      type: "website",
      title,
      description,
      siteName: "SCOUT.AI",
      images: [{ url: image, width: 1734, height: 906, alt: "SCOUT.AI football decision intelligence dashboard" }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image],
    },
  };
}

export const viewport = {
  colorScheme: "dark",
  themeColor: "#07090d",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
