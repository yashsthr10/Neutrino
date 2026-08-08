import React from "react";
import { Text } from "ink";
import { render } from "ink-testing-library";
import { describe, expect, it } from "vitest";

describe("ink smoke", () => {
  it("renders a simple tree", () => {
    const { lastFrame } = render(<Text>Neutrino</Text>);
    expect(lastFrame()).toContain("Neutrino");
  });
});
