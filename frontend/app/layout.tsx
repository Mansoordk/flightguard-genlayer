import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "FlightGuard", description: "Flight protection decisions powered by GenLayer." };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}</body></html>; }
