import { useEffect, useState, type ChangeEvent } from "react";
import { BookOpenText, Trash } from "@phosphor-icons/react";
import { languageLabel } from "../../i18n/catalog";
import { useLanguage } from "../../i18n/LanguageContext";
import { deleteWordCollection } from "../../lib/api";
import { normalizeWordText } from "../../utils/sentenceTokenText";
import type { WordCollection } from "../../types";
import type { WordCollectionSortMode } from "../../lib/api";

const SORT_OPTIONS: Array<{ value: WordCollectionSortMode; labelKey: string }> = [
  { value: "collected_time_asc", labelKey: "wordCollection.sort.collectedAsc" },
  { value: "collected_time_desc", labelKey: "wordCollection.sort.collectedDesc" },
  { value: "alphabetical", labelKey: "wordCollection.sort.alphabetical" },
];

interface Props {
  collections?: WordCollection[];
  loading?: boolean;
  onRefresh?: (sort: WordCollectionSortMode) => void | Promise<void>;
  onDeleted?: (id: number) => void;
}

export default function WordCollectionPanel({
  collections,
  loading,
  onRefresh,
  onDeleted,
}: Props) {
  const { uiLocale, t } = useLanguage();
  const [deletingIds, setDeletingIds] = useState(() => new Set<number>());
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

    setDeletingIds((previous) => new Set([...previous, collection.id]));
    try {
      await deleteWordCollection(collection.id);
      onDeleted?.(collection.id);
    } catch (error) {
      alert(error instanceof Error ? error.message : t("wordCollection.removeFailed"));
    } finally {
      setDeletingIds((previous) => {
        const next = new Set(previous);
        next.delete(collection.id);
        return next;
      });
    }
  }

  return (
    <section className="secondary-page word-collection-panel">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Shadowing</span>
          <h2>
            <BookOpenText size={26} weight="regular" aria-hidden="true" />
            {t("wordCollection.title")}
          </h2>
          <p>{t("wordCollection.description")}</p>
        </div>
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
          {isLoading && <span className="material-state" role="status">{t("wordCollection.loading")}</span>}
        </div>
      </header>

      {visibleCollections.length === 0 ? (
        <div className="empty-state">
          <BookOpenText size={32} weight="regular" aria-hidden="true" />
          <p>{t("wordCollection.empty")}</p>
        </div>
      ) : (
        <div className="word-collection-list">
          {visibleCollections.map((collection) => {
            const isDeleting = deletingIds.has(collection.id);
            const displayWord = String(collection.word_text ?? "").trim() ||
              normalizeWordText(collection.normalized_word || "");
            return (
              <article className="word-collection-item" key={collection.id}>
                <div className="word-collection-copy">
                  <strong className="word-collection-text" dir="auto">{displayWord}</strong>
                  {collection.translation && (
                    <span className="word-collection-translation" dir="auto">{collection.translation}</span>
                  )}
                  <span className="word-collection-meta">
                    {languageLabel(collection.language || "en", uiLocale)}
                  </span>
                </div>
                <button
                  type="button"
                  className="icon-button remove-word-button"
                  disabled={isDeleting}
                  aria-label={t("wordCollection.removeWord", { word: displayWord })}
                  onClick={() => void handleDelete(collection)}
                >
                  <Trash size={18} weight="regular" />
                </button>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
