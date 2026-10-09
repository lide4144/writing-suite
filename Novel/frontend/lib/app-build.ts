export type AppBuild = {
  version: string;
  schema: string;
  commit: string;
};

export const appBuild: AppBuild = {
  version: process.env.NEXT_PUBLIC_APP_VERSION ?? "0.1.0-m1",
  schema: "m1",
  commit: process.env.NEXT_PUBLIC_APP_COMMIT ?? "local",
};

export function isAutomationMode(search: string): boolean {
  return new URLSearchParams(search).get("automation") === "1";
}

declare global {
  interface Window {
    __APP_BUILD__: AppBuild;
  }
}
