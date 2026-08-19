import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Power } from "@phosphor-icons/react";
import AppHeader, { type AppPanel } from "./AppHeader";
import MaterialDrawer from "../features/materials/MaterialDrawer";
import SentenceTrainer from "../features/practice/SentenceTrainer";
import WordCollectionPanel from "../features/vocabulary/WordCollectionPanel";
import TextGeneratorPanel from "../features/create-practice/TextGeneratorPanel";
import SettingsPanel from "../features/settings/SettingsPanel";
import {
  cleanupRecordingFiles,
  getLatestMaterialEvaluations,
  getSentences,
  listWordCollections,
  listMaterials,
  shutdownBackend,
} from "../lib/api";
import type { WordCollectionSortMode } from "../lib/api";
import type { Material, Sentence, SentenceLatestEvaluation, WordCollection } from "../types";
import { buildCollectedWordKey, normalizeWordText } from "../utils/sentenceTokenText";
import { useLanguage } from "../i18n/LanguageContext";

function indexLatestEvaluations(
  evaluations: SentenceLatestEvaluation[]
): Record<number, SentenceLatestEvaluation> {
  const next: Record<number, SentenceLatestEvaluation> = {};
  for (const item of evaluations) {
    next[item.sentence_id] = item;
  }
  return next;
}

function getWordCollectionKey(collection: WordCollection): string {
  const normalizedWord = normalizeWordText(collection.normalized_word || collection.word_text);
  return buildCollectedWordKey(normalizedWord, collection.language);
}

function collectionUsesLanguage(collection: WordCollection, language: string): boolean {
  const normalize = (value: string) => String(value || "en").trim().replace(/_/g, "-").toLowerCase();
  return normalize(collection.language) === normalize(language);
}

