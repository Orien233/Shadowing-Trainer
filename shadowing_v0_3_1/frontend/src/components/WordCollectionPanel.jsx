import { useEffect, useState } from "react";
import { deleteWordCollection } from "../lib/api";
import { normalizeWordText } from "../utils/sentenceTokenText.js";

const SORT_OPTIONS = [
  { value: "collected_time_asc", label: "收藏时间正序（新到旧）" },
  { value: "collected_time_desc", label: "收藏时间倒序（旧到新）" },
  { value: "alphabetical", label: "字母顺序" },
];

export default function WordCollectionPanel({
  collections,
  loading,
  onRefresh,
  onDeleted,
}) {
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
    if (deletingIds.has(collection.id)) {
      return;
    }

    setDeletingIds((prev) => new Set([...prev, collection.id]));
    try {
      await deleteWordCollection(collection.id);
      onDeleted?.(collection.id);
    } catch (error) {
      alert(error instanceof Error ? error.message : "取消收藏失败");
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
        <h2>收藏单词</h2>
        <div className="word-collection-controls">
          <label className="word-collection-sort">
            <span>排序</span>
            <select value={sortMode} onChange={handleSortChange}>
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          {isLoading && <span className="material-state">Loading...</span>}
        </div>
      </div>

      {visibleCollections.length === 0 ? (
        <p className="muted">还没有收藏单词。</p>
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
                onClick={() => {
                  void handleDelete(collection);
                }}
                title="点击取消收藏"
              >
                <span className="word-collection-text">{displayWord}</span>
                <span className="word-collection-meta">
                  {collection.language || "en"}
                  {isDeleting ? " · Removing..." : ""}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
