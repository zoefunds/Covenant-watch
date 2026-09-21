import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Covenant Watch",
  description:
    "On-chain covenant monitoring and automatic-penalty lending on GenLayer — precommitted covenants, validator-verified checks, graduated consequences.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-surface text-on-surface">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
