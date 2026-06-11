import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { build } from "esbuild";


const outputDir = await mkdtemp(join(tmpdir(), "rag-chat-api-test-"));
const outputFile = join(outputDir, "chat-api.mjs");

try {
  await build({
    entryPoints: [new URL("../src/services/chatApi.ts", import.meta.url).pathname],
    outfile: outputFile,
    bundle: true,
    format: "esm",
    platform: "node",
    logLevel: "silent",
    define: {
      "import.meta.env.DEV": "false",
      "import.meta.env.VITE_API_BASE_URL": JSON.stringify("http://127.0.0.1:8010")
    }
  });

  const { sendChatMessage } = await import(`${pathToFileURL(outputFile).href}?v=${Date.now()}`);
  const payload = { conversation_id: null, message: "Bonjour", mode: "auto" };
  const successBody = {
    conversation_id: "conversation-id",
    answer: "Bonjour.",
    intent: "greeting",
    used_rag: false,
    sources: [],
    provider: "mock"
  };
  let lastRequest;

  globalThis.fetch = async (url, init) => {
    lastRequest = { url: String(url), init };
    return jsonResponse(200, successBody);
  };

  await sendChatMessage(payload, undefined, "test-user-token");
  assert.equal(lastRequest.url, "http://127.0.0.1:8010/api/chat");
  assert.equal(new Headers(lastRequest.init.headers).get("Authorization"), "Bearer test-user-token");

  await sendChatMessage(payload, "http://api.example.test/", undefined);
  assert.equal(lastRequest.url, "http://api.example.test/api/chat");
  assert.equal(new Headers(lastRequest.init.headers).has("Authorization"), false);

  globalThis.fetch = async () => jsonResponse(401, { detail: "Token invalide." });
  await assert.rejects(
    sendChatMessage(payload, undefined, "mauvais-token"),
    /Non authentifié : vérifiez le token de démonstration\./
  );

  globalThis.fetch = async () => jsonResponse(403, { detail: "Rôle insuffisant." });
  await assert.rejects(
    sendChatMessage(payload, undefined, "test-user-token"),
    /Accès refusé : rôle insuffisant\./
  );

  globalThis.fetch = async () => jsonResponse(500, { detail: "Détail interne." });
  await assert.rejects(
    sendChatMessage(payload, undefined, "test-user-token"),
    /Une erreur interne empêche temporairement le chatbot de répondre\./
  );

  globalThis.fetch = async () => jsonResponse(503, { detail: "Ollama est inaccessible." });
  await assert.rejects(
    sendChatMessage(payload, undefined, "test-user-token"),
    /Le serveur IA local n’est pas disponible pour le moment\./
  );

  globalThis.fetch = async () => jsonResponse(503, { detail: "Timeout lors de la génération." });
  await assert.rejects(
    sendChatMessage(payload, undefined, "test-user-token"),
    /La réponse prend trop de temps\. Veuillez réessayer\./
  );

  globalThis.fetch = async () => {
    throw new TypeError("fetch failed");
  };
  await assert.rejects(
    sendChatMessage(payload, undefined, "test-user-token"),
    /Le service du chatbot n’est pas disponible pour le moment\. Vérifiez que le back-end est démarré\./
  );

  console.log("chatApi service tests passed");
} finally {
  await rm(outputDir, { recursive: true, force: true });
}


function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}
