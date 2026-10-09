"use client";

import { useEffect, useState } from "react";

import { isAutomationMode } from "@/lib/app-build";

export default function HomePage() {
  const [automationMode, setAutomationMode] = useState(false);

  useEffect(() => {
    setAutomationMode(isAutomationMode(window.location.search));
  }, []);

  return (
    <main
      data-testid="platform-home"
      data-automation-mode={automationMode ? "on" : "off"}
      className="min-h-screen bg-slate-950 px-6 py-16 text-slate-100"
    >
      <section className="mx-auto max-w-3xl rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
        <p className="mb-3 text-sm font-medium uppercase tracking-[0.25em] text-cyan-300">M1 foundation</p>
        <h1 className="text-4xl font-semibold tracking-tight">Novel Agent Platform</h1>
        <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-300">
          运行环境与 Project、Preset、Model Registry API 已就绪。Workflow 和章节业务将在后续里程碑接入。
        </p>
        <div className="mt-8 grid gap-3 sm:grid-cols-3" data-testid="m0-capabilities">
          <div className="rounded-lg bg-slate-800 p-4">FastAPI health</div>
          <div className="rounded-lg bg-slate-800 p-4">Project + Preset API</div>
          <div className="rounded-lg bg-slate-800 p-4">Redis + ARQ heartbeat</div>
        </div>
        <p className="mt-8 text-sm text-slate-400" data-testid="automation-status">
          Automation mode: {automationMode ? "enabled" : "disabled"}
        </p>
      </section>
    </main>
  );
}
