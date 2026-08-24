import { useEffect, useRef, useState } from "react";
import {
  ArrowCounterClockwise,
  ArrowsLeftRight,
  CheckCircle,
  Headphones,
  Microphone,
  Record,
  SpinnerGap,
  Stop,
} from "@phosphor-icons/react";
import { useLanguage } from "../../../i18n/LanguageContext";
import { stageLabel } from "../../../i18n/statusLabels";
import { apiBase, getJob, retryJob, uploadRecording } from "../../../lib/api";
import type { Evaluation, Sentence } from "../../../types";

const MAX_SECONDS = 90;

interface Props {
  sentence: Sentence | null;
  evaluation: Evaluation | null;
  onEvaluated: (evaluation: Evaluation) => void;
  onPlayReference: () => void | Promise<void>;
}

function formatDuration(seconds: number | null | undefined) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return null;
  const safeSeconds = Math.max(seconds, 0);
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remainder.toFixed(2).padStart(5, "0")}`;
}

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable);
}

export default function RecorderPanel({ sentence, evaluation, onEvaluated, onPlayReference }: Props) {
  const { t } = useLanguage();
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const stopTimerRef = useRef<number | null>(null);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const savedRecordingUrl = evaluation?.recording_id
    ? `${apiBase}/api/recordings/${evaluation.recording_id}/audio`
    : null;
  const activePreviewUrl = previewUrl ?? savedRecordingUrl;
  const readyDuration = previewUrl ? elapsed : evaluation?.recording_duration;

  useEffect(() => () => {
    if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => setElapsed((value) => Math.min(value + 1, MAX_SECONDS)), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  useEffect(() => {
    setBlob(null);
    setPreviewUrl(null);
    setElapsed(0);
    setJobId(null);
    setStage(null);
    setProgress(0);
    setError(null);
  }, [sentence?.id]);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    const poll = async () => {
      try {
        const job = await getJob(jobId);
        if (!active) return;
        setStage(job.stage);
        setProgress(job.progress);
        if (job.status === "succeeded") {
          const evaluation = job.result?.evaluation;
          if (evaluation) onEvaluated(evaluation);
          setJobId(null);
          setStage("completed");
        } else if (job.status === "failed" || job.status === "cancelled") {
          setError(job.error_message || t("recorder.scoringFailed"));
        }
      } catch (pollError) {
        if (active) {
          setError(pollError instanceof Error ? pollError.message : t("recorder.scoringProgressFailed"));
        }
      }
    };
    void poll();
    const interval = window.setInterval(() => void poll(), 1000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [jobId, onEvaluated, t]);

  function clearPreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setBlob(null);
    setError(null);
    setElapsed(0);
    setStage(null);
    setProgress(0);
  }

  async function startRecording() {
    if (!sentence) return;
    clearPreview();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      streamRef.current = stream;
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current);
        const nextBlob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        setBlob(nextBlob);
        setPreviewUrl(URL.createObjectURL(nextBlob));
        setRecording(false);
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      };
      recorder.start();
      setRecording(true);
      stopTimerRef.current = window.setTimeout(() => stopRecording(), MAX_SECONDS * 1000);
    } catch (mediaError) {
      setError(mediaError instanceof Error
        ? t("recorder.microphoneFailed", { message: mediaError.message })
        : t("recorder.microphoneFailedGeneric"));
    }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  async function submitRecording() {
    if (!sentence || !blob) return;
    try {
      setError(null);
      setStage("uploading");
      setProgress(5);
      const accepted = await uploadRecording(sentence.id, blob);
      setJobId(accepted.job_id);
      setStage("queued");
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : t("recorder.uploadFailed"));
    }
  }

  async function compareRecording() {
    if (blob) {
      await submitRecording();
      return;
    }
    const audio = previewAudioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    await audio.play().catch(() => undefined);
  }

  function rerecord() {
    if (blob) clearPreview();
    void startRecording();
  }

  async function retry() {
    if (!jobId) return;
    try {
      const job = await retryJob(jobId);
      setError(null);
      setStage(job.stage);
      setProgress(job.progress);
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : t("recorder.retryFailed"));
    }
  }

  useEffect(() => {
    function handleKeyboardShortcut(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) return;
      if (event.code === "Space") {
        event.preventDefault();
        if (recording) {
          stopRecording();
        } else if (!jobId) {
          void startRecording();
        }
        return;
      }
      if (event.key.toLowerCase() === "c" && activePreviewUrl && !jobId && !recording) {
        event.preventDefault();
        void compareRecording();
      }
      if (event.key.toLowerCase() === "r" && activePreviewUrl && !jobId && !recording) {
        event.preventDefault();
        rerecord();
      }
    }
    window.addEventListener("keydown", handleKeyboardShortcut);
    return () => window.removeEventListener("keydown", handleKeyboardShortcut);
  }, [activePreviewUrl, blob, jobId, recording, sentence, previewUrl]);

  const isScoring = Boolean(jobId && !error);
  const canCompare = Boolean(activePreviewUrl && !recording && !jobId);

  return (
    <section className="recording-console" aria-label={t("recorder.title")}>
      <div className="practice-action-dock">
        <button
          type="button"
          className="practice-action reference-action"
          disabled={!sentence}
          onClick={() => void onPlayReference()}
        >
          <Headphones size={21} weight="regular" />
          <span>{t("recorder.listenReference")}</span>
          <kbd>L</kbd>
        </button>

        <button
          id="sentence-record-action"
          type="button"
          className={`practice-action record-action ${recording ? "recording" : ""}`}
          disabled={!sentence || isScoring}
          onClick={() => recording ? stopRecording() : void startRecording()}
        >
          {recording
            ? <Stop size={22} weight="fill" />
            : <Microphone size={22} weight="fill" />}
          <span>{recording ? t("recorder.stop") : t("recorder.start")}</span>
          <kbd>Space</kbd>
        </button>

        <button
          type="button"
          className="practice-action compare-action"
          disabled={!canCompare}
          onClick={() => void compareRecording()}
        >
          <ArrowsLeftRight size={21} weight="regular" />
          <span>{t("recorder.compare")}</span>
          <kbd>C</kbd>
        </button>
      </div>

      <div className="recording-status" aria-live="polite">
        {recording && (
          <span className="recording-live">
            <Record size={16} weight="fill" aria-hidden="true" />
            {t("recorder.recordingTime", { elapsed, maxSeconds: MAX_SECONDS })}
          </span>
        )}
        {!recording && activePreviewUrl && (
          <>
            <span className="recording-ready">
              <CheckCircle size={18} weight="fill" />
              {t("recorder.recordingReady")}
              {formatDuration(readyDuration) && <time>{formatDuration(readyDuration)}</time>}
            </span>
            <audio ref={previewAudioRef} className="recording-preview" preload="metadata" src={activePreviewUrl} />
            {!jobId && (
              <button type="button" className="text-button" onClick={rerecord}>
                <ArrowCounterClockwise size={16} weight="bold" />
                {t("recorder.rerecord")}
                <kbd>R</kbd>
              </button>
            )}
          </>
        )}
        {isScoring && (
          <span className="scoring-progress">
            <SpinnerGap size={18} weight="bold" />
            {t("recorder.scoringProgress", { stage: stageLabel(t, stage), progress })}
          </span>
        )}
        {!recording && !activePreviewUrl && !jobId && !error && (
          <span className="muted">{t("recorder.maxDuration", { maxSeconds: MAX_SECONDS })}</span>
        )}
        {error && (
          <>
            <span role="alert" className="error-message">{error}</span>
            {jobId && (
              <button type="button" className="text-button" onClick={() => void retry()}>
                {t("recorder.retry")}
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}
