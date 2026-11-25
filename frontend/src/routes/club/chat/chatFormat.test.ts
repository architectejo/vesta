import { describe, expect, it } from "vitest";
import { formatChannelCount } from "./chatFormat";

describe("formatChannelCount", () => {
  it("accorde correctement canal / canaux", () => {
    expect(formatChannelCount(0)).toBe("0 canal");
    expect(formatChannelCount(1)).toBe("1 canal");
    expect(formatChannelCount(2)).toBe("2 canaux");
  });
});
