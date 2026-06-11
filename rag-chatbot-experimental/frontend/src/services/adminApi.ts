import { buildHeaders, resolveApiBaseUrl } from "./chatApi";
import type { SimulatorDocument, SimulatorStatus, SyncSummary } from "../types/admin";

export async function getSimulatorStatus(apiBaseUrl?: string, token?: string): Promise<SimulatorStatus> {
  return getJson<SimulatorStatus>("/admin/index/status", apiBaseUrl, token);
}

export async function getSimulatorDocuments(apiBaseUrl?: string, token?: string): Promise<SimulatorDocument[]> {
  return getJson<SimulatorDocument[]>("/admin/index/documents", apiBaseUrl, token);
}

export async function syncSimulator(apiBaseUrl?: string, token?: string): Promise<SyncSummary> {
  const response = await fetch(`${resolveApiBaseUrl(apiBaseUrl)}/admin/index/sync`, {
    method: "POST",
    headers: buildHeaders(token)
  });
  if (!response.ok) {
    throw new Error(await adminError(response));
  }
  return response.json() as Promise<SyncSummary>;
}

async function getJson<T>(path: string, apiBaseUrl?: string, token?: string): Promise<T> {
  const response = await fetch(`${resolveApiBaseUrl(apiBaseUrl)}${path}`, {
    headers: buildHeaders(token)
  });
  if (!response.ok) {
    throw new Error(await adminError(response));
  }
  return response.json() as Promise<T>;
}

async function adminError(response: Response): Promise<string> {
  if (response.status === 401) {
    return "Authentification administrateur requise.";
  }
  if (response.status === 403) {
    return "Le rôle administrateur est requis.";
  }
  try {
    const data = await response.json();
    return typeof data.detail === "string" ? data.detail : `Erreur HTTP ${response.status}`;
  } catch {
    return `Erreur HTTP ${response.status}`;
  }
}
