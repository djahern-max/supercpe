import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import { ApiError } from "../../api/client";
import { createSme, deleteSme, listSmes, updateSme } from "../../api/admin";
import styles from "./AdminSmes.module.css";

const CREDENTIAL_TYPES = [
  { value: "cpa", label: "CPA" },
  { value: "tax_attorney", label: "Tax attorney" },
  { value: "enrolled_agent", label: "Enrolled agent" },
  { value: "other", label: "Other" },
];

const LICENSE_STATUSES = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "unknown", label: "Unknown" },
];

const EMPTY_FORM = {
  name: "",
  credentials: "",
  credential_type: "other",
  license_jurisdiction: "",
  license_number: "",
  license_status: "unknown",
  email: "",
  notes: "",
};

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

function credentialLabel(value) {
  return CREDENTIAL_TYPES.find((t) => t.value === value)?.label ?? value;
}

function AdminSmes() {
  const { refresh: refreshSession } = useSession();
  const [smes, setSmes] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  // null: creating; an id: editing that SME.
  const [editingId, setEditingId] = useState(null);
  const [formErrors, setFormErrors] = useState(null);
  const [listErrors, setListErrors] = useState(null);

  const refresh = useCallback(() => {
    listSmes()
      .then((data) => {
        setSmes(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else setLoadError("Could not load the experts. Is the backend running?");
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

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormErrors(null);
    const body = { ...form, name: form.name.trim() };
    try {
      if (editingId === null) await createSme(body);
      else await updateSme(editingId, body);
      setForm(EMPTY_FORM);
      setEditingId(null);
      refresh();
    } catch (err) {
      handleApiError(err, setFormErrors);
    }
  };

  const startEdit = (sme) => {
    setEditingId(sme.id);
    setFormErrors(null);
    setForm({
      name: sme.name,
      credentials: sme.credentials,
      credential_type: sme.credential_type,
      license_jurisdiction: sme.license_jurisdiction,
      license_number: sme.license_number,
      license_status: sme.license_status,
      email: sme.email,
      notes: sme.notes,
    });
  };

  const handleDelete = async (sme) => {
    if (!window.confirm(`Delete ${sme.name}?`)) return;
    setListErrors(null);
    try {
      await deleteSme(sme.id);
      if (editingId === sme.id) {
        setEditingId(null);
        setForm(EMPTY_FORM);
      }
      refresh();
    } catch (err) {
      handleApiError(err, setListErrors);
    }
  };

  const field = (name) => ({
    value: form[name],
    onChange: (event) => setForm({ ...form, [name]: event.target.value }),
  });

  if (loadError) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <div className={styles.errorPanel}>{loadError}</div>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Subject matter experts</h1>
      <p className={styles.muted}>
        The people named as course developers (4.01.1) and content reviewers
        (4.02). Not logins: a person, their credentials, and their license
        claim.
      </p>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>
          {editingId === null ? "Add an expert" : "Edit expert"}
        </h2>
        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span className={styles.label}>Name</span>
              <input className={styles.input} {...field("name")} />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Credentials (as they print)</span>
              <input
                className={styles.input}
                placeholder="CPA"
                {...field("credentials")}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Credential type</span>
              <select className={styles.input} {...field("credential_type")}>
                {CREDENTIAL_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.label}>License status</span>
              <select className={styles.input} {...field("license_status")}>
                {LICENSE_STATUSES.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.label}>License jurisdiction</span>
              <input
                className={styles.input}
                placeholder="NH"
                {...field("license_jurisdiction")}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>License number</span>
              <input className={styles.input} {...field("license_number")} />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Email (optional)</span>
              <input className={styles.input} {...field("email")} />
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Notes</span>
              <input className={styles.input} {...field("notes")} />
            </label>
          </div>
          <div className={styles.formActions}>
            <button
              className={styles.button}
              type="submit"
              disabled={!form.name.trim()}
            >
              {editingId === null ? "Add expert" : "Save changes"}
            </button>
            {editingId !== null && (
              <button
                className={styles.smallButton}
                type="button"
                onClick={() => {
                  setEditingId(null);
                  setForm(EMPTY_FORM);
                  setFormErrors(null);
                }}
              >
                Cancel
              </button>
            )}
          </div>
          <ErrorPanel errors={formErrors} />
        </form>
        <p className={styles.muted}>
          License claims are recorded as stated; superCPE does not verify them
          against any state board.
        </p>
      </section>

      <section className={styles.card}>
        <h2 className={styles.sectionTitle}>Experts</h2>
        <ErrorPanel errors={listErrors} />
        {smes === null && <p className={styles.muted}>Loading…</p>}
        {smes !== null && smes.length === 0 && (
          <p className={styles.muted}>No experts recorded yet.</p>
        )}
        {smes !== null && smes.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Credentials</th>
                <th>Type</th>
                <th>License</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {smes.map((sme) => (
                <tr key={sme.id}>
                  <td>{sme.name}</td>
                  <td>{sme.credentials}</td>
                  <td>{credentialLabel(sme.credential_type)}</td>
                  <td>
                    {sme.license_jurisdiction || sme.license_number
                      ? `${sme.license_jurisdiction} ${sme.license_number}`.trim()
                      : "—"}
                  </td>
                  <td>{sme.license_status}</td>
                  <td className={styles.actions}>
                    <button
                      className={styles.smallButton}
                      type="button"
                      onClick={() => startEdit(sme)}
                    >
                      Edit
                    </button>
                    <button
                      className={styles.smallButtonDanger}
                      type="button"
                      onClick={() => handleDelete(sme)}
                    >
                      Delete
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

export default AdminSmes;
