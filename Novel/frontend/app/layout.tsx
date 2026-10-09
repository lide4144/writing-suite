import type { Metadata } from "next";

import { appBuild } from "@/lib/app-build";

import "./globals.css";

export const metadata: Metadata = {
  title: "Novel Agent Platform",
  description: "Headless-first multi-agent novel platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const buildPayload = JSON.stringify(appBuild).replace(/</g, "\\u003c");

  return (
    <html lang="zh-CN">
      <body>
        <script
          id="app-build"
          dangerouslySetInnerHTML={{ __html: `window.__APP_BUILD__ = ${buildPayload};` }}
        />
        {children}
      </body>
    </html>
  );
}
