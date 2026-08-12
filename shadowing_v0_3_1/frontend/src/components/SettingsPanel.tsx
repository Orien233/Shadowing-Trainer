import { useEffect, useMemo, useState } from "react";
import {
  createProvider,
  deleteProvider,
  getASRSceneSettings,
  getLocalASRStatus,
  listProviderCatalog,
  listProviderVoices,
  listProviders,
  releaseLocalASR,
  testLocalASR,
  testProvider,
  testProviderDraft,
  updateASRSceneSettings,
  updateProvider,
} from "../lib/api";
import type {
  AIProvider,
  ASRSceneSettings,
  ASRSceneSettingsUpdate,
  LocalASRStatus,
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
  enabled_capabilities: string[];
  enabled_formats: string[];
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
    key: "openai_audio_asr", label: "OpenAI Audio Transcription", kind: "asr",
    capabilities: ["transcribe", "word_timestamps"], endpoint_mode: "base_url",
    endpoint_hint: "https://api.openai.com/v1", required_fields: ["base_url", "api_key", "model_name"],
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
  const preset = entry.preset_defaults || {};
  return {
    name: name || entry.label,
    capability: entry.kind,
    provider_type: entry.key,
    base_url: typeof preset.base_url === "string" ? preset.base_url : "",
    api_key: "",
    model_name: "",
    extra_config: configDefaults(entry),
    enabled_capabilities: Array.isArray(preset.enabled_capabilities) ? preset.enabled_capabilities.filter((item): item is string => typeof item === "string") : [...(entry.available_capabilities || entry.capabilities)],
    enabled_formats: Array.isArray(preset.enabled_formats) ? preset.enabled_formats.filter((item): item is string => typeof item === "string") : entry.kind === "llm" ? ["response_format"] : entry.kind === "tts" ? (entry.available_formats?.includes("wav") ? ["wav"] : entry.available_formats?.slice(0, 1) || []) : [],
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
  const billing = result.billable ? " This test may be billable." : "";
  return `${result.ok ? "Test passed." : "Test failed."} ${result.message}${verification}${providerCapabilities}${billing}`;
}

function localASRSummary(status: LocalASRStatus | null): string {
  if (!status) return "Local Whisper environment status could not be loaded.";
  if (!status.runtime_ready) return status.error || "Local Whisper is unavailable.";
  if (status.model_loaded) return `Ready: ${status.model_name} is loaded on ${status.device}.`;
  if (status.model_cached) return `Ready: ${status.model_name} is cached and will load on first use.`;
  if (status.will_download_on_first_use) return `Ready: ${status.model_name} will download on first use.`;
  return `Ready: ${status.model_name} will load on first use.`;
}

export default function SettingsPanel() {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [catalog, setCatalog] = useState<ProviderCatalogEntry[]>(FALLBACK_CATALOG);
  const [scenes, setScenes] = useState<ASRSceneSettings | null>(null);
  const [localASR, setLocalASR] = useState<LocalASRStatus | null>(null);
  const [message, setMessage] = useState("");
  const [draftTest, setDraftTest] = useState<ProviderTestResponse | null>(null);
  const [testingDraft, setTestingDraft] = useState(false);
  const [checkingLocalASR, setCheckingLocalASR] = useState(false);
  const [providerVoices, setProviderVoices] = useState<Record<number, ProviderVoice[]>>({});
  const [loadingVoices, setLoadingVoices] = useState<number | null>(null);
  const [draft, setDraft] = useState<ProviderDraft>(() => newDraft(FALLBACK_CATALOG[0]));
  const [editingProviderId, setEditingProviderId] = useState<number | null>(null);

  const adapters = useMemo(() => catalog.filter((entry) => entry.kind === draft.capability), [catalog, draft.capability]);
  const selectedCatalog = useMemo(
    () => adapters.find((entry) => entry.key === draft.provider_type) || adapters[0] || FALLBACK_CATALOG[0],
    [adapters, draft.provider_type],
  );
  const selectedConfigFields = selectedCatalog.config_fields || [];

  const load = async () => {
    try {
      const [nextProviders, nextScenes, nextCatalog, nextLocalASR] = await Promise.all([
        listProviders(),
        getASRSceneSettings(),
        listProviderCatalog().catch(() => []),
        getLocalASRStatus().catch(() => null),
      ]);
      const usableCatalog = nextCatalog.length ? nextCatalog : FALLBACK_CATALOG;
      setProviders(nextProviders);
      setScenes(nextScenes);
      setCatalog(usableCatalog);
      setLocalASR(nextLocalASR);
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
    setEditingProviderId(null);
    setDraftTest(null);
  }

  function selectAdapter(id: string) {
    const entry = adapters.find((item) => catalogId(item) === id);
    if (!entry) return;
    setDraft(newDraft(entry, draft.name));
    setEditingProviderId(null);
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
      enabled_capabilities: draft.enabled_capabilities,
      enabled_formats: draft.enabled_formats,
    };
  }

  function isDraftComplete(): boolean {
    return hasValue(draft.name) && selectedCatalog.required_fields.every((field) => {
      if (field === "base_url") return hasValue(draft.base_url);
      if (field === "api_key") return hasValue(draft.api_key);
      if (field === "model_name") return hasValue(draft.model_name);
      return hasValue(draft.extra_config[field]);
    }) && selectedConfigFields.filter((field) => field.required && !standardFields.has(field.key)).every((field) => hasValue(draft.extra_config[field.key])) && draft.enabled_capabilities.length > 0 && !(draft.capability === "tts" && draft.enabled_capabilities.includes("synthesize") && draft.enabled_formats.length === 0) && !(draft.capability === "llm" && draft.enabled_capabilities.includes("generate_json") && draft.enabled_formats.length === 0) && !(draft.enabled_capabilities.includes("word_timestamps") && !draft.enabled_capabilities.includes("transcribe"));
  }

  async function saveConfiguration() {
    try {
      const payload = draftPayload();
      if (editingProviderId !== null) {
        await updateProvider(editingProviderId, { ...payload, api_key: payload.api_key || undefined });
      } else {
        await createProvider({ ...payload, is_enabled: true, is_default: !providers.some((provider) => provider.capability === draft.capability && provider.is_default) });
      }
      setDraft(newDraft(catalog.find((entry) => entry.kind === "llm") || FALLBACK_CATALOG[0]));
      setEditingProviderId(null);
      setDraftTest(null);
      setMessage(editingProviderId !== null ? "Provider configuration updated." : "Provider configuration saved.");
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

  async function testSaved(provider: AIProvider, mode: "configuration" | "network" | "inference" = "configuration") {
    if (mode === "inference" && !window.confirm("This sends a small live provider request and may incur charges. Continue?")) return;
    try {
      const result = await testProvider(provider.id, { test_mode: mode });
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

  function edit(provider: AIProvider) {
    const entry = catalog.find((item) => item.kind === provider.capability && item.key === provider.provider_type);
    if (!entry || provider.is_deprecated) return;
    setDraft({
      name: provider.name, capability: provider.capability, provider_type: provider.provider_type,
      base_url: provider.base_url || "", api_key: "", model_name: provider.model_name || "",
      extra_config: Object.fromEntries(Object.entries(provider.extra_config).filter(([, value]) => typeof value === "string" || typeof value === "number" || typeof value === "boolean" || value === null)) as ProviderDraft["extra_config"],
      enabled_capabilities: provider.enabled_capabilities || provider.capabilities,
      enabled_formats: provider.enabled_formats || [],
    });
    setEditingProviderId(provider.id);
    setDraftTest(null);
    setMessage(`Editing ${provider.name}. Leave API key blank to retain it.`);
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

  async function checkLocalASR(loadModel = false) {
    if (loadModel && !window.confirm("Loading Local Whisper can download the configured model and use significant memory. Continue?")) return;
    setCheckingLocalASR(true);
    try {
      const status = await testLocalASR(loadModel);
      setLocalASR(status);
      setMessage(localASRSummary(status));
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Local Whisper check failed.");
    } finally {
      setCheckingLocalASR(false);
    }
  }

  async function releaseLocalASRModel() {
    setCheckingLocalASR(true);
    try {
      const status = await releaseLocalASR();
      setLocalASR(status);
      setMessage("Local Whisper model was released from memory.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not release Local Whisper.");
    } finally {
      setCheckingLocalASR(false);
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

  function toggleBoundary(key: "enabled_capabilities" | "enabled_formats", value: string, checked: boolean) {
    setDraft((current) => {
      let next = checked ? [...new Set([...current[key], value])] : current[key].filter((item) => item !== value);
      if (key === "enabled_capabilities" && value === "word_timestamps" && checked) next = [...new Set([...next, "transcribe"])];
      return { ...current, [key]: next };
    });
    setDraftTest(null);
  }

  const materialRemoteAvailable = scenes?.material_transcription_remote_available ?? false;
  const recordingRemoteAvailable = scenes?.recording_evaluation_remote_available ?? false;
  const materialLocalAvailable = scenes?.material_transcription_local_available ?? true;
  const recordingLocalAvailable = scenes?.recording_evaluation_local_available ?? true;

  return <div className="card settings-panel"><h2>Settings</h2><p className="muted">Credentials stay in the backend. A blank API-key edit retains the saved key.</p>
    <section className="provider-section"><h3>Quick templates</h3><p className="muted">OpenAI and MiMo templates are built in and cannot be edited or deleted. Using one only pre-fills a new configuration; it does not save credentials.</p><div className="panel-actions">{catalog.filter((entry) => entry.preset !== false).map((entry) => <button key={catalogId(entry)} onClick={() => { setDraft(newDraft(entry)); setEditingProviderId(null); setDraftTest(null); }}>{entry.label}</button>)}</div></section>
    <section className="provider-section provider-draft"><h3>{editingProviderId === null ? "New provider configuration" : "Edit provider configuration"}</h3>
      <div className="form-grid">
        <label>Name<input value={draft.name} placeholder={selectedCatalog.label} onChange={(event) => setDraftValue("name", event.target.value)} /></label>
        <label>Capability<select value={draft.capability} onChange={(event) => selectCapability(event.target.value as ProviderCapability)}>{capabilities.map((capability) => <option key={capability} value={capability}>{capability.toUpperCase()}</option>)}</select></label>
        <label>Adapter<select value={catalogId(selectedCatalog)} onChange={(event) => selectAdapter(event.target.value)}>{adapters.map((entry) => <option key={catalogId(entry)} value={catalogId(entry)}>{entry.label}</option>)}</select></label>
        {selectedCatalog.endpoint_mode !== "none" && <label>{selectedCatalog.endpoint_mode === "full_endpoint" ? "Full endpoint" : "API base URL"}{selectedCatalog.required_fields.includes("base_url") ? " *" : ""}<input placeholder={selectedCatalog.endpoint_hint || ""} value={draft.base_url} onChange={(event) => setDraftValue("base_url", event.target.value)} /></label>}
        {selectedCatalog.required_fields.includes("api_key") && <label>API key *<input type="password" value={draft.api_key} onChange={(event) => setDraftValue("api_key", event.target.value)} /></label>}
        {selectedCatalog.required_fields.includes("model_name") && <label>Model / voice *<input value={draft.model_name} onChange={(event) => setDraftValue("model_name", event.target.value)} /></label>}
        {selectedConfigFields.map(renderConfigField)}
        <div className="boundary-options"><strong>Enabled capabilities</strong>{(selectedCatalog.available_capabilities || selectedCatalog.capabilities).map((item) => <label key={item} className="config-checkbox"><input type="checkbox" checked={draft.enabled_capabilities.includes(item)} onChange={(event) => toggleBoundary("enabled_capabilities", item, event.target.checked)} /> {item}</label>)}</div>
        {(selectedCatalog.available_formats || []).length > 0 && <div className="boundary-options"><strong>{draft.capability === "llm" ? "JSON output methods" : "Enabled output formats"}</strong>{(selectedCatalog.available_formats || []).map((item) => <label key={item} className="config-checkbox"><input type="checkbox" checked={draft.enabled_formats.includes(item)} onChange={(event) => toggleBoundary("enabled_formats", item, event.target.checked)} /> {item}</label>)}</div>}
        {selectedCatalog.voice_presets?.length && !selectedConfigFields.some((field) => field.key === "default_voice") && <label>Default voice<select value={String(draft.extra_config.default_voice || "")} onChange={(event) => setConfigValue({ key: "default_voice", label: "Default voice", field_type: "select", required: false, options: [], default: null, placeholder: null, help_text: null }, event.target.value || null)}><option value="">No default voice</option>{selectedCatalog.voice_presets.map((voice) => <option key={voice.id} value={voice.id}>{displayVoice(voice)}</option>)}</select></label>}
      </div>
      <div className="catalog-summary"><span>Protocol allows: {(selectedCatalog.available_capabilities || selectedCatalog.capabilities).join(", ") || "none"}. Checked boundaries are enforced by the backend.</span>{selectedCatalog.endpoint_hint && <span> Endpoint: {selectedCatalog.endpoint_hint}</span>}{selectedCatalog.docs_url && <a href={selectedCatalog.docs_url} target="_blank" rel="noreferrer">Adapter documentation</a>}</div>
      <div className="panel-actions"><button disabled={!isDraftComplete() || testingDraft} onClick={() => void testDraft()}>{testingDraft ? "Testing…" : "Test draft"}</button><button disabled={!isDraftComplete()} onClick={() => void saveConfiguration()}>{editingProviderId === null ? "Save configuration" : "Save changes"}</button>{editingProviderId !== null && <button onClick={() => { setEditingProviderId(null); setDraft(newDraft(catalog[0] || FALLBACK_CATALOG[0])); }}>Cancel edit</button>}</div>
      {draftTest && <p className={`provider-test ${draftTest.ok ? "success" : "error"}`}>Verification level: {draftTest.verification_level || "unspecified"}{draftTest.billable ? " · may incur charges" : ""}</p>}
    </section>
    {capabilities.map((capability) => {
      const capabilityProviders = providers.filter((provider) => provider.capability === capability);
      return <section key={capability} className="provider-section"><h3>{capability.toUpperCase()}</h3>{capabilityProviders.length ? capabilityProviders.map((provider) => <div className="provider-row" key={provider.id}><div className="provider-details"><span><strong>{provider.name}</strong> · {provider.model_name || "no model"} · {provider.base_url || "no URL"} · {provider.is_enabled ? "enabled" : "disabled"} · capabilities: {provider.capabilities.join(", ") || "none"}</span>{provider.capability === "tts" && providerVoices[provider.id] && <span className="provider-voices">Available voices: {providerVoices[provider.id].length ? providerVoices[provider.id].map(displayVoice).join(", ") : "none reported"}</span>}</div><div><button onClick={() => void setDefault(provider)} disabled={provider.is_default}>{provider.is_default ? "Default" : "Set default"}</button><button onClick={() => void edit(provider)}>Edit</button><button onClick={() => void updateProvider(provider.id, { is_enabled: !provider.is_enabled }).then(load).catch((error) => setMessage(error instanceof Error ? error.message : "Could not update provider."))}>{provider.is_enabled ? "Disable" : "Enable"}</button>{provider.capability === "tts" && <button onClick={() => void loadVoices(provider)} disabled={loadingVoices === provider.id}>{loadingVoices === provider.id ? "Loading voices…" : providerVoices[provider.id] ? "Hide voices" : "Show voices"}</button>}<button onClick={() => void testSaved(provider)}>Check configuration</button><button onClick={() => void testSaved(provider, "network")}>{provider.capability === "llm" ? "Verify connection" : "Verify adapter"}</button><button className="provider-live-test" onClick={() => void testSaved(provider, "inference")}>Run paid test</button><button onClick={() => void remove(provider.id)}>Delete</button></div></div>) : <p className="muted">No provider configured.</p>}</section>;
    })}
    <section className="provider-section"><h3>Local Whisper runtime</h3><p className={localASR?.runtime_ready ? "muted" : "provider-test error"}>{localASRSummary(localASR)}</p>{localASR && <p className="muted">Model: {localASR.model_name} · {localASR.device} · {localASR.compute_type} · {localASR.model_cached ? "cached" : "not cached"}</p>}<div className="panel-actions"><button disabled={checkingLocalASR} onClick={() => void checkLocalASR()}>{checkingLocalASR ? "Checking…" : "Check environment"}</button>{localASR?.runtime_ready && !localASR.model_loaded && <button disabled={checkingLocalASR} onClick={() => void checkLocalASR(true)}>Load model</button>}{localASR?.model_loaded && <button disabled={checkingLocalASR} onClick={() => void releaseLocalASRModel()}>Release model memory</button>}</div>{!localASR?.installed && <p className="muted">Install it when local ASR is needed: <code>pip install -r requirements-local-whisper.txt</code></p>}</section>
    <section className="provider-section"><h3>ASR scene routing</h3><label><input type="checkbox" checked={scenes?.material_transcription_use_local ?? true} disabled={!materialRemoteAvailable || !materialLocalAvailable} onChange={(event) => void updateScene("material_transcription_use_local", event.target.checked)} /> Use Local Whisper for material transcription</label><p className="muted">Effective route: {scenes?.material_transcription_effective_route || (scenes?.material_transcription_use_local ? "local" : "remote")}.{!materialLocalAvailable ? ` Local Whisper unavailable: ${scenes?.material_transcription_local_unavailable_reason || "not installed"}.` : ""}{!materialRemoteAvailable ? ` ${missingReason(scenes?.material_transcription_missing_capabilities ?? [])}` : ""}</p><label><input type="checkbox" checked={scenes?.recording_evaluation_use_local ?? true} disabled={!recordingRemoteAvailable || !recordingLocalAvailable} onChange={(event) => void updateScene("recording_evaluation_use_local", event.target.checked)} /> Use Local Whisper for recording evaluation</label><p className="muted">Effective route: {scenes?.recording_evaluation_effective_route || (scenes?.recording_evaluation_use_local ? "local" : "remote")}.{!recordingLocalAvailable ? ` Local Whisper unavailable: ${scenes?.recording_evaluation_local_unavailable_reason || "not installed"}.` : ""}{!recordingRemoteAvailable ? ` ${missingReason(scenes?.recording_evaluation_missing_capabilities ?? [])}` : ""}</p></section>
    {message && <p className="muted">{message}</p>}
  </div>;
}
