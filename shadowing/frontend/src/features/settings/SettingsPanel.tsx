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
} from "../../lib/api";
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
} from "../../types";
import { useLanguage } from "../../i18n/LanguageContext";

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

function catalogId(entry: ProviderCatalogEntry): string {
  return `${entry.kind}:${entry.key}`;
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

export default function SettingsPanel({ onProvidersChanged }: { onProvidersChanged?: () => void }) {
  const { t } = useLanguage();
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [catalog, setCatalog] = useState<ProviderCatalogEntry[]>([]);
  const [scenes, setScenes] = useState<ASRSceneSettings | null>(null);
  const [localASR, setLocalASR] = useState<LocalASRStatus | null>(null);
  const [message, setMessage] = useState("");
  const [draftTest, setDraftTest] = useState<ProviderTestResponse | null>(null);
  const [testingDraft, setTestingDraft] = useState(false);
  const [checkingLocalASR, setCheckingLocalASR] = useState(false);
  const [providerVoices, setProviderVoices] = useState<Record<number, ProviderVoice[]>>({});
  const [loadingVoices, setLoadingVoices] = useState<number | null>(null);
  const [draft, setDraft] = useState<ProviderDraft>({ name: "", capability: "llm", provider_type: "", base_url: "", api_key: "", model_name: "", extra_config: {}, enabled_capabilities: [], enabled_formats: [] });
  const [editingProviderId, setEditingProviderId] = useState<number | null>(null);

  const adapters = useMemo(() => catalog.filter((entry) => entry.kind === draft.capability), [catalog, draft.capability]);
  const selectedCatalog = useMemo(
    () => adapters.find((entry) => entry.key === draft.provider_type) || adapters[0] || null,
    [adapters, draft.provider_type],
  );
  const selectedConfigFields = selectedCatalog?.config_fields || [];
  const capabilityLabel = (value: string) => t(`settings.capability.${value}`) === `settings.capability.${value}` ? value.toUpperCase() : t(`settings.capability.${value}`);
  const adapterLabel = (entry: ProviderCatalogEntry) => t(`settings.adapter.${entry.kind}.${entry.key}`) === `settings.adapter.${entry.kind}.${entry.key}` ? entry.label : t(`settings.adapter.${entry.kind}.${entry.key}`);
  const formatLabel = (value: string) => t(`settings.format.${value}`) === `settings.format.${value}` ? value : t(`settings.format.${value}`);
  const capabilityValueLabel = (value: string) => t(`settings.capabilityValue.${value}`) === `settings.capabilityValue.${value}` ? value : t(`settings.capabilityValue.${value}`);
  const configFieldLabel = (field: ProviderConfigField) => {
    const key = `settings.configField.${field.key}.label`;
    const translated = t(key);
    return translated === key ? field.label : translated;
  };
  const configFieldHelp = (field: ProviderConfigField) => {
    if (!field.help_text) return null;
    const key = `settings.configField.${field.key}.help`;
    const translated = t(key);
    return translated === key ? field.help_text : translated;
  };
  const missingReason = (missing: string[]) => missing.length ? t("settings.remoteMissing", { values: missing.map(capabilityValueLabel).join(", ") }) : t("settings.remoteUnavailable");
  const testSummary = (result: ProviderTestResponse) => `${result.ok ? t("settings.testPassed") : t("settings.testFailedStatus")} ${result.message}${result.verification_level ? ` ${t("settings.verification", { value: result.verification_level })}` : ""}${result.capabilities.length ? ` ${t("settings.testCapabilities", { values: result.capabilities.map(capabilityValueLabel).join(", ") })}` : ""}${result.billable ? ` ${t("settings.testBillable")}` : ""}`;
  const localASRSummary = (status: LocalASRStatus | null) => {
    if (!status) return t("settings.localStatusUnavailable");
    if (!status.runtime_ready) return status.error || t("settings.localUnavailableGeneric");
    if (status.model_loaded) return t("settings.localReadyLoaded", { model: status.model_name, device: status.device });
    if (status.model_cached) return t("settings.localReadyCached", { model: status.model_name });
    if (status.will_download_on_first_use) return t("settings.localReadyDownload", { model: status.model_name });
    return t("settings.localReady", { model: status.model_name });
  };

  const load = async () => {
    try {
      const [nextProviders, nextScenes, nextCatalog, nextLocalASR] = await Promise.all([
        listProviders(),
        getASRSceneSettings(),
        listProviderCatalog(),
        getLocalASRStatus().catch(() => null),
      ]);
      setProviders(nextProviders);
      setScenes(nextScenes);
      setCatalog(nextCatalog);
      setLocalASR(nextLocalASR);
      setDraft((current) => {
        const currentEntry = nextCatalog.find((entry) => entry.kind === current.capability && entry.key === current.provider_type);
        return currentEntry ? current : nextCatalog[0] ? newDraft(nextCatalog[0], current.name) : current;
      });
    } catch (error) {
      setCatalog([]);
      setMessage(error instanceof Error ? `${error.message} ${t("settings.retryConnection")}` : t("settings.loadFailed"));
    }
  };

  useEffect(() => { void load(); }, []);

  if (!selectedCatalog) {
    return <div className="card settings-panel"><h2>{t("settings.title")}</h2><p className="provider-test error">{message || t("settings.catalogUnavailable")}</p><button onClick={() => void load()}>{t("settings.retry")}</button></div>;
  }

  function setDraftValue<K extends keyof ProviderDraft>(key: K, value: ProviderDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setDraftTest(null);
  }

  function selectCapability(capability: ProviderCapability) {
    const entry = catalog.find((item) => item.kind === capability);
    if (!entry) return;
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
      const defaultEntry = catalog.find((entry) => entry.kind === "llm") || catalog[0];
      if (defaultEntry) setDraft(newDraft(defaultEntry));
      setEditingProviderId(null);
      setDraftTest(null);
      setMessage(editingProviderId !== null ? t("settings.updated") : t("settings.saved"));
      onProvidersChanged?.();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("settings.addFailed"));
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
      setMessage(error instanceof Error ? error.message : t("settings.testFailed"));
    } finally {
      setTestingDraft(false);
    }
  }

  async function testSaved(provider: AIProvider, mode: "configuration" | "network" | "inference" = "configuration") {
    if (mode === "inference" && !window.confirm(t("settings.paidConfirm"))) return;
    try {
      const result = await testProvider(provider.id, { test_mode: mode });
      setMessage(testSummary(result));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("settings.testFailed"));
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
      setMessage(error instanceof Error ? error.message : t("settings.voiceLoadFailed"));
    } finally {
      setLoadingVoices(null);
    }
  }

  async function setDefault(provider: AIProvider) {
    try {
      await updateProvider(provider.id, { is_default: true, is_enabled: true });
      onProvidersChanged?.();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("settings.defaultFailed"));
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
    setMessage(t("settings.editing", { name: provider.name }));
  }

  async function remove(id: number) {
    if (!window.confirm(t("settings.deleteConfirm"))) return;
    try {
      await deleteProvider(id);
      setProviderVoices((current) => {
        const next = { ...current };
        delete next[id];
        return next;
      });
      onProvidersChanged?.();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("settings.deleteFailed"));
    }
  }

  async function toggleProviderEnabled(provider: AIProvider) {
    try {
      await updateProvider(provider.id, { is_enabled: !provider.is_enabled });
      onProvidersChanged?.();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("settings.updateFailed"));
    }
  }

  async function updateScene(key: keyof ASRSceneSettingsUpdate, value: boolean) {
    const payload: ASRSceneSettingsUpdate = key === "material_transcription_use_local"
      ? { material_transcription_use_local: value }
      : { recording_evaluation_use_local: value };
    try {
      setScenes(await updateASRSceneSettings(payload));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("settings.asrUpdateFailed"));
      await load();
    }
  }

  async function checkLocalASR(loadModel = false) {
    if (loadModel && !window.confirm(t("settings.loadModelConfirm"))) return;
    setCheckingLocalASR(true);
    try {
      const status = await testLocalASR(loadModel);
      setLocalASR(status);
      setMessage(localASRSummary(status));
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("settings.localCheckFailed"));
    } finally {
      setCheckingLocalASR(false);
    }
  }

  async function releaseLocalASRModel() {
    setCheckingLocalASR(true);
    try {
      const status = await releaseLocalASR();
      setLocalASR(status);
      setMessage(t("settings.localReleased"));
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("settings.localReleaseFailed"));
    } finally {
      setCheckingLocalASR(false);
    }
  }

  function renderConfigField(field: ProviderConfigField) {
    const value = draft.extra_config[field.key];
    const label = configFieldLabel(field);
    const help = configFieldHelp(field);
    const voiceOptions = field.key === "default_voice" ? selectedCatalog.voice_presets || [] : [];
    const options = [...new Set([...(field.options || []), ...voiceOptions.map((voice) => voice.id)])];
    if (field.field_type === "boolean") {
      return <label key={field.key} className="config-checkbox"><input type="checkbox" checked={Boolean(value)} onChange={(event) => setConfigValue(field, event.target.checked)} /> {label}{field.required ? " *" : ""}{help && <small>{help}</small>}</label>;
    }
    if (field.field_type === "select") {
      return <label key={field.key}>{label}{field.required ? " *" : ""}<select value={value == null ? "" : String(value)} onChange={(event) => setConfigValue(field, event.target.value || null)}><option value="">{t("settings.select")}</option>{options.map((option) => {
        const preset = voiceOptions.find((voice) => voice.id === option);
        return <option key={option} value={option}>{preset ? displayVoice(preset) : option}</option>;
      })}</select>{help && <small>{help}</small>}</label>;
    }
    if (field.field_type === "number") {
      return <label key={field.key}>{label}{field.required ? " *" : ""}<input type="number" value={value == null ? "" : String(value)} placeholder={field.placeholder || ""} onChange={(event) => setConfigValue(field, event.target.value === "" ? null : Number(event.target.value))} />{help && <small>{help}</small>}</label>;
    }
    return <label key={field.key}>{label}{field.required ? " *" : ""}<input value={value == null ? "" : String(value)} placeholder={field.placeholder || ""} onChange={(event) => setConfigValue(field, event.target.value)} />{help && <small>{help}</small>}</label>;
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

  const routeSummary = (route: string, localAvailable: boolean, reason: string | null | undefined, remoteAvailable: boolean, missing: string[]) => <>{t("settings.route", { route: t(`settings.route.${route}`) === `settings.route.${route}` ? route : t(`settings.route.${route}`) })}{!localAvailable ? ` ${t("settings.localUnavailable", { reason: reason || t("settings.notInstalled") })}` : ""}{!remoteAvailable ? ` ${missingReason(missing)}` : ""}</>;
  return <div className="card settings-panel"><h2>{t("settings.title")}</h2><p className="muted">{t("settings.credentialsHint")}</p>
    <section className="provider-section"><h3>{t("settings.quickTemplates")}</h3><p className="muted">{t("settings.templatesHint")}</p><div className="panel-actions">{catalog.filter((entry) => entry.preset !== false).map((entry) => <button key={catalogId(entry)} onClick={() => { setDraft(newDraft(entry)); setEditingProviderId(null); setDraftTest(null); }}>{adapterLabel(entry)}</button>)}</div></section>
    <section className="provider-section provider-draft"><h3>{editingProviderId === null ? t("settings.newProvider") : t("settings.editProvider")}</h3><div className="form-grid">
      <label>{t("settings.name")}<input value={draft.name} placeholder={adapterLabel(selectedCatalog)} onChange={(event) => setDraftValue("name", event.target.value)} /></label><label>{t("settings.capability")}<select value={draft.capability} onChange={(event) => selectCapability(event.target.value as ProviderCapability)}>{capabilities.map((capability) => <option key={capability} value={capability}>{capabilityLabel(capability)}</option>)}</select></label><label>{t("settings.adapter")}<select value={catalogId(selectedCatalog)} onChange={(event) => selectAdapter(event.target.value)}>{adapters.map((entry) => <option key={catalogId(entry)} value={catalogId(entry)}>{adapterLabel(entry)}</option>)}</select></label>
      {selectedCatalog.endpoint_mode !== "none" && <label>{selectedCatalog.endpoint_mode === "full_endpoint" ? t("settings.fullEndpoint") : t("settings.apiBaseUrl")}{selectedCatalog.required_fields.includes("base_url") ? " *" : ""}<input placeholder={selectedCatalog.endpoint_hint || ""} value={draft.base_url} onChange={(event) => setDraftValue("base_url", event.target.value)} /></label>}{selectedCatalog.required_fields.includes("api_key") && <label>{t("settings.apiKey")} *<input type="password" value={draft.api_key} onChange={(event) => setDraftValue("api_key", event.target.value)} /></label>}{selectedCatalog.required_fields.includes("model_name") && <label>{t("settings.modelVoice")} *<input value={draft.model_name} onChange={(event) => setDraftValue("model_name", event.target.value)} /></label>}{selectedConfigFields.map(renderConfigField)}
      <div className="boundary-options"><strong>{t("settings.enabledCapabilities")}</strong>{(selectedCatalog.available_capabilities || selectedCatalog.capabilities).map((item) => <label key={item} className="config-checkbox"><input type="checkbox" checked={draft.enabled_capabilities.includes(item)} onChange={(event) => toggleBoundary("enabled_capabilities", item, event.target.checked)} /> {capabilityValueLabel(item)}</label>)}</div>{(selectedCatalog.available_formats || []).length > 0 && <div className="boundary-options"><strong>{draft.capability === "llm" ? t("settings.jsonFormats") : t("settings.enabledFormats")}</strong>{(selectedCatalog.available_formats || []).map((item) => <label key={item} className="config-checkbox"><input type="checkbox" checked={draft.enabled_formats.includes(item)} onChange={(event) => toggleBoundary("enabled_formats", item, event.target.checked)} /> {formatLabel(item)}</label>)}</div>}
      {selectedCatalog.voice_presets?.length && !selectedConfigFields.some((field) => field.key === "default_voice") && <label>{t("settings.defaultVoice")}<select value={String(draft.extra_config.default_voice || "")} onChange={(event) => setConfigValue({ key: "default_voice", label: "Default voice", field_type: "select", required: false, options: [], default: null, placeholder: null, help_text: null }, event.target.value || null)}><option value="">{t("settings.noDefaultVoice")}</option>{selectedCatalog.voice_presets.map((voice) => <option key={voice.id} value={voice.id}>{displayVoice(voice)}</option>)}</select></label>}</div>
      <div className="catalog-summary"><span>{t("settings.protocolAllows", { values: (selectedCatalog.available_capabilities || selectedCatalog.capabilities).map(capabilityValueLabel).join(", ") || t("settings.none") })}</span>{selectedCatalog.endpoint_hint && <span> {t("settings.endpoint", { value: selectedCatalog.endpoint_hint })}</span>}{selectedCatalog.docs_url && <a href={selectedCatalog.docs_url} target="_blank" rel="noreferrer">{t("settings.adapterDocs")}</a>}</div><div className="panel-actions"><button disabled={!isDraftComplete() || testingDraft} onClick={() => void testDraft()}>{testingDraft ? t("settings.testing") : t("settings.testDraft")}</button><button disabled={!isDraftComplete()} onClick={() => void saveConfiguration()}>{editingProviderId === null ? t("settings.saveConfiguration") : t("settings.saveChanges")}</button>{editingProviderId !== null && <button onClick={() => { setEditingProviderId(null); const entry = catalog[0]; if (entry) setDraft(newDraft(entry)); }}>{t("settings.cancelEdit")}</button>}</div>{draftTest && <p className={`provider-test ${draftTest.ok ? "success" : "error"}`}>{t("settings.verificationLevel", { value: draftTest.verification_level || t("settings.unspecified") })}{draftTest.billable ? ` · ${t("settings.mayCharge")}` : ""}</p>}</section>
    {capabilities.map((capability) => { const capabilityProviders = providers.filter((provider) => provider.capability === capability); return <section key={capability} className="provider-section"><h3>{capabilityLabel(capability)}</h3>{capabilityProviders.length ? capabilityProviders.map((provider) => <div className="provider-row" key={provider.id}><div className="provider-details"><span><strong>{provider.name}</strong> · {provider.model_name || t("settings.noModel")} · {provider.base_url || t("settings.noUrl")} · {provider.is_enabled ? t("settings.enabled") : t("settings.disabled")} · {t("settings.capabilities", { values: provider.capabilities.map(capabilityValueLabel).join(", ") || t("settings.none") })}</span>{provider.capability === "tts" && providerVoices[provider.id] && <span className="provider-voices">{t("settings.availableVoices", { values: providerVoices[provider.id].length ? providerVoices[provider.id].map(displayVoice).join(", ") : t("settings.noneReported") })}</span>}</div><div><button onClick={() => void setDefault(provider)} disabled={provider.is_default}>{provider.is_default ? t("settings.default") : t("settings.setDefault")}</button><button onClick={() => void edit(provider)}>{t("settings.edit")}</button><button onClick={() => void toggleProviderEnabled(provider)}>{provider.is_enabled ? t("settings.disable") : t("settings.enable")}</button>{provider.capability === "tts" && <button onClick={() => void loadVoices(provider)} disabled={loadingVoices === provider.id}>{loadingVoices === provider.id ? t("settings.loadingVoices") : providerVoices[provider.id] ? t("settings.hideVoices") : t("settings.showVoices")}</button>}<button onClick={() => void testSaved(provider)}>{t("settings.checkConfiguration")}</button><button onClick={() => void testSaved(provider, "network")}>{provider.capability === "llm" ? t("settings.verifyConnection") : t("settings.verifyAdapter")}</button><button className="provider-live-test" onClick={() => void testSaved(provider, "inference")}>{t("settings.runPaidTest")}</button><button onClick={() => void remove(provider.id)}>{t("settings.delete")}</button></div></div>) : <p className="muted">{t("settings.noProviders")}</p>}</section>; })}
    <section className="provider-section"><h3>{t("settings.localWhisper")}</h3><p className={localASR?.runtime_ready ? "muted" : "provider-test error"}>{localASRSummary(localASR)}</p>{localASR && <p className="muted">{t("settings.modelStatus", { model: localASR.model_name, device: localASR.device, computeType: localASR.compute_type, cached: localASR.model_cached ? t("settings.cached") : t("settings.notCached") })}</p>}<div className="panel-actions"><button disabled={checkingLocalASR} onClick={() => void checkLocalASR()}>{checkingLocalASR ? t("settings.checking") : t("settings.checkEnvironment")}</button>{localASR?.runtime_ready && !localASR.model_loaded && <button disabled={checkingLocalASR} onClick={() => void checkLocalASR(true)}>{t("settings.loadModel")}</button>}{localASR?.model_loaded && <button disabled={checkingLocalASR} onClick={() => void releaseLocalASRModel()}>{t("settings.releaseModel")}</button>}</div>{!localASR?.installed && <p className="muted">{t("settings.installLocalAsr")} <code>pip install -r requirements-local-whisper.txt</code></p>}</section>
    <section className="provider-section"><h3>{t("settings.asrRouting")}</h3><label><input type="checkbox" checked={scenes?.material_transcription_use_local ?? true} disabled={!materialRemoteAvailable || !materialLocalAvailable} onChange={(event) => void updateScene("material_transcription_use_local", event.target.checked)} /> {t("settings.materialLocalAsr")}</label><p className="muted">{routeSummary(scenes?.material_transcription_effective_route || (scenes?.material_transcription_use_local ? "local" : "remote"), materialLocalAvailable, scenes?.material_transcription_local_unavailable_reason, materialRemoteAvailable, scenes?.material_transcription_missing_capabilities ?? [])}</p><label><input type="checkbox" checked={scenes?.recording_evaluation_use_local ?? true} disabled={!recordingRemoteAvailable || !recordingLocalAvailable} onChange={(event) => void updateScene("recording_evaluation_use_local", event.target.checked)} /> {t("settings.recordingLocalAsr")}</label><p className="muted">{routeSummary(scenes?.recording_evaluation_effective_route || (scenes?.recording_evaluation_use_local ? "local" : "remote"), recordingLocalAvailable, scenes?.recording_evaluation_local_unavailable_reason, recordingRemoteAvailable, scenes?.recording_evaluation_missing_capabilities ?? [])}</p></section>{message && <p className="muted">{message}</p>}</div>;
}