export default function App() {
  const { learningLanguage, translationLanguage, t } = useLanguage();
  const [materials, setMaterials] = useState<Material[]>([]);
  const [activeMaterialId, setActiveMaterialId] = useState<number | null>(null);
  const [activePanel, setActivePanel] = useState<AppPanel>("practice");
  const [materialDrawerOpen, setMaterialDrawerOpen] = useState(false);
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const [latestEvaluations, setLatestEvaluations] = useState<Record<number, SentenceLatestEvaluation>>({});
  const [wordCollections, setWordCollections] = useState<WordCollection[]>([]);
  const [loadingSentences, setLoadingSentences] = useState(false);
  const [loadingWordCollections, setLoadingWordCollections] = useState(false);
  const [shuttingDown, setShuttingDown] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [providerRevision, setProviderRevision] = useState(0);
  const sentenceRequestIdRef = useRef(0);
  const wordCollectionRequestIdRef = useRef(0);

  const activeMaterial = useMemo(
    () => materials.find((item) => item.id === activeMaterialId) ?? null,
    [materials, activeMaterialId]
  );
  const hasProcessingMaterials = useMemo(
    () => materials.some((item) => item.status === "processing" || item.status === "queued"),
    [materials]
  );
  const collectedWordSet = useMemo(
    () =>
      new Set(
        wordCollections.map((item) => getWordCollectionKey(item)).filter(Boolean)
      ),
    [wordCollections]
  );
  const learningWordCollections = useMemo(
    () => wordCollections.filter((item) => collectionUsesLanguage(item, learningLanguage)),
    [learningLanguage, wordCollections]
  );

  const loadMaterials = useCallback(async () => {
    try {
      const data = await listMaterials();
      setLoadError(null);
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

  const loadWordCollections = useCallback(async (
    sort: WordCollectionSortMode = "collected_time_asc"
  ) => {
    const requestId = wordCollectionRequestIdRef.current + 1;
    wordCollectionRequestIdRef.current = requestId;
    setLoadingWordCollections(true);
    try {
      // Keep a complete in-memory index: the active material may retain a
      // language different from today's global preference. UI consumers below
      // still receive only the current learning-language slice.
      const data = await listWordCollections({ sort });
      if (requestId !== wordCollectionRequestIdRef.current) return;
      setWordCollections(data);
    } catch (error) {
      if (requestId !== wordCollectionRequestIdRef.current) return;
      setLoadError(error instanceof Error ? error.message : t("app.libraryLoadFailed"));
    } finally {
      if (requestId === wordCollectionRequestIdRef.current) {
        setLoadingWordCollections(false);
      }
    }
  }, [t]);

  useEffect(() => {
    void loadWordCollections();
  }, [loadWordCollections]);

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
      setLoadError(error instanceof Error ? error.message : t("app.practiceLoadFailed"));
      setSentences([]);
      setLatestEvaluations({});
    } finally {
      if (requestId === sentenceRequestIdRef.current) {
        setLoadingSentences(false);
      }
    }
  }, [t]);

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
    setActivePanel("practice");
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

  function handleSelectMaterial(materialId: number) {
    setActiveMaterialId(materialId);
    setActivePanel("practice");
  }

  function handleTextMaterialReady(materialId: number) {
    void loadMaterials();
    setActiveMaterialId(materialId);
    setActivePanel("practice");
  }

  const handleProvidersChanged = useCallback(() => {
    setProviderRevision((current) => current + 1);
  }, []);

  function handleWordCollected(collection: WordCollection) {
    const collectionKey = getWordCollectionKey(collection);
    setWordCollections((prev) => [
      collection,
      ...prev.filter((item) => getWordCollectionKey(item) !== collectionKey),
    ]);
  }

  function handleWordDeleted(collectionId: number) {
    setWordCollections((prev) => prev.filter((item) => item.id !== collectionId));
  }

  function closeFrontendWindow() {
    window.open("", "_self");
    window.close();
    window.location.replace("about:blank");
  }

  async function handleShutdown() {
    if (shuttingDown) return;

    const confirmed = window.confirm(t("app.closeConfirm"));
    if (!confirmed) return;

    setShuttingDown(true);
    try {
      const cleanupResult = await cleanupRecordingFiles();
      if (cleanupResult.failed_files.length > 0) {
        throw new Error(t("app.closeCleanupFailed"));
      }
      await shutdownBackend();
      closeFrontendWindow();
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t("app.closeFailed"));
      alert(error instanceof Error ? error.message : t("app.closeFailed"));
      setShuttingDown(false);
    }
  }

  return (
    <div className="app-shell">
      <AppHeader
        activePanel={activePanel}
        materialTitle={activeMaterial?.title ?? null}
        sentenceCount={sentences.length}
        onPanelChange={setActivePanel}
      />

      <MaterialDrawer
        open={materialDrawerOpen}
        materials={materials}
        activeId={activeMaterialId}
        onOpenChange={setMaterialDrawerOpen}
        onUploaded={handleUploaded}
        onSelect={handleSelectMaterial}
        onProcessed={handleProcessed}
        onDeleted={handleDeleted}
      />

      <main className="workspace">
        {loadError && (
          <div className="workspace-alert error-message" role="alert">
            <span>{loadError}</span>
            <button type="button" onClick={() => void loadMaterials()}>{t("app.retry")}</button>
          </div>
        )}
        <section
          id="workspace-panel"
          className={`workspace-panel panel-${activePanel}`}
          role={activePanel === "settings" ? undefined : "tabpanel"}
          aria-labelledby={activePanel === "settings" ? undefined : `nav-${activePanel}`}
        >
          {activePanel === "textGenerator" && <TextGeneratorPanel collections={wordCollections} defaultLanguage={learningLanguage} defaultTranslationLanguage={translationLanguage} providerRefreshToken={providerRevision} onMaterialReady={handleTextMaterialReady} />}
          {activePanel === "textGenerator" ? null : activePanel === "wordLibrary" ? (
            <WordCollectionPanel
              collections={learningWordCollections}
              loading={loadingWordCollections}
              onRefresh={loadWordCollections}
              onDeleted={handleWordDeleted}
            />
          ) : activePanel === "settings" ? (
            <div className="secondary-workspace">
              <div className="secondary-workspace-header">
                <div>
                  <span className="eyebrow">Shadowing</span>
                  <h2>{t("settings.title")}</h2>
                </div>
                <button
                  type="button"
                  className="danger-button"
                  disabled={shuttingDown}
                  onClick={handleShutdown}
                >
                  <Power size={18} weight="bold" />
                  {shuttingDown ? t("app.closing") : t("app.close")}
                </button>
              </div>
              <SettingsPanel onProvidersChanged={handleProvidersChanged} />
            </div>
          ) : loadingSentences ? (
            <div className="workspace-state"><p>{t("app.sentencesLoading")}</p></div>
          ) : (
            <SentenceTrainer
              material={activeMaterial}
              sentences={sentences}
              latestEvaluations={latestEvaluations}
              collectedWordSet={collectedWordSet}
              onWordCollected={handleWordCollected}
              onRefreshWordCollections={loadWordCollections}
            />
          )}
        </section>
      </main>
    </div>
  );
}
