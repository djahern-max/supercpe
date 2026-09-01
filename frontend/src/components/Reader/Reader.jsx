import { useEffect, useMemo, useRef, useState } from "react";
import { resolveMediaUrl } from "../../api/client";
import SimpleMarkdown from "../SimpleMarkdown/SimpleMarkdown.jsx";
import styles from "./Reader.module.css";

const ROLE_LABELS = {
  front_matter: "How this course works",
  body: "Guide",
  glossary: "Glossary",
  appendix: "Appendix",
};

const REFERENCE_ROLES = ["front_matter", "glossary", "appendix"];

/**
 * The participant reader: one text lesson's study guide, read in order,
 * with review questions between its sections (5.01.2.1 "throughout the
 * program in sufficient intervals").
 *
 * The gate is not here. A locked section arrives with `markdown: null`,
 * because the server withholds the text until the placed review question
 * is answered; this component renders what it was given and says why the
 * rest is not there. Likewise the payload never carries the answer key —
 * `gradeAnswer` is the only way to learn whether a choice was right, and
 * the feedback comes back with the verdict (5.01.2.2).
 *
 * Supplemental videos render inline at their placement with ordinary
 * controls and no seek lock: completion is verified by the qualified
 * assessment (6.01.2), not by watch time, and interval placement is
 * satisfied by the section gates. That is the 023 decision, recorded in
 * docs/decisions/2026-09-01-text-first.md; the video-only player keeps
 * its own behavior.
 *
 * `onSearch` and `onLookup` are the 4.05.3 items 2 and 3 surfaces, passed
 * in so this component never talks to the API itself — the same rule the
 * player follows.
 */
