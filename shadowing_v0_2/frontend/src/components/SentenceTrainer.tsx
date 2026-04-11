import { useEffect, useMemo, useRef, useState } from "react";
import { apiBase } from "../lib/api";
import type { Evaluation, Material, Sentence } from "../types";
import EvaluationPanel from "./EvaluationPanel";
import RecorderPanel from "./RecorderPanel";

interface Props {
  material: Material | null;
  sentences: Sentence[];
}

type SyncSource = "audio" | "video" | "internal";

function getSentenceStart(sentence: Sentence): number {
  return sentence.original_start_time ?? sentence.start_time;
}

function getSentenceEnd(sentence: Sentence): number {
  return sentence.original_end_time ?? sentence.end_time;
}

function getSentenceDuration(sentence: Sentence): number {
  if (sentence.clip_duration !== null && sentence.clip_duration > 0) {
    return sentence.clip_duration;
  }
  return Math.max(getSentenceEnd(sentence) - getSentenceStart(sentence), 0);
}

function locateSentenceIndex(sentences: Sentence[], time: number): number {
  if (sentences.length === 0) return 0;

  for (let i = 0; i < sentences.length; i += 1) {
    const sentence = sentences[i];
    const start = getSentenceStart(sentence);
    const end = getSentenceEnd(sentence);
    const isLast = i === sentences.length - 1;
    if (time >= start && (time < end || (isLast && time <= end + 0.05))) {
      return i;
    }
  }

  if (time < getSentenceStart(sentences[0])) return 0;
  return sentences.length - 1;
}

