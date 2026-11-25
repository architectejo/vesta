import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PitchBoard, PitchPin, pinInitials, pitchDragBus } from "./PitchBoard";

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

describe("PitchPin — photo (sport-vestiaire.md §9)", () => {
  const base = { id: "1", membershipId: 1, label: "Jean K.", fullName: "Jean Kabila", number: 7, x: 50, y: 50, jerseyColor: "#2563eb" };

  it("affiche la photo (alt vide, non glissable, lazy) avec le numéro dans la pastille", () => {
    const { container } = render(
      <PitchPin vertical draggable dragKind="pin" pin={{ ...base, photoUrl: "https://api.test/media/jean.jpg" }} />,
    );
    const img = container.querySelector("img") as HTMLImageElement;
    expect(img).not.toBeNull();
    expect(img.getAttribute("src")).toBe("https://api.test/media/jean.jpg");
    expect(img.getAttribute("alt")).toBe("");
    expect(img.getAttribute("draggable")).toBe("false");
    expect(img.getAttribute("loading")).toBe("lazy");
    expect(img.className).toContain("pointer-events-none");
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("affiche les initiales sans photo", () => {
    const { container } = render(<PitchPin vertical draggable dragKind="pin" pin={{ ...base, photoUrl: null }} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByTestId("pin-initials")).toHaveTextContent("JK");
  });

  it("bascule sur les initiales quand l'image échoue", () => {
    const { container } = render(
      <PitchPin vertical draggable dragKind="pin" pin={{ ...base, photoUrl: "https://api.test/media/cassee.jpg" }} />,
    );
    fireEvent.error(container.querySelector("img") as HTMLImageElement);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByTestId("pin-initials")).toHaveTextContent("JK");
  });

  it("garde un cercle de 40 px avec ou sans photo", () => {
    const { container, rerender } = render(
      <PitchPin vertical draggable dragKind="pin" pin={{ ...base, photoUrl: "https://api.test/a.jpg" }} />,
    );
    expect(container.querySelector(".h-10.w-10")).not.toBeNull();
    rerender(<PitchPin vertical draggable dragKind="pin" pin={{ ...base, photoUrl: null }} />);
    expect(container.querySelector(".h-10.w-10")).not.toBeNull();
  });

  it("affiche le libellé complet, sans troncature", () => {
    render(<PitchPin vertical draggable dragKind="pin" pin={{ ...base, label: "Jean-Baptiste M." }} />);
    const label = screen.getByText("Jean-Baptiste M.");
    expect(label.className).not.toContain("truncate");
    expect(label.className).toContain("text-[12px]");
  });

  it("le pion avec photo reste soulevable : pointeur déplacé puis relâché ne déclenche pas le toucher", () => {
    const onTap = vi.fn();
    (document as unknown as { elementFromPoint: () => null }).elementFromPoint = () => null; // absent de jsdom
    render(
      <PitchPin vertical draggable dragKind="pin" pin={{ ...base, photoUrl: "https://api.test/a.jpg" }} onTap={onTap} />,
    );
    const pin = screen.getByRole("button", { name: "Jean K." });
    expect(pin.className).toContain("touch-none");
    // jsdom n'a pas de PointerEvent : un MouseEvent nommé « pointer* » porte les coordonnées.
    const fire = (type: string, x: number, y: number) =>
      fireEvent(pin, new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }));
    fire("pointerdown", 10, 10);
    fire("pointermove", 80, 90);
    expect(pitchDragBus.getSnapshot().dragging?.label).toBe("Jean K.");
    fire("pointerup", 80, 90);
    expect(pitchDragBus.getSnapshot().dragging).toBeNull();
    expect(onTap).not.toHaveBeenCalled();
  });

  it("fonctionne en mode standalone (banc) avec photo", () => {
    const { container } = render(
      <PitchPin vertical standalone draggable dragKind="pin" pin={{ ...base, photoUrl: "https://api.test/a.jpg" }} />,
    );
    expect(screen.getByRole("button", { name: "Jean K." }).className).not.toContain("absolute");
    expect(container.querySelector("img")).not.toBeNull();
  });
});

describe("pinInitials", () => {
  it("prend la première lettre du prénom et du dernier mot, « ? » si vide", () => {
    expect(pinInitials("Jean Kabila")).toBe("JK");
    expect(pinInitials("Jean K.")).toBe("JK");
    expect(pinInitials("Pelé")).toBe("P");
    expect(pinInitials("")).toBe("?");
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

describe("PitchPin - étiquette", () => {
  it("limite l'étiquette à 2 lignes, réduit le corps du texte et garde le nom complet en infobulle", () => {
    render(
      <PitchPin
        vertical
        standalone
        draggable={false}
        dragKind="pin"
        pin={{ id: "1", membershipId: 1, label: "Maximilien-Alexandre K.", fullName: "Maximilien-Alexandre Kabongo", x: 0, y: 0 }}
      />,
    );
    const label = screen.getByTestId("pin-label");
    expect(label.className).toContain("line-clamp-2");
    expect(label.className).toContain("text-[11px]");
    expect(screen.getByRole("button").getAttribute("title")).toBe("Maximilien-Alexandre Kabongo");
  });
});
