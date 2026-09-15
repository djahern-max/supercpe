/**
 * 035: the renderer's defensive guard.
 *
 * The backend strips HTML comments from the reader payload, the search
 * index, and the word count. This is the second line: an authoring
 * annotation must not render even if one reaches the client from a path
 * that was missed. Everything else about the renderer is unchanged —
 * raw HTML is still text, never an element.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import SimpleMarkdown from "./SimpleMarkdown.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(markdown) {
  act(() => root.render(<SimpleMarkdown markdown={markdown} />));
  return container;
}

describe("SimpleMarkdown and HTML comments (035)", () => {
  it("renders no comment text", () => {
    const node = render(
      "Alpha beta.\n\n<!-- index: 9#1, 9#2; 4#3 attributed -->\n\nGamma.\n"
    );
    expect(node.textContent).not.toContain("<!--");
    expect(node.textContent).not.toContain("attributed");
    expect(node.textContent).toContain("Alpha beta.");
    expect(node.textContent).toContain("Gamma.");
  });

  it("drops a comment that spans several lines", () => {
    const node = render("Alpha\n\n<!-- index: 9#1,\n 4#3 attributed -->\n\nbeta");
    expect(node.textContent).not.toContain("attributed");
    expect(node.textContent).not.toContain("-->");
    expect(node.textContent).toContain("Alpha");
    expect(node.textContent).toContain("beta");
  });

  it("drops a comment sitting inside a paragraph", () => {
    const node = render("Alpha <!-- a note --> beta");
    expect(node.textContent).not.toContain("note");
    expect(node.textContent).toContain("Alpha");
    expect(node.textContent).toContain("beta");
  });

  it("leaves an unclosed comment opener as text", () => {
    const node = render("Alpha <!-- never closed beta");
    expect(node.textContent).toContain("<!--");
    expect(node.textContent).toContain("never closed beta");
  });
});

describe("SimpleMarkdown still escapes every other raw HTML (035)", () => {
  it("shows a script tag as text and creates no element", () => {
    const node = render("<script>alert(1)</script>");
    expect(node.querySelector("script")).toBeNull();
    expect(node.textContent).toContain("<script>alert(1)</script>");
  });

  it("shows a bold tag as text rather than bolding", () => {
    const node = render("A tag <b>x</b> here.");
    expect(node.querySelector("b")).toBeNull();
    expect(node.textContent).toContain("<b>x</b>");
  });

  it("still renders the Markdown subset it supports", () => {
    const node = render("# Title\n\n- one\n- two\n\n**bold** text");
    expect(node.querySelector("h1").textContent).toBe("Title");
    expect(node.querySelectorAll("li")).toHaveLength(2);
    expect(node.querySelector("strong").textContent).toBe("bold");
  });
});
