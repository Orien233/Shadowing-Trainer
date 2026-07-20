import { useEffect, useMemo, useState } from "react";
import {
  createProvider,
  deleteProvider,
  getASRSceneSettings,
  listProviderCatalog,
  listProviderVoices,
  listProviders,
  testProvider,
  testProviderDraft,
  updateASRSceneSettings,
  updateProvider,
} from "../lib/api";
import type {
  AIProvider,
  ASRSceneSettings,
  ASRSceneSettingsUpdate,
  ProviderCapability,
  ProviderCatalogEntry,
  ProviderConfigField,
  ProviderTestResponse,
  ProviderVoice,
} from "../types";

const capabilities: ProviderCapability[] = ["llm", "tts", "asr"];

type ProviderDraft = {
  name: string;
  capability: ProviderCapability;
  provider_type: string;
  base_url: string;
  api_key: string;
  model_name: string;
  extra_config: Record<string, string | number | boolean | null>;
};

const standardFields = new Set(["base_url", "api_key", "model_name"]);

const FALLBACK_CATALOG: ProviderCatalogEntry[] = [
  {
    key: "openai_compatible", label: "OpenAI-compatible", kind: "llm",
    capabilities: ["generate_text", "generate_json"], endpoint_mode: "base_url",
    endpoint_hint: "API base URL, for example https://api.example.com/v1", required_fields: ["base_url", "api_key", "model_name"],
    config_fields: [], voice_presets: [], docs_url: null,
  },
  {
    key: "openai_compatible", label: "OpenAI-compatible speech", kind: "tts",
    capabilities: ["synthesize"], endpoint_mode: "full_endpoint",
    endpoint_hint: "Full speech endpoint, for example https://api.example.com/v1/audio/speech", required_fields: ["base_url", "api_key", "model_name"],
    config_fields: [{ key: "default_voice", label: "Default voice", field_type: "select", required: false, options: ["alloy", "echo", "fable", "onyx", "nova", "shimmer"], default: "alloy", placeholder: null, help_text: "Used when no voice is chosen for a practice." }],
    voice_presets: [
      { id: "alloy", name: "Alloy" }, { id: "echo", name: "Echo" }, { id: "fable", name: "Fable" },
      { id: "onyx", name: "Onyx" }, { id: "nova", name: "Nova" }, { id: "shimmer", name: "Shimmer" },
    ],
    docs_url: null,
  },
  {
    key: "openai_compatible", label: "OpenAI-compatible transcription", kind: "asr",
    capabilities: ["transcribe"], endpoint_mode: "full_endpoint",
    endpoint_hint: "Full transcription endpoint supplied by the provider", required_fields: ["base_url", "api_key", "model_name"],
    config_fields: [], voice_presets: [], docs_url: null,
  },
  {
    key: "azure_speech", label: "Azure Speech", kind: "tts",
    capabilities: ["synthesize", "list_voices"], endpoint_mode: "base_url",
    endpoint_hint: "Speech resource endpoint, for example https://your-resource.cognitiveservices.azure.com", required_fields: ["base_url", "api_key", "model_name"],
    config_fields: [
      { key: "locale", label: "Locale", field_type: "string", required: false, options: [], default: "en-US", placeholder: "en-US", help_text: "Voice locale used in generated SSML." },
      { key: "output_format", label: "Output format", field_type: "string", required: false, options: [], default: "audio-24khz-48kbitrate-mono-mp3", placeholder: null, help_text: null },
    ], voice_presets: [], docs_url: null,
  },
  {
    key: "azure_speech", label: "Azure Speech", kind: "asr",
    capabilities: ["transcribe", "word_timestamps"], endpoint_mode: "base_url",
    endpoint_hint: "Speech resource endpoint, for example https://your-resource.cognitiveservices.azure.com", required_fields: ["base_url", "api_key", "model_name"],
    config_fields: [], voice_presets: [], docs_url: null,
  },
  {
    key: "mimo_tts", label: "MiMo TTS", kind: "tts",
    capabilities: ["synthesize"], endpoint_mode: "full_endpoint",
    endpoint_hint: "Full MiMo chat-completions endpoint", required_fields: ["base_url", "api_key", "model_name"],
    config_fields: [
      { key: "default_voice", label: "Default voice", field_type: "string", required: false, options: [], default: "mimo_default", placeholder: "mimo_default", help_text: null },
      { key: "audio_format", label: "Audio format", field_type: "select", required: false, options: ["wav", "mp3", "pcm16", "opus", "flac"], default: "wav", placeholder: null, help_text: null },
    ], voice_presets: [{ id: "mimo_default", name: "MiMo default" }], docs_url: null,
  },
  {
    key: "mimo_asr", label: "MiMo ASR", kind: "asr",
    capabilities: ["transcribe"], endpoint_mode: "full_endpoint",
    endpoint_hint: "Full MiMo chat-completions endpoint", required_fields: ["base_url", "api_key", "model_name"],
    config_fields: [], voice_presets: [], docs_url: null,
  },
];

