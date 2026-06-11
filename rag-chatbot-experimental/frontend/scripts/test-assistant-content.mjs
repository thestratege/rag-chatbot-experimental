import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { build } from "esbuild";


const outputDir = await mkdtemp(join(tmpdir(), "rag-assistant-content-test-"));
const outputFile = join(outputDir, "assistant-content.mjs");

try {
  await build({
    entryPoints: [new URL("../src/utils/assistantContent.ts", import.meta.url).pathname],
    outfile: outputFile,
    bundle: true,
    format: "esm",
    platform: "node",
    logLevel: "silent"
  });

  const { prepareAssistantContent, stripInternalReasoning } = await import(
    `${pathToFileURL(outputFile).href}?v=${Date.now()}`
  );

  assert.equal(
    stripInternalReasoning("<think>raisonnement privé</think>\n\n**Réponse finale**"),
    "**Réponse finale**"
  );
  assert.equal(
    stripInternalReasoning("thinking=raisonnement privé\nRéponse finale"),
    "Réponse finale"
  );
  assert.equal(
    prepareAssistantContent(
      "Réponse utile.\n\n**Sources :**\n- document.txt",
      true
    ),
    "Réponse utile."
  );
  assert.equal(
    prepareAssistantContent(
      "Réponse utile.\n\nSource utilisée : document.txt",
      true
    ),
    "Réponse utile."
  );
  assert.equal(
    prepareAssistantContent(
      "Je ne trouve pas cette information.\n\nSources :\n- Aucune source pertinente trouvée.",
      false
    ),
    "Je ne trouve pas cette information.\n\nSources :\n- Aucune source pertinente trouvée."
  );

  console.log("assistant content tests passed");
} finally {
  await rm(outputDir, { recursive: true, force: true });
}
