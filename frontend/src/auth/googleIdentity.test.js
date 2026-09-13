/**
 * 030: the GIS script is appended once, lazily, and never twice — the
 * loader is the only place the tag is written (not index.html).
 */
import { afterEach, describe, expect, it } from "vitest";
import { GIS_SCRIPT_SRC, loadGoogleIdentity } from "./googleIdentity";

const gisScripts = () =>
  document.head.querySelectorAll(`script[src="${GIS_SCRIPT_SRC}"]`);

describe("loadGoogleIdentity", () => {
  afterEach(() => {
    delete window.google;
  });

  it("appends the script tag once for two calls and resolves when it loads", async () => {
    expect(gisScripts()).toHaveLength(0);
    const first = loadGoogleIdentity();
    const second = loadGoogleIdentity();
    expect(gisScripts()).toHaveLength(1);
    expect(second).toBe(first);

    const gis = { initialize: () => {}, renderButton: () => {} };
    window.google = { accounts: { id: gis } };
    gisScripts()[0].onload();
    expect(await first).toBe(gis);
  });

  it("resolves immediately once the global exists", async () => {
    const gis = { initialize: () => {}, renderButton: () => {} };
    window.google = { accounts: { id: gis } };
    const before = gisScripts().length;
    expect(await loadGoogleIdentity()).toBe(gis);
    expect(gisScripts()).toHaveLength(before);
  });
});
