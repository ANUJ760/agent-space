import React from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ShieldX, LogIn, ArrowLeft } from "lucide-react";

export default function UnauthorizedPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] text-center px-4">
      <div className="w-16 h-16 rounded-2xl bg-destructive/10 text-destructive flex items-center justify-center mb-6 shadow-sm">
        <ShieldX className="w-8 h-8" />
      </div>
      <h1 className="text-3xl font-bold tracking-tight text-foreground">
        403 — Access Denied
      </h1>
      <p className="text-muted-foreground mt-2 max-w-md text-sm">
        You do not have the required permissions or role within this organization to access
        the requested resource. Please sign in with an authorized account or contact your organization administrator.
      </p>

      <div className="flex items-center gap-3 mt-8">
        <Link href="/">
          <Button variant="outline" className="gap-2">
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Dashboard</span>
          </Button>
        </Link>
        <Link href="/login">
          <Button className="gap-2">
            <LogIn className="w-4 h-4" />
            <span>Switch Account</span>
          </Button>
        </Link>
      </div>
    </div>
  );
}
