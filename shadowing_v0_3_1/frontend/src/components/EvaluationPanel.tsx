import { useLanguage } from "../i18n/LanguageContext";
import type { Evaluation } from "../types";
import WordAlignmentView from "./WordAlignmentView.jsx";

interface Props { evaluation: Evaluation | null; }

export default function EvaluationPanel({ evaluation }: Props) {
  const { t } = useLanguage();
  if (!evaluation) {
    return <div className="card"><h3>{t("evaluation.title")}</h3><p className="muted">{t("evaluation.empty")}</p></div>;
  }

  return (
    <div className="card">
      <h3>{t("evaluation.title")}</h3>
      <div className="score-grid">
        <div><strong>{t("evaluation.overall")}</strong><span>{evaluation.overall_score}</span></div>
        <div><strong>{t("evaluation.completeness")}</strong><span>{evaluation.completeness_score}</span></div>
        <div><strong>{t("evaluation.fluency")}</strong><span>{evaluation.fluency_score}</span></div>
        <div><strong>{t("evaluation.sync")}</strong><span>{evaluation.sync_score}</span></div>
        <div><strong>{t("evaluation.pronunciation")}</strong><span>{evaluation.pronunciation_score}</span></div>
      </div>
      <p><strong>{t("evaluation.feedback")}</strong>{evaluation.feedback}</p>
      <p><strong>{t("evaluation.suggestion")}</strong>{evaluation.suggestion}</p>
      {evaluation.word_alignment && <WordAlignmentView alignment={evaluation.word_alignment} />}
    </div>
  );
}
