import { useEffect, useMemo, useRef, useState } from "react";
import { apiBase } from "../lib/api";
import type { Evaluation, Material, Sentence } from "../types";
import EvaluationPanel from "./EvaluationPanel";
import RecorderPanel from "./RecorderPanel";

interface Props {
  material: Material | null;
  sentences: Sentence[];
}

export default function SentenceTrainer({ material, sentences }: Props) {
  const [index, setIndex] = useState(0);
  const [loop, setLoop] = useState(false);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [processingDots, setProcessingDots] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopTimerRef = useRef<number | null>(null);

  const currentSentence = useMemo(
    () => (sentences.length > 0 ? sentences[index] : null),
    [sentences, index]
  );

  useEffect(() => {
    setIndex(0);
    setEvaluation(null);
  }, [material?.id]);

  useEffect(() => {
    if (!material?.id || material.status !== "ready") {
      if (stopTimerRef.current) {
        window.clearTimeout(stopTimerRef.current);
        stopTimerRef.current = null;
      }
      audioRef.current?.pause();
      audioRef.current = null;
      return;
    }
    audioRef.current = new Audio(`${apiBase}/api/materials/${material.id}/audio`);
    return () => {
      if (stopTimerRef.current) {
        window.clearTimeout(stopTimerRef.current);
        stopTimerRef.current = null;
      }
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, [material?.id, material?.status]);

  useEffect(() => {
    if (material?.status !== "processing") {
      setProcessingDots(0);
      return;
    }
    const timer = window.setInterval(() => {
      setProcessingDots((prev) => (prev + 1) % 4);
    }, 500);
    return () => window.clearInterval(timer);
  }, [material?.id, material?.status]);

  async function playCurrent() {
    if (!audioRef.current || !currentSentence) return;
    const audio = audioRef.current;

    if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current);

    audio.currentTime = currentSentence.start_time;
    await audio.play();

    const durationMs = Math.max((currentSentence.end_time - currentSentence.start_time) * 1000, 300);
    stopTimerRef.current = window.setTimeout(async () => {
      audio.pause();
      if (loop) {
        await playCurrent();
      }
    }, durationMs);
  }

  function prevSentence() {
    setEvaluation(null);
    setIndex((prev) => Math.max(prev - 1, 0));
  }

  function nextSentence() {
    setEvaluation(null);
    setIndex((prev) => Math.min(prev + 1, Math.max(sentences.length - 1, 0)));
  }

  if (!material) {
    return (
      <div className="card">
        <h2>3. 训练区</h2>
        <p className="muted">处理好素材后，点击左侧素材开始训练。</p>
      </div>
    );
  }

  if (material.status === "processing") {
    const dots = ".".repeat(processingDots);
    return (
      <div className="card">
        <h2>3. 训练区</h2>
        <p className="muted">当前素材正在后台处理中{dots}</p>
        <p className="muted">你可以切换到其他素材继续训练，当前处理不会中断。</p>
      </div>
    );
  }

  if (material.status === "failed") {
    return (
      <div className="card">
        <h2>3. 训练区</h2>
        <p className="muted">当前素材处理失败，请点击“重新处理”再试一次。</p>
      </div>
    );
  }

  if (material.status !== "ready") {
    return (
      <div className="card">
        <h2>3. 训练区</h2>
        <p className="muted">当前素材还没处理完成，先点击“开始处理”。</p>
      </div>
    );
  }

  if (!currentSentence) {
    return (
      <div className="card">
        <h2>3. 训练区</h2>
        <p className="muted">当前素材没有句子数据。</p>
      </div>
    );
  }

  return (
    <div className="trainer-grid">
      <div className="card">
        <h2>3. 逐句播放 + 跟读</h2>
        <div className="sentence-badge">
          第 {currentSentence.display_order} / {sentences.length} 句
        </div>
        <div className="sentence-text">{currentSentence.source_text}</div>
        <div className="sentence-translation">{currentSentence.translation ?? "暂无翻译"}</div>

        <div className="row gap wrap">
          <button type="button" onClick={prevSentence}>上一句</button>
          <button type="button" onClick={playCurrent}>播放当前句</button>
          <button type="button" onClick={nextSentence}>下一句</button>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={loop}
              onChange={(e) => setLoop(e.target.checked)}
            />
            单句循环
          </label>
        </div>

        <div className="time-row">
          <span>{currentSentence.start_time.toFixed(2)}s</span>
          <span>{currentSentence.end_time.toFixed(2)}s</span>
        </div>
      </div>

      <RecorderPanel sentence={currentSentence} onEvaluated={setEvaluation} />
      <EvaluationPanel evaluation={evaluation} />
    </div>
  );
}
