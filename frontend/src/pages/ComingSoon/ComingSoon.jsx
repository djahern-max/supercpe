import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { getLanding, joinWaitingList } from "../../api/landing";
import { US_JURISDICTIONS } from "../../constants/jurisdictions";
import styles from "./ComingSoon.module.css";

/**
 * The whole public site while site_mode is coming_soon (015). This page
 * deliberately states no 8.01 item as fact — no credit figure, field of
 * study, knowledge level, prerequisites, or price — because partial
 * disclosure reads as descriptive material and is not (016 owns the full
 * eleven-item disclosure). It never links /login and renders Registry
 * language only behind may_claim_registry, which is false until NASBA
 * says otherwise.
 */
function ComingSoon() {
  const [landing, setLanding] = useState(null);
  const [form, setForm] = useState({
    name: "",
    email: "",
    state: "",
    firm: "",
    website: "", // honeypot; hidden, must stay empty
  });
  const [submitting, setSubmitting] = useState(false);
  const [joined, setJoined] = useState(null);
  const [errors, setErrors] = useState(null);

  useEffect(() => {
    getLanding()
      .then(setLanding)
      .catch(() => setLanding(null));
  }, []);

  const set = (field) => (event) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setErrors(null);
    try {
      const response = await joinWaitingList(form);
      setJoined(response.message);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setErrors(err.data.errors);
      } else {
        setErrors(["The request failed. Please try again."]);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const sponsorName = landing?.sponsor_name || "superCPE";

  return (
    <main className={styles.page}>
      <header className={styles.hero}>
        <h1 className={styles.wordmark}>
          super<span className={styles.accent}>CPE</span>
        </h1>
        <p className={styles.tagline}>
          Self-study continuing professional education for licensed CPAs —
          in preparation.
        </p>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>What this is</h2>
        <p className={styles.body}>
          {sponsorName} is building a self-study CPE platform: watch a
          narrated video course with review questions along the way, pass an
          assessment, and receive a certificate of completion for your CPE
          records.
        </p>
        <p className={styles.body}>
          The first course, now in preparation, covers the private-company
          practical expedients under ASC 842, the lease accounting standard
          — what they simplify, who can elect them, and how the elections
          play out in practice.
        </p>
        <p className={styles.muted}>
          Full program details — learning objectives, recommended CPE credit
          and field of study, prerequisites, advance preparation, and the
          registration, refund, and complaint policies — will be published
          before registration opens.
        </p>
        {landing?.may_claim_registry && (
          <p className={styles.body}>
            {sponsorName} is registered on the National Registry of CPE
            Sponsors.
          </p>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Get one email when it opens</h2>
        {joined ? (
          <p className={styles.joined}>{joined}</p>
        ) : (
          <form className={styles.form} onSubmit={handleSubmit}>
            <label className={styles.label}>
              Name
              <input
                className={styles.input}
                value={form.name}
                onChange={set("name")}
                autoComplete="name"
              />
            </label>
            <label className={styles.label}>
              Email
              <input
                className={styles.input}
                type="email"
                value={form.email}
                onChange={set("email")}
                autoComplete="email"
              />
            </label>
            <label className={styles.label}>
              State of licensure
              <select
                className={styles.input}
                value={form.state}
                onChange={set("state")}
              >
                <option value="">Choose…</option>
                {Object.entries(US_JURISDICTIONS).map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.label}>
              Firm (optional)
              <input
                className={styles.input}
                value={form.firm}
                onChange={set("firm")}
                autoComplete="organization"
              />
            </label>
            <div className={styles.trap} aria-hidden="true">
              <label>
                Website
                <input
                  tabIndex={-1}
                  autoComplete="off"
                  value={form.website}
                  onChange={set("website")}
                />
              </label>
            </div>
            {errors && (
              <ul className={styles.errorList}>
                {errors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            )}
            <button
              className={styles.button}
              type="submit"
              disabled={
                submitting || !form.name.trim() || !form.email.trim() || !form.state
              }
            >
              {submitting ? "Joining…" : "Join the waiting list"}
            </button>
            <p className={styles.emailUse}>
              Your email will be used for one message when the course opens —
              nothing else, and never shared.
            </p>
          </form>
        )}
      </section>

      <footer className={styles.footer}>
        <span>© {new Date().getFullYear()} {sponsorName}</span>
        {landing?.policies_published && (
          <span className={styles.footerLinks}>
            <a href="/policies">Policies</a>
          </span>
        )}
      </footer>
    </main>
  );
}

export default ComingSoon;
