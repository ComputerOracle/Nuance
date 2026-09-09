import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { DocsContent } from "@/components/docs-content";

export const metadata: Metadata = {
  title: "Nuance Docs — API Reference & Contract Addresses",
};

export default function DocsPage() {
  return (
    <>
      <SiteHeader />
      <DocsContent />
      <SiteFooter />
    </>
  );
}
