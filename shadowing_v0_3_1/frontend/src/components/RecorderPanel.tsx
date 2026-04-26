import { useRef, useState } from "react";
import { uploadRecording } from "../lib/api";
import type { Evaluation, Sentence } from "../types";

interface Props {
  sentence: Sentence | null;
  onEvaluated: (evaluation: Evaluation) => void;
}

export default function RecorderPanel({ sentence, onEvaluated }: Props) {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function startRecording() {
    if (!sentence) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    recorderRef.current = mediaRecorder;
    chunksRef.current = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      setUploading(true);
      try {
        const evaluation = await uploadRecording(sentence.id, blob);
        onEvaluated(evaluation);
      } catch (error) {
        alert(error);
      } finally {
        setUploading(false);
        stream.getTracks().forEach((track) => track.stop());
      }
    };

    mediaRecorder.start();
    setRecording(true);
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  return (
    <div className="card">
      <h3>跟读录音</h3>
      <div className="row gap">
        <button type="button" disabled={!sentence || recording || uploading} onClick={startRecording}>
          开始录音
        </button>
        <button type="button" disabled={!recording} onClick={stopRecording}>
          停止录音
        </button>
      </div>
      <p className="muted">
        {!sentence ? "请先选择句子。" : recording ? "录音中..." : uploading ? "评估中..." : "准备开始。"}
      </p>
    </div>
  );
}
