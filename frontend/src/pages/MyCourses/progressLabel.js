/**
 * "2 of 3 lessons read": the verb follows what the course's lessons are
 * (023c F2). `lessons_kind` comes from the enrollment summary — "text",
 * "video", or "mixed" — and `lessons_done` counts lessons read (every
 * review question answered) or watched (played to the end).
 */
const VERB = {
  text: "read",
  video: "watched",
  mixed: "read or watched",
};

export function lessonsProgressLabel(enrollment) {
  const verb = VERB[enrollment.lessons_kind] || VERB.mixed;
  return `${enrollment.lessons_done} of ${enrollment.lessons_total} lessons ${verb}`;
}
