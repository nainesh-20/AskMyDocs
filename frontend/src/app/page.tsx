"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";

export default function RootPage() {
  const router = useRouter();
  const supabase = createClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      router.replace(session ? "/dashboard" : "/login");
    });
  }, [router, supabase.auth]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-zinc-400 border-t-transparent" />
    </div>
  );
}
