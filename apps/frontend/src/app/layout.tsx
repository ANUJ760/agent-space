import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth-context";
import { AppShell } from "@/components/layout/app-shell";
import { ThreeTransitionCanvas } from "@/components/canvas/ThreeTransitionCanvas";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent Space — Autonomous AI Collaboration Platform",
  description:
    "A modular, self-hostable collaboration platform where humans and autonomous AI agents work together on software projects.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background font-sans antialiased text-foreground selection:bg-primary/20 selection:text-primary">
        <ThreeTransitionCanvas />
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
