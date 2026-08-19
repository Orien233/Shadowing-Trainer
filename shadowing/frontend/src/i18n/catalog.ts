import languageCatalog from "../../../shared/language_catalog.json";

export type UILocale = "zh-CN" | "en-US";
export const UI_LOCALES: readonly UILocale[] = languageCatalog.ui_locales as UILocale[];

export interface LanguageOption {
  code: string;
  nativeName: string;
  labels: Record<UILocale, string>;
}

export const LEARNING_LANGUAGES: LanguageOption[] = languageCatalog.languages.map((item) => ({
  code: item.code,
  nativeName: item.native_name,
  labels: item.labels,
}));

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
