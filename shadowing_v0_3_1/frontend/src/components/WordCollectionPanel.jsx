import { useEffect, useState } from "react";
import { useLanguage } from "../i18n/LanguageContext";
import { deleteWordCollection } from "../lib/api";
import { normalizeWordText } from "../utils/sentenceTokenText.js";

const SORT_OPTIONS = [
  { value: "collected_time_asc", labelKey: "wordCollection.sort.collectedAsc" },
  { value: "collected_time_desc", labelKey: "wordCollection.sort.collectedDesc" },
  { value: "alphabetical", labelKey: "wordCollection.sort.alphabetical" },
];

export default function WordCollectionPanel({
  collections,
  loading,
  onRefresh,
  onDeleted,
}) {
  const { t } = useLanguage();
  const [deletingIds, setDeletingIds] = useState(() => new Set());
  const [sortMode, setSortMode] = useState("collected_time_asc");
  const visibleCollections = collections ?? [];
  const isLoading = Boolean(loading);

  useEffect(() => {
    void onRefresh?.(sortMode);
  }, [onRefresh, sortMode]);

  function handleSortChange(event) {
    setSortMode(event.target.value);
  }

  async function handleDelete(collection) {
    if (deletingIds.has(collection.id)) return;

    setDeletingIds((prev) => new Set([...prev, collection.id]));
    try {
      await deleteWordCollection(collection.id);
      onDeleted?.(collection.id);
    } catch (error) {
      alert(error instanceof Error ? error.message : t("wordCollection.removeFailed"));
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(collection.id);
        return next;
      });
    }
  }

  return (
    <div className="card word-collection-panel">
      <div className="word-collection-heading">
        <h2>{t("wordCollection.title")}</h2>
        <div className="word-collection-controls">
          <label className="word-collection-sort">
            <span>{t("wordCollection.sort")}</span>
            <select value={sortMode} onChange={handleSortChange}>
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {t(option.labelKey)}
                </option>
              ))}
            </select>
          </label>
          {isLoading && <span className="material-state">{t("wordCollection.loading")}</span>}
        </div>
      </div>

      {visibleCollections.length === 0 ? (
        <p className="muted">{t("wordCollection.empty")}</p>
      ) : (
        <div className="word-collection-list">
          {visibleCollections.map((collection) => {
            const isDeleting = deletingIds.has(collection.id);
            const displayWord =
              normalizeWordText(collection.normalized_word || collection.word_text) ||
              String(collection.word_text ?? "").toLowerCase();
            return (
              <button
                key={collection.id}
                type="button"
                className="word-collection-item"
                disabled={isDeleting}
                onClick={() => void handleDelete(collection)}
                title={t("wordCollection.remove")}
              >
                <span className="word-collection-text">{displayWord}</span>
                <span className="word-collection-meta">
                  {collection.language || "en"}
                  {isDeleting ? ` · ${t("wordCollection.removing")}` : ""}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
