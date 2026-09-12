import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getPublicSponsor } from "../../api/sponsor";
import styles from "./RetakesExhausted.module.css";

/**
 * 027: the one wording for an enrollment with no sittings left, shared by
 * the failed result and the course page so the two cannot disagree. Three
 * parts: how many re-takes were used, the published policy (linked, not
 * restated — `retake_policy_text()` renders on /policies), and where to
 * write about re-enrolling. Wording only: the exit from this state is
 * 028; nothing here starts a re-purchase, a reset, or an admin action.
 *
 * The study guide stays readable (the enrollment is not expired or
 * voided), and the notice says so. Nothing per question appears here or
 * anywhere near it (6.01.2 sub-ii).
 */
function RetakesExhausted({ retakesAllowed, coursePath, lessonsKind }) {
  const [contact, setContact] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getPublicSponsor()
      .then((profile) => {
        if (!cancelled) setContact(profile.contact_email || null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const material =
    lessonsKind === "video"
      ? "The lessons stay open"
      : lessonsKind === "mixed"
        ? "The study guide and the lessons stay open"
        : "The study guide stays open";

  return (
    <div className={styles.notice}>
      <p className={styles.lead}>
        You have used all {retakesAllowed} re-takes on this enrollment.
      </p>
      <p className={styles.line}>
        <Link className={styles.link} to="/policies#retakes">
          Read the re-take policy
        </Link>
        .
      </p>
      {contact && (
        <p className={styles.line}>
          Contact us about re-enrolling:{" "}
          <a className={styles.link} href={`mailto:${contact}`}>
            {contact}
          </a>
        </p>
      )}
      <p className={styles.line}>
        {material}
        {coursePath ? (
          <>
            : you can{" "}
            <Link className={styles.link} to={coursePath}>
              keep reading it
            </Link>
            .
          </>
        ) : (
          "."
        )}
      </p>
    </div>
  );
}

export default RetakesExhausted;
