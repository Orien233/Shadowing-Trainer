import { CheckCircle, Info } from "@phosphor-icons/react";
import { useLanguage } from "../../../i18n/LanguageContext";
import type { Evaluation } from "../../../types";
import { getLocalizedEvaluationCopy } from "../../../utils/evaluationCopy";
import WordAlignmentView from "../alignment/WordAlignmentView";

interface Props {
  evaluation: Evaluation | null;
}

export default function EvaluationPanel({ evaluation }: Props) {
  const { t } = useLanguage();

  if (!evaluation) {
    return (
      <section className="evaluation-panel evaluation-empty" aria-label={t("evaluation.title")}>
        <div className="evaluation-empty-icon" aria-hidden="true">
          <CheckCircle size={22} weight="regular" />
        </div>
        <div>
          <h3>{t("evaluation.title")}</h3>
          <p>{t("evaluation.empty")}</p>
        </div>
      </section>
    );
  }

  const localizedCopy = getLocalizedEvaluationCopy(evaluation, t);
  const metrics = [
    { label: t("evaluation.pronunciation"), value: evaluation.pronunciation_score },
    { label: t("evaluation.fluency"), value: evaluation.fluency_score },
    { label: t("evaluation.sync"), value: evaluation.sync_score },
    { label: t("evaluation.completeness"), value: evaluation.completeness_score },
  ];

  return (
    <section className="evaluation-panel" aria-label={t("evaluation.title")}>
      <div className="score-summary">
        <div className="overall-score">
          <span className="score-label">
            {t("evaluation.overall")}
            <Info size={15} weight="regular" aria-hidden="true" />
          </span>
          <strong>
            {Math.round(evaluation.overall_score)}
            <small>/100</small>
          </strong>
        </div>

        <div className="metric-grid">
          {metrics.map((metric) => (
            <div className="score-metric" key={metric.label}>
              <div>
                <span>{metric.label}</span>
                <strong>{Math.round(metric.value)}<small>/100</small></strong>
              </div>
              <progress max={100} value={metric.value} aria-label={metric.label} />
            </div>
          ))}
        </div>
      </div>

      <div className="evaluation-copy-grid">
        <p>
          <strong>{t("evaluation.feedback")}</strong>
          <span>{localizedCopy.feedback}</span>
        </p>
        <p>
          <strong>{t("evaluation.suggestion")}</strong>
          <span>{localizedCopy.suggestion}</span>
        </p>
      </div>

      {evaluation.word_alignment && (
        <div className="alignment-feedback">
          <WordAlignmentView alignment={evaluation.word_alignment} />
        </div>
      )}
    </section>
  );
}
