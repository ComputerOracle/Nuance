import { SiteHeader } from "@/components/site-header";
import { Hero } from "@/components/hero";
import { TickerStrip } from "@/components/ticker-strip";
import { HowItWorks } from "@/components/how-it-works";
import { UseCases } from "@/components/use-cases";
import { NetworkCta } from "@/components/network-cta";
import { SiteFooter } from "@/components/site-footer";

export default function Home() {
  return (
    <>
      <SiteHeader />
      <Hero />
      <TickerStrip />
      <HowItWorks />
      <UseCases />
      <NetworkCta />
      <SiteFooter />
    </>
  );
}
