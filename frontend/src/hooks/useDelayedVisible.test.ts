import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDelayedVisible } from "./useDelayedVisible";

describe("useDelayedVisible", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("ne s'affiche pas avant le délai (200 ms par défaut)", () => {
    const { result } = renderHook(({ loading }) => useDelayedVisible(loading), {
      initialProps: { loading: true },
    });

    expect(result.current).toBe(false);

    act(() => {
      vi.advanceTimersByTime(199);
    });
    expect(result.current).toBe(false);
  });

  it("s'affiche après le délai si le chargement dure encore", () => {
    const { result } = renderHook(({ loading }) => useDelayedVisible(loading), {
      initialProps: { loading: true },
    });

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current).toBe(true);
  });

  it("ne clignote pas si le chargement se termine avant le délai", () => {
    const { result, rerender } = renderHook(({ loading }) => useDelayedVisible(loading), {
      initialProps: { loading: true },
    });

    act(() => {
      vi.advanceTimersByTime(100);
    });
    rerender({ loading: false });

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(result.current).toBe(false);
  });

  it("reste visible au moins 300 ms une fois apparu, même si le chargement se termine vite", () => {
    const { result, rerender } = renderHook(({ loading }) => useDelayedVisible(loading), {
      initialProps: { loading: true },
    });

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current).toBe(true);

    rerender({ loading: false });

    act(() => {
      vi.advanceTimersByTime(100);
    });
    // Apparu depuis 100 ms seulement (< 300 ms minimum) : reste visible.
    expect(result.current).toBe(true);

    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current).toBe(false);
  });
});
