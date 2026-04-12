import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiBase } from "../lib/api";
import type { Evaluation, Material, Sentence } from "../types";
import EvaluationPanel from "./EvaluationPanel";
import RecorderPanel from "./RecorderPanel";

interface Props {
  material: Material | null;
  sentences: Sentence[];
}

type SegmentType = "sentence" | "gap";

interface TimelineSegment {
  key: string;
  type: SegmentType;
  start: number;
  end: number;
  duration: number;
  sentence: Sentence | null;
  displayOrder: number;
}

const SEGMENT_EPSILON = 0.05;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function getSentenceStart(sentence: Sentence): number {
  return sentence.original_start_time ?? sentence.start_time;
}

function getSentenceEnd(sentence: Sentence): number {
  return sentence.original_end_time ?? sentence.end_time;
}

function buildTimelineSegments(sentences: Sentence[], timelineDuration: number): TimelineSegment[] {
  const segments: TimelineSegment[] = [];
  let cursor = 0;
  let gapOrder = 0;

  for (const sentence of sentences) {
    const sentenceStart = Math.max(getSentenceStart(sentence), 0);
    const sentenceEnd = Math.max(getSentenceEnd(sentence), sentenceStart + SEGMENT_EPSILON);

    if (sentenceStart - cursor > SEGMENT_EPSILON) {
      gapOrder += 1;
      segments.push({
        key: `gap-${gapOrder}-${cursor.toFixed(3)}`,
        type: "gap",
        start: cursor,
        end: sentenceStart,
        duration: sentenceStart - cursor,
        sentence: null,
        displayOrder: gapOrder,
      });
    }

    const sentenceDuration = Math.max(sentenceEnd - sentenceStart, SEGMENT_EPSILON);

    segments.push({
      key: `sentence-${sentence.id}`,
      type: "sentence",
      start: sentenceStart,
      end: sentenceStart + sentenceDuration,
      duration: sentenceDuration,
      sentence,
      displayOrder: sentence.display_order,
    });

    cursor = Math.max(cursor, sentenceStart + sentenceDuration);
  }

  if (timelineDuration - cursor > SEGMENT_EPSILON) {
    gapOrder += 1;
    segments.push({
      key: `gap-${gapOrder}-${cursor.toFixed(3)}`,
      type: "gap",
      start: cursor,
      end: timelineDuration,
      duration: timelineDuration - cursor,
      sentence: null,
      displayOrder: gapOrder,
    });
  }

  if (segments.length === 0 && timelineDuration > SEGMENT_EPSILON) {
    segments.push({
      key: "gap-1-0",
      type: "gap",
      start: 0,
      end: timelineDuration,
      duration: timelineDuration,
      sentence: null,
      displayOrder: 1,
    });
  }

  return segments;
}

function locateSegmentIndex(segments: TimelineSegment[], time: number): number {
  if (segments.length === 0) return 0;

  for (let i = 0; i < segments.length; i += 1) {
    const segment = segments[i];
    const isLast = i === segments.length - 1;
    if (time >= segment.start && (time < segment.end || (isLast && time <= segment.end + SEGMENT_EPSILON))) {
      return i;
    }
  }

  if (time < segments[0].start) return 0;
  return segments.length - 1;
}

