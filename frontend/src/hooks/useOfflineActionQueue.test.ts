import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useOfflineActionQueue } from "./useOfflineActionQueue";

function setOnline(value: boolean): void {
  Object.defineProperty(window.navigator, "onLine", { value, configurable: true });
}

describe("useOfflineActionQueue", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setOnline(true);
  });
  afterEach(() => {
    setOnline(true);
  });

  it("traite immédiatement une action en ligne", async () => {
    const processItem = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useOfflineActionQueue<{ id: number }>({ storageKey: "test-queue-1", processItem }));

    act(() => {
      result.current.enqueue({ id: 1 });
    });

    await waitFor(() => expect(result.current.pendingCount).toBe(0));
    expect(processItem).toHaveBeenCalledWith({ id: 1 });
  });

  it("garde une action en file hors connexion, jusqu'au retour du réseau", async () => {
    setOnline(false);
    const processItem = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useOfflineActionQueue<{ id: number }>({ storageKey: "test-queue-2", processItem }));

    act(() => {
      result.current.enqueue({ id: 2 });
    });

    expect(result.current.pendingCount).toBe(1);
    expect(processItem).not.toHaveBeenCalled();

    setOnline(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });

    await waitFor(() => expect(result.current.pendingCount).toBe(0));
    expect(processItem).toHaveBeenCalledWith({ id: 2 });
  });

  it("retire une action refusée par l'API et prévient l'appelant", async () => {
    const processItem = vi.fn().mockRejectedValue({ status: 400, detail: "Ne peut pas jouer : en dette." });
    const onRejected = vi.fn();
    const { result } = renderHook(() =>
      useOfflineActionQueue<{ id: number }>({ storageKey: "test-queue-3", processItem, onRejected }),
    );

    act(() => {
      result.current.enqueue({ id: 3 });
    });

    await waitFor(() => expect(result.current.pendingCount).toBe(0));
    expect(onRejected).toHaveBeenCalledWith({ id: 3 }, "Ne peut pas jouer : en dette.");
  });
});
