import { useState } from "react";
import { processMaterial } from "../lib/api";
import type { Material } from "../types";

interface Props {
  materials: Material[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onProcessed: (material: Material) => void;
}

export default function MaterialList({
  materials,
  activeId,
  onSelect,
  onProcessed,
}: Props) {
  const [processingIds, setProcessingIds] = useState<number[]>([]);

  async function handleProcess(material: Material) {
    if (processingIds.includes(material.id)) return;
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

  return (
    <div className="card">
      <h2>2. 素材列表</h2>
      <div className="material-list">
        {materials.length === 0 && <p className="muted">还没有素材，先上传一个。</p>}
        {materials.map((material) => (
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
            <button
              type="button"
              disabled={material.status === "processing" || processingIds.includes(material.id)}
              onClick={() => handleProcess(material)}
            >
              {material.status === "processing" || processingIds.includes(material.id)
                ? "处理中..."
                : material.status === "ready"
                  ? "重新处理"
                  : "开始处理"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
