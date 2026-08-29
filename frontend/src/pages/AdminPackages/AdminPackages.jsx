import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  deletePackage,
  getPackage,
  getTranscript,
  listPackages,
  uploadPackage,
} from "../../api/admin";
import AdminNav from "../../admin/AdminNav.jsx";
import { useSession } from "../../auth/SessionContext.jsx";
import styles from "./AdminPackages.module.css";

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function UploadResult({ result }) {
  if (!result) return null;
  if (result.kind === "errors") {
    return (
      <div className={styles.errorPanel}>
        <p className={styles.errorTitle}>Package refused</p>
        <ul className={styles.errorList}>
          {result.errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      </div>
    );
  }
  if (result.kind === "failure") {
    return <div className={styles.errorPanel}>{result.message}</div>;
  }
  const { package: pkg, created } = result.data;
  if (!created) {
    return (
      <div className={styles.infoPanel}>
        Already ingested — nothing was created. Lesson {pkg.lesson_id} v
        {pkg.version} is unchanged.
      </div>
    );
  }
  return (
    <div className={styles.successPanel}>
      Ingested lesson {pkg.lesson_id} v{pkg.version} — “{pkg.title}”,{" "}
      {formatDuration(pkg.duration_seconds)}
    </div>
  );
}

function PackageDetail({ id, onAuthFailure }) {
  const [detail, setDetail] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getPackage(id)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) onAuthFailure();
        else setError("Could not load the package detail.");
      });
    return () => {
      cancelled = true;
    };
  }, [id, onAuthFailure]);

  if (error) return <div className={styles.errorPanel}>{error}</div>;
  if (!detail) return <p className={styles.muted}>Loading detail…</p>;

  const loadTranscript = () => {
    getTranscript(id)
      .then(setTranscript)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) onAuthFailure();
        else setError("Could not load the transcript.");
      });
  };

  return (
    <section className={styles.detail}>
      <h3 className={styles.detailTitle}>
        {detail.lesson_id} v{detail.version} — {detail.title}
      </h3>
      <h4 className={styles.blockTitle}>Manifest</h4>
      <pre className={styles.json}>{JSON.stringify(detail.manifest, null, 2)}</pre>
      <h4 className={styles.blockTitle}>Questions</h4>
      <pre className={styles.json}>{JSON.stringify(detail.questions, null, 2)}</pre>
      <h4 className={styles.blockTitle}>Transcript</h4>
      {transcript === null ? (
        <button className={styles.linkButton} type="button" onClick={loadTranscript}>
          View transcript
        </button>
      ) : (
        <pre className={styles.json}>{transcript}</pre>
      )}
    </section>
  );
}

function AdminPackages() {
  const { refresh: refreshSession } = useSession();
  const [packages, setPackages] = useState(null);
  const [listError, setListError] = useState(null);
  const [file, setFile] = useState(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  const handleAuthFailure = useCallback(() => {
    refreshSession();
  }, [refreshSession]);

  const refresh = useCallback(() => {
    listPackages()
      .then((data) => {
        setPackages(data);
        setListError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) handleAuthFailure();
        else setListError("Could not load packages. Is the backend running?");
      });
  }, [handleAuthFailure]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleDelete = async (pkg) => {
    if (
      !window.confirm(
        `Delete package ${pkg.lesson_id} v${pkg.version}? This removes the stored video too.`
      )
    ) {
      return;
    }
    try {
      await deletePackage(pkg.id);
      if (pkg.id === selectedId) setSelectedId(null);
      setResult(null);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setResult({ kind: "errors", errors: err.data.errors });
      } else if (err instanceof ApiError && err.status === 401) {
        handleAuthFailure();
      } else {
        setResult({ kind: "failure", message: "Delete failed. Try again." });
      }
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setResult(null);
    try {
      const data = await uploadPackage(file);
      setResult({ kind: "success", data });
      setFile(null);
      setFileInputKey((key) => key + 1);
      refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.data?.errors) {
        setResult({ kind: "errors", errors: err.data.errors });
      } else if (err instanceof ApiError && err.status === 401) {
        handleAuthFailure();
      } else {
        setResult({ kind: "failure", message: "Upload failed. Try again." });
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className={styles.page}>
      <AdminNav />
      <h1 className={styles.heading}>Lesson packages</h1>

      <section className={styles.uploadRow}>
        <input
          key={fileInputKey}
          className={styles.fileInput}
          type="file"
          accept=".zip"
          onChange={(event) => setFile(event.target.files[0] ?? null)}
        />
        <button
          className={styles.button}
          type="button"
          disabled={!file || uploading}
          onClick={handleUpload}
        >
          {uploading ? "Uploading…" : "Upload package"}
        </button>
      </section>

      <UploadResult result={result} />

      {listError && <div className={styles.errorPanel}>{listError}</div>}
      {!listError && packages === null && (
        <p className={styles.muted}>Loading packages…</p>
      )}
      {packages !== null && packages.length === 0 && (
        <p className={styles.muted}>No packages ingested yet.</p>
      )}
      {packages !== null && packages.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Lesson</th>
              <th>Version</th>
              <th>Title</th>
              <th>Duration</th>
              <th>Field of study</th>
              <th>Level</th>
              <th>Attached to</th>
              <th>Ingested</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {packages.map((pkg) => (
              <tr
                key={pkg.id}
                className={pkg.id === selectedId ? styles.rowSelected : styles.row}
                onClick={() =>
                  setSelectedId(pkg.id === selectedId ? null : pkg.id)
                }
              >
                <td>{pkg.lesson_id}</td>
                <td>v{pkg.version}</td>
                <td>{pkg.title}</td>
                <td>{formatDuration(pkg.duration_seconds)}</td>
                <td>{pkg.field_of_study}</td>
                <td>{pkg.knowledge_level}</td>
                <td>{pkg.attached_to ?? "—"}</td>
                <td>{new Date(pkg.ingested_at).toLocaleString()}</td>
                <td>
                  {!pkg.attached_to && (
                    <button
                      className={styles.deleteButton}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDelete(pkg);
                      }}
                    >
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedId !== null && (
        <PackageDetail
          key={selectedId}
          id={selectedId}
          onAuthFailure={handleAuthFailure}
        />
      )}
    </main>
  );
}

export default AdminPackages;