export default function SentenceTrainer({ material, sentences }: Props) {
  const [index, setIndex] = useState(0);
  const [loop, setLoop] = useState(false);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [processingDots, setProcessingDots] = useState(0);
  const [playbackTime, setPlaybackTime] = useState(0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const stopTimerRef = useRef<number | null>(null);
  const syncSourceRef = useRef<SyncSource | null>(null);

  const currentSentence = useMemo(
    () => (sentences.length > 0 ? sentences[index] : null),
    [sentences, index]
  );

  const timelineDuration = useMemo(() => {
    const materialDuration = material?.duration ?? 0;
    const lastSentence = sentences[sentences.length - 1];
    const sentenceEnd = lastSentence ? getSentenceEnd(lastSentence) : 0;
    return Math.max(materialDuration, sentenceEnd, 0);
  }, [material?.duration, sentences]);

  useEffect(() => {
    setIndex(0);
    setEvaluation(null);
    setPlaybackTime(0);
    if (stopTimerRef.current) {
      window.clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
  }, [material?.id]);

  useEffect(() => {
    setIndex((prev) => Math.min(prev, Math.max(sentences.length - 1, 0)));
  }, [sentences.length]);

  useEffect(
    () => () => {
      if (stopTimerRef.current) {
        window.clearTimeout(stopTimerRef.current);
        stopTimerRef.current = null;
      }
    },
    []
  );

  function syncTimeline(targetTime: number, source: SyncSource) {
    const maxTime = Math.max(timelineDuration, 0);
    const clampedTime = Math.min(Math.max(targetTime, 0), maxTime > 0 ? maxTime : targetTime);
    setPlaybackTime(clampedTime);

    if (sentences.length > 0) {
      const nextIndex = locateSentenceIndex(sentences, clampedTime);
      setIndex((prev) => (prev === nextIndex ? prev : nextIndex));
    }

    const audio = audioRef.current;
    const video = videoRef.current;
    const tolerance = 0.2;
    syncSourceRef.current = source;
    try {
      if (audio && source !== "audio" && Math.abs(audio.currentTime - clampedTime) > tolerance) {
        audio.currentTime = clampedTime;
      }
      if (video && source !== "video" && Math.abs(video.currentTime - clampedTime) > tolerance) {
        video.currentTime = clampedTime;
      }
    } finally {
      syncSourceRef.current = null;
    }
  }

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

    const audio = new Audio(`${apiBase}/api/materials/${material.id}/audio`);
    audio.preload = "auto";
    audioRef.current = audio;

    const handleTimeUpdate = () => {
      if (syncSourceRef.current === "video") return;
      syncTimeline(audio.currentTime, "audio");
    };

    const handleSeeking = () => {
      syncTimeline(audio.currentTime, "audio");
    };

    const handlePlay = () => {
      if (material.file_type !== "video") return;
      const video = videoRef.current;
      if (!video || !video.paused) return;
      void video.play().catch(() => undefined);
    };

    const handlePause = () => {
      const video = videoRef.current;
      if (!video || video.paused) return;
      video.pause();
    };

    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("seeking", handleSeeking);
    audio.addEventListener("play", handlePlay);
    audio.addEventListener("pause", handlePause);

    return () => {
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("seeking", handleSeeking);
      audio.removeEventListener("play", handlePlay);
      audio.removeEventListener("pause", handlePause);
      audio.pause();
      if (audioRef.current === audio) {
        audioRef.current = null;
      }
    };
  }, [material?.id, material?.status, material?.file_type, sentences, timelineDuration]);

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
    const video = videoRef.current;
    const start = getSentenceStart(currentSentence);
    const durationMs = Math.max(getSentenceDuration(currentSentence) * 1000, 300);

    if (stopTimerRef.current) {
      window.clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }

    syncTimeline(start, "internal");
    const playTasks: Array<Promise<unknown>> = [];
    playTasks.push(audio.play());
    if (material?.file_type === "video" && video) {
      playTasks.push(video.play());
    }
    await Promise.allSettled(playTasks);

    stopTimerRef.current = window.setTimeout(() => {
      audio.pause();
      if (video) video.pause();
      if (loop) {
        void playCurrent();
      }
    }, durationMs);
  }

  function jumpToSentence(nextIndex: number) {
    if (sentences.length === 0) return;
    setEvaluation(null);
    const safeIndex = Math.min(Math.max(nextIndex, 0), sentences.length - 1);
    setIndex(safeIndex);
    syncTimeline(getSentenceStart(sentences[safeIndex]), "internal");
  }

  function prevSentence() {
    jumpToSentence(index - 1);
  }

  function nextSentence() {
    jumpToSentence(index + 1);
  }

  function handleTimelineChange(value: string) {
    const parsed = Number(value);
    if (Number.isNaN(parsed)) return;
    syncTimeline(parsed, "internal");
  }

  async function handleVideoPlay() {
    const audio = audioRef.current;
    if (!audio || !audio.paused) return;
    await audio.play().catch(() => undefined);
  }

  function handleVideoPause() {
    const audio = audioRef.current;
    if (!audio || audio.paused) return;
    audio.pause();
  }

  function handleVideoTimeUpdate() {
    const video = videoRef.current;
    if (!video) return;
    if (syncSourceRef.current === "audio") return;
    syncTimeline(video.currentTime, "video");
  }

  function handleVideoSeeking() {
    const video = videoRef.current;
    if (!video) return;
    syncTimeline(video.currentTime, "video");
  }

  if (!material) {
    return (
      <div className="card">
        <h2>3. 练习区</h2>
        <p className="muted">处理好素材后，点击左侧素材开始练习。</p>
      </div>
    );
  }

  if (material.status === "processing") {
    const dots = ".".repeat(processingDots);
    return (
      <div className="card">
        <h2>3. 练习区</h2>
        <p className="muted">当前素材正在后台处理中{dots}</p>
        <p className="muted">你可以切换到其他素材继续练习，当前处理不会中断。</p>
      </div>
    );
  }

  if (material.status === "failed") {
    return (
      <div className="card">
        <h2>3. 练习区</h2>
        <p className="muted">当前素材处理失败，请点击“重新处理”再试一次。</p>
      </div>
    );
  }

  if (material.status !== "ready") {
    return (
      <div className="card">
        <h2>3. 练习区</h2>
        <p className="muted">当前素材还没有处理完成，先点击“开始处理”。</p>
      </div>
    );
  }

  if (!currentSentence) {
    return (
      <div className="card">
        <h2>3. 练习区</h2>
        <p className="muted">当前素材没有句子数据。</p>
      </div>
    );
  }

  const sentenceStart = getSentenceStart(currentSentence);
  const sentenceEnd = getSentenceEnd(currentSentence);

  return (
    <div className="trainer-grid">
      {material.file_type === "video" && (
        <div className="card video-card">
          <h2>3. 视频播放</h2>
          <video
            ref={videoRef}
            className="material-video"
            controls
            preload="metadata"
            src={`${apiBase}/api/materials/${material.id}/video`}
            onPlay={() => {
              void handleVideoPlay();
            }}
            onPause={handleVideoPause}
            onTimeUpdate={handleVideoTimeUpdate}
            onSeeking={handleVideoSeeking}
          />
          <p className="muted">拖动视频进度条会同步更新下方音频练习进度。</p>
        </div>
      )}

      <div className="card">
        <h2>4. 逐句播放 + 跟读</h2>
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
              onChange={(event) => setLoop(event.target.checked)}
            />
            单句循环
          </label>
        </div>

        <div className="progress-row">
          <span>{playbackTime.toFixed(2)}s</span>
          <span>{timelineDuration.toFixed(2)}s</span>
        </div>
        <input
          className="timeline-slider"
          type="range"
          min={0}
          max={timelineDuration > 0 ? timelineDuration : 0}
          step={0.01}
          value={Math.min(playbackTime, timelineDuration)}
          onChange={(event) => handleTimelineChange(event.target.value)}
          disabled={timelineDuration <= 0}
        />

        <div className="time-row">
          <span>{sentenceStart.toFixed(2)}s</span>
          <span>{sentenceEnd.toFixed(2)}s</span>
        </div>
      </div>

      <RecorderPanel sentence={currentSentence} onEvaluated={setEvaluation} />
      <EvaluationPanel evaluation={evaluation} />
    </div>
  );
}
