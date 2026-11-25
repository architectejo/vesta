import { describe, expect, it } from "vitest";
import tokensCss from "../tokens/tokens.css?raw";
import { contrastRatio, hexToRgb } from "../tokens/color-contrast";

const darkStart = tokensCss.indexOf('[data-theme="dark"]');
const lightBlock = tokensCss.slice(0, darkStart);
const darkBlock = tokensCss.slice(darkStart, tokensCss.indexOf("Thème Classic (2.4)"));

function token(block: string, name: string): string {
  const match = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`).exec(block);
  if (!match?.[1]) throw new Error(`Token ${name} introuvable`);
  return match[1];
}

describe("tokens --color-series-*", () => {
  for (const [theme, block] of [
    ["Clair / Classic", lightBlock],
    ["Sombre", darkBlock],
  ] as const) {
    it(`${theme} : 4 séries, au moins 3:1 sur la surface et sur le fond grisé`, () => {
      const surface = token(block, "--color-surface");
      const muted = token(block, "--color-surface-muted");
      for (let i = 1; i <= 4; i += 1) {
        const color = token(block, `--color-series-${i}`);
        expect(contrastRatio(hexToRgb(color)!, hexToRgb(surface)!)).toBeGreaterThanOrEqual(3);
        expect(contrastRatio(hexToRgb(color)!, hexToRgb(muted)!)).toBeGreaterThanOrEqual(3);
      }
    });
  }
});
