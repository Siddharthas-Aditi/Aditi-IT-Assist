/** Tests for the IT-staff ticket workspace page.
 *
 * Gating mirrors the backend guards: only IT staff (it_agent/it_lead/it_admin)
 * may reopen or close; reopen only from terminal statuses; Close hidden when
 * already closed; Properties status dropdown excludes `closed`.
 */

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/stores/auth-store";
import type { AuthUser } from "@/types/auth";

import { TicketWorkspacePage } from "./TicketWorkspacePage";

const TICKET_ID = "tkt-1";

const IT_AGENT: AuthUser = {
  id: "agent-1",
  email: "agent@aditi.com",
  full_name: "Test Agent",
  role: "it_agent",
  roles: ["it_agent"],
};

const EMPLOYEE: AuthUser = {
  id: "emp-1",
  email: "employee@aditi.com",
  full_name: "Test Employee",
  role: "employee",
  roles: ["employee"],
};

const EMPTY_CATEGORY_TREE = { categories: [] };

function baseTicket(status: string) {
  return {
    id: TICKET_ID,
    ticket_number: "TCK-1001",
    title: "Mailbox full",
    description: "Cannot receive email — mailbox over quota.",
    status,
    priority: "medium",
    category: "Incident",
    subcategory: "Network Connectivity",
    item: "VPN",
    ticket_type: "incident",
    urgency: "medium",
    impact: "individual",
    source: "chat",
    requester_id: "emp-1",
    assigned_to: "agent-1",
    created_at: new Date().toISOString(),
    sla_resolution_target: null,
    ai_summary: null,
    resolution_notes: null,
  };
}

function jsonResponse(body: unknown) {
  const text = JSON.stringify(body);
  return {
    ok: true,
    status: 200,
    text: async () => text,
    clone() {
      return this;
    },
  };
}

function mockTicketDetailFetch(status: string): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url.includes(`/tickets/${TICKET_ID}/reopen`) && method === "POST") {
      return Promise.resolve(
        jsonResponse({
          id: TICKET_ID,
          ticket_number: "TCK-1001",
          status: "in_progress",
        }),
      );
    }
    if (url.includes(`/tickets/${TICKET_ID}`) && method === "GET") {
      return Promise.resolve(
        jsonResponse({
          ticket: baseTicket(status),
          comments: [],
          events: [],
        }),
      );
    }
    if (url.includes("/handoff-view")) {
      return Promise.resolve(jsonResponse(null));
    }
    if (url.includes("/ticket-categories/tree")) {
      return Promise.resolve(jsonResponse(EMPTY_CATEGORY_TREE));
    }
    return Promise.resolve(jsonResponse({}));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock as unknown as ReturnType<typeof vi.fn>;
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/operations/tickets/${TICKET_ID}`]}>
        <Routes>
          <Route
            path="/operations/tickets/:id"
            element={<TicketWorkspacePage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TicketWorkspacePage — Reopen button", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders and calls the reopen API for a resolved ticket as IT staff", async () => {
    useAuthStore.setState({
      user: IT_AGENT,
      token: "test-token",
      isAuthenticated: true,
    });
    const fetchMock = mockTicketDetailFetch("resolved");
    renderPage();

    const button = await screen.findByRole("button", {
      name: /reopen ticket/i,
    });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/tickets/${TICKET_ID}/reopen`),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("does not render for a non-resolved ticket as IT staff", async () => {
    useAuthStore.setState({
      user: IT_AGENT,
      token: "test-token",
      isAuthenticated: true,
    });
    mockTicketDetailFetch("in_progress");
    renderPage();

    await screen.findByText("Mailbox full");
    expect(screen.queryByRole("button", { name: /reopen ticket/i })).toBeNull();
  });

  it("does not render for a resolved ticket when the user is not IT staff", async () => {
    useAuthStore.setState({
      user: EMPLOYEE,
      token: "test-token",
      isAuthenticated: true,
    });
    mockTicketDetailFetch("resolved");
    renderPage();

    await screen.findByText("Mailbox full");
    expect(screen.queryByRole("button", { name: /reopen ticket/i })).toBeNull();
  });
});

describe("TicketWorkspacePage — Close button", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders Close for an in_progress ticket as IT staff", async () => {
    useAuthStore.setState({
      user: IT_AGENT,
      token: "test-token",
      isAuthenticated: true,
    });
    mockTicketDetailFetch("in_progress");
    renderPage();

    expect(
      await screen.findByRole("button", { name: /^Close$/i }),
    ).toBeInTheDocument();
  });

  it("does not render Close for a closed ticket as IT staff", async () => {
    useAuthStore.setState({
      user: IT_AGENT,
      token: "test-token",
      isAuthenticated: true,
    });
    mockTicketDetailFetch("closed");
    renderPage();

    await screen.findByText("Mailbox full");
    expect(screen.queryByRole("button", { name: /^Close$/i })).toBeNull();
  });
});

describe("TicketWorkspacePage — Properties status control", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("does not list closed in the Properties status dropdown", async () => {
    useAuthStore.setState({
      user: IT_AGENT,
      token: "test-token",
      isAuthenticated: true,
    });
    mockTicketDetailFetch("in_progress");
    renderPage();

    const statusSelect = await screen.findByLabelText(/^Status$/i);
    const options = within(statusSelect).getAllByRole("option");
    const values = options.map((o) => o.getAttribute("value"));
    const labels = options.map((o) => o.textContent?.trim().toLowerCase());

    expect(values).not.toContain("closed");
    expect(labels).not.toContain("closed");
  });

  it("shows closed status as read-only text when ticket is closed", async () => {
    useAuthStore.setState({
      user: IT_AGENT,
      token: "test-token",
      isAuthenticated: true,
    });
    mockTicketDetailFetch("closed");
    renderPage();

    await screen.findByText("Mailbox full");
    expect(screen.queryByLabelText(/^Status$/i)).toBeNull();
    expect(
      screen.getByText(/^Status$/i).nextElementSibling?.textContent?.trim(),
    ).toBe("closed");
  });
});
