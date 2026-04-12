import type { Evaluation } from "../types";

interface Props {
  evaluation: Evaluation | null;
}

export default function EvaluationPanel({ evaluation }: Props) {
  if (!evaluation) {
    return (
      <div className="card">
        <h3>评估结果</h3>
        <p className="muted">录音后会显示评分和建议。</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>评估结果</h3>
      <div className="score-grid">
        <div><strong>综合</strong><span>{evaluation.overall_score}</span></div>
        <div><strong>完整性</strong><span>{evaluation.completeness_score}</span></div>
        <div><strong>流畅度</strong><span>{evaluation.fluency_score}</span></div>
        <div><strong>同步度</strong><span>{evaluation.sync_score}</span></div>
        <div><strong>发音表现</strong><span>{evaluation.pronunciation_score}</span></div>
      </div>
      <p><strong>反馈：</strong>{evaluation.feedback}</p>
      <p><strong>建议：</strong>{evaluation.suggestion}</p>
    </div>
  );
}
