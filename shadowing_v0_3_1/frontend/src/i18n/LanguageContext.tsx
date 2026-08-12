import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  isUILocale,
  normalizeLearningLanguage,
  type UILocale,
} from "./catalog";
import { messages, type MessageParams } from "./messages";

const UI_LOCALE_STORAGE_KEY = "shadowing.uiLocale";
const LEARNING_LANGUAGE_STORAGE_KEY = "shadowing.learningLanguage";

interface LanguageContextValue {
  uiLocale: UILocale;
  learningLanguage: string;
  setUILocale: (locale: UILocale) => void;
  setLearningLanguage: (language: string) => void;
  t: (key: string, params?: MessageParams) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

function detectUILocale(): UILocale {
  const stored = window.localStorage.getItem(UI_LOCALE_STORAGE_KEY);
  if (isUILocale(stored)) return stored;
  return window.navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

function interpolate(template: string, params?: MessageParams): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    Object.prototype.hasOwnProperty.call(params, key) ? String(params[key]) : match
  );
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [uiLocale, setUILocaleState] = useState<UILocale>(detectUILocale);
  const [learningLanguage, setLearningLanguageState] = useState(() =>
    normalizeLearningLanguage(window.localStorage.getItem(LEARNING_LANGUAGE_STORAGE_KEY))
  );

  useEffect(() => {
    document.documentElement.lang = uiLocale;
    document.documentElement.dir = "ltr";
    window.localStorage.setItem(UI_LOCALE_STORAGE_KEY, uiLocale);
  }, [uiLocale]);

  useEffect(() => {
    window.localStorage.setItem(LEARNING_LANGUAGE_STORAGE_KEY, learningLanguage);
  }, [learningLanguage]);

  const setUILocale = useCallback((locale: UILocale) => setUILocaleState(locale), []);
  const setLearningLanguage = useCallback((language: string) => {
    setLearningLanguageState(normalizeLearningLanguage(language));
  }, []);
  const t = useCallback(
    (key: string, params?: MessageParams) => {
      const template = messages[uiLocale][key] ?? messages["en-US"][key] ?? key;
      return interpolate(template, params);
    },
    [uiLocale]
  );

  const value = useMemo(
    () => ({ uiLocale, learningLanguage, setUILocale, setLearningLanguage, t }),
    [learningLanguage, setLearningLanguage, setUILocale, t, uiLocale]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("useLanguage must be used inside LanguageProvider");
  return value;
}
