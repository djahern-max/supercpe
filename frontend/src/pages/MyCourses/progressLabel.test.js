import { describe, expect, it } from "vitest";
import { lessonsProgressLabel } from "./progressLabel.js";

describe("lessonsProgressLabel (023c F2)", () => {
  it("says read for a text course", () => {
    expect(
      lessonsProgressLabel({ lessons_kind: "text", lessons_done: 0, lessons_total: 1 })
    ).toBe("0 of 1 lessons read");
  });
  it("says watched for a video course", () => {
    expect(
      lessonsProgressLabel({ lessons_kind: "video", lessons_done: 2, lessons_total: 3 })
    ).toBe("2 of 3 lessons watched");
  });
  it("says both for a mixed course", () => {
    expect(
      lessonsProgressLabel({ lessons_kind: "mixed", lessons_done: 1, lessons_total: 2 })
    ).toBe("1 of 2 lessons read or watched");
  });
});
