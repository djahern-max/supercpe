import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import { ApiError } from "../../api/client";
import {
  createAccount,
  deactivateAccount,
  listAccounts,
  reactivateAccount,
  revokeAccountSessions,
  setAccountRole,
} from "../../api/accounts";
import styles from "./AdminAccounts.module.css";

const ROLES = ["participant", "reviewer", "admin"];

function ErrorPanel({ errors }) {
  if (!errors || errors.length === 0) return null;
  return (
    <div className={styles.errorPanel}>
      <ul className={styles.errorList}>
        {errors.map((error) => (
          <li key={error}>{error}</li>
        ))}
      </ul>
    </div>
  );
}

function AdminAccounts() {
  const { account: me, refresh: refreshSession } = useSession();
  const [accounts, setAccounts] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("reviewer");
  const [displayName, setDisplayName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createErrors, setCreateErrors] = useState(null);
  // {email, initial_password} for the account just created; shown once.
  const [created, setCreated] = useState(null);
  const [copied, setCopied] = useState(false);
  const [listErrors, setListErrors] = useState(null);

  const refresh = useCallback(() => {
    listAccounts()
      .then((data) => {
        setAccounts(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else setLoadError("Could not load accounts. Is the backend running?");
      });
  }, [refreshSession]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleApiError = (err, setErrors) => {
    if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
      setErrors(err.data.errors);
    } else if (err instanceof ApiError && err.status === 401) {
      refreshSession();
    } else {
      setErrors(["The request failed. Try again."]);
    }
  };

  const handleCreate = async (event) => {
    event.preventDefault();
    setCreating(true);
    setCreateErrors(null);
    setCreated(null);
    setCopied(false);
    try {
      const data = await createAccount({
        email: email.trim(),
        role,
        display_name: displayName.trim(),
      });
      setCreated(data);
      setEmail("");
      setDisplayName("");
      refresh();
    } catch (err) {
      handleApiError(err, setCreateErrors);
    } finally {
      setCreating(false);
    }
  };

  const act = async (call) => {
    setListErrors(null);
    try {
      await call();
      refresh();
    } catch (err) {
      handleApiError(err, setListErrors);
    }
  };

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Accounts</h1>
      <p className={styles.muted}>
        Who can sign in, and as what. Accounts are deactivated, never
        deleted: the records they signed (9.02) keep their name.
      </p>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Create an account</h2>
        <form className={styles.createRow} onSubmit={handleCreate}>
          <input
            className={styles.input}
            type="email"
            placeholder="Email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <input
            className={styles.input}
            placeholder="Display name (optional)"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
          <select
            className={styles.input}
            value={role}
            onChange={(event) => setRole(event.target.value)}
          >
            {ROLES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <button
            className={styles.button}
            type="submit"
            disabled={!email.trim() || creating}
          >
            {creating ? "Creating…" : "Create account"}
          </button>
        </form>
        <ErrorPanel errors={createErrors} />
        {created && (
          <div className={styles.createdPanel}>
            <p className={styles.createdLine}>
              Initial password for {created.email}:{" "}
              <code className={styles.password}>{created.initial_password}</code>
              <button
                className={styles.smallButton}
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(created.initial_password);
                  setCopied(true);
                }}
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </p>
            <p className={styles.mutedStrong}>
              This will not be shown again. They must change it on first
              sign-in.
            </p>
          </div>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>All accounts</h2>
        <ErrorPanel errors={listErrors} />
        {loadError && <div className={styles.errorPanel}>{loadError}</div>}
        {!loadError && accounts === null && (
          <p className={styles.muted}>Loading accounts…</p>
        )}
        {accounts !== null && accounts.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Active</th>
                <th>Last sign-in</th>
                <th>Open sessions</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((row) => (
                <tr key={row.id} className={row.is_active ? "" : styles.inactive}>
                  <td>
                    {row.email}
                    {row.id === me?.id && (
                      <span className={styles.youBadge}>you</span>
                    )}
                  </td>
                  <td>
                    <select
                      className={styles.inputSmall}
                      value={row.role}
                      disabled={row.id === me?.id}
                      onChange={(event) =>
                        act(() => setAccountRole(row.id, event.target.value))
                      }
                    >
                      {ROLES.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>{row.is_active ? "yes" : "deactivated"}</td>
                  <td>
                    {row.last_sign_in
                      ? new Date(row.last_sign_in).toLocaleString()
                      : "never"}
                  </td>
                  <td>{row.open_sessions}</td>
                  <td className={styles.actions}>
                    <button
                      className={styles.smallButton}
                      type="button"
                      onClick={() => act(() => revokeAccountSessions(row.id))}
                    >
                      Sign out everywhere
                    </button>
                    {row.is_active ? (
                      <button
                        className={styles.smallButtonDanger}
                        type="button"
                        disabled={row.id === me?.id}
                        onClick={() => act(() => deactivateAccount(row.id))}
                      >
                        Deactivate
                      </button>
                    ) : (
                      <button
                        className={styles.smallButton}
                        type="button"
                        onClick={() => act(() => reactivateAccount(row.id))}
                      >
                        Reactivate
                      </button>
                    )}
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

export default AdminAccounts;
