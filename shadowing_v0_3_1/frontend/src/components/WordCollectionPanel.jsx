import { useEffect, useState } from "react";
import { deleteWordCollection } from "../lib/api";

export default function WordCollectionPanel({
  collections,
  loading,
  onRefresh,
  onDeleted,
}) {
  const [deletingIds, setDeletingIds] = useState(() => new Set());
  const visibleCollections = collections ?? [];
  const isLoading = Boolean(loading);

  useEffect(() => {
    void onRefresh?.();
  }, [onRefresh]);

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
        {isLoading && <span className="material-state">Loading...</span>}
      </div>

      {visibleCollections.length === 0 ? (
        <p className="muted">还没有收藏单词。</p>
      ) : (
        <div className="word-collection-list">
          {visibleCollections.map((collection) => {
            const isDeleting = deletingIds.has(collection.id);
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
                <span className="word-collection-text">{collection.word_text}</span>
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