function catalogId(entry: ProviderCatalogEntry): string {
  return `${entry.kind}:${entry.key}`;
}

function missingReason(missing: string[]): string {
  return missing.length ? `Remote ASR unavailable: missing ${missing.join(", ")}.` : "Remote ASR is unavailable.";
}

function configDefaults(entry: ProviderCatalogEntry): ProviderDraft["extra_config"] {
  return Object.fromEntries((entry.config_fields || []).map((field) => [field.key, typeof field.default === "string" || typeof field.default === "number" || typeof field.default === "boolean" ? field.default : null]));
}

function newDraft(entry: ProviderCatalogEntry, name = ""): ProviderDraft {
  return {
    name,
    capability: entry.kind,
    provider_type: entry.key,
    base_url: "",
    api_key: "",
    model_name: "",
    extra_config: configDefaults(entry),
  };
}

function hasValue(value: unknown): boolean {
  if (typeof value === "string") return Boolean(value.trim());
  return value !== null && value !== undefined;
}

function displayVoice(voice: ProviderVoice): string {
  const languages = voice.languages?.length ? ` (${voice.languages.join(", ")})` : voice.locale ? ` (${voice.locale})` : "";
  return `${voice.name || voice.id}${languages}`;
}

function testSummary(result: ProviderTestResponse): string {
  const verification = result.verification_level ? ` Verification: ${result.verification_level}.` : "";
  const providerCapabilities = result.capabilities.length ? ` Capabilities: ${result.capabilities.join(", ")}.` : "";
  return `${result.ok ? "Test passed." : "Test failed."} ${result.message}${verification}${providerCapabilities}`;
}

