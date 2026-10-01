import { describe, expect, it } from "vitest";
import { ImageValidationError, validateImageFile } from "./imagePrep";

function makeFile(name: string, type: string, sizeBytes: number): File {
  const file = new File([new Uint8Array(sizeBytes)], name, { type });
  return file;
}

describe("validateImageFile", () => {
  it("accepte JPEG, PNG et WebP sous 10 Mo", () => {
    expect(() => validateImageFile(makeFile("a.jpg", "image/jpeg", 1024))).not.toThrow();
    expect(() => validateImageFile(makeFile("a.png", "image/png", 1024))).not.toThrow();
    expect(() => validateImageFile(makeFile("a.webp", "image/webp", 1024))).not.toThrow();
  });

  it("refuse un format non accepté", () => {
    expect(() => validateImageFile(makeFile("a.gif", "image/gif", 1024))).toThrow(ImageValidationError);
    expect(() => validateImageFile(makeFile("a.gif", "image/gif", 1024))).toThrow(
      "Format non accepté : JPEG, PNG ou WebP.",
    );
  });

  it("refuse un fichier de plus de 10 Mo", () => {
    const tooBig = makeFile("a.jpg", "image/jpeg", 10 * 1024 * 1024 + 1);
    expect(() => validateImageFile(tooBig)).toThrow("Fichier trop lourd : 10 Mo maximum.");
  });
});
