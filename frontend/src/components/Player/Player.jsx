import { useEffect, useMemo, useRef, useState } from "react";
import { resolveMediaUrl } from "../../api/client";
import styles from "./Player.module.css";

// How far past the furthest-watched point a seek may land. Covers timeupdate
// granularity, not participants.
const SEEK_TOLERANCE_SECONDS = 0.25;
const ARROW_SEEK_SECONDS = 5;
// Progress reports go out at most this often while playing; pause and
// question stops always report.
const PROGRESS_REPORT_SECONDS = 10;

function formatTime(totalSeconds) {
  const whole = Math.max(0, Math.floor(totalSeconds || 0));
  const minutes = Math.floor(whole / 60);
  const seconds = whole % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * The participant player: one lesson's video with review questions asked
 * inside it (5.01.2.1 "throughout the program"). Mounted by the admin
 * preview now and by enrollment (010) later; it never talks to the API
 * itself — the lesson payload and the grading call come in as props, and
 * the payload never contains the answer key.
 *
 * Forward seeking past the furthest point watched is prevented. That is a
 * sponsor design choice, not a Standards requirement.
 *
 * `initialFurthestSeconds` restores the furthest point from a prior
 * session (the enrollment mount, 010); `onProgress(seconds)` reports the
 * furthest point back, throttled, fire-and-forget. The preview mount
 * passes neither and behaves exactly as before.
 */
function Player({ lesson, gradeAnswer, initialFurthestSeconds = 0, onProgress }) {
  const videoRef = useRef(null);
  const containerRef = useRef(null);
  const lastTimeRef = useRef(0);
  const pendingRef = useRef([]);
  const panelScrollRef = useRef(null);
  // True from the seeking event until seeked. The video element's own
  // `seeking` property is already false again on the timeupdate a seek
  // fires as it completes, so it cannot tell that tick apart from playback.
  const seekInFlightRef = useRef(false);

  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(lesson.duration_seconds);
  const [furthest, setFurthest] = useState(initialFurthestSeconds);
  const furthestRef = useRef(initialFurthestSeconds);
  const lastReportedRef = useRef(initialFurthestSeconds);

  const reportProgress = () => {
    if (!onProgress) return;
    const seconds = Math.floor(furthestRef.current);
    if (seconds > lastReportedRef.current) {
      lastReportedRef.current = seconds;
      onProgress(seconds);
    }
  };

  const [activeQuestion, setActiveQuestion] = useState(null);
  const [selectedChoice, setSelectedChoice] = useState(null);
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [gradeError, setGradeError] = useState(null);

  // A review point is the measured end of the question's block.
  const reviewPoints = useMemo(() => {
    return lesson.questions
      .map((question) => {
        const block = lesson.blocks[question.after_block - 1];
        return block ? { time: block.end_seconds, question } : null;
      })
      .filter(Boolean)
      .sort((a, b) => a.time - b.time);
  }, [lesson]);

  const advanceFurthest = (time) => {
    if (time > furthestRef.current) {
      furthestRef.current = time;
      setFurthest(time);
      if (time - lastReportedRef.current >= PROGRESS_REPORT_SECONDS) {
        reportProgress();
      }
    }
  };

  // A final report when the player unmounts, so navigating away mid-lesson
  // loses at most the throttle window.
  useEffect(() => {
    return () => reportProgress();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openQuestion = (question) => {
    setActiveQuestion(question);
    setSelectedChoice(null);
    setResult(null);
    setGradeError(null);
  };

  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;
    // Mid-seek positions are not watched time: they must not advance the
    // furthest point or trigger questions. handleSeeked takes over once
    // the seek settles.
    if (video.seeking || seekInFlightRef.current) return;
    const time = video.currentTime;
    setCurrentTime(time);
    if (activeQuestion) return;
    advanceFurthest(time);
    // Crossing a review point pauses the video and asks the question.
    // Crossing again after seeking back asks again; re-answering is allowed.
    const crossed = reviewPoints.filter(
      (point) => lastTimeRef.current < point.time && point.time <= time
    );
    lastTimeRef.current = time;
    if (crossed.length > 0) {
      video.pause();
      pendingRef.current = crossed.slice(1).map((point) => point.question);
      openQuestion(crossed[0].question);
    }
  };

  // Forward seeks past the furthest point watched are undone once the seek
  // settles. Correcting on `seeked` rather than mid-`seeking` matters:
  // re-targeting an in-flight seek can wedge the media element.
  const handleSeeked = () => {
    const video = videoRef.current;
    if (!video) return;
    seekInFlightRef.current = false;
    if (video.currentTime > furthestRef.current + SEEK_TOLERANCE_SECONDS) {
      video.currentTime = furthestRef.current;
      return;
    }
    lastTimeRef.current = video.currentTime;
    setCurrentTime(video.currentTime);
  };

  const seekTo = (time) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = Math.max(0, Math.min(time, furthestRef.current));
  };

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video || activeQuestion) return;
    if (video.paused) video.play();
    else video.pause();
  };

  const handleSubmit = async () => {
    if (!selectedChoice || submitting || result) return;
    setSubmitting(true);
    setGradeError(null);
    try {
      const graded = await gradeAnswer(
        activeQuestion.question_key,
        selectedChoice
      );
      setResult(graded);
    } catch {
      setGradeError("Could not check the answer. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  // Any answer continues; review questions have no passing rate (5.01.2.1).
  const handleContinue = () => {
    const next = pendingRef.current.shift();
    if (next) {
      openQuestion(next);
      return;
    }
    setActiveQuestion(null);
    setResult(null);
    setSelectedChoice(null);
    const video = videoRef.current;
    if (video) {
      lastTimeRef.current = video.currentTime;
      video.play();
    }
  };

  const handleRewatch = () => {
    const block = lesson.blocks[activeQuestion.after_block - 1];
    pendingRef.current = [];
    setActiveQuestion(null);
    setResult(null);
    setSelectedChoice(null);
    const video = videoRef.current;
    if (video && block) {
      video.currentTime = block.start_seconds;
      lastTimeRef.current = block.start_seconds;
      video.play();
    }
  };

  const handleKeyDown = (event) => {
    if (activeQuestion) {
      if (event.key === "Enter" && !result && selectedChoice) {
        // Enter submits unless a specific control has focus and handles it.
        if (event.target.tagName !== "BUTTON") {
          event.preventDefault();
          handleSubmit();
        }
      }
      return;
    }
    if (event.key === " ") {
      event.preventDefault();
      togglePlay();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      seekTo(videoRef.current.currentTime - ARROW_SEEK_SECONDS);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      seekTo(videoRef.current.currentTime + ARROW_SEEK_SECONDS);
    }
  };

  const handleBarClick = (event) => {
    if (activeQuestion || !duration) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientX - rect.left) / rect.width;
    seekTo(fraction * duration);
  };

  // The panel must stay up until the question is answered: a play() from
  // anywhere else (e.g. media keys) is paused right back.
  useEffect(() => {
    const video = videoRef.current;
    if (activeQuestion && video && !video.paused) video.pause();
  });

  // Bring the verdict and feedback into view once they exist.
  useEffect(() => {
    const panel = panelScrollRef.current;
    if (result && panel) panel.scrollTop = panel.scrollHeight;
  }, [result]);

  const toggleMute = () => {
    const video = videoRef.current;
    if (video) video.muted = !muted;
    setMuted(!muted);
  };

  return (
    <div
      className={styles.player}
      ref={containerRef}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      <h1 className={styles.title}>{lesson.title}</h1>

      <div className={styles.stage}>
        <video
          ref={videoRef}
          className={styles.video}
          src={resolveMediaUrl(lesson.video_url)}
          onTimeUpdate={handleTimeUpdate}
          onSeeking={() => {
            seekInFlightRef.current = true;
          }}
          onSeeked={handleSeeked}
          onPlay={() => setPlaying(true)}
          onPause={() => {
            setPlaying(false);
            reportProgress();
          }}
          onEnded={reportProgress}
          onLoadedMetadata={(event) => {
            setDuration(event.target.duration);
            // Resume at the furthest point watched; the seeked handler
            // realigns the crossing detector so earlier questions are not
            // re-asked on the way in.
            const video = event.target;
            if (
              furthestRef.current > 0 &&
              video.currentTime < furthestRef.current
            ) {
              video.currentTime = Math.min(
                furthestRef.current,
                video.duration
              );
            }
          }}
          onClick={togglePlay}
          playsInline
        />

        {activeQuestion && (
          <div
            className={styles.questionPanel}
            role="dialog"
            aria-label="Review question"
          >
            <div className={styles.panelScroll} ref={panelScrollRef}>
              <p className={styles.stem}>{activeQuestion.stem}</p>
              <div className={styles.choices}>
                {activeQuestion.choices.map((choice) => {
                  const isSelected = selectedChoice === choice.choice_key;
                  const isCorrectChoice =
                    result && result.correct_choice_key === choice.choice_key;
                  const classNames = [styles.choice];
                  if (isSelected) classNames.push(styles.choiceSelected);
                  if (result && isCorrectChoice)
                    classNames.push(styles.choiceCorrect);
                  if (result && isSelected && !result.correct)
                    classNames.push(styles.choiceIncorrect);
                  return (
                    <button
                      key={choice.choice_key}
                      type="button"
                      className={classNames.join(" ")}
                      disabled={Boolean(result)}
                      onClick={() => setSelectedChoice(choice.choice_key)}
                    >
                      {choice.text}
                    </button>
                  );
                })}
              </div>

              {gradeError && <p className={styles.gradeError}>{gradeError}</p>}

              {result && (
                <div className={styles.feedback}>
                  <p className={styles.verdict}>
                    {result.correct ? "Correct" : "Not quite"}
                  </p>
                  <p className={styles.feedbackText}>{result.feedback}</p>
                </div>
              )}
            </div>

            <div className={styles.panelActions}>
              {!result && (
                <button
                  type="button"
                  className={styles.submit}
                  disabled={!selectedChoice || submitting}
                  onClick={handleSubmit}
                >
                  Submit
                </button>
              )}
              {result && (
                <>
                  <button
                    type="button"
                    className={styles.submit}
                    onClick={handleContinue}
                  >
                    Continue
                  </button>
                  {!result.correct && (
                    <button
                      type="button"
                      className={styles.rewatch}
                      onClick={handleRewatch}
                    >
                      Re-watch this section
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>

      <div
        className={styles.progress}
        onClick={handleBarClick}
        role="presentation"
      >
        <div
          className={styles.progressFill}
          style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
        />
        {reviewPoints.map((point) => (
          <span
            key={point.question.question_key}
            className={styles.tick}
            style={{ left: `${duration ? (point.time / duration) * 100 : 0}%` }}
            title="Review question"
          />
        ))}
      </div>

      <div className={styles.controls}>
        <button
          type="button"
          className={styles.control}
          onClick={togglePlay}
          disabled={Boolean(activeQuestion)}
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <span className={styles.time}>
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
        <button
          type="button"
          className={styles.control}
          onClick={toggleMute}
          aria-label={muted ? "Unmute" : "Mute"}
        >
          {muted ? "Unmute" : "Mute"}
        </button>
      </div>
    </div>
  );
}

export default Player;
