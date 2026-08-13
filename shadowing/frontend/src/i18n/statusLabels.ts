type Translate = (key: string, params?: Record<string, string | number>) => string;

function translatedOrFallback(t: Translate, key: string, fallback: string): string {
  const translated = t(key);
  return translated === key ? fallback : translated;
}

export function statusLabel(t: Translate, value: string | null | undefined): string {
  const code = String(value || "").trim();
  if (!code) return "-";
  return translatedOrFallback(t, `status.${code}`, code.replace(/_/g, " "));
}

export function stageLabel(t: Translate, value: string | null | undefined): string {
  const code = String(value || "").trim() || "queued";
  const synthesis = /^synthesizing_sentence_(\d+)$/.exec(code);
  if (synthesis) return t("stage.synthesizingSentence", { number: synthesis[1] });
  return translatedOrFallback(t, `stage.${code}`, code.replace(/_/g, " "));
}

export function mediaTypeLabel(t: Translate, value: string | null | undefined): string {
  const code = String(value || "").trim();
  if (!code) return "-";
  return translatedOrFallback(t, `mediaType.${code}`, code);
}
