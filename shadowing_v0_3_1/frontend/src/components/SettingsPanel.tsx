import { useEffect, useState } from "react";
import { createProvider, deleteProvider, getASRSceneSettings, listProviders, testProvider, updateASRSceneSettings, updateProvider } from "../lib/api";
import type { AIProvider, ASRSceneSettings, ProviderCapability } from "../types";

const capabilities: ProviderCapability[] = ["llm", "tts", "asr"];

function missingReason(missing: string[]): string {
  return missing.length ? `Remote ASR unavailable: missing ${missing.join(", ")}.` : "Remote ASR is unavailable.";
}

export default function SettingsPanel() {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [scenes, setScenes] = useState<ASRSceneSettings | null>(null);
  const [message, setMessage] = useState("");
  const [draft, setDraft] = useState({ name: "", capability: "llm" as ProviderCapability, provider_type: "openai_compatible", base_url: "", api_key: "", model_name: "" });

  const load = async () => {
    try {
      const [nextProviders, nextScenes] = await Promise.all([listProviders(), getASRSceneSettings()]);
      setProviders(nextProviders); setScenes(nextScenes);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Settings failed to load."); }
  };
  useEffect(() => { void load(); }, []);

  async function add() {
    try {
      await createProvider({ ...draft, is_enabled: true, is_default: !providers.some((provider) => provider.capability === draft.capability && provider.is_default) });
      setDraft({ name: "", capability: "llm", provider_type: "openai_compatible", base_url: "", api_key: "", model_name: "" });
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not add provider."); }
  }
  async function test(id: number) {
    try {
      const result = await testProvider(id);
      setMessage(`${result.message} Capabilities: ${result.capabilities.join(", ") || "none"}.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Provider test failed."); }
  }
  async function setDefault(provider: AIProvider) { try { await updateProvider(provider.id, { is_default: true, is_enabled: true }); await load(); } catch (error) { setMessage(error instanceof Error ? error.message : "Could not set default."); } }
  async function edit(provider: AIProvider) { const base_url = window.prompt("Provider base URL", provider.base_url || ""); if (base_url === null) return; const model_name = window.prompt("Model name", provider.model_name || ""); if (model_name === null) return; const api_key = window.prompt("New API key (leave blank to retain saved key)", ""); if (api_key === null) return; try { await updateProvider(provider.id, { base_url, model_name, api_key: api_key || undefined }); await load(); } catch (error) { setMessage(error instanceof Error ? error.message : "Could not update provider."); } }
  async function remove(id: number) { if (!window.confirm("Delete this provider configuration?")) return; try { await deleteProvider(id); await load(); } catch (error) { setMessage(error instanceof Error ? error.message : "Could not delete provider."); } }
  async function updateScene(key: "material_transcription_use_local" | "recording_evaluation_use_local", value: boolean) { try { setScenes(await updateASRSceneSettings({ [key]: value })); } catch (error) { setMessage(error instanceof Error ? error.message : "Could not update ASR setting."); await load(); } }

  const materialRemoteAvailable = scenes?.material_transcription_remote_available ?? false;
  const recordingRemoteAvailable = scenes?.recording_evaluation_remote_available ?? false;
  return <div className="card settings-panel"><h2>Settings</h2><p className="muted">Credentials stay in the backend. A blank API-key edit retains the saved key.</p>
    <div className="form-grid"><label>Name<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><label>Capability<select value={draft.capability} onChange={(event) => setDraft({ ...draft, capability: event.target.value as ProviderCapability, provider_type: "openai_compatible" })}><option value="llm">LLM</option><option value="tts">TTS</option><option value="asr">ASR</option></select></label><label>Adapter<select value={draft.provider_type} onChange={(event) => setDraft({ ...draft, provider_type: event.target.value })}><option value="openai_compatible">OpenAI-compatible</option>{draft.capability !== "llm" && <option value="azure_speech">Azure Speech</option>}{draft.capability === "tts" && <option value="mimo_tts">MiMo TTS</option>}{draft.capability === "asr" && <option value="mimo_asr">MiMo ASR</option>}</select></label><label>Base URL<input placeholder={draft.provider_type === "mimo_tts" || draft.provider_type === "mimo_asr" ? "https://api.xiaomimimo.com/v1/chat/completions" : draft.capability === "tts" && draft.provider_type === "openai_compatible" ? "Full endpoint, e.g. https://…/audio/speech" : "https://…/v1"} value={draft.base_url} onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} /></label><label>API key<input type="password" value={draft.api_key} onChange={(event) => setDraft({ ...draft, api_key: event.target.value })} /></label><label>Model<input placeholder={draft.provider_type === "mimo_tts" ? "mimo-v2.5-tts" : draft.provider_type === "mimo_asr" ? "mimo-v2.5-asr" : ""} value={draft.model_name} onChange={(event) => setDraft({ ...draft, model_name: event.target.value })} /></label></div><button disabled={!draft.name || !draft.base_url || !draft.model_name} onClick={() => void add()}>Add provider</button>
    {capabilities.map((capability) => <section key={capability} className="provider-section"><h3>{capability.toUpperCase()}</h3>{providers.filter((provider) => provider.capability === capability).map((provider) => <div className="provider-row" key={provider.id}><span><strong>{provider.name}</strong> · {provider.model_name || "no model"} · {provider.base_url || "no URL"} · {provider.is_enabled ? "enabled" : "disabled"} · capabilities: {provider.capabilities.join(", ") || "none"}</span><div><button onClick={() => void setDefault(provider)} disabled={provider.is_default}> {provider.is_default ? "Default" : "Set default"}</button><button onClick={() => void edit(provider)}>Edit</button><button onClick={() => void updateProvider(provider.id, { is_enabled: !provider.is_enabled }).then(load).catch((error) => setMessage(error instanceof Error ? error.message : "Could not update provider."))}>{provider.is_enabled ? "Disable" : "Enable"}</button><button onClick={() => void test(provider.id)}>Test</button><button onClick={() => void remove(provider.id)}>Delete</button></div></div>) || <p className="muted">No provider configured.</p>}</section>)}
    <section className="provider-section"><h3>ASR scene routing</h3><label><input type="checkbox" checked={scenes?.material_transcription_use_local ?? true} disabled={!materialRemoteAvailable} onChange={(event) => void updateScene("material_transcription_use_local", event.target.checked)} /> Use Local Whisper for material transcription</label>{!materialRemoteAvailable && <p className="muted">{missingReason(scenes?.material_transcription_missing_capabilities ?? [])}</p>}<label><input type="checkbox" checked={scenes?.recording_evaluation_use_local ?? true} disabled={!recordingRemoteAvailable} onChange={(event) => void updateScene("recording_evaluation_use_local", event.target.checked)} /> Use Local Whisper for recording evaluation</label>{!recordingRemoteAvailable && <p className="muted">{missingReason(scenes?.recording_evaluation_missing_capabilities ?? [])}</p>}</section>{message && <p className="muted">{message}</p>}</div>;
}
