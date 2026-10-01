import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PitchBoard, PitchPin } from "./PitchBoard";

describe("PitchBoard", () => {
  it("affiche un pion par joueur avec son numéro et son nom", () => {
    render(
      <PitchBoard
        mode="readonly"
        ariaLabel="Équipe A"
        pins={[{ id: "1", membershipId: 1, label: "Jean K.", number: 7, x: 50, y: 50 }]}
      />,
    );
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Jean K.")).toBeInTheDocument();
  });

  it("déclenche onTapPin même pour un pion verrouillé (panneau en lecture seule, §3.2 bis)", () => {
    const onTapPin = vi.fn();
    render(
      <PitchBoard
        mode="teams"
        ariaLabel="Non répartis"
        pins={[{ id: "1", membershipId: 1, label: "Jean K.", number: 7, x: 50, y: 50, locked: true }]}
        onTapPin={onTapPin}
      />,
    );
    fireEvent.pointerDown(screen.getByRole("button", { name: "Jean K. : indisponible" }));
    fireEvent.pointerUp(screen.getByRole("button", { name: "Jean K. : indisponible" }));
    expect(onTapPin).toHaveBeenCalled();
  });

  it("ne déclenche aucun toucher quand pinsInteractive est faux (outil de dessin actif)", () => {
    const onTapPin = vi.fn();
    render(
      <PitchBoard
        mode="tactic"
        ariaLabel="Terrain"
        pins={[{ id: "1", membershipId: 1, label: "Jean K.", number: 7, x: 50, y: 50 }]}
        onTapPin={onTapPin}
        pinsInteractive={false}
      />,
    );
    fireEvent.pointerDown(screen.getByRole("button", { name: "Jean K." }));
    fireEvent.pointerUp(screen.getByRole("button", { name: "Jean K." }));
    expect(onTapPin).not.toHaveBeenCalled();
  });
});

describe("PitchBoard — marquages selon l'orientation", () => {
  it("dessine la ligne médiane horizontale et les surfaces de réparation en haut/bas en mode portrait (vertical, par défaut)", () => {
    const { container } = render(<PitchBoard mode="readonly" ariaLabel="Terrain" pins={[]} />);
    const markings = container.querySelectorAll("svg")[0] as SVGSVGElement;
    const line = markings.querySelector("line") as SVGLineElement;
    expect(line.getAttribute("x1")).toBe("1.5");
    expect(line.getAttribute("y1")).toBe("50");
    expect(line.getAttribute("x2")).toBe("98.5");
    expect(line.getAttribute("y2")).toBe("50");

    const rects = markings.querySelectorAll("rect");
    // rects[0] = contour du terrain, rects[1] et [2] = surfaces de réparation
    expect(rects[1]?.getAttribute("x")).toBe("20");
    expect(rects[1]?.getAttribute("y")).toBe("1.5");
    expect(rects[1]?.getAttribute("width")).toBe("60");
    expect(rects[1]?.getAttribute("height")).toBe("16");
    expect(rects[2]?.getAttribute("x")).toBe("20");
    expect(rects[2]?.getAttribute("y")).toBe("82.5");
    expect(rects[2]?.getAttribute("width")).toBe("60");
    expect(rects[2]?.getAttribute("height")).toBe("16");
  });

  it("dessine la ligne médiane verticale et les surfaces de réparation à gauche/droite en mode paysage (vertical=false)", () => {
    const { container } = render(<PitchBoard mode="readonly" ariaLabel="Terrain" pins={[]} vertical={false} />);
    const markings = container.querySelectorAll("svg")[0] as SVGSVGElement;
    const line = markings.querySelector("line") as SVGLineElement;
    expect(line.getAttribute("x1")).toBe("50");
    expect(line.getAttribute("y1")).toBe("1.5");
    expect(line.getAttribute("x2")).toBe("50");
    expect(line.getAttribute("y2")).toBe("98.5");

    const rects = markings.querySelectorAll("rect");
    expect(rects[1]?.getAttribute("x")).toBe("1.5");
    expect(rects[1]?.getAttribute("y")).toBe("20");
    expect(rects[1]?.getAttribute("width")).toBe("16");
    expect(rects[1]?.getAttribute("height")).toBe("60");
    expect(rects[2]?.getAttribute("x")).toBe("82.5");
    expect(rects[2]?.getAttribute("y")).toBe("20");
    expect(rects[2]?.getAttribute("width")).toBe("16");
    expect(rects[2]?.getAttribute("height")).toBe("60");
  });

  it("tourne aussi les tracés (flèches, zones) avec l'orientation du terrain", () => {
    const annotations = [
      { id: "z1", type: "zone" as const, points: [{ x: 20, y: 30 }, { x: 80, y: 60 }] },
    ];
    const { container: verticalContainer } = render(
      <PitchBoard mode="readonly" ariaLabel="Terrain" pins={[]} annotations={annotations} />,
    );
    const verticalZone = verticalContainer.querySelectorAll("svg")[1]?.querySelector("rect");
    // vertical : x=min(20,80)=20, y=100-max(30,60)=40, w=60, h=30
    expect(verticalZone?.getAttribute("x")).toBe("20");
    expect(verticalZone?.getAttribute("y")).toBe("40");
    expect(verticalZone?.getAttribute("width")).toBe("60");
    expect(verticalZone?.getAttribute("height")).toBe("30");

    const { container: landscapeContainer } = render(
      <PitchBoard mode="readonly" ariaLabel="Terrain" pins={[]} annotations={annotations} vertical={false} />,
    );
    const landscapeZone = landscapeContainer.querySelectorAll("svg")[1]?.querySelector("rect");
    // paysage (x,y échangés) : x=min(30,60)=30, y=min(20,80)=20, w=30, h=60
    expect(landscapeZone?.getAttribute("x")).toBe("30");
    expect(landscapeZone?.getAttribute("y")).toBe("20");
    expect(landscapeZone?.getAttribute("width")).toBe("30");
    expect(landscapeZone?.getAttribute("height")).toBe("60");
  });
});

