import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  isUILocale,
  normalizeLearningLanguage,
  type UILocale,
} from "./catalog";
import { messages, type MessageParams } from "./messages";
import { getLanguagePreferences, updateLanguagePreferences } from "../lib/api";

const UI_LOCALE_STORAGE_KEY = "shadowing.uiLocale";
const LEARNING_LANGUAGE_STORAGE_KEY = "shadowing.learningLanguage";
const TRANSLATION_LANGUAGE_STORAGE_KEY = "shadowing.translationLanguage";

interface LanguageContextValue {
  uiLocale: UILocale;
  learningLanguage: string;
  translationLanguage: string;
  setUILocale: (locale: UILocale) => void;
  setLearningLanguage: (language: string) => void;
  setTranslationLanguage: (language: string) => void;
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
  const hadStoredUILocale = useRef(window.localStorage.getItem(UI_LOCALE_STORAGE_KEY) !== null);
  const hadStoredLearningLanguage = useRef(window.localStorage.getItem(LEARNING_LANGUAGE_STORAGE_KEY) !== null);
  const hadStoredTranslationLanguage = useRef(window.localStorage.getItem(TRANSLATION_LANGUAGE_STORAGE_KEY) !== null);
  const [uiLocale, setUILocaleState] = useState<UILocale>(detectUILocale);
  const [learningLanguage, setLearningLanguageState] = useState(() =>
    normalizeLearningLanguage(window.localStorage.getItem(LEARNING_LANGUAGE_STORAGE_KEY))
  );
  const [translationLanguage, setTranslationLanguageState] = useState(() => {
    const stored = window.localStorage.getItem(TRANSLATION_LANGUAGE_STORAGE_KEY);
    if (stored) return normalizeLearningLanguage(stored);
    return detectUILocale() === "zh-CN" ? "zh-CN" : "en";
  });
  const [preferencesHydrated, setPreferencesHydrated] = useState(false);

  useEffect(() => {
    document.documentElement.lang = uiLocale;
    document.documentElement.dir = "ltr";
    window.localStorage.setItem(UI_LOCALE_STORAGE_KEY, uiLocale);
  }, [uiLocale]);

  useEffect(() => {
    window.localStorage.setItem(LEARNING_LANGUAGE_STORAGE_KEY, learningLanguage);
  }, [learningLanguage]);

  useEffect(() => {
    window.localStorage.setItem(TRANSLATION_LANGUAGE_STORAGE_KEY, translationLanguage);
  }, [translationLanguage]);

  useEffect(() => {
    let cancelled = false;
    void getLanguagePreferences()
      .then((preference) => {
        if (cancelled) return;
        if (!hadStoredUILocale.current && isUILocale(preference.ui_locale)) {
          setUILocaleState(preference.ui_locale);
        }
        if (!hadStoredLearningLanguage.current) {
          setLearningLanguageState(normalizeLearningLanguage(preference.learning_language));
        }
        if (!hadStoredTranslationLanguage.current) {
          setTranslationLanguageState(normalizeLearningLanguage(preference.translation_language));
        }
      })
      .catch(() => {
        // Offline startup keeps the local preference; backend sync is best-effort.
      })
      .finally(() => {
        if (!cancelled) setPreferencesHydrated(true);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!preferencesHydrated) return;
    const timer = window.setTimeout(() => {
      void updateLanguagePreferences({
        ui_locale: uiLocale,
        learning_language: learningLanguage,
        translation_language: translationLanguage,
      }).catch(() => {
        // The local selection remains usable while the backend is unavailable.
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [learningLanguage, preferencesHydrated, translationLanguage, uiLocale]);

  const setUILocale = useCallback((locale: UILocale) => setUILocaleState(locale), []);
  const setLearningLanguage = useCallback((language: string) => {
    setLearningLanguageState(normalizeLearningLanguage(language));
  }, []);
  const setTranslationLanguage = useCallback((language: string) => {
    setTranslationLanguageState(normalizeLearningLanguage(language));
  }, []);
  const t = useCallback(
    (key: string, params?: MessageParams) => {
      const template = messages[uiLocale][key] ?? messages["en-US"][key] ?? key;
      return interpolate(template, params);
    },
    [uiLocale]
  );

  const value = useMemo(
    () => ({ uiLocale, learningLanguage, translationLanguage, setUILocale, setLearningLanguage, setTranslationLanguage, t }),
    [learningLanguage, setLearningLanguage, setTranslationLanguage, setUILocale, t, translationLanguage, uiLocale]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("useLanguage must be used inside LanguageProvider");
  return value;
}