function Reader({ lesson, gradeAnswer, onSearch, onLookup, onAnswered }) {
  const [results, setResults] = useState({});
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(null);
  const [glossary, setGlossary] = useState(null);
  const [panel, setPanel] = useState(null);
  const sectionRefs = useRef({});

  // A fresh lesson payload clears the per-question verdicts: they belong
  // to the answers just given, not to the lesson.
  useEffect(() => {
    setResults({});
  }, [lesson]);

  // Every review question placed after a section, in order. A list, not
  // one per section: a section may carry more than one, and all of them
  // must be answered before the next body section opens.
  const questionsFor = useMemo(() => {
    const map = {};
    for (const question of lesson.questions) {
      map[question.after_section] = (map[question.after_section] || []).concat(
        question
      );
    }
    return map;
  }, [lesson]);

  const mediaFor = useMemo(() => {
    const map = {};
    for (const item of lesson.media) {
      map[item.after_section] = (map[item.after_section] || []).concat(item);
    }
    return map;
  }, [lesson]);

  const reading = lesson.sections.filter((s) => s.role === "body");
  const reference = lesson.sections.filter((s) =>
    REFERENCE_ROLES.includes(s.role)
  );

  const answer = (question, choiceKey) => {
    gradeAnswer(question.question_key, choiceKey).then((result) => {
      setResults((prev) => ({
        ...prev,
        [question.question_key]: { ...result, choiceKey },
      }));
      // The verdict is the participant's; reloading is how the next
      // section opens, and only the server decides that.
      if (onAnswered) onAnswered();
    });
  };

  const runSearch = (event) => {
    event.preventDefault();
    if (!onSearch) return;
    onSearch(query).then((data) => setHits(data.hits));
  };

  const openGlossary = () => {
    setPanel(panel === "glossary" ? null : "glossary");
    if (glossary === null && onLookup) {
      onLookup("").then((data) => setGlossary(data.terms));
    }
  };

  const goToSection = (sectionKey) => {
    const node = sectionRefs.current[sectionKey];
    if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className={styles.reader}>
      <div className={styles.chrome}>
        <form className={styles.searchForm} onSubmit={runSearch}>
          <label className={styles.searchLabel} htmlFor="reader-search">
            Search this course
          </label>
          <input
            id="reader-search"
            className={styles.searchInput}
            type="search"
            value={query}
            placeholder="Find a word in the guide"
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="submit" className={styles.searchButton}>
            Search
          </button>
        </form>
        <button
          type="button"
          className={styles.chromeButton}
          onClick={openGlossary}
        >
          {panel === "glossary" ? "Hide glossary" : "Glossary"}
        </button>
      </div>

      {hits !== null && (
        <div className={styles.panel}>
          <div className={styles.panelHead}>
            <h2 className={styles.panelTitle}>
              {hits.length === 0
                ? `No section mentions “${query}”.`
                : `${hits.length} section${hits.length === 1 ? "" : "s"} mention “${query}”`}
            </h2>
            <button
              type="button"
              className={styles.chromeButton}
              onClick={() => setHits(null)}
            >
              Clear
            </button>
          </div>
          <ul className={styles.hitList}>
            {hits.map((hit) => (
              <li key={`${hit.package_id}-${hit.section_key}`}>
                <button
                  type="button"
                  className={styles.hitLink}
                  onClick={() => goToSection(hit.section_key)}
                >
                  {hit.section_title}
                </button>
                {hit.snippets.map((snippet, i) => (
                  <p key={i} className={styles.snippet}>
                    <Highlighted text={snippet} term={query} />
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}

      {panel === "glossary" && (
        <div className={styles.panel}>
          <h2 className={styles.panelTitle}>Glossary</h2>
          {glossary === null ? (
            <p className={styles.muted}>Loading…</p>
          ) : (
            <dl className={styles.glossary}>
              {glossary.map((entry) => (
                <div key={entry.term} className={styles.glossaryRow}>
                  <dt>{entry.term}</dt>
                  <dd>{entry.definition}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}

      <nav className={styles.contents} aria-label="Course contents">
        <h2 className={styles.contentsTitle}>Contents</h2>
        <ol className={styles.contentsList}>
          {lesson.sections.map((section) => (
            <li key={section.section_key}>
              <button
                type="button"
                className={
                  section.locked ? styles.contentsLocked : styles.contentsLink
                }
                disabled={section.locked}
                onClick={() => goToSection(section.section_key)}
              >
                {section.title}
                {section.locked && " (locked)"}
              </button>
            </li>
          ))}
        </ol>
      </nav>

      {lesson.sections.map((section) => (
        <section
          key={section.section_key}
          className={styles.section}
          ref={(node) => {
            sectionRefs.current[section.section_key] = node;
          }}
        >
          <p className={styles.role}>
            {ROLE_LABELS[section.role] || section.role}
          </p>
          <h2 className={styles.sectionTitle}>{section.title}</h2>

          {section.locked ? (
            <p className={styles.locked}>
              Answer the review question above to open this section.
            </p>
          ) : (
            <>
              <SimpleMarkdown markdown={section.markdown} />
              {(mediaFor[section.section_key] || []).map((item) => (
                <figure key={item.media_key} className={styles.mediaFigure}>
                  <video
                    className={styles.video}
                    src={resolveMediaUrl(item.url)}
                    controls
                    preload="metadata"
                  />
                  <figcaption className={styles.mediaCaption}>
                    A worked example that adds to the guide — it does not
                    read it aloud. Watch, skip, or replay it as you like.
                  </figcaption>
                </figure>
              ))}
              {(questionsFor[section.section_key] || []).map((question) => (
                <ReviewQuestion
                  key={question.question_key}
                  question={question}
                  result={results[question.question_key]}
                  onAnswer={answer}
                />
              ))}
            </>
          )}
        </section>
      ))}

      {reading.length > 0 && reference.length > 0 && (
        <p className={styles.footnote}>
          The glossary and any appendixes are reference material. They are
          open from the start and are not required reading.
        </p>
      )}
    </div>
  );
}

/** The query, marked inside a snippet. Text nodes only; no HTML. */
function Highlighted({ text, term }) {
  if (!term) return text;
  const parts = text.split(new RegExp(`(${escapeRegExp(term)})`, "ig"));
  return parts.map((part, i) =>
    part.toLowerCase() === term.toLowerCase() ? (
      <mark key={i}>{part}</mark>
    ) : (
      part
    )
  );
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * One review question, asked between sections. Nothing here knows the
 * right answer until the server says so: `result` arrives from grading and
 * always carries feedback, correct or not (5.01.2.2).
 */
function ReviewQuestion({ question, result, onAnswer }) {
  const [chosen, setChosen] = useState(null);
  const answered = result !== undefined;

  return (
    <div className={styles.question}>
      <p className={styles.questionStem}>{question.stem}</p>
      <ul className={styles.choiceList}>
        {question.choices.map((choice) => {
          const isChosen = chosen === choice.choice_key;
          const isRight =
            answered && result.correct_choice_key === choice.choice_key;
          return (
            <li key={choice.choice_key}>
              <button
                type="button"
                className={[
                  styles.choice,
                  isChosen ? styles.choiceChosen : "",
                  answered && isRight ? styles.choiceRight : "",
                  answered && isChosen && !result.correct
                    ? styles.choiceWrong
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => {
                  setChosen(choice.choice_key);
                  onAnswer(question, choice.choice_key);
                }}
              >
                {choice.text}
              </button>
            </li>
          );
        })}
      </ul>
      {answered && (
        <div
          className={result.correct ? styles.feedbackRight : styles.feedbackWrong}
        >
          <strong>{result.correct ? "Correct." : "Not quite."}</strong>{" "}
          {result.feedback}
        </div>
      )}
      {!answered && question.answered && (
        <p className={styles.muted}>
          You answered this question earlier. Answer it again to see the
          feedback, or read on.
        </p>
      )}
    </div>
  );
}

export default Reader;
