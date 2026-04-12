import { useEffect, useState } from "react";
import { deleteMaterial, processMaterial } from "../lib/api";
import type { Material } from "../types";

interface Props {
  materials: Material[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onProcessed: (material: Material) => void;
  onDeleted: (materialId: number) => void;
}

export default function MaterialList({
  materials,
  activeId,
  onSelect,
  onProcessed,
  onDeleted,
}: Props) {
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
      alert(error instanceof Error ? error.message : "Processing failed.");
    } finally {
      setProcessingIds((prev) => prev.filter((id) => id !== material.id));
    }
  }

  async function handleDelete(material: Material) {
    if (processingIds.includes(material.id) || deletingIds.includes(material.id)) return;
    const confirmed = window.confirm(`Delete "${material.title}" and all generated files?`);
    if (!confirmed) return;

    setOpenMenuId(null);
    setDeletingIds((prev) => [...prev, material.id]);
    try {
      await deleteMaterial(material.id);
      onDeleted(material.id);
    } catch (error) {
      alert(error instanceof Error ? error.message : "Delete failed.");
    } finally {
      setDeletingIds((prev) => prev.filter((id) => id !== material.id));
    }
  }

  return (
    <div className="card">
      <h2>素材列表</h2>
      <div className="material-list">
        {materials.length === 0 && <p className="muted">No materials yet. Upload one first.</p>}
        {materials.map((material) => {
          const isProcessing = material.status === "processing" || processingIds.includes(material.id);
          const isDeleting = deletingIds.includes(material.id);
          const canOpenMenu = !isDeleting;

          return (
            <div
              key={material.id}
              className={`material-item ${material.id === activeId ? "active" : ""}`}
            >
              <div className="material-main" onClick={() => onSelect(material.id)}>
                <div className="material-title">{material.title}</div>
                <div className="material-meta">
                  <span>{material.file_type}</span>
                  <span>{material.status}</span>
                </div>
              </div>

              <div className="material-actions">
                {isProcessing && <span className="material-state">Processing...</span>}
                {isDeleting && <span className="material-state">Deleting...</span>}
                <div className="material-menu-anchor">
                  <button
                    type="button"
                    className="material-more-button"
                    disabled={!canOpenMenu}
                    aria-label="More actions"
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
                          ? "Processing..."
                          : material.status === "ready"
                            ? "Reprocess"
                            : "Start Processing"}
                      </button>
                      <button
                        type="button"
                        className="material-menu-item danger"
                        disabled={isProcessing || isDeleting}
                        onClick={() => {
                          void handleDelete(material);
                        }}
                      >
                        Delete Material
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