export default function SettingsPanel() {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [catalog, setCatalog] = useState<ProviderCatalogEntry[]>(FALLBACK_CATALOG);
  const [scenes, setScenes] = useState<ASRSceneSettings | null>(null);
  const [message, setMessage] = useState("");
  const [draftTest, setDraftTest] = useState<ProviderTestResponse | null>(null);
  const [testingDraft, setTestingDraft] = useState(false);
  const [providerVoices, setProviderVoices] = useState<Record<number, ProviderVoice[]>>({});
  const [loadingVoices, setLoadingVoices] = useState<number | null>(null);
  const [draft, setDraft] = useState<ProviderDraft>(() => newDraft(FALLBACK_CATALOG[0]));

  const adapters = useMemo(() => catalog.filter((entry) => entry.kind === draft.capability), [catalog, draft.capability]);
  const selectedCatalog = useMemo(
    () => adapters.find((entry) => entry.key === draft.provider_type) || adapters[0] || FALLBACK_CATALOG[0],
    [adapters, draft.provider_type],
  );
  const selectedConfigFields = selectedCatalog.config_fields || [];

  const load = async () => {
    try {
      const [nextProviders, nextScenes, nextCatalog] = await Promise.all([
        listProviders(),
        getASRSceneSettings(),
        listProviderCatalog().catch(() => []),
      ]);
      const usableCatalog = nextCatalog.length ? nextCatalog : FALLBACK_CATALOG;
      setProviders(nextProviders);
      setScenes(nextScenes);
      setCatalog(usableCatalog);
      setDraft((current) => {
        const currentEntry = usableCatalog.find((entry) => entry.kind === current.capability && entry.key === current.provider_type);
        return currentEntry ? current : newDraft(usableCatalog[0], current.name);
      });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Settings failed to load.");
    }
  };

  useEffect(() => { void load(); }, []);

  function setDraftValue<K extends keyof ProviderDraft>(key: K, value: ProviderDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setDraftTest(null);
  }

  function selectCapability(capability: ProviderCapability) {
    const entry = catalog.find((item) => item.kind === capability) || FALLBACK_CATALOG.find((item) => item.kind === capability) || FALLBACK_CATALOG[0];
    setDraft(newDraft(entry, draft.name));
    setDraftTest(null);
  }

  function selectAdapter(id: string) {
    const entry = adapters.find((item) => catalogId(item) === id);
    if (!entry) return;
    setDraft(newDraft(entry, draft.name));
    setDraftTest(null);
  }

  function setConfigValue(field: ProviderConfigField, value: string | number | boolean | null) {
    setDraft((current) => ({ ...current, extra_config: { ...current.extra_config, [field.key]: value } }));
    setDraftTest(null);
  }

  function draftPayload() {
    return {
      name: draft.name.trim(),
      capability: draft.capability,
      provider_type: draft.provider_type,
      base_url: draft.base_url.trim() || null,
      api_key: draft.api_key.trim() || null,
      model_name: draft.model_name.trim() || null,
      extra_config: Object.fromEntries(Object.entries(draft.extra_config).filter(([, value]) => value !== null && value !== "")),
    };
  }

  function isDraftComplete(): boolean {
    return hasValue(draft.name) && selectedCatalog.required_fields.every((field) => {
      if (field === "base_url") return hasValue(draft.base_url);
      if (field === "api_key") return hasValue(draft.api_key);
      if (field === "model_name") return hasValue(draft.model_name);
      return hasValue(draft.extra_config[field]);
    }) && selectedConfigFields.filter((field) => field.required && !standardFields.has(field.key)).every((field) => hasValue(draft.extra_config[field.key]));
  }

  async function add() {
    try {
      const payload = draftPayload();
      await createProvider({ ...payload, is_enabled: true, is_default: !providers.some((provider) => provider.capability === draft.capability && provider.is_default) });
      setDraft(newDraft(catalog.find((entry) => entry.kind === "llm") || FALLBACK_CATALOG[0]));
      setDraftTest(null);
      setMessage("Provider saved.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add provider.");
    }
  }

  async function testDraft() {
    setTestingDraft(true);
    setMessage("");
    try {
      const result = await testProviderDraft(draftPayload());
      setDraftTest(result);
      setMessage(testSummary(result));
    } catch (error) {
      setDraftTest(null);
      setMessage(error instanceof Error ? error.message : "Provider test failed.");
    } finally {
      setTestingDraft(false);
    }
  }

  async function testSaved(provider: AIProvider) {
    try {
      const result = await testProvider(provider.id);
      setMessage(testSummary(result));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Provider test failed.");
    }
  }

  async function loadVoices(provider: AIProvider) {
    if (providerVoices[provider.id]) {
      setProviderVoices((current) => {
        const next = { ...current };
        delete next[provider.id];
        return next;
      });
      return;
    }
    setLoadingVoices(provider.id);
    try {
      const voices = await listProviderVoices(provider.id);
      setProviderVoices((current) => ({ ...current, [provider.id]: voices }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load provider voices.");
    } finally {
      setLoadingVoices(null);
    }
  }

  async function setDefault(provider: AIProvider) {
    try {
      await updateProvider(provider.id, { is_default: true, is_enabled: true });
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not set default.");
    }
  }

  async function edit(provider: AIProvider) {
    const base_url = window.prompt("Provider base URL", provider.base_url || "");
    if (base_url === null) return;
    const model_name = window.prompt("Model name", provider.model_name || "");
    if (model_name === null) return;
    const api_key = window.prompt("New API key (leave blank to retain saved key)", "");
    if (api_key === null) return;
    try {
      await updateProvider(provider.id, { base_url, model_name, api_key: api_key || undefined });
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update provider.");
    }
  }

  async function remove(id: number) {
    if (!window.confirm("Delete this provider configuration?")) return;
    try {
      await deleteProvider(id);
      setProviderVoices((current) => {
        const next = { ...current };
        delete next[id];
        return next;
      });
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not delete provider.");
    }
  }

  async function updateScene(key: keyof ASRSceneSettingsUpdate, value: boolean) {
    const payload: ASRSceneSettingsUpdate = key === "material_transcription_use_local"
      ? { material_transcription_use_local: value }
      : { recording_evaluation_use_local: value };
    try {
      setScenes(await updateASRSceneSettings(payload));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update ASR setting.");
      await load();
    }
  }

  function renderConfigField(field: ProviderConfigField) {
    const value = draft.extra_config[field.key];
    const voiceOptions = field.key === "default_voice" ? selectedCatalog.voice_presets || [] : [];
    const options = [...new Set([...(field.options || []), ...voiceOptions.map((voice) => voice.id)])];
    if (field.field_type === "boolean") {
      return <label key={field.key} className="config-checkbox"><input type="checkbox" checked={Boolean(value)} onChange={(event) => setConfigValue(field, event.target.checked)} /> {field.label}{field.required ? " *" : ""}{field.help_text && <small>{field.help_text}</small>}</label>;
    }
    if (field.field_type === "select") {
      return <label key={field.key}>{field.label}{field.required ? " *" : ""}<select value={value == null ? "" : String(value)} onChange={(event) => setConfigValue(field, event.target.value || null)}><option value="">Select…</option>{options.map((option) => {
        const preset = voiceOptions.find((voice) => voice.id === option);
        return <option key={option} value={option}>{preset ? displayVoice(preset) : option}</option>;
      })}</select>{field.help_text && <small>{field.help_text}</small>}</label>;
    }
    if (field.field_type === "number") {
      return <label key={field.key}>{field.label}{field.required ? " *" : ""}<input type="number" value={value == null ? "" : String(value)} placeholder={field.placeholder || ""} onChange={(event) => setConfigValue(field, event.target.value === "" ? null : Number(event.target.value))} />{field.help_text && <small>{field.help_text}</small>}</label>;
    }
    return <label key={field.key}>{field.label}{field.required ? " *" : ""}<input value={value == null ? "" : String(value)} placeholder={field.placeholder || ""} onChange={(event) => setConfigValue(field, event.target.value)} />{field.help_text && <small>{field.help_text}</small>}</label>;
  }

  const materialRemoteAvailable = scenes?.material_transcription_remote_available ?? false;
  const recordingRemoteAvailable = scenes?.recording_evaluation_remote_available ?? false;

  return <div className="card settings-panel"><h2>Settings</h2><p className="muted">Credentials stay in the backend. A blank API-key edit retains the saved key.</p>
    <section className="provider-section provider-draft"><h3>Add provider</h3>
      <div className="form-grid">
        <label>Name<input value={draft.name} placeholder={selectedCatalog.label} onChange={(event) => setDraftValue("name", event.target.value)} /></label>
        <label>Capability<select value={draft.capability} onChange={(event) => selectCapability(event.target.value as ProviderCapability)}>{capabilities.map((capability) => <option key={capability} value={capability}>{capability.toUpperCase()}</option>)}</select></label>
        <label>Adapter<select value={catalogId(selectedCatalog)} onChange={(event) => selectAdapter(event.target.value)}>{adapters.map((entry) => <option key={catalogId(entry)} value={catalogId(entry)}>{entry.label}</option>)}</select></label>
        {selectedCatalog.endpoint_mode !== "none" && <label>{selectedCatalog.endpoint_mode === "full_endpoint" ? "Full endpoint" : "API base URL"}{selectedCatalog.required_fields.includes("base_url") ? " *" : ""}<input placeholder={selectedCatalog.endpoint_hint || ""} value={draft.base_url} onChange={(event) => setDraftValue("base_url", event.target.value)} /></label>}
        {selectedCatalog.required_fields.includes("api_key") && <label>API key *<input type="password" value={draft.api_key} onChange={(event) => setDraftValue("api_key", event.target.value)} /></label>}
        {selectedCatalog.required_fields.includes("model_name") && <label>Model / voice *<input value={draft.model_name} onChange={(event) => setDraftValue("model_name", event.target.value)} /></label>}
        {selectedConfigFields.map(renderConfigField)}
        {selectedCatalog.voice_presets?.length && !selectedConfigFields.some((field) => field.key === "default_voice") && <label>Default voice<select value={String(draft.extra_config.default_voice || "")} onChange={(event) => setConfigValue({ key: "default_voice", label: "Default voice", field_type: "select", required: false, options: [], default: null, placeholder: null, help_text: null }, event.target.value || null)}><option value="">No default voice</option>{selectedCatalog.voice_presets.map((voice) => <option key={voice.id} value={voice.id}>{displayVoice(voice)}</option>)}</select></label>}
      </div>
      <div className="catalog-summary"><span>Declared capabilities: {selectedCatalog.capabilities.length ? selectedCatalog.capabilities.join(", ") : "none"}.</span>{selectedCatalog.endpoint_hint && <span> Endpoint: {selectedCatalog.endpoint_hint}</span>}{selectedCatalog.docs_url && <a href={selectedCatalog.docs_url} target="_blank" rel="noreferrer">Adapter documentation</a>}</div>
      <div className="panel-actions"><button disabled={!isDraftComplete() || testingDraft} onClick={() => void testDraft()}>{testingDraft ? "Testing…" : "Test draft"}</button><button disabled={!isDraftComplete()} onClick={() => void add()}>Add provider</button></div>
      {draftTest && <p className={`provider-test ${draftTest.ok ? "success" : "error"}`}>Verification level: {draftTest.verification_level || "unspecified"}</p>}
    </section>
    {capabilities.map((capability) => {
      const capabilityProviders = providers.filter((provider) => provider.capability === capability);
      return <section key={capability} className="provider-section"><h3>{capability.toUpperCase()}</h3>{capabilityProviders.length ? capabilityProviders.map((provider) => <div className="provider-row" key={provider.id}><div className="provider-details"><span><strong>{provider.name}</strong> · {provider.model_name || "no model"} · {provider.base_url || "no URL"} · {provider.is_enabled ? "enabled" : "disabled"} · capabilities: {provider.capabilities.join(", ") || "none"}</span>{provider.capability === "tts" && providerVoices[provider.id] && <span className="provider-voices">Available voices: {providerVoices[provider.id].length ? providerVoices[provider.id].map(displayVoice).join(", ") : "none reported"}</span>}</div><div><button onClick={() => void setDefault(provider)} disabled={provider.is_default}>{provider.is_default ? "Default" : "Set default"}</button><button onClick={() => void edit(provider)}>Edit</button><button onClick={() => void updateProvider(provider.id, { is_enabled: !provider.is_enabled }).then(load).catch((error) => setMessage(error instanceof Error ? error.message : "Could not update provider."))}>{provider.is_enabled ? "Disable" : "Enable"}</button>{provider.capability === "tts" && <button onClick={() => void loadVoices(provider)} disabled={loadingVoices === provider.id}>{loadingVoices === provider.id ? "Loading voices…" : providerVoices[provider.id] ? "Hide voices" : "Show voices"}</button>}<button onClick={() => void testSaved(provider)}>Test</button><button onClick={() => void remove(provider.id)}>Delete</button></div></div>) : <p className="muted">No provider configured.</p>}</section>;
    })}
    <section className="provider-section"><h3>ASR scene routing</h3><label><input type="checkbox" checked={scenes?.material_transcription_use_local ?? true} disabled={!materialRemoteAvailable} onChange={(event) => void updateScene("material_transcription_use_local", event.target.checked)} /> Use Local Whisper for material transcription</label>{!materialRemoteAvailable && <p className="muted">{missingReason(scenes?.material_transcription_missing_capabilities ?? [])}</p>}<label><input type="checkbox" checked={scenes?.recording_evaluation_use_local ?? true} disabled={!recordingRemoteAvailable} onChange={(event) => void updateScene("recording_evaluation_use_local", event.target.checked)} /> Use Local Whisper for recording evaluation</label>{!recordingRemoteAvailable && <p className="muted">{missingReason(scenes?.recording_evaluation_missing_capabilities ?? [])}</p>}</section>
    {message && <p className="muted">{message}</p>}
  </div>;
}
