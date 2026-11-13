import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Reel Box · 미디어 라이브러리",
  description:
    "링크를 모으고, 영상으로 보관하세요. 개인용 멀티플랫폼 다운로더.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
