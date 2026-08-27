import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { clearToken, getToken, setToken } from "../../admin/token";
import { ApiError } from "../../api/client";
import {
  getSponsor,
  setStateRegistrations,
  updateSponsor,
} from "../../api/sponsor";
import styles from "./AdminSponsor.module.css";

const PROFILE_FIELDS = [
  { name: "name", label: "Sponsor name" },
  { name: "legal_name", label: "Legal name" },
  { name: "website", label: "Website" },
  { name: "contact_email", label: "Contact email" },
  { name: "contact_phone", label: "Contact phone" },
  { name: "address", label: "Address" },
];

const MISSING_LABELS = {
  name: "Sponsor name is blank",
  national_registry_id: "NASBA sponsor ID is blank",
  registry_status: "Not yet on the National Registry",
};

function TokenForm({ onSubmit }) {
  const [value, setValue] = useState("");
  return (
    <form
      className={styles.tokenForm}
      onSubmit={(event) => {
        event.preventDefault();
        if (value.trim()) onSubmit(value.trim());
      }}
    >
      <label className={styles.label} htmlFor="admin-token">
        Admin token
      </label>
      <input
        id="admin-token"
        className={styles.input}
        type="password"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Paste the admin token"
      />
      <button className={styles.button} type="submit" disabled={!value.trim()}>
        Continue
      </button>
    </form>
  );
}

function StatusPanel({ missingFields }) {
  if (missingFields.length === 0) {
    return <div className={styles.successPanel}>Certificates can be issued.</div>;
  }
  return (
    <div className={styles.warnPanel}>
      <p className={styles.panelTitle}>
        Certificates cannot be issued yet. Missing:
      </p>
      <ul className={styles.panelList}>
        {missingFields.map((field) => (
          <li key={field}>{MISSING_LABELS[field] ?? field}</li>
        ))}
      </ul>
    </div>
  );
}

function ErrorPanel({ errors }) {
  if (!errors || errors.length === 0) return null;
  return (
    <div className={styles.errorPanel}>
      <ul className={styles.panelList}>
        {errors.map((error) => (
          <li key={error}>{error}</li>
        ))}
      </ul>
    </div>
  );
}

function profileToForm(profile) {
  return {
    name: profile.name,
    legal_name: profile.legal_name,
    registry_status: profile.registry_status,
    national_registry_id: profile.national_registry_id,
    website: profile.website,
    contact_email: profile.contact_email,
    contact_phone: profile.contact_phone,
    address: profile.address,
    other_certificate_statements: profile.other_certificate_statements,
  };
}

