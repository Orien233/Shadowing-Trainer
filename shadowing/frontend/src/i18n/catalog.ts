export const UI_LOCALES = ["zh-CN", "en-US"] as const;

export type UILocale = (typeof UI_LOCALES)[number];

export interface LanguageOption {
  code: string;
  nativeName: string;
  labels: Record<UILocale, string>;
}

export const LEARNING_LANGUAGES: LanguageOption[] = [
  { code: "en", nativeName: "English", labels: { "zh-CN": "英语", "en-US": "English" } },
  { code: "zh-CN", nativeName: "简体中文", labels: { "zh-CN": "简体中文", "en-US": "Chinese (Simplified)" } },
  { code: "zh-TW", nativeName: "繁體中文", labels: { "zh-CN": "繁体中文", "en-US": "Chinese (Traditional)" } },
  { code: "ja", nativeName: "日本語", labels: { "zh-CN": "日语", "en-US": "Japanese" } },
  { code: "ko", nativeName: "한국어", labels: { "zh-CN": "韩语", "en-US": "Korean" } },
  { code: "es", nativeName: "Español", labels: { "zh-CN": "西班牙语", "en-US": "Spanish" } },
  { code: "fr", nativeName: "Français", labels: { "zh-CN": "法语", "en-US": "French" } },
  { code: "de", nativeName: "Deutsch", labels: { "zh-CN": "德语", "en-US": "German" } },
  { code: "it", nativeName: "Italiano", labels: { "zh-CN": "意大利语", "en-US": "Italian" } },
  { code: "pt", nativeName: "Português", labels: { "zh-CN": "葡萄牙语", "en-US": "Portuguese" } },
  { code: "ru", nativeName: "Русский", labels: { "zh-CN": "俄语", "en-US": "Russian" } },
  { code: "ar", nativeName: "العربية", labels: { "zh-CN": "阿拉伯语", "en-US": "Arabic" } },
];

export function isUILocale(value: string | null): value is UILocale {
  return UI_LOCALES.includes(value as UILocale);
}

export function normalizeLearningLanguage(value: string | null | undefined): string {
  const normalized = String(value || "").trim();
  return LEARNING_LANGUAGES.some((item) => item.code === normalized) ? normalized : "en";
}

export function languageLabel(code: string, locale: UILocale): string {
  const language = LEARNING_LANGUAGES.find((item) => item.code === code);
  if (!language) return code;
  const localized = language.labels[locale];
  return localized === language.nativeName ? localized : `${localized} · ${language.nativeName}`;
}
