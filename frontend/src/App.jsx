import { useEffect, useState } from "react";
import { getHealth } from "./api/health";
import styles from "./App.module.css";

function App() {
  const [connected, setConnected] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then(() => {
        if (!cancelled) setConnected(true);
      })
      .catch(() => {
        if (!cancelled) setConnected(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className={styles.page}>
      <h1 className={styles.wordmark}>
        super<span className={styles.accent}>CPE</span>
      </h1>
      {connected !== null && (
        <span
          className={connected ? styles.pillConnected : styles.pillUnreachable}
        >
          {connected ? "Backend connected" : "Backend unreachable"}
        </span>
      )}
    </main>
  );
}

export default App;