function AdminSponsor() {
  const [token, setTokenState] = useState(getToken());
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState(null);
  const [registrations, setRegistrations] = useState(null);
  const [profileErrors, setProfileErrors] = useState(null);
  const [registrationErrors, setRegistrationErrors] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [savingRegistrations, setSavingRegistrations] = useState(false);

  const handleAuthFailure = useCallback(() => {
    clearToken();
    setTokenState(null);
    setProfile(null);
    setForm(null);
    setRegistrations(null);
  }, []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    getSponsor(token)
      .then((data) => {
        if (cancelled) return;
        setProfile(data);
        setForm(profileToForm(data));
        setRegistrations(data.state_registrations);
        setLoadError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) handleAuthFailure();
        else setLoadError("Could not load the sponsor profile. Is the backend running?");
      });
    return () => {
      cancelled = true;
    };
  }, [token, handleAuthFailure]);

  if (!token) {
    return (
      <main className={styles.page}>
        <AdminNav />
        <h1 className={styles.heading}>Sponsor</h1>
        <TokenForm
          onSubmit={(value) => {
            setToken(value);
            setTokenState(value);
          }}
        />
      </main>
    );
  }

  const setField = (name, value) => {
    setForm((current) => ({ ...current, [name]: value }));
  };

  const handleStatusChange = (status) => {
    // The pair behaves together: leaving the Registry clears the ID.
    setForm((current) => ({
      ...current,
      registry_status: status,
      national_registry_id:
        status === "not_registered" ? "" : current.national_registry_id,
    }));
  };

  const handleSaveProfile = async (event) => {
    event.preventDefault();
    setSaving(true);
    setProfileErrors(null);
    try {
      const data = await updateSponsor(token, form);
      setProfile(data);
      setForm(profileToForm(data));
      setRegistrations(data.state_registrations);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) handleAuthFailure();
      else if (err instanceof ApiError && err.status === 422 && err.data?.errors)
        setProfileErrors(err.data.errors);
      else setProfileErrors(["Saving failed. Try again."]);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveRegistrations = async () => {
    setSavingRegistrations(true);
    setRegistrationErrors(null);
    try {
      const rows = registrations.map((row) => ({
        state: row.state,
        registration_number: row.registration_number,
        notes: row.notes,
      }));
      const data = await setStateRegistrations(token, rows);
      setRegistrations(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) handleAuthFailure();
      else if (err instanceof ApiError && err.status === 422 && err.data?.errors)
        setRegistrationErrors(err.data.errors);
      else if (err instanceof ApiError && err.status === 422)
        setRegistrationErrors([
          "Each row needs a two-letter state code and a registration number.",
        ]);
      else setRegistrationErrors(["Saving failed. Try again."]);
    } finally {
      setSavingRegistrations(false);
    }
  };

  const setRegistrationField = (index, name, value) => {
    setRegistrations((current) =>
      current.map((row, i) => (i === index ? { ...row, [name]: value } : row))
    );
  };

  const registered = form?.registry_status === "registered";

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Sponsor</h1>

      {loadError && <div className={styles.errorPanel}>{loadError}</div>}
      {!loadError && profile === null && (
        <p className={styles.muted}>Loading sponsor profile…</p>
      )}

      {profile !== null && form !== null && (
        <>
          <StatusPanel missingFields={profile.missing_fields} />

          <form className={styles.form} onSubmit={handleSaveProfile}>
            {PROFILE_FIELDS.map(({ name, label }) => (
              <div className={styles.field} key={name}>
                <label className={styles.label} htmlFor={`sponsor-${name}`}>
                  {label}
                </label>
                <input
                  id={`sponsor-${name}`}
                  className={styles.input}
                  type="text"
                  value={form[name]}
                  onChange={(event) => setField(name, event.target.value)}
                />
              </div>
            ))}

            <div className={styles.field}>
              <label className={styles.label} htmlFor="sponsor-registry-status">
                National Registry status
              </label>
              <select
                id="sponsor-registry-status"
                className={styles.input}
                value={form.registry_status}
                onChange={(event) => handleStatusChange(event.target.value)}
              >
                <option value="not_registered">Not registered</option>
                <option value="registered">Registered</option>
              </select>
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="sponsor-registry-id">
                NASBA sponsor ID
              </label>
              <input
                id="sponsor-registry-id"
                className={styles.input}
                type="text"
                value={form.national_registry_id}
                onChange={(event) =>
                  setField("national_registry_id", event.target.value)
                }
                disabled={!registered}
                required={registered}
              />
            </div>

            <div className={styles.field}>
              <label
                className={styles.label}
                htmlFor="sponsor-other-statements"
              >
                Other certificate statements (one per line)
              </label>
              <textarea
                id="sponsor-other-statements"
                className={styles.textarea}
                rows={3}
                value={form.other_certificate_statements}
                onChange={(event) =>
                  setField("other_certificate_statements", event.target.value)
                }
              />
            </div>

            <ErrorPanel errors={profileErrors} />
            <button className={styles.button} type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save profile"}
            </button>
          </form>

          <section className={styles.registrations}>
            <h2 className={styles.subheading}>State registrations</h2>
            <p className={styles.muted}>
              Only the registrations the sponsor actually holds. Certificates
              will print them where a state board requires one.
            </p>
            {registrations.length > 0 && (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>State</th>
                    <th>Registration number</th>
                    <th>Notes</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {registrations.map((row, index) => (
                    <tr key={index}>
                      <td>
                        <input
                          className={styles.inputSmall}
                          type="text"
                          maxLength={2}
                          value={row.state}
                          onChange={(event) =>
                            setRegistrationField(index, "state", event.target.value)
                          }
                        />
                      </td>
                      <td>
                        <input
                          className={styles.input}
                          type="text"
                          value={row.registration_number}
                          onChange={(event) =>
                            setRegistrationField(
                              index,
                              "registration_number",
                              event.target.value
                            )
                          }
                        />
                      </td>
                      <td>
                        <input
                          className={styles.input}
                          type="text"
                          value={row.notes}
                          onChange={(event) =>
                            setRegistrationField(index, "notes", event.target.value)
                          }
                        />
                      </td>
                      <td>
                        <button
                          className={styles.linkButton}
                          type="button"
                          onClick={() =>
                            setRegistrations((current) =>
                              current.filter((_, i) => i !== index)
                            )
                          }
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <ErrorPanel errors={registrationErrors} />
            <div className={styles.registrationActions}>
              <button
                className={styles.linkButton}
                type="button"
                onClick={() =>
                  setRegistrations((current) => [
                    ...current,
                    { state: "", registration_number: "", notes: "" },
                  ])
                }
              >
                Add row
              </button>
              <button
                className={styles.button}
                type="button"
                disabled={savingRegistrations}
                onClick={handleSaveRegistrations}
              >
                {savingRegistrations ? "Saving…" : "Save registrations"}
              </button>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

export default AdminSponsor;
