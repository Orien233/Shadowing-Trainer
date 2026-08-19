import { useEffect, useState } from "react";
import { deleteMaterial, processMaterial } from "../../lib/api";
import type { Material } from "../../types";
import { languageLabel } from "../../i18n/catalog";
import { useLanguage } from "../../i18n/LanguageContext";
import { mediaTypeLabel, stageLabel, statusLabel } from "../../i18n/statusLabels";

interface Props {
  materials: Material[];
  activeId: number | null;
  isWordLibraryActive: boolean;
  onSelect: (id: number) => void;
  onOpenWordLibrary: () => void;
  onProcessed: (material: Material) => void;
  onDeleted: (materialId: number) => void;
}

export default function MaterialList({
  materials,
  activeId,
  isWordLibraryActive,
  onSelect,
  onOpenWordLibrary,
  onProcessed,
  onDeleted,
}: Props) {
  const { uiLocale, t } = useLanguage();
  const [processingIds, setProcessingIds] = useState<number[]>([]);
  const [deletingIds, setDeletingIds] = useState<number[]>([]);
  const [openMenuId, setOpenMenuId] = useState<number | null>(null);

  useEffect(() => {
    if (openMenuId === null) return;
    if (materials.some((item) => item.id === openMenuId)) return;
    setOpenMenuId(null);
  }, [materials, openMenuId]);

  async function handleProcess(material: Material) {
    if (processingIds.includes(material.id) || deletingIds.includes(material.id)) return;
    setOpenMenuId(null);
    setProcessingIds((prev) => [...prev, material.id]);
    onProcessed({ ...material, status: "processing" });
    try {
      const updated = await processMaterial(material.id);
      onProcessed(updated);
    } catch (error) {
      onProcessed(material);
      alert(error instanceof Error ? error.message : t("material.processingFailed"));
    } finally {
      setProcessingIds((prev) => prev.filter((id) => id !== material.id));
    }
  }

  async function handleDelete(material: Material) {
    if (processingIds.includes(material.id) || deletingIds.includes(material.id)) return;
    const confirmed = window.confirm(t("material.deleteConfirm", { title: material.title }));
    if (!confirmed) return;

    setOpenMenuId(null);
    setDeletingIds((prev) => [...prev, material.id]);
    try {
      await deleteMaterial(material.id);
      onDeleted(material.id);
    } catch (error) {
      alert(error instanceof Error ? error.message : t("material.deleteFailed"));
    } finally {
      setDeletingIds((prev) => prev.filter((id) => id !== material.id));
    }
  }

  return (
    <div className="card">
      <h2>{t("material.listTitle")}</h2>
      <button
        type="button"
        className={`word-library-button ${isWordLibraryActive ? "active" : ""}`}
        onClick={() => {
          setOpenMenuId(null);
          onOpenWordLibrary();
        }}
      >
        {t("material.wordLibrary")}
      </button>
      <div className="material-list">
        {materials.length === 0 && <p className="muted">{t("material.empty")}</p>}
        {materials.map((material) => {
          const isProcessing = material.status === "processing" || material.status === "queued" || processingIds.includes(material.id);
          const isDeleting = deletingIds.includes(material.id);
          const canOpenMenu = !isDeleting;

          return (
            <div
              key={material.id}
              className={`material-item ${material.id === activeId ? "active" : ""}`}
            >
              <button type="button" className="material-main" onClick={() => onSelect(material.id)}>
                <div className="material-title" dir="auto">{material.title}</div>
                <div className="material-meta">
                  <span>{mediaTypeLabel(t, material.file_type)}</span>
                  <span>{statusLabel(t, material.status)}</span>
                  <span>{languageLabel(material.content_language, uiLocale)}</span>
                  <span>→ {languageLabel(material.translation_language, uiLocale)}</span>
                </div>
                {isProcessing && (
                  <div className="material-progress" aria-label={t("material.processingProgress")}>
                    <span>{t("material.processing")}</span>
                    <span>{stageLabel(t, material.processing_stage)}</span>
                    <strong>{material.processing_progress ?? 0}%</strong>
                  </div>
                )}
                {material.status === "failed" && material.error_message && (
                  <div className="material-error" title={material.error_message}>{material.error_message}</div>
                )}
              </button>

              <div className="material-actions">
                {isDeleting && <span className="material-state">{t("material.deleting")}</span>}
                <div className="material-menu-anchor">
                  <button
                    type="button"
                    className="material-more-button"
                    disabled={!canOpenMenu}
                    aria-label={t("material.moreActions")}
                    onClick={() => setOpenMenuId((prev) => (prev === material.id ? null : material.id))}
                  >
                    ...
                  </button>
                  {openMenuId === material.id && (
                    <div className="material-menu">
                      <button
                        type="button"
                        className="material-menu-item"
                        disabled={isProcessing}
                        onClick={() => {
                          void handleProcess(material);
                        }}
                      >
                        {isProcessing
                          ? t("material.processing")
                          : material.status === "ready"
                            ? t("material.reprocess")
                            : material.status === "failed"
                              ? t("material.retryProcessing")
                            : t("material.startProcessing")}
                      </button>
                      <button
                        type="button"
                        className="material-menu-item danger"
                        disabled={isProcessing || isDeleting}
                        onClick={() => {
                          void handleDelete(material);
                        }}
                      >
                        {t("material.delete")}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
