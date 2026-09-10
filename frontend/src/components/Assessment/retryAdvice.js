/**
 * The one line of advice under a failed attempt (023c F1). Kind-aware:
 * a study-guide course is re-read, not re-watched. Nothing per question
 * may appear here (6.01.2 sub-ii); this is the whole of what is said.
 */
const ADVICE = {
  text: "Consider re-reading the guide before trying again.",
  video: "Consider re-watching the lessons before trying again.",
  mixed:
    "Consider re-reading the guide and re-watching the lessons before trying again.",
};

export function retryAdvice(lessonsKind) {
  return ADVICE[lessonsKind] || ADVICE.mixed;
}
