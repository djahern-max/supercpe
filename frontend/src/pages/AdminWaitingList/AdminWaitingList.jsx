import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { ApiError } from "../../api/client";
import {
  listWaitingList,
  removeWaitingListEntry,
  resendInvitation,
  sendInvitations,
  waitingListCsvUrl,
} from "../../api/landing";
import { getSite } from "../../api/site";
import { useSession } from "../../auth/SessionContext.jsx";
import styles from "./AdminWaitingList.module.css";

function invitationCell(entry) {
  // 019's idiom: failed is the loud flag, sent shows when, blank means
  // no attempt yet.
  if (entry.invitation_status === "failed") return "failed";
  if (entry.invitation_status === "sent") {
    return `sent ${new Date(entry.invited_at).toLocaleDateString()}`;
  }
  return "—";
}

function AdminWaitingList() {
  const { refresh: refreshSession } = useSession();
  const [listing, setListing] = useState(null);
  const [siteMode, setSiteMode] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [query, setQuery] = useState("");
  const [errors, setErrors] = useState(null);
  const [summary, setSummary] = useState(null);
  const [sending, setSending] = useState(false);

  const refresh = useCallback(() => {
    listWaitingList()
      .then((data) => {
        setListing(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else setLoadError("Could not load the waiting list. Is the backend running?");
      });
    getSite()
      .then((site) => setSiteMode(site.site_mode))
      .catch(() => {});
  }, [refreshSession]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleRemove = async (entry) => {
    const reason = window.prompt(
      `Remove ${entry.email} from the waiting list? Reason (optional):`
    );
    if (reason === null) return; // cancelled
    setErrors(null);
    try {
      setListing(await removeWaitingListEntry(entry.id, reason));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) refreshSession();
      else setErrors(["The remove failed. Try again."]);
    }
  };

  const handleSendInvitations = async () => {
    // The confirm repeats the refusal rule and the count about to be
    // emailed; the backend enforces both regardless.
    const confirmed = window.confirm(
      `Send the one promised invitation to ${listing.invitable} ` +
        `invitable ${listing.invitable === 1 ? "entry" : "entries"}?\n\n` +
        "This only works while the site is open — in coming_soon the " +
        "send refuses, because the links would 404. Already-invited " +
        "entries are always skipped, so re-running after a partial " +
        "failure reaches only the failed rows."
    );
    if (!confirmed) return;
    setErrors(null);
    setSummary(null);
    setSending(true);
    try {
      setSummary(await sendInvitations());
      refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) refreshSession();
      else if (err instanceof ApiError && err.status === 422 && err.data?.errors)
        setErrors(err.data.errors);
      else setErrors(["The send failed. Try again."]);
    } finally {
      setSending(false);
    }
  };

  const handleResend = async (entry) => {
    setErrors(null);
    try {
      setListing(await resendInvitation(entry.id));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) refreshSession();
      else if (err instanceof ApiError && err.status === 422 && err.data?.errors)
        setErrors(err.data.errors);
      else setErrors(["The resend failed. Try again."]);
    }
  };

  const needle = query.trim().toLowerCase();
  const shown = (listing?.entries || []).filter(
    (entry) =>
      !needle ||
      entry.name.toLowerCase().includes(needle) ||
      entry.email.toLowerCase().includes(needle)
  );

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Waiting list</h1>
      <p className={styles.muted}>
        CPAs who asked to hear when the course opens. Not CPE records:
        Remove honors an off-the-list request immediately, and removed
        entries leave every count, listing, and export. Flipping the site
        mode to open closes submissions permanently.
      </p>

      <section className={styles.card}>
        <h2 className={styles.subheading}>Invitations</h2>
        <p className={styles.muted}>
          The one email each entry was promised: the site is open, here is
          where to register. Send refuses while the site is coming_soon —
          the links would 404 — and never emails a removed or
          already-invited entry, so it is safe to press again after a
          partial failure.
        </p>
        {listing !== null && (
          <div className={styles.toolbar}>
            <span className={styles.count}>
              {listing.total} active · {listing.invited} invited ·{" "}
              {listing.failed} failed · {listing.invitable} invitable
            </span>
            <button
              className={styles.button}
              type="button"
              disabled={sending || listing.invitable === 0}
              onClick={handleSendInvitations}
            >
              {sending ? "Sending…" : "Send invitations"}
            </button>
          </div>
        )}
        {siteMode === "coming_soon" && (
          <p className={styles.muted}>
            The site is still coming_soon, so the send will refuse. Open
            the site first — the flip itself never sends; this button is a
            deliberate, separate step.
          </p>
        )}
        {summary && (
          <p className={styles.summary}>
            Run finished: {summary.attempted} attempted, {summary.sent}{" "}
            sent, {summary.failed} failed, {summary.skipped_already_invited}{" "}
            skipped as already invited.
          </p>
        )}
      </section>

      <section className={styles.card}>
        <div className={styles.toolbar}>
          <span className={styles.count}>
            {listing === null ? "…" : `${listing.total} on the list`}
          </span>
          <input
            className={styles.input}
            placeholder="Search name or email"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <a className={styles.button} href={waitingListCsvUrl}>
            Export CSV
          </a>
        </div>
        {errors && <div className={styles.errorPanel}>{errors.join(" ")}</div>}
        {loadError && <div className={styles.errorPanel}>{loadError}</div>}
        {listing !== null && listing.total === 0 && (
          <p className={styles.muted}>Nobody yet.</p>
        )}
        {shown.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>State</th>
                <th>Firm</th>
                <th>Signed up</th>
                <th>Invitation</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.name}</td>
                  <td>{entry.email}</td>
                  <td>{entry.state}</td>
                  <td>{entry.firm || "—"}</td>
                  <td>{new Date(entry.created_at).toLocaleString()}</td>
                  <td
                    className={
                      entry.invitation_status === "failed"
                        ? styles.failed
                        : undefined
                    }
                  >
                    {invitationCell(entry)}
                  </td>
                  <td className={styles.actions}>
                    {entry.invitation_status === "failed" && (
                      <button
                        className={styles.smallButton}
                        type="button"
                        onClick={() => handleResend(entry)}
                      >
                        Resend
                      </button>
                    )}
                    <button
                      className={styles.smallButtonDanger}
                      type="button"
                      onClick={() => handleRemove(entry)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

export default AdminWaitingList;
