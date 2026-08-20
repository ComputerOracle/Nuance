import Link from "next/link";
import { Logo } from "@/components/logo";

const NAV_LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#use-cases", label: "Use cases" },
  { href: "#network", label: "Network" },
];

export function SiteHeader() {
  return (
    <header className="mx-auto flex max-w-[1160px] items-center justify-between px-8 py-6">
      <Link href="/">
        <Logo />
      </Link>

      <nav className="flex items-center gap-8">
        <div className="hidden items-center gap-8 md:flex">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm text-fg-muted transition-colors hover:text-fg-hover"
            >
              {link.label}
            </a>
          ))}
        </div>

        <Link
          href="/app"
          className="rounded-lg border border-border-6 bg-chip-hover px-4 py-2.5 text-sm font-semibold transition-colors hover:bg-chip-hover-2"
        >
          Launch App
        </Link>
      </nav>
    </header>
  );
}
