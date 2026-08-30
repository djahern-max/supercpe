import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { ApiError } from "../../api/client";
import {
  listWaitingList,
  removeWaitingListEntry,
  waitingListCsvUrl,
} from "../../api/landing";
import { useSession } from "../../auth/SessionContext.jsx";
import styles from "./AdminWaitingList.module.css";

function AdminWaitingList() {
  const { refresh: refreshSession } = useSession();
  const [listing, setListing] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [query, setQuery] = useState("");
  const [errors, setErrors] = useState(null);

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
                  <td className={styles.actions}>
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
