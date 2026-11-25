import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useClientUuid } from "./useClientUuid";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("useClientUuid", () => {
  it("génère un UUID v4 non vide", () => {
    const { result } = renderHook(() => useClientUuid());
    expect(result.current.get("a")).toMatch(UUID_V4);
  });

  it("conserve le même UUID tant que la saisie ne change pas", () => {
    const { result } = renderHook(() => useClientUuid());
    expect(result.current.get("a")).toBe(result.current.get("a"));
  });

  it("génère un nouvel UUID quand la saisie change", () => {
    const { result } = renderHook(() => useClientUuid());
    const first = result.current.get("a");
    expect(result.current.get("b")).not.toBe(first);
  });

  it("génère un nouvel UUID après reset (succès)", () => {
    const { result } = renderHook(() => useClientUuid());
    const first = result.current.get("a");
    result.current.reset();
    expect(result.current.get("a")).not.toBe(first);
  });
});
