import type { Metadata } from "next";
import { NuanceApp } from "@/components/app/nuance-app";

export const metadata: Metadata = {
  title: "Nuance App — Escrows, Markets & the Internet Court",
};

export default function AppPage() {
  return <NuanceApp />;
}
