"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const supabase = createClient();

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  const linkClass = (path: string) =>
    `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
      pathname === path
        ? "bg-white/10 text-white"
        : "text-zinc-400 hover:text-white hover:bg-white/5"
    }`;

  return (
    <nav className="border-b border-zinc-800 bg-zinc-950">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href="/dashboard" className="text-base font-bold tracking-tight text-white">
          Ask<span className="text-blue-400">My</span>Docs
        </Link>

        <div className="flex items-center gap-0.5 sm:gap-1">
          <Link href="/dashboard" className={linkClass("/dashboard")}>
            <span className="hidden sm:inline">Dashboard</span>
            <span className="sm:hidden">Docs</span>
          </Link>
          <Link href="/query" className={linkClass("/query")}>
            <span className="hidden sm:inline">Query</span>
            <span className="sm:hidden">Ask</span>
          </Link>
          <button
            onClick={handleLogout}
            className="ml-2 rounded-md px-3 py-1.5 text-sm font-medium text-zinc-400 transition-colors hover:bg-white/5 hover:text-white sm:ml-3"
          >
            Logout
          </button>
        </div>
      </div>
    </nav>
  );
}
