import { ChatWidget } from "./components/ChatWidget";
import { AdminDashboard } from "./components/AdminDashboard";
import type { WidgetConfig, WidgetTheme } from "./types/chat";

export default function App() {
  const config = getWidgetConfig();
  if (window.location.pathname === "/admin") {
    return <AdminDashboard apiBaseUrl={config.apiBaseUrl} />;
  }
  return (
    <main className={config.embed ? "embed-page" : "main-page"}>
      <ChatWidget
        apiBaseUrl={config.apiBaseUrl}
        title={config.title}
        providerLabel={config.providerLabel}
        compact={config.compact}
        theme={config.theme}
        embed={config.embed}
      />
    </main>
  );
}

function getWidgetConfig(): WidgetConfig {
  const params = new URLSearchParams(window.location.search);
  const embed = window.location.pathname === "/embed";
  return {
    apiBaseUrl: sanitizeApiBaseUrl(params.get("apiBaseUrl")),
    theme: sanitizeTheme(params.get("theme")),
    title: sanitizeTitle(params.get("title")) || "Assistant documentaire",
    providerLabel: sanitizeTitle(params.get("providerLabel")) || undefined,
    compact: params.get("compact") === "true",
    embed
  };
}

function sanitizeApiBaseUrl(value: string | null): string | undefined {
  if (!value) {
    return undefined;
  }
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol)) {
      return undefined;
    }
    url.hash = "";
    url.search = "";
    return url.toString().replace(/\/+$/, "");
  } catch {
    return undefined;
  }
}

function sanitizeTheme(value: string | null): WidgetTheme {
  return value === "ism" ? "ism" : "default";
}

function sanitizeTitle(value: string | null): string {
  return (value || "").trim().slice(0, 80);
}
