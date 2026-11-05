import type { Metadata } from "next";
import { Inter_Tight } from "next/font/google";
import "../src/styles.css";

const display = Inter_Tight({ subsets: ["latin"], weight: ["500", "600", "800", "900"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "GeoFlora — Plant Intelligence",
  description:
    "A research workspace for Philippine plant identification and biodiversity monitoring.",
  applicationName: "GeoFlora",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={display.variable}>
      <body>{children}</body>
    </html>
  );
}
