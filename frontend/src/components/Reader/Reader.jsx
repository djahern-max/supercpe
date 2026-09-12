import { useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { resolveMediaUrl } from "../../api/client";
import SimpleMarkdown from "../SimpleMarkdown/SimpleMarkdown.jsx";
import styles from "./Reader.module.css";
import { stripLeadingTitle } from "./sectionTitle.js";
import {
  allAnswered,
  bodySections,
  isAnswered,
  progressLabel,
  questionsAfter,
  readingChain,
  referenceSections,
  resumeKey,
  sectionStates,
} from "./stepper.js";

const ROLE_LABELS = {
  front_matter: "How this course works",
  body: "Guide",
  glossary: "Glossary",
  appendix: "Appendix",
};

// The URL carries the reading position (`?section=<key>`), so reload and
// back/forward return to the same section. It is browser state, not a
// record: nothing here is written to the server (010: progress never
// decreases, and this is not progress).
const SECTION_PARAM = "section";

/**
 * The participant reader: one text lesson's study guide, read one section
 * at a time in order, with review questions between its sections
 * (5.01.2.1 "throughout the program in sufficient intervals").
 *
 * The gate is not here. A locked section arrives with `markdown: null`,
 * because the server withholds the text until the placed review question
 * is answered; this component renders what it was given and says why the
 * rest is not there. Likewise the payload never carries the answer key —
 * `gradeAnswer` is the only way to learn whether a choice was right, and
 * the feedback comes back with the verdict (5.01.2.2).
 *
 * 027: a stepper. A table of contents lists every section with its state
 * (read, current, unread, locked — a locked entry is a title and nothing
 * more); the pane shows one section; Continue opens the next once every
 * question placed after the current one is answered. That button is a
 * presentation of the server's gate, not a second gate: answering already
 * refetched the payload, and Continue shows what the server unlocked.
 * Front matter (4.05.3 item 4, "instructions … regarding navigation")
 * comes first, always. After the last body section, when every question
 * in the lesson is answered, a completion card names the next step —
 * `nextStep` is derived by the page from the enrollment detail; the
 * preview mount passes none.
 *
 * Supplemental videos render inline at their placement with ordinary
 * controls and no seek lock: completion is verified by the qualified
 * assessment (6.01.2), not by watch time, and interval placement is
 * satisfied by the section gates. That is the 023 decision, recorded in
 * docs/decisions/2026-09-01-text-first.md; the video-only player keeps
 * its own behavior. When a clip ends it says where to go next.
 *
 * `onSearch` and `onLookup` are the 4.05.3 items 2 and 3 surfaces, passed
 * in so this component never talks to the API itself — the same rule the
 * player follows.
 */
function Reader({
  lesson,
  gradeAnswer,
  onSearch,
  onLookup,
  onAnswered,
  onContinue,
  nextStep,
}) {
  // The per-question verdicts, tied to the lesson they were given in. A
  // refetch of the *same* lesson — which is how the next section opens
  // after an answer — keeps them, so the feedback stays on screen until
  // the participant acts again (5.01.2.2; 023c D2: an effect keyed on
  // the payload object cleared them under a second after every answer).
  // A different lesson starts them over.
  const [verdicts, setVerdicts] = useState({
    lessonId: lesson.lesson_id,
    results: {},
  });
  const results =
    verdicts.lessonId === lesson.lesson_id ? verdicts.results : {};
  // Sections this session has moved on from — the "read" mark for
  // ungated sections the payload cannot vouch for. Same lesson-keyed
  // shape as the verdicts, for the same reason.
  const [visitedState, setVisitedState] = useState({
    lessonId: lesson.lesson_id,
    keys: [],
  });
  const visited = useMemo(
    () =>
      new Set(
        visitedState.lessonId === lesson.lesson_id ? visitedState.keys : []
      ),
    [visitedState, lesson.lesson_id]
  );
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState(null);
  const [glossary, setGlossary] = useState(null);
  const [panel, setPanel] = useState(null);
  const [contentsOpen, setContentsOpen] = useState(false);
  const [endedClips, setEndedClips] = useState({});
  const [searchParams, setSearchParams] = useSearchParams();
  const paneRef = useRef(null);
  const questionsRef = useRef(null);
  const continueRef = useRef(null);

  const chain = useMemo(() => readingChain(lesson.sections), [lesson]);
  const bodies = useMemo(() => bodySections(lesson.sections), [lesson]);
  const reference = useMemo(() => referenceSections(lesson.sections), [lesson]);

  const mediaFor = useMemo(() => {
    const map = {};
    for (const item of lesson.media) {
      map[item.after_section] = (map[item.after_section] || []).concat(item);
    }
    return map;
  }, [lesson]);

  // Where we are: the URL's section when it names one of this lesson's
  // sections, else the first section not yet read as far as the payload
  // can tell (front matter when it cannot).
  const requested = searchParams.get(SECTION_PARAM);
  const currentKey =
    requested && lesson.sections.some((s) => s.section_key === requested)
      ? requested
      : resumeKey(lesson, results);
  const current = lesson.sections.find((s) => s.section_key === currentKey);
  const chainIndex = chain.findIndex((s) => s.section_key === currentKey);
  const states = sectionStates(lesson, results, currentKey, visited);

  const placedHere = current ? questionsAfter(lesson, currentKey) : [];
  const gateClear = placedHere.every((q) => isAnswered(q, results));
  const previous = chainIndex > 0 ? chain[chainIndex - 1] : null;
  const next = chainIndex >= 0 ? chain[chainIndex + 1] : null;
  const atEnd = chainIndex >= 0 && chainIndex === chain.length - 1;
  const lessonFinished = atEnd && allAnswered(lesson, results);
  const readBodies = bodies.filter((s) => states[s.section_key] === "read");

  const goToSection = (sectionKey) => {
    if (!lesson.sections.some((s) => s.section_key === sectionKey)) return;
    setVisitedState((prev) => ({
      lessonId: lesson.lesson_id,
      keys: Array.from(
        new Set([
          ...(prev.lessonId === lesson.lesson_id ? prev.keys : []),
          currentKey,
          sectionKey,
        ])
      ),
    }));
    setSearchParams({ [SECTION_PARAM]: sectionKey });
    setContentsOpen(false);
    const pane = paneRef.current;
    if (pane && typeof pane.scrollIntoView === "function") {
      pane.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const continueReading = () => {
    if (!next || !gateClear) return;
    // Only the server decides what is open; the page refetches on every
    // answer, and Continue asks once more so it shows what was unlocked.
    if (onContinue) onContinue();
    goToSection(next.section_key);
  };

  const answer = (question, choiceKey) => {
    gradeAnswer(question.question_key, choiceKey).then((result) => {
      setVerdicts((prev) => ({
        lessonId: lesson.lesson_id,
        results: {
          ...(prev.lessonId === lesson.lesson_id ? prev.results : {}),
          [question.question_key]: { ...result, choiceKey },
        },
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

  // A finished clip points at what follows it: the question placed after
  // this section if one is still open, else the next section.
  const afterClip = () => {
    const target =
      placedHere.length > 0 && !gateClear
        ? questionsRef.current
        : continueRef.current;
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (placedHere.length === 0 || gateClear) continueReading();
  };

  const handleKeyDown = (event) => {
    const tag = event.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (event.key === "ArrowRight") {
      event.preventDefault();
      continueReading();
    } else if (event.key === "ArrowLeft" && previous) {
      event.preventDefault();
      goToSection(previous.section_key);
    }
  };

  const stateLabel = (key) =>
    states[key] === "locked" ? "Locked" : states[key] === "read" ? "Read" : null;

  const contentsEntry = (section) => {
    const state = states[section.section_key];
    return (
      <li key={section.section_key} className={styles[`entry_${state}`]}>
        <button
          type="button"
          className={styles.contentsLink}
          disabled={state === "locked"}
          aria-current={state === "current" ? "step" : undefined}
          onClick={() => goToSection(section.section_key)}
        >
          <span className={styles.entryTitle}>{section.title}</span>
          {stateLabel(section.section_key) && (
            <span className={styles.entryState}>
              {stateLabel(section.section_key)}
            </span>
          )}
        </button>
      </li>
    );
  };

  return (
    <div className={styles.reader} onKeyDown={handleKeyDown} tabIndex={-1}>
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
        <button
          type="button"
          className={styles.contentsToggle}
          aria-expanded={contentsOpen}
          onClick={() => setContentsOpen(!contentsOpen)}
        >
          {contentsOpen ? "Hide contents" : "Contents"}
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
                  <dd>
                    {entry.definition}
                    {entry.section_key &&
                      lesson.sections.some(
                        (s) => s.section_key === entry.section_key
                      ) && (
                        <>
                          {" "}
                          <button
                            type="button"
                            className={styles.hitLink}
                            onClick={() => goToSection(entry.section_key)}
                          >
                            Open the section
                          </button>
                        </>
                      )}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}

      <div className={styles.layout}>
        <nav
          className={
            contentsOpen ? `${styles.contents} ${styles.contentsOpen}` : styles.contents
          }
          aria-label="Course contents"
        >
          <h2 className={styles.contentsTitle}>Contents</h2>
          <ol className={styles.contentsList}>{chain.map(contentsEntry)}</ol>
          {reference.length > 0 && (
            <>
              <h3 className={styles.contentsTitle}>Reference</h3>
              <ul className={styles.contentsList}>
                {reference.map(contentsEntry)}
              </ul>
            </>
          )}
        </nav>

        <article className={styles.pane} ref={paneRef}>
          {current && (
            <>
              <div className={styles.progress}>
                <p className={styles.progressLine}>
                  {progressLabel(lesson, currentKey)}
                </p>
                <div
                  className={styles.progressBar}
                  role="progressbar"
                  aria-label="Sections read"
                  aria-valuemin={0}
                  aria-valuemax={bodies.length}
                  aria-valuenow={readBodies.length}
                >
                  <div
                    className={styles.progressFill}
                    style={{
                      width: `${bodies.length ? (readBodies.length / bodies.length) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>

              <section key={currentKey} className={styles.section}>
                <p className={styles.role}>
                  {ROLE_LABELS[current.role] || current.role}
                </p>
                <h2 className={styles.sectionTitle}>{current.title}</h2>

                {current.locked ? (
                  <p className={styles.locked}>
                    Answer the review question after the previous section to
                    open this one.
                  </p>
                ) : (
                  <>
                    <SimpleMarkdown
                      markdown={stripLeadingTitle(current.markdown, current.title)}
                    />
                    {(mediaFor[currentKey] || []).map((item) => (
                      <figure key={item.media_key} className={styles.mediaFigure}>
                        <video
                          className={styles.video}
                          src={resolveMediaUrl(item.url)}
                          controls
                          preload="metadata"
                          onEnded={() =>
                            setEndedClips((prev) => ({
                              ...prev,
                              [item.media_key]: true,
                            }))
                          }
                          onPlay={() =>
                            setEndedClips((prev) => ({
                              ...prev,
                              [item.media_key]: false,
                            }))
                          }
                        />
                        <figcaption className={styles.mediaCaption}>
                          A worked example that adds to the guide — it does
                          not read it aloud. Watch, skip, or replay it as you
                          like.
                        </figcaption>
                        {endedClips[item.media_key] && (
                          <p className={styles.clipEnded}>
                            <button
                              type="button"
                              className={styles.clipContinue}
                              onClick={afterClip}
                            >
                              Continue reading
                            </button>
                          </p>
                        )}
                      </figure>
                    ))}
                    {placedHere.length > 0 && (
                      <div ref={questionsRef}>
                        {placedHere.map((question) => (
                          <ReviewQuestion
                            key={question.question_key}
                            question={question}
                            result={results[question.question_key]}
                            onAnswer={answer}
                          />
                        ))}
                      </div>
                    )}
                  </>
                )}
              </section>

              <div className={styles.stepNav} ref={continueRef}>
                {chainIndex === -1 ? (
                  <button
                    type="button"
                    className={styles.stepButton}
                    onClick={() => goToSection(resumeKey(lesson, results))}
                  >
                    Back to the guide
                  </button>
                ) : (
                  <>
                    {previous && (
                      <button
                        type="button"
                        className={styles.stepButton}
                        onClick={() => goToSection(previous.section_key)}
                      >
                        Previous
                      </button>
                    )}
                    {next && (
                      <>
                        <button
                          type="button"
                          className={styles.continueButton}
                          disabled={!gateClear || current.locked}
                          onClick={continueReading}
                        >
                          Continue
                        </button>
                        {!gateClear && !current.locked && (
                          <span className={styles.stepHint}>
                            Answer the review question
                            {placedHere.length > 1 ? "s" : ""} above to
                            continue.
                          </span>
                        )}
                      </>
                    )}
                  </>
                )}
              </div>

              {lessonFinished && <CompletionCard nextStep={nextStep} />}
            </>
          )}

          {bodies.length > 0 && reference.length > 0 && (
            <p className={styles.footnote}>
              The glossary and any appendixes are reference material. They are
              open from the start and are not required reading.
            </p>
          )}
        </article>
      </div>
    </div>
  );
}

/**
 * After the last body section, once every question in the lesson is
 * answered: what to do next. The page derives `nextStep` from the
 * enrollment detail (the next unread lesson, else the assessment when it
 * is available, else the course page, which says why it is not).
 */
function CompletionCard({ nextStep }) {
  const finished =
    nextStep?.kind === "lesson"
      ? "You've finished this lesson"
      : "You've finished the study guide";
  return (
    <section className={styles.completion} aria-label="Next step">
      <h2 className={styles.completionTitle}>{finished}</h2>
      {nextStep ? (
        <>
          <Link className={styles.completionPrimary} to={nextStep.to}>
            {nextStep.label}
          </Link>
          {nextStep.kind !== "course" && nextStep.course && (
            <Link className={styles.completionSecondary} to={nextStep.course}>
              Back to the course page
            </Link>
          )}
        </>
      ) : (
        <p className={styles.muted}>Every review question here is answered.</p>
      )}
    </section>
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
 * always carries feedback, correct or not (5.01.2.2). The chosen key rides
 * on the result, so leaving and returning to the section shows the same
 * verdict (023c D2, kept through the stepper).
 */
function ReviewQuestion({ question, result, onAnswer }) {
  const [chosenHere, setChosenHere] = useState(null);
  const answered = result !== undefined;
  const chosen = answered ? result.choiceKey : chosenHere;

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
                  setChosenHere(choice.choice_key);
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
