import { useCallback, useEffect, useState } from "react";
import AdminNav from "../../admin/AdminNav.jsx";
import { listJurisdictions, updateJurisdiction } from "../../api/admin";
import { ApiError } from "../../api/client";
import { useSession } from "../../auth/SessionContext.jsx";
import styles from "./AdminJurisdictions.module.css";

const INCREMENTS = [
  ["unknown", "Unknown"],
  ["one_fifth", "One-fifth (0.2)"],
  ["one_half", "One-half (0.5)"],
  ["whole", "Whole (1.0)"],
];

function editableFields(row) {
  return {
    credit_increment: row.credit_increment,
    non_technical_cap_note: row.non_technical_cap_note,
    source: row.source,
    verified_on: row.verified_on || "",
    notes: row.notes,
  };
}

/**
 * 020: the per-jurisdiction credit policy table. Every displayed fact is
 * one Dane verified against a source on a date; Displayable and the
 * staleness nudge are derived by the server, never stored. The table
 * ships with all 55 codes and no verified rows.
 */
function Row({ row, onSaved, onError }) {
  const [fields, setFields] = useState(() => editableFields(row));
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const set = (key) => (event) => {
    setFields({ ...fields, [key]: event.target.value });
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const saved = await updateJurisdiction(row.jurisdiction, {
        ...fields,
        verified_on: fields.verified_on || null,
      });
      setFields(editableFields(saved));
      setDirty(false);
      onSaved(saved);
    } catch (err) {
      onError(
        err instanceof ApiError && err.status === 422 && err.data?.errors
          ? err.data.errors
          : [`Saving ${row.jurisdiction} failed. Try again.`]
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <tr>
      <td className={styles.codeCell}>
        <strong>{row.jurisdiction}</strong>
        <span className={styles.stateName}>{row.name}</span>
      </td>
      <td>
        <select
          className={styles.input}
          value={fields.credit_increment}
          onChange={set("credit_increment")}
        >
          {INCREMENTS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </td>
      <td>
        <input
          className={styles.input}
          value={fields.non_technical_cap_note}
          onChange={set("non_technical_cap_note")}
          placeholder="Quoted cap, if any"
        />
      </td>
      <td>
        <input
          className={styles.input}
          value={fields.source}
          onChange={set("source")}
          placeholder="Where the rule was read"
        />
      </td>
      <td>
        <input
          className={styles.input}
          type="date"
          value={fields.verified_on}
          onChange={set("verified_on")}
        />
      </td>
      <td>
        <input
          className={styles.input}
          value={fields.notes}
          onChange={set("notes")}
        />
      </td>
      <td className={styles.derivedCell}>
        {row.displayable ? (
          <span className={styles.displayable}>Yes</span>
        ) : (
          <span className={styles.notDisplayable}>No</span>
        )}
        {row.verification_stale && (
          <span
            className={styles.stale}
            title="Verified more than 12 months ago — re-check the source."
          >
            Re-verify
          </span>
        )}
      </td>
      <td>
        <button
          className={styles.smallButton}
          type="button"
          disabled={!dirty || saving}
          onClick={handleSave}
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </td>
    </tr>
  );
}

function AdminJurisdictions() {
  const { refresh: refreshSession } = useSession();
  const [rows, setRows] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [errors, setErrors] = useState(null);

  const refresh = useCallback(() => {
    listJurisdictions()
      .then((data) => {
        setRows(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) refreshSession();
        else
          setLoadError(
            "Could not load the jurisdictions. Is the backend running?"
          );
      });
  }, [refreshSession]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSaved = (saved) => {
    setErrors(null);
    setRows((current) =>
      current.map((row) =>
        row.jurisdiction === saved.jurisdiction ? saved : row
      )
    );
  };

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Jurisdictions</h1>
      <p className={styles.muted}>
        Board credit rules, one row per jurisdiction, shown to a
        participant only when the row has an increment, a source, and a
        verification date (Displayable). Caps are quoted, never computed.
        Rows verified more than 12 months ago ask to be re-verified.
        Boards of accountancy keep final authority — these rows never
        speak for one.
      </p>

      {errors && <div className={styles.errorPanel}>{errors.join(" ")}</div>}
      {loadError && <div className={styles.errorPanel}>{loadError}</div>}
      {rows === null && !loadError && <p className={styles.muted}>Loading…</p>}

      {rows !== null && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Jurisdiction</th>
                <th>Credit increment</th>
                <th>Non-technical cap (quoted)</th>
                <th>Source</th>
                <th>Verified on</th>
                <th>Notes (admin only)</th>
                <th>Displayable</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Row
                  key={row.jurisdiction}
                  row={row}
                  onSaved={handleSaved}
                  onError={setErrors}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

export default AdminJurisdictions;
