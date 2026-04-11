import { useState, type FormEvent } from "react";
import { uploadMaterial } from "../lib/api";
import type { Material } from "../types";

interface Props {
  onUploaded: (material: Material) => void;
}

export default function MaterialUploader({ onUploaded }: Props) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title || !file) return;

    setLoading(true);
    try {
      const material = await uploadMaterial(title, file);
      onUploaded(material);
      setTitle("");
      setFile(null);
    } catch (error) {
      alert(error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="card upload-form" onSubmit={handleSubmit}>
      <h2>1. 上传素材</h2>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="素材标题"
      />
      <input
        type="file"
        accept="audio/*,video/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button type="submit" disabled={loading || !title || !file}>
        {loading ? "上传中..." : "上传"}
      </button>
    </form>
  );
}
