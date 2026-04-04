/**
 * Render tests for core UI components from @/components/ui/
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

describe("Badge", () => {
  it("renders with text content", () => {
    render(<Badge>ALLOW</Badge>);
    expect(screen.getByText("ALLOW")).toBeInTheDocument();
  });

  it("renders destructive variant", () => {
    render(<Badge variant="destructive">BLOCK</Badge>);
    expect(screen.getByText("BLOCK")).toBeInTheDocument();
  });

  it("renders secondary variant", () => {
    render(<Badge variant="secondary">ESCALATE</Badge>);
    expect(screen.getByText("ESCALATE")).toBeInTheDocument();
  });
});

describe("Button", () => {
  it("renders with label", () => {
    render(<Button>Save Policy</Button>);
    expect(screen.getByRole("button", { name: "Save Policy" })).toBeInTheDocument();
  });

  it("renders disabled state", () => {
    render(<Button disabled>Processing</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("renders variant outline", () => {
    render(<Button variant="outline">Cancel</Button>);
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });
});

describe("Card", () => {
  it("renders card with title and content", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Total Decisions</CardTitle>
        </CardHeader>
        <CardContent>1,234</CardContent>
      </Card>
    );
    expect(screen.getByText("Total Decisions")).toBeInTheDocument();
    expect(screen.getByText("1,234")).toBeInTheDocument();
  });
});
