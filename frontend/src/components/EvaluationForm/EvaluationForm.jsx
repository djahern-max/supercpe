import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { getMyEvaluation, submitMyEvaluation } from "../../api/my";
import styles from "./EvaluationForm.module.css";

/**
 * The 4.04.1 evaluation, solicited after a passing completion. Rendered
 * only while the server says the prompt is due; skippable — dismissing or
 * ignoring it costs the participant nothing, and the form says so. The
 * prompts come from the server so what was asked is exactly what
 * app/constants/evaluation.py records.
 */
function EvaluationForm({ completionId, onDone }) {
  const [info, setInfo] = useState(null);
  const [ratings, setRatings] = useState({});
  const [comments, setComments] = useState("");
  const [errors, setErrors] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [state, setState] = useState("open"); // open | submitted | dismissed

  useEffect(() => {
    let cancelled = false;
    getMyEvaluation(completionId)
      .then((data) => {
        if (!cancelled) setInfo(data);
      })
      .catch(() => {
        if (!cancelled) setState("dismissed");
      });
    return () => {
      cancelled = true;
    };
  }, [completionId]);

  if (state === "submitted") {
    return (
      <div className={styles.card}>
        <p className={styles.thanks}>Thank you — your evaluation is recorded.</p>
      </div>
    );
  }
  if (state === "dismissed" || info === null || !info.due) return null;

  const scale = [];
  for (let point = info.scale_min; point <= info.scale_max; point += 1) {
    scale.push(point);
  }
  const complete = info.prompts.every((prompt) => ratings[prompt.key] != null);

  const submit = async () => {
    setSubmitting(true);
    setErrors(null);
    try {
      await submitMyEvaluation(completionId, ratings, comments.trim());
      setState("submitted");
      if (onDone) onDone();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors(["Submitting failed. Try again."]);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.card}>
      <p className={styles.title}>How was this course?</p>
      <p className={styles.muted}>
        Optional — your certificate does not depend on it. 1 is poor, 5 is
        excellent.
      </p>
      {info.prompts.map((prompt) => (
        <fieldset key={prompt.key} className={styles.question}>
          <legend className={styles.prompt}>{prompt.text}</legend>
          <div className={styles.scale}>
            {scale.map((point) => (
              <label key={point} className={styles.point}>
                <input
                  type="radio"
                  name={`evaluation-${completionId}-${prompt.key}`}
                  checked={ratings[prompt.key] === point}
                  onChange={() =>
                    setRatings((current) => ({
                      ...current,
                      [prompt.key]: point,
                    }))
                  }
                />
                {point}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <textarea
        className={styles.comments}
        rows={3}
        placeholder="Anything else? (optional)"
        value={comments}
        onChange={(event) => setComments(event.target.value)}
      />
      {errors && (
        <ul className={styles.errorList}>
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
      <div className={styles.actions}>
        <button
          className={styles.button}
          type="button"
          disabled={!complete || submitting}
          onClick={submit}
        >
          {submitting ? "Submitting…" : "Submit evaluation"}
        </button>
        <button
          className={styles.linkButton}
          type="button"
          onClick={() => setState("dismissed")}
        >
          Skip
        </button>
      </div>
    </div>
  );
}

export default EvaluationForm;
