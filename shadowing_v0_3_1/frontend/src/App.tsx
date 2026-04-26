import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MaterialList from "./components/MaterialList";
import MaterialUploader from "./components/MaterialUploader";
import SentenceTrainer from "./components/SentenceTrainer";
import {
  cleanupRecordingFiles,
  getLatestMaterialEvaluations,
  getSentences,
  listMaterials,
  shutdownBackend,
} from "./lib/api";
import type { Material, Sentence, SentenceLatestEvaluation } from "./types";

function indexLatestEvaluations(
  evaluations: SentenceLatestEvaluation[]
): Record<number, SentenceLatestEvaluation> {
  const next: Record<number, SentenceLatestEvaluation> = {};
  for (const item of evaluations) {
    next[item.sentence_id] = item;
  }
  return next;
}

export default function App() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [activeMaterialId, setActiveMaterialId] = useState<number | null>(null);
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const [latestEvaluations, setLatestEvaluations] = useState<Record<number, SentenceLatestEvaluation>>({});
  const [loadingSentences, setLoadingSentences] = useState(false);
  const [shuttingDown, setShuttingDown] = useState(false);
  const sentenceRequestIdRef = useRef(0);

  const activeMaterial = useMemo(
    () => materials.find((item) => item.id === activeMaterialId) ?? null,
    [materials, activeMaterialId]
  );
  const hasProcessingMaterials = useMemo(
    () => materials.some((item) => item.status === "processing"),
    [materials]
  );

  const loadMaterials = useCallback(async () => {
    try {
      const data = await listMaterials();
      setMaterials(data);
      setActiveMaterialId((prev) => {
        if (data.length === 0) return null;
        if (prev && data.some((item) => item.id === prev)) return prev;
        return data[0].id;
      });
    } catch (error) {
      console.error(error);
    }
  }, []);

  useEffect(() => {
    void loadMaterials();
  }, [loadMaterials]);

  useEffect(() => {
    if (!hasProcessingMaterials) return;
    const timer = window.setInterval(() => {
      void loadMaterials();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [hasProcessingMaterials, loadMaterials]);

  const loadSentences = useCallback(async (materialId: number) => {
    const requestId = sentenceRequestIdRef.current + 1;
    sentenceRequestIdRef.current = requestId;
    setLoadingSentences(true);
    try {
      const [sentenceResult, evaluationResult] = await Promise.allSettled([
        getSentences(materialId),
        getLatestMaterialEvaluations(materialId),
      ]);
      if (sentenceResult.status !== "fulfilled") {
        throw sentenceResult.reason;
      }
      const sentenceData = sentenceResult.value;
      const evaluationData =
        evaluationResult.status === "fulfilled" ? evaluationResult.value : [];
      if (evaluationResult.status !== "fulfilled") {
        console.error(evaluationResult.reason);
      }
      if (requestId !== sentenceRequestIdRef.current) return;
      setSentences(sentenceData);
      setLatestEvaluations(indexLatestEvaluations(evaluationData));
    } catch (error) {
      if (requestId !== sentenceRequestIdRef.current) return;
      console.error(error);
      setSentences([]);
      setLatestEvaluations({});
    } finally {
      if (requestId === sentenceRequestIdRef.current) {
        setLoadingSentences(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!activeMaterialId) {
      sentenceRequestIdRef.current += 1;
      setSentences([]);
      setLatestEvaluations({});
      setLoadingSentences(false);
      return;
    }
    if (activeMaterial?.status !== "ready") {
      sentenceRequestIdRef.current += 1;
      setSentences([]);
      setLatestEvaluations({});
      setLoadingSentences(false);
      return;
    }
    void loadSentences(activeMaterialId);
  }, [activeMaterialId, activeMaterial?.status, loadSentences]);

  function handleUploaded(material: Material) {
    setMaterials((prev) => [material, ...prev]);
    setActiveMaterialId(material.id);
  }

  function handleProcessed(material: Material) {
    setMaterials((prev) => {
      const exists = prev.some((item) => item.id === material.id);
      if (!exists) return [material, ...prev];
      return prev.map((item) => (item.id === material.id ? { ...item, ...material } : item));
    });
  }

  function handleDeleted(materialId: number) {
    setMaterials((prev) => {
      const next = prev.filter((item) => item.id !== materialId);
      setActiveMaterialId((activeId) => {
        if (activeId !== materialId) return activeId;
        return next[0]?.id ?? null;
      });
      return next;
    });
  }

  function closeFrontendWindow() {
    window.open("", "_self");
    window.close();
    window.location.replace("about:blank");
  }

  async function handleShutdown() {
    if (shuttingDown) return;

    const confirmed = window.confirm("This will delete all recording files and close the app. Continue?");
    if (!confirmed) return;

    setShuttingDown(true);
    try {
      const cleanupResult = await cleanupRecordingFiles();
      if (cleanupResult.failed_files.length > 0) {
        throw new Error("Failed to delete one or more recording files.");
      }
      await shutdownBackend();
      closeFrontendWindow();
    } catch (error) {
      console.error(error);
      alert(error instanceof Error ? error.message : "Shutdown failed.");
      setShuttingDown(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-main">
          <h1>Shadowing Trainer V0.3</h1>
          <p>上传素材 → 转写切句 → 翻译 → 逐句播放 → 跟读录音 → 基础评估</p>
        </div>
        <button type="button" className="shutdown-button" disabled={shuttingDown} onClick={handleShutdown}>
          {shuttingDown ? "Closing..." : "Close App"}
        </button>
      </header>

      <main className="layout">
        <section className="sidebar">
          <MaterialUploader onUploaded={handleUploaded} />
          <MaterialList
            materials={materials}
            activeId={activeMaterialId}
            onSelect={setActiveMaterialId}
            onProcessed={handleProcessed}
            onDeleted={handleDeleted}
          />
        </section>

        <section className="content">
          {loadingSentences ? (
            <div className="card"><p>句子加载中...</p></div>
          ) : (
            <SentenceTrainer
              material={activeMaterial}
              sentences={sentences}
              latestEvaluations={latestEvaluations}
            />
          )}
        </section>
      </main>
    </div>
  );
}
