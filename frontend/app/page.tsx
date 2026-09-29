import React from "react";
import { HeroSection } from "@/components/collection/HeroSection";
import { MetricCards } from "@/components/collection/MetricCards";
import { RecentCollectionsTable } from "@/components/collection/RecentCollectionsTable";
import { BlurFade } from "@/components/ui/blur-fade";

export default function DashboardPage() {
  return (
    <div className="mx-auto w-full max-w-[1680px] 2xl:max-w-none">
      <BlurFade duration={0.42} initial={false} offset={8}>
        <HeroSection />
      </BlurFade>
      <BlurFade
        delay={0.08}
        duration={0.42}
        initial={false}
        offset={8}
      >
        <div className="mt-[clamp(24px,1.8vw,36px)] grid grid-cols-[minmax(0,1fr)] items-start gap-[clamp(24px,1.8vw,36px)] lg:grid-cols-[minmax(0,1fr)_clamp(340px,24vw,440px)]">
          <RecentCollectionsTable />
          <MetricCards />
        </div>
      </BlurFade>
    </div>
  );
}
