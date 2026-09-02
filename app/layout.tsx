import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Растём вместе — навигатор развития ребёнка",
  description:
    "Возрастные потребности ребёнка, практики саморегуляции, самостоятельности, внимания и корректная поддержка для родителей.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  );
}
