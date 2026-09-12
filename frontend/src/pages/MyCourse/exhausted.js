/**
 * 027: the enrollment's status is derived, never stored (010); the
 * sittings are 1 + RETAKES_ALLOWED less the failed attempts. "Exhausted"
 * is that count reaching zero on an active enrollment — the state 028
 * builds the exit from. Here it is only named, from fields the enrollment
 * detail already carries.
 */
export function isExhausted(enrollment) {
  return (
    enrollment.status === "active" &&
    !enrollment.assessment_available &&
    !enrollment.open_attempt_id &&
    enrollment.retakes_remaining === 0
  );
}
