import "./globals.css";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import Script from "next/script";

export const metadata: Metadata = {
  title: "TaskButler — your liquid-glass butler",
  description:
    "A fully-duplex voice AI agent with persistent memory and a real browser at its fingertips.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f5f3ee",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Suppress SES lockdown warnings from livekit-client dependencies */}
        <Script id="ses-suppress" strategy="beforeInteractive">{`
          (function() {
            var origWarn = console.warn;
            console.warn = function() {
              if (typeof arguments[0] === 'string' && arguments[0].indexOf('Removing unpermitted intrinsics') !== -1) return;
              origWarn.apply(console, arguments);
            };
          })();
        `}</Script>
        {children}
      </body>
    </html>
  );
}