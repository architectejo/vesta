import { describe, expect, it } from "vitest";
import { toViewableBlob } from "./safeBlob";

describe("toViewableBlob", () => {
  it("refuse text/html, svg et type vide", () => {
    expect(toViewableBlob(new Blob(["<script>1</script>"], { type: "text/html" }))).toBeNull();
    expect(toViewableBlob(new Blob(["<svg/>"], { type: "image/svg+xml" }))).toBeNull();
    expect(toViewableBlob(new Blob(["x"]))).toBeNull();
  });
  it("accepte les types autorisés et normalise le type", () => {
    expect(toViewableBlob(new Blob(["x"], { type: "application/pdf" }))?.type).toBe("application/pdf");
    expect(toViewableBlob(new Blob(["x"], { type: "IMAGE/PNG; charset=x" }))?.type).toBe("image/png");
  });
});
