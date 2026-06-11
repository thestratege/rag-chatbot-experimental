import type { ChatApiRequest, ChatApiResponse } from "../types/chat";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";
const IS_DEVELOPMENT = import.meta.env.DEV;

export async function sendChatMessage(
  payload: ChatApiRequest,
  apiBaseUrl?: string,
  demoAuthToken?: string
): Promise<ChatApiResponse> {
  const endpoint = "/api/chat";
  const baseUrl = resolveApiBaseUrl(apiBaseUrl);
  const url = `${baseUrl}${endpoint}`;
  const response = await request(url, endpoint, {
    method: "POST",
    headers: buildHeaders(demoAuthToken),
    body: JSON.stringify(payload)
  }, demoAuthToken);

  if (!response.ok) {
    throw new Error(await formatHttpError(response));
  }

  return response.json() as Promise<ChatApiResponse>;
}

export async function resetConversation(
  conversationId: string,
  apiBaseUrl?: string,
  demoAuthToken?: string
): Promise<void> {
  const endpoint = "/api/conversations/reset";
  const baseUrl = resolveApiBaseUrl(apiBaseUrl);
  const url = `${baseUrl}${endpoint}`;
  const response = await request(url, endpoint, {
    method: "POST",
    headers: buildHeaders(demoAuthToken),
    body: JSON.stringify({ conversation_id: conversationId })
  }, demoAuthToken);

  if (!response.ok) {
    throw new Error(await formatHttpError(response));
  }
}

export function resolveApiBaseUrl(apiBaseUrl?: string): string {
  return (apiBaseUrl || API_BASE_URL).replace(/\/+$/, "");
}

export function buildHeaders(demoAuthToken?: string): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  };
  const token = demoAuthToken?.trim();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function request(
  url: string,
  endpoint: string,
  init: RequestInit,
  demoAuthToken?: string
): Promise<Response> {
  logDevelopment("request", {
    apiBaseUrl: url.slice(0, -endpoint.length),
    endpoint,
    tokenPresent: Boolean(demoAuthToken?.trim())
  });
  try {
    const response = await fetch(url, init);
    logDevelopment("response", { endpoint, status: response.status });
    return response;
  } catch (error) {
    const message = error instanceof Error ? error.message : "Erreur réseau inconnue";
    logDevelopment("network-error", { endpoint, message });
    throw new Error("Le service du chatbot n’est pas disponible pour le moment. Vérifiez que le back-end est démarré.");
  }
}

async function formatHttpError(response: Response): Promise<string> {
  if (response.status === 401) {
    return "Non authentifié : vérifiez le token de démonstration.";
  }
  if (response.status === 403) {
    return "Accès refusé : rôle insuffisant.";
  }
  if (response.status === 503) {
    const detail = (await readError(response)).toLowerCase();
    if (detail.includes("timeout")) {
      return "La réponse prend trop de temps. Veuillez réessayer.";
    }
    if (detail.includes("ollama") || detail.includes("embedding")) {
      return "Le serveur IA local n’est pas disponible pour le moment.";
    }
    return "Le service documentaire n’est pas disponible pour le moment.";
  }
  if (response.status === 504) {
    return "La réponse prend trop de temps. Veuillez réessayer.";
  }
  if (response.status >= 500) {
    return "Une erreur interne empêche temporairement le chatbot de répondre.";
  }
  const detail = await readError(response);
  return detail || `Le backend FastAPI a retourné une erreur HTTP ${response.status}.`;
}

async function readError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") {
      return data.detail;
    }
  } catch {
    return "";
  }
  return "";
}

function logDevelopment(event: string, details: Record<string, unknown>): void {
  if (IS_DEVELOPMENT) {
    console.info(`[chat-api] ${event}`, details);
  }
}
