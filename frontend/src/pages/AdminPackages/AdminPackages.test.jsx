/**
 * 038: the packages page acts on a version's lifecycle. Delete only an
 * unused version, archive a superseded one, purge an archived version's
 * media only past retention — each button following the server's derived
 * flags — and a refusal shows the server's reasons, not "Delete failed".
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import AdminPackages from "./AdminPackages.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({
  listPackages: vi.fn(),
  deletePackage: vi.fn(),
  archivePackage: vi.fn(),
  unarchivePackage: vi.fn(),
  purgePackageMedia: vi.fn(),
}));

vi.mock("../../api/admin", async (importOriginal) => ({
  ...(await importOriginal()),
  ...api,
}));

vi.mock("../../auth/SessionContext.jsx", () => ({
  useSession: () => ({
    account: { id: 1, email: "admin@supercpe.test", role: "admin" },
    refresh: vi.fn(),
    signOut: vi.fn(),
  }),
}));

function pkg(overrides) {
  return {
    id: 6,
    kind: "video",
    lesson_id: "GPT-06",
    version: 1,
    title: "A task, start to finish",
    duration_seconds: 410,
    field_of_study: "Accounting",
    knowledge_level: "Basic",
    ingested_at: "2026-09-14T10:00:00Z",
    course_code: "GPT",
    attached_to: null,
    archived_at: null,
    media_purged_at: null,
    media_purged_by: null,
    attached_course_codes: [],
    enrollment_count: 0,
    preview_attempt_count: 0,
    retain_until: null,
    deletable: true,
    media_purgeable: false,
    ...overrides,
  };
}

let container;
let root;

async function mount(rows) {
  api.listPackages.mockResolvedValue(rows);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={["/admin/packages"]}>
        <AdminPackages />
      </MemoryRouter>
    );
  });
}

const button = (label) =>
  Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent === label
  );

async function click(element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("AdminPackages lifecycle (038)", () => {
  it("asks for archived versions when the toggle is on", async () => {
    await mount([pkg()]);
    expect(api.listPackages).toHaveBeenLastCalledWith({
      includeArchived: false,
    });
    const toggle = container.querySelector('input[type="checkbox"]');
    await click(toggle);
    expect(api.listPackages).toHaveBeenLastCalledWith({
      includeArchived: true,
    });
  });

  it("enables Delete only for a deletable version", async () => {
    await mount([pkg({ deletable: false, enrollment_count: 1 })]);
    expect(button("Delete").disabled).toBe(true);
    expect(button("Archive").disabled).toBe(false);
    expect(button("Purge media")).toBeUndefined();
  });

  it("shows when an archived version's media can be purged", async () => {
    await mount([
      pkg({
        archived_at: "2026-09-15T12:00:00Z",
        deletable: false,
        enrollment_count: 1,
        retain_until: "2031-09-15T12:00:00Z",
        media_purgeable: false,
      }),
    ]);
    expect(button("Purge media").disabled).toBe(true);
    expect(button("Unarchive")).toBeDefined();
    expect(container.textContent).toContain(
      `Media can be purged after ${new Date(
        "2031-09-15T12:00:00Z"
      ).toLocaleDateString()}`
    );
  });

  it("enables Purge media once purgeable, confirming with the lesson and version", async () => {
    api.purgePackageMedia.mockResolvedValue({});
    await mount([
      pkg({
        archived_at: "2026-09-15T12:00:00Z",
        deletable: false,
        enrollment_count: 1,
        retain_until: "2020-01-01T00:00:00Z",
        media_purgeable: true,
      }),
    ]);
    expect(button("Purge media").disabled).toBe(false);
    await click(button("Purge media"));
    const [message] = window.confirm.mock.calls[0];
    expect(message).toContain("GPT-06 v1");
    expect(message).toContain(
      "The video and media files are deleted. Participant records and questions are kept."
    );
    expect(api.purgePackageMedia).toHaveBeenCalledWith(6);
  });

  it("renders a delete refusal's reasons, not 'Delete failed'", async () => {
    const reason =
      "package GPT-06 v1 is referenced by 1 enrollment; archive it instead";
    api.deletePackage.mockRejectedValue(
      new ApiError(422, { errors: [reason] })
    );
    await mount([pkg()]);
    await click(button("Delete"));
    expect(container.textContent).toContain(reason);
    expect(container.textContent).not.toContain("Delete failed");
  });
});
