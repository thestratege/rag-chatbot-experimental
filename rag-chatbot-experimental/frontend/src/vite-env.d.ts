/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_AUTH_DEMO_ENABLED?: string;
  readonly VITE_RUNTIME_MODE?: "local" | "sharepoint";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