export default function SentenceTrainer({ material, sentences }: Props) {
  const [segmentIndex, setSegmentIndex] = useState(0);
  const [loop, setLoop] = useState(false);
  const [autoPlay, setAutoPlay] = useState(false);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [processingDots, setProcessingDots] = useState(0);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [mediaDuration, setMediaDuration] = useState(0);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const stopTimerRef = useRef<number | null>(null);
  const loopRef = useRef(loop);
  const autoPlayRef = useRef(autoPlay);
  const timelineDurationRef = useRef(0);
  const segmentsRef = useRef<TimelineSegment[]>([]);

  const timelineDuration = useMemo(() => {
    const materialDuration = material?.duration ?? 0;
    const lastSentence = sentences[sentences.length - 1];
    const sentenceEnd = lastSentence ? getSentenceEnd(lastSentence) : 0;
    return Math.max(materialDuration, sentenceEnd, mediaDuration, 0);
  }, [material?.duration, mediaDuration, sentences]);

  const segments = useMemo(
    () => buildTimelineSegments(sentences, timelineDuration),
    [sentences, timelineDuration]
  );

  const currentSegment = useMemo(
    () => (segments.length > 0 ? segments[segmentIndex] : null),
    [segments, segmentIndex]
  );
  const currentSentence = currentSegment?.sentence ?? null;
  const isGapSegment = currentSegment?.type === "gap";

  const currentSegmentPlaybackTime = useMemo(() => {
    if (!currentSegment) return 0;
    return clamp(playbackTime - currentSegment.start, 0, currentSegment.duration);
  }, [currentSegment, playbackTime]);

  const clearStopTimer = useCallback(() => {
    if (stopTimerRef.current) {
      window.clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
  }, []);

  const getMediaElement = useCallback((): HTMLMediaElement | null => {
    if (material?.file_type === "video") {
      return videoRef.current;
    }
    return audioRef.current;
  }, [material?.file_type]);

  const syncFromGlobalTime = useCallback((targetTime: number) => {
    const maxTime = timelineDurationRef.current;
    const clampedGlobalTime = maxTime > 0 ? clamp(targetTime, 0, maxTime) : Math.max(targetTime, 0);

    setPlaybackTime(clampedGlobalTime);
    if (segmentsRef.current.length > 0) {
      const nextIndex = locateSegmentIndex(segmentsRef.current, clampedGlobalTime);
      setSegmentIndex((prev) => (prev === nextIndex ? prev : nextIndex));
    } else {
      setSegmentIndex(0);
    }
  }, []);

  const seekToGlobalTime = useCallback(
    (targetTime: number) => {
      const maxTime = timelineDurationRef.current;
      const clampedGlobalTime = maxTime > 0 ? clamp(targetTime, 0, maxTime) : Math.max(targetTime, 0);
      syncFromGlobalTime(clampedGlobalTime);

      const media = getMediaElement();
      if (!media) return;
      if (Math.abs(media.currentTime - clampedGlobalTime) <= SEGMENT_EPSILON) return;
      media.currentTime = clampedGlobalTime;
    },
    [getMediaElement, syncFromGlobalTime]
  );

  useEffect(() => {
    loopRef.current = loop;
  }, [loop]);

  useEffect(() => {
    autoPlayRef.current = autoPlay;
  }, [autoPlay]);

  useEffect(() => {
    timelineDurationRef.current = timelineDuration;
  }, [timelineDuration]);

  useEffect(() => {
    segmentsRef.current = segments;
  }, [segments]);

  useEffect(() => {
    setSegmentIndex(0);
    setEvaluation(null);
    setPlaybackTime(0);
    setMediaDuration(0);
    clearStopTimer();
    audioRef.current?.pause();
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
    }
  }, [clearStopTimer, material?.id]);

  useEffect(() => {
    setSegmentIndex((prev) => clamp(prev, 0, Math.max(segments.length - 1, 0)));
  }, [segments.length]);

  useEffect(() => {
    setEvaluation(null);
  }, [currentSegment?.key]);

  useEffect(
    () => () => {
      clearStopTimer();
    },
    [clearStopTimer]
  );

  useEffect(() => {
    if (!material?.id || material.status !== "ready" || material.file_type !== "audio") {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      return;
    }

    const audio = new Audio(`${apiBase}/api/materials/${material.id}/audio`);
    audio.preload = "metadata";
    audioRef.current = audio;

    const handleTimeUpdate = () => {
      syncFromGlobalTime(audio.currentTime);
    };
    const handleSeeking = () => {
      syncFromGlobalTime(audio.currentTime);
    };
    const handleLoadedMetadata = () => {
      if (Number.isFinite(audio.duration)) {
        setMediaDuration(audio.duration);
      }
    };
    const handlePause = () => {
      clearStopTimer();
    };

    audio.addEventListener("timeupdate", handleTimeUpdate);
    audio.addEventListener("seeking", handleSeeking);
    audio.addEventListener("loadedmetadata", handleLoadedMetadata);
    audio.addEventListener("pause", handlePause);

    return () => {
      audio.removeEventListener("timeupdate", handleTimeUpdate);
      audio.removeEventListener("seeking", handleSeeking);
      audio.removeEventListener("loadedmetadata", handleLoadedMetadata);
      audio.removeEventListener("pause", handlePause);
      audio.pause();
      if (audioRef.current === audio) {
        audioRef.current = null;
      }
    };
  }, [clearStopTimer, material?.file_type, material?.id, material?.status, syncFromGlobalTime]);

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

  const scheduleSegmentBoundary = useCallback(
    (segment: TimelineSegment, media: HTMLMediaElement) => {
      const playNextSegment = (): boolean => {
        const activeSegments = segmentsRef.current;
        let currentIndex = activeSegments.findIndex((item) => item.key === segment.key);
        if (currentIndex < 0) {
          currentIndex = locateSegmentIndex(activeSegments, segment.start + SEGMENT_EPSILON);
        }

        const nextIndex = currentIndex + 1;
        if (nextIndex >= activeSegments.length) {
          media.pause();
          return false;
        }

        const nextSegment = activeSegments[nextIndex];
        setSegmentIndex((prev) => (prev === nextIndex ? prev : nextIndex));
        seekToGlobalTime(nextSegment.start);
        void media.play().catch(() => undefined);
        scheduleSegmentBoundary(nextSegment, media);
        return true;
      };

      const tick = () => {
        if (media.paused) {
          clearStopTimer();
          return;
        }

        const remainingMediaSeconds = segment.end - media.currentTime;
        if (remainingMediaSeconds <= SEGMENT_EPSILON) {
          if (autoPlayRef.current) {
            playNextSegment();
            return;
          }

          if (segment.type === "gap") {
            playNextSegment();
            return;
          }

          const shouldLoopCurrentSegment = loopRef.current;
          if (shouldLoopCurrentSegment) {
            seekToGlobalTime(segment.start);
            void media.play().catch(() => undefined);
            stopTimerRef.current = window.setTimeout(tick, 40);
            return;
          }

          media.pause();
          seekToGlobalTime(segment.start);
          return;
        }

        const playbackRate = Math.max(media.playbackRate, 0.1);
        const remainingWallClockMs = (remainingMediaSeconds / playbackRate) * 1000;
        const nextTickMs = Math.min(Math.max(remainingWallClockMs, 40), 250);
        stopTimerRef.current = window.setTimeout(tick, nextTickMs);
      };

      clearStopTimer();
      tick();
    },
    [clearStopTimer, seekToGlobalTime]
  );

  const scheduleBoundaryForCurrentPlayback = useCallback(() => {
    const media = getMediaElement();
    if (!media || media.paused) {
      clearStopTimer();
      return;
    }

    const activeSegments = segmentsRef.current;
    if (activeSegments.length === 0) {
      clearStopTimer();
      return;
    }

    const activeIndex = locateSegmentIndex(activeSegments, media.currentTime);
    const activeSegment = activeSegments[activeIndex];
    setSegmentIndex((prev) => (prev === activeIndex ? prev : activeIndex));
    scheduleSegmentBoundary(activeSegment, media);
  }, [clearStopTimer, getMediaElement, scheduleSegmentBoundary]);

  function handleVideoPlay() {
    scheduleBoundaryForCurrentPlayback();
  }

  function handleVideoRateChange() {
    scheduleBoundaryForCurrentPlayback();
  }

  const playSegment = useCallback(
    async (segment: TimelineSegment) => {
      const media = getMediaElement();
      if (!media) return;

      clearStopTimer();
      seekToGlobalTime(segment.start);
      await media.play().catch(() => undefined);
      if (media.paused) return;
      scheduleSegmentBoundary(segment, media);
    },
    [clearStopTimer, getMediaElement, scheduleSegmentBoundary, seekToGlobalTime]
  );

  async function playCurrentSegment() {
    if (!currentSegment) return;
    await playSegment(currentSegment);
  }

  function jumpToSegment(nextIndex: number) {
    if (segments.length === 0) return;
    const safeIndex = clamp(nextIndex, 0, segments.length - 1);
    const targetSegment = segments[safeIndex];
    setSegmentIndex(safeIndex);
    void playSegment(targetSegment);
  }

  function prevSegment() {
    jumpToSegment(segmentIndex - 1);
  }

  function nextSegment() {
    jumpToSegment(segmentIndex + 1);
  }

  function handleLoopChange(checked: boolean) {
    if (checked) {
      setAutoPlay(false);
    }
    setLoop(checked);
  }

  function handleAutoPlayChange(checked: boolean) {
    if (checked) {
      setLoop(false);
    }
    setAutoPlay(checked);
  }

  function handleSegmentTimelineChange(value: string) {
    if (!currentSegment) return;
    const parsed = Number(value);
    if (Number.isNaN(parsed)) return;
    clearStopTimer();
    const localTime = clamp(parsed, 0, currentSegment.duration);
    seekToGlobalTime(currentSegment.start + localTime);
    scheduleBoundaryForCurrentPlayback();
  }

  function handleVideoTimeUpdate() {
    const video = videoRef.current;
    if (!video) return;
    syncFromGlobalTime(video.currentTime);
  }

  function handleVideoSeeking() {
    const video = videoRef.current;
    if (!video) return;
    clearStopTimer();
    syncFromGlobalTime(video.currentTime);
    if (!video.paused) {
      scheduleBoundaryForCurrentPlayback();
    }
  }

  function handleVideoPause() {
    clearStopTimer();
  }

  function handleVideoLoadedMetadata() {
    const video = videoRef.current;
    if (!video) return;
    if (!Number.isFinite(video.duration)) return;
    setMediaDuration(video.duration);
    if (Math.abs(video.currentTime - playbackTime) > SEGMENT_EPSILON) {
      video.currentTime = playbackTime;
    }
  }

  if (!material) {
    return (
      <div className="card">
        <h2>分句练习</h2>
        <p className="muted">Select a processed material from the left panel to start practicing.</p>
      </div>
    );
  }

  if (material.status === "processing") {
    const dots = ".".repeat(processingDots);
    return (
      <div className="card">
        <h2>分句练习</h2>
        <p className="muted">Current material is processing in the background{dots}</p>
        <p className="muted">You can switch to other materials while this one finishes.</p>
      </div>
    );
  }

  if (material.status === "failed") {
    return (
      <div className="card">
        <h2>分句练习</h2>
        <p className="muted">Processing failed. Re-run processing from the material "More" menu.</p>
      </div>
    );
  }

  if (material.status !== "ready") {
    return (
      <div className="card">
        <h2>分句练习</h2>
        <p className="muted">Current material is not ready yet.</p>
      </div>
    );
  }

  if (!currentSegment) {
    return (
      <div className="card">
        <h2>分句练习</h2>
        <p className="muted">No playable segment data found for this material.</p>
      </div>
    );
  }

  return (
    <div className="trainer-grid">
      {material.file_type === "video" && (
        <div className="card video-card">
          <h2>视频回放</h2>
          <div className="video-frame">
            <video
              ref={videoRef}
              className="material-video"
              controls
              preload="metadata"
              src={`${apiBase}/api/materials/${material.id}/video`}
              onPause={handleVideoPause}
              onPlay={handleVideoPlay}
              onRateChange={handleVideoRateChange}
              onTimeUpdate={handleVideoTimeUpdate}
              onSeeking={handleVideoSeeking}
              onLoadedMetadata={handleVideoLoadedMetadata}
            />
          </div>
        </div>
      )}

      <div className="card">
        <h2>分句练习</h2>
        <div className="sentence-badge">
          {isGapSegment
            ? `Silent Segment ${currentSegment.displayOrder}`
            : `Sentence ${currentSentence?.display_order ?? 0} / ${sentences.length}`}
        </div>

        <div className="sentence-text">
          {isGapSegment ? "[Silent Segment]" : currentSentence?.source_text}
        </div>
        {!isGapSegment && (
          <div className="sentence-translation">{currentSentence?.translation ?? "No translation yet."}</div>
        )}
        {isGapSegment && (
          <div className="sentence-translation muted">No spoken sentence detected in this time range.</div>
        )}

        <div className="row gap wrap">
          <button type="button" onClick={prevSegment}>Prev Segment</button>
          <button type="button" onClick={playCurrentSegment}>Play Current Segment</button>
          <button type="button" onClick={nextSegment}>Next Segment</button>
          {!isGapSegment && (
            <div className="row gap">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={autoPlay}
                  onChange={(event) => handleAutoPlayChange(event.target.checked)}
                />
                Auto Play
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={loop}
                  onChange={(event) => handleLoopChange(event.target.checked)}
                />
                Loop Segment
              </label>
            </div>
          )}
        </div>

        <div className="progress-row">
          <span>{currentSegmentPlaybackTime.toFixed(2)}s</span>
          <span>{currentSegment.duration.toFixed(2)}s</span>
        </div>
        <input
          className="timeline-slider"
          type="range"
          min={0}
          max={currentSegment.duration > 0 ? currentSegment.duration : 0}
          step={0.01}
          value={currentSegment.duration > 0 ? currentSegmentPlaybackTime : 0}
          onChange={(event) => handleSegmentTimelineChange(event.target.value)}
          disabled={currentSegment.duration <= 0}
        />

        <div className="time-row">
          <span>{currentSegment.start.toFixed(2)}s</span>
          <span>{currentSegment.end.toFixed(2)}s</span>
        </div>
        <p className="muted">
          Global Position: {playbackTime.toFixed(2)}s / {timelineDuration.toFixed(2)}s
        </p>
      </div>

      {!isGapSegment && <RecorderPanel sentence={currentSentence} onEvaluated={setEvaluation} />}
      {!isGapSegment && <EvaluationPanel evaluation={evaluation} />}
    </div>
  );
}
