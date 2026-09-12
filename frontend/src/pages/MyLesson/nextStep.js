/**
 * 027: what comes after this lesson, derived from the enrollment detail
 * the page already holds — the same derivation the reader's completion
 * card, the player's end panel, and the course page share. Nothing is
 * added to the payload: `lessons[].done`, `assessment_available`,
 * `open_attempt_id`, `failed_attempts`, and `retakes_remaining` are what
 * 010 and 023c already serve.
 *
 * Returns `{ kind, to, label, course }`: kind is "assessment", "lesson",
 * or "course" (nothing else is open — completed, expired, exhausted — so
 * the course page says why); `course` is the course page's path.
 */
/**
 * 028: the words on the assessment button. Under the unlimited policy
 * (`retakes_remaining` is null) there is no count to show; under a finite
 * one the sittings left follow in parentheses, as 027 wrote them.
 */
export function retakeLabel(enrollment) {
  if (enrollment.failed_attempts > 0) {
    return enrollment.retakes_remaining == null
      ? "Re-take the qualified assessment"
      : `Re-take the qualified assessment (${enrollment.retakes_remaining} left)`;
  }
  return "Take the qualified assessment";
}

export function deriveNextStep(enrollment, packageId) {
  const base = `/my/courses/${enrollment.enrollment_id}`;
  if (enrollment.completion) {
    return { kind: "course", to: base, label: "Back to the course page", course: base };
  }
  if (enrollment.open_attempt_id) {
    return {
      kind: "assessment",
      to: `${base}/assessment`,
      label: "Resume the assessment",
      course: base,
    };
  }
  const remaining = enrollment.lessons
    .filter((l) => !l.done && String(l.package_id) !== String(packageId))
    .sort((a, b) => a.position - b.position);
  if (remaining.length > 0) {
    const next = remaining[0];
    return {
      kind: "lesson",
      to: `${base}/lessons/${next.package_id}`,
      label: `Next lesson: ${next.title}`,
      title: next.title,
      course: base,
    };
  }
  if (enrollment.assessment_available) {
    return {
      kind: "assessment",
      to: `${base}/assessment`,
      label: retakeLabel(enrollment),
      course: base,
    };
  }
  return { kind: "course", to: base, label: "Back to the course page", course: base };
}

/** Review questions in this lesson still unanswered, per the enrollment. */
export function reviewRemaining(enrollment, packageId) {
  const lesson = enrollment.lessons.find(
    (l) => String(l.package_id) === String(packageId)
  );
  if (!lesson) return 0;
  return Math.max(lesson.review_total - lesson.review_answered, 0);
}