describe("PitchPin", () => {
  it("appelle onTap au relâchement sans glissement", () => {
    const onTap = vi.fn();
    render(
      <PitchPin
        vertical
        draggable
        dragKind="pin"
        pin={{ id: "1", membershipId: 1, label: "Jean K.", number: 7, x: 50, y: 50 }}
        onTap={onTap}
      />,
    );
    const pin = screen.getByRole("button", { name: "Jean K." });
    fireEvent.pointerDown(pin, { clientX: 10, clientY: 10 });
    fireEvent.pointerUp(pin, { clientX: 10, clientY: 10 });
    expect(onTap).toHaveBeenCalled();
  });

  it("reste en position absolue (pin.x/pin.y) quand standalone n'est pas précisé, pour un pion posé sur un terrain", () => {
    render(
      <PitchPin
        vertical
        draggable
        dragKind="pin"
        pin={{ id: "1", membershipId: 1, label: "Jean K.", number: 7, x: 50, y: 50 }}
      />,
    );
    const pin = screen.getByRole("button", { name: "Jean K." });
    expect(pin.className).toContain("absolute");
    expect(pin.style.left).toBe("50%");
  });

  it("n'applique aucun positionnement absolu en mode standalone (banc, « Non répartis » : liste à puces sans terrain)", () => {
    render(
      <PitchPin
        vertical
        standalone
        draggable
        dragKind="pin"
        pin={{ id: "1", membershipId: 1, label: "Jean K.", number: 7, x: 50, y: 50 }}
      />,
    );
    const pin = screen.getByRole("button", { name: "Jean K." });
    // Sans ce mode, un pion de banc reste en `position: absolute` au
    // pourcentage `pin.x`/`pin.y` (valeurs factices, toujours 50/50) : il se
    // positionne alors par rapport au premier ancêtre positionné trouvé en
    // remontant le DOM, presque jamais la petite liste elle-même (qui n'a
    // pas de position relative) — tous les pions d'une même liste finissent
    // superposés au même endroit ailleurs sur la page (constat du client :
    // bancs visuellement vides, un seul pion flottant « dans le vide »).
    expect(pin.className).not.toContain("absolute");
    expect(pin.style.left).toBe("");
  });
});
