import { languageLabel, LEARNING_LANGUAGES, UI_LOCALES, type UILocale } from "../i18n/catalog";
import { useLanguage } from "../i18n/LanguageContext";

export default function LanguageSelector() {
  const {
    uiLocale,
    learningLanguage,
    translationLanguage,
    setUILocale,
    setLearningLanguage,
    setTranslationLanguage,
    t,
  } = useLanguage();

  return (
    <section className="language-selector" aria-label={t("language.preferences")}>
      <label>
        <span>{t("language.interface")}</span>
        <select value={uiLocale} onChange={(event) => setUILocale(event.target.value as UILocale)}>
          {UI_LOCALES.map((locale) => (
            <option key={locale} value={locale}>{t(`language.ui.${locale}`)}</option>
          ))}
        </select>
        <small>{t("language.interfaceHelp")}</small>
      </label>
      <label>
        <span>{t("language.learningTarget")}</span>
        <select value={learningLanguage} onChange={(event) => setLearningLanguage(event.target.value)}>
          {LEARNING_LANGUAGES.map((language) => (
            <option key={language.code} value={language.code}>{languageLabel(language.code, uiLocale)}</option>
          ))}
        </select>
        <small>{t("language.learningHelp")}</small>
      </label>
      <label>
        <span>{t("language.translationTarget")}</span>
        <select value={translationLanguage} onChange={(event) => setTranslationLanguage(event.target.value)}>
          {LEARNING_LANGUAGES.map((language) => (
            <option key={language.code} value={language.code}>{languageLabel(language.code, uiLocale)}</option>
          ))}
        </select>
        <small>{t("language.translationHelp")}</small>
      </label>
    </section>
  );
}
