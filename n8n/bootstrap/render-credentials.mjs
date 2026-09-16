// Renders n8n credential import files from environment variables.
// IDs are fixed so the versioned workflows can reference them.
import { writeFileSync } from "node:fs";
import { join } from "node:path";

const outputDir = process.argv[2];
if (!outputDir) {
  console.error("usage: node render-credentials.mjs <output-dir>");
  process.exit(1);
}

const env = (name) => (process.env[name] ?? "").trim();

const clinicApiKey = env("CLINIC_API_KEY");
if (!clinicApiKey) {
  console.error("CLINIC_API_KEY is required");
  process.exit(1);
}

const credentials = {
  "clinic-api": {
    id: "clinicApiKeyCred",
    name: "Clinic API key",
    type: "httpHeaderAuth",
    data: { name: "X-API-Key", value: clinicApiKey },
  },
  openai: {
    id: "clinicOpenAiCred",
    name: "OpenAI (Clinic)",
    type: "openAiApi",
    data: { apiKey: env("OPENAI_API_KEY"), url: "https://api.openai.com/v1" },
  },
  // Only the OAuth client is provisioned; the token comes from "Sign in with Google" in the UI.
  gmail: {
    id: "clinicGmailCred1",
    name: "Gmail (Clinic)",
    type: "gmailOAuth2",
    data: {
      clientId: env("GOOGLE_OAUTH_CLIENT_ID"),
      clientSecret: env("GOOGLE_OAUTH_CLIENT_SECRET"),
    },
  },
};

for (const [file, credential] of Object.entries(credentials)) {
  writeFileSync(join(outputDir, `${file}.json`), JSON.stringify([credential], null, 2), {
    mode: 0o600,
  });
}
