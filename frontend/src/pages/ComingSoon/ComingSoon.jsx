import { useState } from "react";
import { ApiError } from "../../api/client";
import { joinWaitingList } from "../../api/landing";
import { US_JURISDICTIONS } from "../../constants/jurisdictions";
import styles from "./ComingSoon.module.css";

/**
 * The whole public site while site_mode is coming_soon (015, cut down in
 * 024). It says the name and "Coming Soon" and nothing else: no 8.01
 * item, no program description, no field of study, no course, and never
 * a word about the Registry — partial disclosure reads as descriptive
 * material, so the eleven items publish with the course (016) and not
 * before. The waiting-list form asks only for what the API requires and
 * describes nothing about what the email will say. It never links
 * /login.
 */
const JOINED = "You're on the list.";

function ComingSoon() {
  const [form, setForm] = useState({
    name: "",
    email: "",
    state: "",
    website: "", // honeypot; hidden, must stay empty
  });
  const [submitting, setSubmitting] = useState(false);
  const [joined, setJoined] = useState(false);
  const [errors, setErrors] = useState(null);

  const set = (field) => (event) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setErrors(null);
    try {
      await joinWaitingList(form);
      setJoined(true);
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

  return (
    <main className={styles.page}>
      <h1 className={styles.wordmark}>superCPE</h1>
      <p className={styles.comingSoon}>Coming Soon</p>

      {joined ? (
        <p className={styles.joined}>{JOINED}</p>
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
            State
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
            {submitting ? "Sending…" : "Notify me"}
          </button>
        </form>
      )}
    </main>
  );
}

export default ComingSoon;
