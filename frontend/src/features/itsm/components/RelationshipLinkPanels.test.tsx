import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { AssetAssociationPanels, ChangeAssetLinksPanel } from "./RelationshipLinkPanels";

function renderPanel(ui: ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("relationship link panels", () => {
  it("renders persisted change-to-asset link data", () => {
    renderPanel(
      <ChangeAssetLinksPanel
        query={{
          data: { items: [{ id: "asset-1", asset_tag: "LT-104", name: "Aditi laptop", status: "in_use" }] },
          isError: false,
          isLoading: false,
        }}
      />,
    );

    expect(screen.getByRole("link", { name: "LT-104 — Aditi laptop" })).toHaveAttribute(
      "href",
      "/itsm/assets/asset-1",
    );
  });

  it("distinguishes a real empty relationship from an unavailable service", () => {
    const { rerender } = renderPanel(
      <ChangeAssetLinksPanel query={{ data: { items: [] }, isError: false, isLoading: false }} />,
    );
    expect(screen.getByText("No associated assets")).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <ChangeAssetLinksPanel query={{ isError: true, isLoading: false }} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Relationship data is unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No associated assets")).not.toBeInTheDocument();
  });

  it("renders persisted asset-to-ticket and asset-to-change link data", () => {
    renderPanel(
      <AssetAssociationPanels
        changeQuery={{
          data: {
            items: [
              { id: "change-1", change_number: "CHG-42", title: "Mail migration", status: "scheduled" },
            ],
          },
          isError: false,
          isLoading: false,
        }}
        ticketQuery={{
          data: {
            items: [
              { id: "ticket-1", ticket_number: "ITA-42", title: "Mail issue", status: "new", priority: "high" },
            ],
          },
          isError: false,
          isLoading: false,
        }}
      />,
    );

    expect(screen.getByRole("link", { name: "CHG-42 — Mail migration" })).toHaveAttribute(
      "href",
      "/itsm/changes/change-1",
    );
    expect(screen.getByRole("link", { name: "ITA-42 — Mail issue" })).toHaveAttribute(
      "href",
      "/operations/tickets/ticket-1",
    );
  });
});
