import { useState, type FormEvent } from "react";
import { processMaterial, uploadMaterial } from "../../lib/api";
import type { Material } from "../../types";
import { languageLabel } from "../../i18n/catalog";
import { useLanguage } from "../../i18n/LanguageContext";

interface Props {
  onUploaded: (material: Material) => void;
}

export default function MaterialUploader({ onUploaded }: Props) {
  const { uiLocale, learningLanguage, translationLanguage, t } = useLanguage();
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title || !file) return;

    setLoading(true);
    try {
      const uploaded = await uploadMaterial(title, file, learningLanguage, translationLanguage);
      let material = uploaded;
      if (uploaded.status === "uploaded") {
        try {
          material = await processMaterial(uploaded.id);
        } catch (error) {
          console.error(error);
        }
      }
      onUploaded(material);
      setTitle("");
      setFile(null);
    } catch (error) {
      alert(error instanceof Error ? error.message : t("material.uploadFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="card upload-form" onSubmit={handleSubmit}>
      <h2>{t("material.uploadTitle")}</h2>
      <div className="material-language-summary">
        <span>{t("material.contentLanguage")}: <strong>{languageLabel(learningLanguage, uiLocale)}</strong></span>
        <span>{t("material.translationLanguage")}: <strong>{languageLabel(translationLanguage, uiLocale)}</strong></span>
      </div>
      <input
        dir="auto"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={t("material.titlePlaceholder")}
      />
      <input
        type="file"
        accept="audio/*,video/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button type="submit" disabled={loading || !title || !file}>
        {loading ? t("material.uploading") : t("material.upload")}
      </button>
    </form>
  );
}
