import { useState } from "react";
import styles from "./TokenForm.module.css";

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

export default TokenForm;
