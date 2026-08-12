import { useEffect, useRef, useState } from "react";
import { useLanguage } from "../i18n/LanguageContext";
import { stageLabel } from "../i18n/statusLabels";
import { getJob, retryJob, uploadRecording } from "../lib/api";
import type { Evaluation, Sentence } from "../types";

const MAX_SECONDS = 90;
interface Props { sentence: Sentence | null; onEvaluated: (evaluation: Evaluation) => void; }

export default function RecorderPanel({ sentence, onEvaluated }: Props) {
  const { t } = useLanguage();
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const stopTimerRef = useRef<number | null>(null);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

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
    if (!jobId) return;
    let active = true;
    const poll = async () => {
      try {
        const job = await getJob(jobId);
        if (!active) return;
        setStage(job.stage); setProgress(job.progress);
        if (job.status === "succeeded") {
          const evaluation = job.result?.evaluation;
          if (evaluation) onEvaluated(evaluation);
          setJobId(null); setStage("completed");
        } else if (job.status === "failed" || job.status === "cancelled") {
          setError(job.error_message || t("recorder.scoringFailed"));
        }
      } catch (pollError) {
        if (active) setError(pollError instanceof Error ? pollError.message : t("recorder.scoringProgressFailed"));
      }
    };
    void poll();
    const interval = window.setInterval(() => void poll(), 1000);
    return () => { active = false; window.clearInterval(interval); };
  }, [jobId, onEvaluated, t]);

  function clearPreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null); setBlob(null); setError(null); setElapsed(0);
  }

  async function startRecording() {
    if (!sentence) return;
    clearPreview(); setError(null); setProgress(0); setStage(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      streamRef.current = stream; recorderRef.current = recorder; chunksRef.current = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        if (stopTimerRef.current) window.clearTimeout(stopTimerRef.current);
        const nextBlob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        setBlob(nextBlob); setPreviewUrl(URL.createObjectURL(nextBlob)); setRecording(false);
        stream.getTracks().forEach((track) => track.stop()); streamRef.current = null;
      };
      recorder.start(); setRecording(true);
      stopTimerRef.current = window.setTimeout(() => stopRecording(), MAX_SECONDS * 1000);
    } catch (mediaError) {
      setError(mediaError instanceof Error
        ? t("recorder.microphoneFailed", { message: mediaError.message })
        : t("recorder.microphoneFailedGeneric"));
    }
  }

  function stopRecording() { if (recorderRef.current?.state === "recording") recorderRef.current.stop(); }

  async function submitRecording() {
    if (!sentence || !blob) return;
    try {
      setError(null); setStage("uploading"); setProgress(5);
      const accepted = await uploadRecording(sentence.id, blob);
      setJobId(accepted.job_id); setStage("queued");
    } catch (uploadError) { setError(uploadError instanceof Error ? uploadError.message : t("recorder.uploadFailed")); }
  }

  async function retry() {
    if (!jobId) return;
    try { const job = await retryJob(jobId); setError(null); setStage(job.stage); setProgress(job.progress); }
    catch (retryError) { setError(retryError instanceof Error ? retryError.message : t("recorder.retryFailed")); }
  }

  return <div className="card">
    <h3>{t("recorder.title")}</h3>
    <div className="row gap">
      <button type="button" disabled={!sentence || recording || !!jobId} onClick={() => void startRecording()}>{recording ? t("recorder.recording") : t("recorder.start")}</button>
      <button type="button" disabled={!recording} onClick={stopRecording}>{t("recorder.stop")}</button>
      {blob && !jobId && <button type="button" onClick={() => void submitRecording()}>{t("recorder.submit")}</button>}
      {blob && !recording && !jobId && <button type="button" onClick={clearPreview}>{t("recorder.rerecord")}</button>}
      {error && jobId && <button type="button" onClick={() => void retry()}>{t("recorder.retry")}</button>}
    </div>
    {recording && <p className="muted">{t("recorder.recordingTime", { elapsed, maxSeconds: MAX_SECONDS })}</p>}
    {previewUrl && <audio controls src={previewUrl} />}
    {jobId && <p className="muted">{t("recorder.scoringProgress", { stage: stageLabel(t, stage), progress })}</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    {!recording && !blob && !jobId && !error && <p className="muted">{t("recorder.maxDuration", { maxSeconds: MAX_SECONDS })}</p>}
  </div>;
}
