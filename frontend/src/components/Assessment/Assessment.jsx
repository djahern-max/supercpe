import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import styles from "./Assessment.module.css";

/**
 * The qualified assessment (6.01.2): a form submitted once, not a sequence
 * of graded questions. While an attempt is open nothing on this page may
 * hint at correctness — no verdicts, no colors — because 6.01.2 sub-ii
 * forbids feedback on a failed assessment and pass/fail is only known after
 * the whole form is scored. The server enforces this by what the payloads
 * contain; this component simply renders them.
 *
 * Mounted by the admin preview now; 010 mounts it for enrolled
 * participants. `api` carries {getAssessment, start, saveAnswers, submit,
 * getAttempt}, already bound to the course and credentials.
 */
function Assessment({ api }) {
  const [info, setInfo] = useState(null);
  const [attemptId, setAttemptId] = useState(null);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [errors, setErrors] = useState(null);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getAssessment()
      .then(async (data) => {
        if (cancelled) return;
        setInfo(data);
        if (data.open_attempt_id) {
          // Resume: restore the saved answers so a refresh loses nothing.
          const attempt = await api.getAttempt(data.open_attempt_id);
          if (cancelled) return;
          setAttemptId(data.open_attempt_id);
          setAnswers(attempt.answers ?? {});
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError("Could not load the assessment. Is the backend running?");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const handleApiError = (err) => {
    if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
      setErrors(err.data.errors);
    } else {
      setErrors(["The request failed. Try again."]);
    }
  };

  const begin = async () => {
    setErrors(null);
    try {
      const attempt = await api.start();
      setAttemptId(attempt.attempt_id);
      setAnswers({});
      setResult(null);
    } catch (err) {
      handleApiError(err);
    }
  };

  const choose = (questionId, choiceId) => {
    const next = { ...answers, [questionId]: choiceId };
    setAnswers(next);
    // Save on change so a refresh does not lose work; a lost save only
    // costs the answer, so failures are silent here.
    api.saveAnswers(attemptId, { [questionId]: choiceId }).catch(() => {});
  };

  const answeredCount = info
    ? info.questions.filter((q) => answers[q.question_id] != null).length
    : 0;
  const allAnswered = info && answeredCount === info.questions.length;

  const submit = async () => {
    if (!window.confirm(`Submit all ${info.questions.length} answers?`)) return;
    setErrors(null);
    try {
      setResult(await api.submit(attemptId, answers));
      setAttemptId(null);
    } catch (err) {
      handleApiError(err);
    }
  };

  if (loadError) return <div className={styles.errorPanel}>{loadError}</div>;
  if (!info) return <p className={styles.muted}>Loading assessment…</p>;

  const errorPanel = errors && (
    <div className={styles.errorPanel}>
      <ul className={styles.errorList}>
        {errors.map((error) => (
          <li key={error}>{error}</li>
        ))}
      </ul>
    </div>
  );

  if (result && result.status === "passed") {
    return (
      <section className={styles.card}>
        <p className={styles.scoreLine}>
          <span className={styles.scoreBig}>{Number(result.score_pct)}%</span>
          <span className={styles.scoreLabel}>Passed</span>
        </p>
        <p className={styles.muted}>
          {result.correct_count} of {result.question_count} correct. The
          course&apos;s completion is recorded.
        </p>
        <ol className={styles.reviewList}>
          {result.questions.map((question) => (
            <li key={question.question_id} className={styles.reviewItem}>
              <p className={styles.stem}>{question.stem}</p>
              <ul className={styles.reviewChoices}>
                {question.choices.map((choice) => (
                  <li
                    key={choice.choice_id}
                    className={
                      choice.choice_id === question.correct_choice_id
                        ? styles.choiceCorrect
                        : choice.choice_id === question.chosen_choice_id
                          ? styles.choiceChosenWrong
                          : styles.choicePlain
                    }
                  >
                    {choice.text}
                    {choice.choice_id === question.correct_choice_id &&
                      " — correct"}
                    {choice.choice_id === question.chosen_choice_id &&
                      choice.choice_id !== question.correct_choice_id &&
                      " — your answer"}
                  </li>
                ))}
              </ul>
              <p className={styles.feedback}>{question.feedback}</p>
            </li>
          ))}
        </ol>
      </section>
    );
  }

  if (result && result.status === "failed") {
    // 6.01.2 sub-ii: nothing per question on a failed attempt. Resist
    // adding anything here; the Standard is restrictive on purpose.
    return (
      <section className={styles.card}>
        <p className={styles.scoreLine}>
          <span className={styles.scoreBig}>
            {result.score_pct !== null ? `${Number(result.score_pct)}%` : "—"}
          </span>
          <span className={styles.scoreLabel}>Not passed</span>
        </p>
        <p className={styles.muted}>
          {Number(result.passing_pct)} percent is required.{" "}
          {result.correct_count !== null &&
            `${result.correct_count} of ${result.question_count} correct.`}
        </p>
        <p className={styles.muted}>
          Consider re-watching the lessons before trying again.
        </p>
        {errorPanel}
        {result.retakes_allowed && (
          <button className={styles.button} type="button" onClick={begin}>
            Try again
          </button>
        )}
      </section>
    );
  }

  if (!attemptId) {
    return (
      <section className={styles.card}>
        <h2 className={styles.title}>Qualified assessment</h2>
        <p>
          {info.question_count} questions. A cumulative score of at least{" "}
          {Number(info.passing_pct)} percent is required. Results come after
          all questions are submitted{info.retakes_allowed &&
            ", and retakes are allowed"}.
        </p>
        {errorPanel}
        <button className={styles.button} type="button" onClick={begin}>
          Begin
        </button>
      </section>
    );
  }

  return (
    <>
      <ol className={styles.questionList}>
        {info.questions.map((question, index) => (
          <li key={question.question_id} className={styles.card}>
            <fieldset className={styles.fieldset}>
              <legend className={styles.stem}>
                {index + 1}. {question.stem}
              </legend>
              {question.choices.map((choice) => (
                <label key={choice.choice_id} className={styles.choiceRow}>
                  <input
                    type="radio"
                    name={`question-${question.question_id}`}
                    checked={answers[question.question_id] === choice.choice_id}
                    onChange={() => choose(question.question_id, choice.choice_id)}
                  />
                  <span>{choice.text}</span>
                </label>
              ))}
            </fieldset>
          </li>
        ))}
      </ol>
      {errorPanel}
      <footer className={styles.footer}>
        <span>
          {answeredCount} of {info.questions.length} answered
        </span>
        <button
          className={styles.button}
          type="button"
          disabled={!allAnswered}
          onClick={submit}
        >
          Submit
        </button>
      </footer>
    </>
  );
}

export default Assessment;
