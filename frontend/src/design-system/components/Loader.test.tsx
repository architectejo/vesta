import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Loader } from "./Loader";

describe("Loader", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("n'affiche rien avant 200 ms", () => {
    render(<Loader loading variant="list" count={2} />);
    expect(screen.queryByText("Chargement…")).not.toBeInTheDocument();
  });

  it("affiche les squelettes de liste après le délai", () => {
    render(<Loader loading variant="list" count={3} />);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText("Chargement…")).toBeInTheDocument();
  });

  it("affiche la barre de progression et les cartes en variante page", () => {
    render(<Loader loading variant="page" />);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    const zone = screen.getByText("Chargement…").closest("[aria-busy]");
    expect(zone).toHaveAttribute("aria-busy", "true");
  });

  it("propose de réessayer après 10 secondes", () => {
    const onRetry = vi.fn();
    render(<Loader loading variant="list" onRetry={onRetry} />);
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(
      screen.getByText("Le chargement prend plus de temps que prévu."),
    ).toBeInTheDocument();
    screen.getByRole("button", { name: "Réessayer" }).click();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("disparaît quand loading redevient faux", () => {
    const { rerender } = render(<Loader loading variant="list" />);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText("Chargement…")).toBeInTheDocument();

    rerender(<Loader loading={false} variant="list" />);
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.queryByText("Chargement…")).not.toBeInTheDocument();
  });
});
