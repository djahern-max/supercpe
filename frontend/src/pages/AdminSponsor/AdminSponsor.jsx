import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import { ApiError } from "../../api/client";
import { getAdminPolicies, publishPolicy } from "../../api/admin";
import {
  getSponsor,
  setStateRegistrations,
  updateSponsor,
} from "../../api/sponsor";
import { getSite, listSiteModeChanges, setSiteMode } from "../../api/site";
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
  legal_name: "Legal name is blank",
  national_registry_id: "NASBA sponsor ID is blank",
  registry_status: "Not yet on the National Registry",
};

// What each flip changes, quoted in the confirm step.
const MODE_CONSEQUENCE = {
  open: "The catalog and course pages become public.",
  coming_soon:
    "The catalog and course pages show only the coming-soon placeholder to anyone not signed in.",
};

function StatusPanel({ missingFields, missingForIssuance }) {
  // Issuance gates on the smaller list (010): a sponsor off the Registry
  // may still issue certificates — they simply cannot print item 8.
  const launchOnly = missingFields.filter(
    (field) => !missingForIssuance.includes(field)
  );
  return (
    <>
      {missingForIssuance.length === 0 ? (
        <div className={styles.successPanel}>Certificates can be issued.</div>
      ) : (
        <div className={styles.warnPanel}>
          <p className={styles.panelTitle}>
            Certificates cannot be issued yet. Missing:
          </p>
          <ul className={styles.panelList}>
            {missingForIssuance.map((field) => (
              <li key={field}>{MISSING_LABELS[field] ?? field}</li>
            ))}
          </ul>
        </div>
      )}
      {launchOnly.length > 0 && (
        <div className={styles.warnPanel}>
          <p className={styles.panelTitle}>
            Not yet fully credentialed for launch:
          </p>
          <ul className={styles.panelList}>
            {launchOnly.map((field) => (
              <li key={field}>{MISSING_LABELS[field] ?? field}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function LaunchPanel({ findings }) {
  // 011: the launch findings. Block findings are exactly what refuses the
  // open flip (site_open_blockers); warn findings sit beside them.
  if (!findings || findings.length === 0) {
    return (
      <div className={styles.successPanel}>
        Launch checks pass: the site can open.
      </div>
    );
  }
  const blocks = findings.filter((finding) => finding.level === "block");
  const warns = findings.filter((finding) => finding.level === "warn");
  return (
    <>
      {blocks.length > 0 && (
        <div className={styles.warnPanel}>
          <p className={styles.panelTitle}>
            The site cannot open until these are resolved:
          </p>
          <ul className={styles.panelList}>
            {blocks.map((finding) => (
              <li key={finding.code + finding.message}>{finding.message}</li>
            ))}
          </ul>
        </div>
      )}
      {warns.length > 0 && (
        <div className={styles.warnPanel}>
          <p className={styles.panelTitle}>Attention needed:</p>
          <ul className={styles.panelList}>
            {warns.map((finding) => (
              <li key={finding.code + finding.message}>{finding.message}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

const POLICY_KINDS = [
  { kind: "registration", label: "Registration and attendance" },
  { kind: "refund", label: "Refund and cancellation" },
  { kind: "complaint", label: "Complaint resolution" },
];

/**
 * The 8.01.1 policies: append-only versions, published from here. The
 * current version of a kind is derived server-side; corrections are new
 * versions, never edits.
 */
function PoliciesCard({ onAuthFailure, onPublished }) {
  const [data, setData] = useState(null);
  const [kind, setKind] = useState("registration");
  const [body, setBody] = useState("");
  const [errors, setErrors] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getAdminPolicies()
      .then(setData)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) onAuthFailure();
        else setErrors(["Could not load the policies."]);
      });
  }, [onAuthFailure]);

  const handlePublish = async () => {
    setSaving(true);
    setErrors(null);
    try {
      const next = await publishPolicy(kind, body);
      setData(next);
      setBody("");
      if (onPublished) onPublished();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onAuthFailure();
      else if (err instanceof ApiError && err.status === 422 && err.data?.errors)
        setErrors(err.data.errors);
      else setErrors(["Publishing failed. Try again."]);
    } finally {
      setSaving(false);
    }
  };

  const current = (data?.history ?? []).filter((v) => v.is_current);

  return (
    <section className={styles.registrations}>
      <h2 className={styles.subheading}>Policies</h2>
      <p className={styles.muted}>
        Published in advance of participation (8.01.1). A new version takes
        effect immediately; every version is kept. The re-take policy and
        the sponsor statement are rendered from code and cannot be edited
        here.
      </p>

      {POLICY_KINDS.map(({ kind: k, label }) => {
        const version = current.find((v) => v.kind === k);
        return (
          <div key={k} className={styles.policyRow}>
            <p className={styles.panelTitle}>
              {label}
              {version ? (
                <span className={styles.mutedInline}>
                  {" "}
                  — effective{" "}
                  {new Date(version.effective_at).toLocaleDateString()}
                </span>
              ) : (
                <span className={styles.missingInline}> — not published</span>
              )}
            </p>
            {version && <p className={styles.policyBody}>{version.body}</p>}
          </div>
        );
      })}

      <div className={styles.field}>
        <label className={styles.label} htmlFor="policy-kind">
          Publish a new version
        </label>
        <select
          id="policy-kind"
          className={styles.input}
          value={kind}
          onChange={(event) => setKind(event.target.value)}
        >
          {POLICY_KINDS.map(({ kind: k, label }) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <textarea
        className={styles.textarea}
        rows={6}
        placeholder="The policy text (Markdown)."
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />
      <ErrorPanel errors={errors} />
      <div className={styles.registrationActions}>
        <button
          className={styles.button}
          type="button"
          disabled={saving || !body.trim()}
          onClick={handlePublish}
        >
          {saving ? "Publishing…" : "Publish version"}
        </button>
      </div>
    </section>
  );
}

function FindingsPanel({ findings }) {
  if (!findings || findings.length === 0) return null;
  return (
    <div className={styles.warnPanel}>
      <p className={styles.panelTitle}>Overdue certificates</p>
      <ul className={styles.panelList}>
        {findings.map((finding) => (
          <li key={finding.code + finding.message}>{finding.message}</li>
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

/**
 * The site mode card: current mode, a switch with a confirm step that
 * quotes what changes, an optional note, and the change log. Reads only
 * /api/v1/site and the change log — deliberately nothing that could carry
 * registry facts.
 */
function SiteModeCard({ onAuthFailure }) {
  const [mode, setMode] = useState(null);
  const [changes, setChanges] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState(null);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    getSite()
      .then((site) => setMode(site.site_mode))
      .catch(() => setErrors(["Could not load the site mode."]));
    listSiteModeChanges()
      .then(setChanges)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) onAuthFailure();
        else setChanges([]);
      });
  }, [onAuthFailure]);

  if (mode === null) {
    return (
      <section className={styles.registrations}>
        <h2 className={styles.subheading}>Site mode</h2>
        <ErrorPanel errors={errors} />
        {!errors && <p className={styles.muted}>Loading…</p>}
      </section>
    );
  }

  const target = mode === "open" ? "coming_soon" : "open";

  const handleConfirm = async () => {
    setSwitching(true);
    setErrors(null);
    try {
      const log = await setSiteMode(target, note.trim());
      setChanges(log);
      setMode(target);
      setConfirming(false);
      setNote("");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onAuthFailure();
      else if (err instanceof ApiError && err.status === 422 && err.data?.errors)
        setErrors(err.data.errors);
      else setErrors(["The switch failed. Try again."]);
    } finally {
      setSwitching(false);
    }
  };

  return (
    <section className={styles.registrations}>
      <h2 className={styles.subheading}>Site mode</h2>
      <p className={styles.muted}>
        Current mode: <strong>{mode}</strong>.{" "}
        {mode === "open"
          ? "The catalog and course pages are public."
          : "Visitors without a sign-in see only the coming-soon placeholder."}
      </p>

      {!confirming ? (
        <button
          className={styles.button}
          type="button"
          onClick={() => setConfirming(true)}
        >
          Switch to {target === "open" ? "open" : "coming soon"}…
        </button>
      ) : (
        <div className={styles.modeConfirm}>
          <p className={styles.panelTitle}>{MODE_CONSEQUENCE[target]}</p>
          <input
            className={styles.input}
            placeholder="Note for the change log (optional)"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
          <div className={styles.registrationActions}>
            <button
              className={styles.button}
              type="button"
              disabled={switching}
              onClick={handleConfirm}
            >
              {switching ? "Switching…" : `Switch to ${target}`}
            </button>
            <button
              className={styles.linkButton}
              type="button"
              onClick={() => {
                setConfirming(false);
                setNote("");
                setErrors(null);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      <ErrorPanel errors={errors} />

      {changes !== null && changes.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>When</th>
              <th>Who</th>
              <th>Change</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {changes.map((change) => (
              <tr key={change.id}>
                <td>{new Date(change.changed_at).toLocaleString()}</td>
                <td>{change.changed_by_email}</td>
                <td>
                  {change.from_mode} → {change.to_mode}
                </td>
                <td>{change.note || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {changes !== null && changes.length === 0 && (
        <p className={styles.muted}>The mode has never been changed.</p>
      )}
    </section>
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
  const { refresh: refreshSession } = useSession();
  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState(null);
  const [registrations, setRegistrations] = useState(null);
  const [profileErrors, setProfileErrors] = useState(null);
  const [registrationErrors, setRegistrationErrors] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [savingRegistrations, setSavingRegistrations] = useState(false);

  const handleAuthFailure = useCallback(() => {
    refreshSession();
  }, [refreshSession]);

  // Refreshes the launch findings after a policy publish, without
  // touching a form the admin may be mid-edit on.
  const reloadProfile = useCallback(() => {
    getSponsor()
      .then((data) => setProfile(data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    getSponsor()
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
  }, [handleAuthFailure]);

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
      const data = await updateSponsor(form);
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
      const data = await setStateRegistrations(rows);
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
          <StatusPanel
            missingFields={profile.missing_fields}
            missingForIssuance={profile.missing_for_issuance}
          />
          <LaunchPanel findings={profile.launch_findings} />
          <FindingsPanel findings={profile.findings} />

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

          <PoliciesCard
            onAuthFailure={handleAuthFailure}
            onPublished={reloadProfile}
          />

          <SiteModeCard onAuthFailure={handleAuthFailure} />

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
