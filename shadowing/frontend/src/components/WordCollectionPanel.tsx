import { useEffect, useState, type ChangeEvent } from "react";
import { languageLabel } from "../i18n/catalog";
import { useLanguage } from "../i18n/LanguageContext";
import { deleteWordCollection } from "../lib/api";
import { normalizeWordText } from "../utils/sentenceTokenText";
import type { WordCollection } from "../types";
import type { WordCollectionSortMode } from "../lib/api";

const SORT_OPTIONS: Array<{ value: WordCollectionSortMode; labelKey: string }> = [
  { value: "collected_time_asc", labelKey: "wordCollection.sort.collectedAsc" },
  { value: "collected_time_desc", labelKey: "wordCollection.sort.collectedDesc" },
  { value: "alphabetical", labelKey: "wordCollection.sort.alphabetical" },
];

export default function WordCollectionPanel({
  collections,
  loading,
  onRefresh,
  onDeleted,
}: { collections?: WordCollection[]; loading?: boolean; onRefresh?: (sort: WordCollectionSortMode) => void | Promise<void>; onDeleted?: (id: number) => void }) {
  const { uiLocale, t } = useLanguage();
  const [deletingIds, setDeletingIds] = useState(() => new Set());
  const [sortMode, setSortMode] = useState<WordCollectionSortMode>("collected_time_asc");
  const visibleCollections = collections ?? [];
  const isLoading = Boolean(loading);

  useEffect(() => {
    void onRefresh?.(sortMode);
  }, [onRefresh, sortMode]);

  function handleSortChange(event: ChangeEvent<HTMLSelectElement>) {
    setSortMode(event.target.value as WordCollectionSortMode);
  }

  async function handleDelete(collection: WordCollection) {
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
            const displayWord = String(collection.word_text ?? "").trim() ||
              normalizeWordText(collection.normalized_word || "");
            return (
              <button
                key={collection.id}
                type="button"
                className="word-collection-item"
                disabled={isDeleting}
                onClick={() => void handleDelete(collection)}
                title={t("wordCollection.remove")}
              >
                <span className="word-collection-text" dir="auto">{displayWord}</span>
                <span className="word-collection-meta">
                  {languageLabel(collection.language || "en", uiLocale)}
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
