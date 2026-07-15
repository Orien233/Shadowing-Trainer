import { useEffect, useRef, useState } from "react";
import { getJob, retryJob, uploadRecording } from "../lib/api";
import type { Evaluation, Sentence } from "../types";

const MAX_SECONDS = 90;

interface Props { sentence: Sentence | null; onEvaluated: (evaluation: Evaluation) => void; }

export default function RecorderPanel({ sentence, onEvaluated }: Props) {
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
          setError(job.error_message || "Scoring failed. You can retry it.");
        }
      } catch (pollError) {
        if (active) setError(pollError instanceof Error ? pollError.message : "Could not check scoring progress.");
      }
    };
    void poll();
    const interval = window.setInterval(() => void poll(), 1000);
    return () => { active = false; window.clearInterval(interval); };
  }, [jobId, onEvaluated]);

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
      setError(mediaError instanceof Error ? `Microphone permission failed: ${mediaError.message}` : "Microphone permission failed.");
    }
  }

  function stopRecording() { if (recorderRef.current?.state === "recording") recorderRef.current.stop(); }

  async function submitRecording() {
    if (!sentence || !blob) return;
    try {
      setError(null); setStage("uploading"); setProgress(5);
      const accepted = await uploadRecording(sentence.id, blob);
      setJobId(accepted.job_id); setStage("queued");
    } catch (uploadError) { setError(uploadError instanceof Error ? uploadError.message : "Could not upload recording."); }
  }

  async function retry() {
    if (!jobId) return;
    try { const job = await retryJob(jobId); setError(null); setStage(job.stage); setProgress(job.progress); }
    catch (retryError) { setError(retryError instanceof Error ? retryError.message : "Retry failed."); }
  }

  return <div className="card">
    <h3>跟读录音</h3>
    <div className="row gap">
      <button type="button" disabled={!sentence || recording || !!jobId} onClick={() => void startRecording()}>{recording ? "录音中" : "开始录音"}</button>
      <button type="button" disabled={!recording} onClick={stopRecording}>停止录音</button>
      {blob && !jobId && <button type="button" onClick={() => void submitRecording()}>提交评分</button>}
      {blob && !recording && !jobId && <button type="button" onClick={clearPreview}>重录</button>}
      {error && jobId && <button type="button" onClick={() => void retry()}>重试评分</button>}
    </div>
    {recording && <p className="muted">录音中：{elapsed}s / {MAX_SECONDS}s</p>}
    {previewUrl && <audio controls src={previewUrl} />}
    {jobId && <p className="muted">评分任务：{stage || "queued"}（{progress}%）</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    {!recording && !blob && !jobId && !error && <p className="muted">最长录音时间为 90 秒。</p>}
  </div>;
}
