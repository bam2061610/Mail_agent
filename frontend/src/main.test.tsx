import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { App } from "./main";
import i18n from "./i18n";

type RouteResponse = {
  status?: number;
  body?: unknown;
  throws?: Error;
};

type MockCall = {
  method: string;
  path: string;
  authorization: string | null;
};

const adminUser = {
  id: 1,
  email: "admin@orhun.local",
  full_name: "Admin User",
  role: "admin",
  is_active: true,
  created_at: "2026-04-01T10:00:00Z",
  updated_at: "2026-04-01T10:00:00Z",
};

const longSummary =
  "Supplier asks for pricing, delivery timing, contractual terms, approval path, fallback shipment options, and wants the whole status visible without opening extra views.";

beforeEach(async () => {
  localStorage.clear();
  vi.unstubAllGlobals();
  await i18n.changeLanguage("en");
});

function installFetchMock(routes: Record<string, RouteResponse | RouteResponse[]>): MockCall[] {
  const calls: MockCall[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const parsed = new URL(url, "http://localhost");
      const method = (init?.method || "GET").toUpperCase();
      const path = `${parsed.pathname}${parsed.search}`;
      const headers = new Headers(init?.headers || {});

      calls.push({
        method,
        path,
        authorization: headers.get("Authorization"),
      });

      const route = routes[`${method} ${path}`];
      if (!route) {
        if (method === "GET" && path === "/api/setup/status") {
          return new Response(JSON.stringify({ completed: true }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        throw new Error(`Unexpected fetch call: ${method} ${path}`);
      }

      const responseConfig = Array.isArray(route) ? (route.shift() ?? route[route.length - 1]) : route;
      if (!responseConfig) {
        throw new Error(`No remaining mocked responses for: ${method} ${path}`);
      }
      if (responseConfig.throws) {
        throw responseConfig.throws;
      }

      return new Response(JSON.stringify(responseConfig.body), {
        status: responseConfig.status ?? 200,
        headers: { "Content-Type": "application/json" },
      });
    })
  );

  return calls;
}

function createSampleEmail(overrides: Record<string, unknown> = {}) {
  return {
    id: 42,
    subject: "Supplier quotation request",
    sender_email: "sales@supplier.com",
    sender_name: "Supplier Sales",
    status: "new",
    priority: "high",
    importance_score: 9,
    category: "RFQ",
    ai_analyzed: true,
    requires_reply: true,
    is_spam: false,
    date_received: "2026-04-02T12:00:00Z",
    ai_summary: "Supplier asks for pricing and delivery timing.",
    body_text: "Hello, please find quotation details attached.",
    direction: "inbound",
    folder: "Inbox",
    attachment_count: 1,
    preferred_reply_language: "en",
    ...overrides,
  };
}

function createSettingsResponse(overrides: Record<string, unknown> = {}) {
  return {
    signature: "Best regards,\nAdmin User",
    summary_language: "en",
    interface_language: "en",
    auto_spam_enabled: true,
    ...overrides,
  };
}

function authenticatedRoutes(user = adminUser, emailOverrides: Record<string, unknown> = {}): Record<string, RouteResponse> {
  const sampleEmail = createSampleEmail(emailOverrides);

  return {
    "GET /api/auth/me": { body: { user } },
    "POST /api/auth/logout": { body: { status: "ok" } },
    "GET /api/setup/status": { body: { completed: true } },
    "GET /api/settings": { body: createSettingsResponse() },
    "GET /api/emails?limit=60&direction=inbound": { body: [sampleEmail] },
    "GET /api/emails/42": { body: { ...sampleEmail, thread_id: "thread-42", created_at: "2026-04-02T11:50:00Z", updated_at: "2026-04-02T12:00:00Z" } },
    "GET /api/emails/42/thread": {
      body: {
        thread_id: "thread-42",
        emails: [
          {
            ...sampleEmail,
            thread_id: "thread-42",
            created_at: "2026-04-02T11:50:00Z",
            updated_at: "2026-04-02T12:00:00Z",
          },
        ],
      },
    },
    "GET /api/emails/42/attachments": { body: [{ id: 7, email_id: 42, filename: "quote.pdf", content_type: "application/pdf", size_bytes: 1024, is_inline: false, created_at: "2026-04-02T12:00:00Z" }] },
    "POST /api/emails/42/generate-draft": { body: { draft_reply: "Hello, thanks for the message.", subject: "Re: Supplier quotation request", target_language: "ru" } },
    "POST /api/emails/42/reply": { body: { status: "replied" } },
    "POST /api/emails/42/status": { body: { status: "archived" } },
    "POST /api/emails/42/restore": { body: { status: "new" } },
    "POST /api/emails/42/confirm-spam": { body: { status: "spam" } },
    "POST /api/settings": { body: createSettingsResponse() },
    "GET /api/emails?limit=60&direction=sent": { body: [] },
    "GET /api/emails?limit=60&status=spam": { body: [] },
  };
}

it("logs in and renders the minimal inbox UI", async () => {
  installFetchMock({
    "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
    ...authenticatedRoutes(adminUser),
  });

  const user = userEvent.setup();
  render(<App />);

  await screen.findByText("Mail login");
  await user.type(screen.getByLabelText("Email"), "admin@orhun.local");
  await user.type(screen.getByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));

  expect(await screen.findByText("Supplier quotation request")).toBeInTheDocument();
  expect(document.querySelector(".sidebar-backdrop")).toBeNull();
  expect(screen.getAllByText("Needs reply").length).toBeGreaterThan(0);
  expect(screen.getByLabelText("Importance: 9/10")).toBeInTheDocument();
  expect(screen.queryByText("Hello, please find quotation details attached.")).not.toBeInTheDocument();
  await user.click(screen.getByText("Supplier quotation request"));
  const dialog = await screen.findByRole("dialog", { name: "Read message" });
  expect(dialog).toBeInTheDocument();
  expect(within(dialog).getByText("Summary")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("Importance: 9/10")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Show original" })).toBeInTheDocument();
  expect(dialog.querySelector(".original-message-text")).toBeNull();
  await user.click(within(dialog).getByRole("button", { name: "Show original" }));
  expect(within(dialog).getByRole("button", { name: "Hide original" })).toBeInTheDocument();
  expect(dialog.querySelector(".original-message-text")).toHaveTextContent("Hello, please find quotation details attached.");
  await user.click(within(dialog).getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("keeps long summaries visible and clears transient overlay state across logout and relogin", async () => {
  installFetchMock({
    "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
    ...authenticatedRoutes(adminUser, { ai_summary: longSummary }),
  });

  const user = userEvent.setup();
  render(<App />);

  expect(await screen.findByText("Use the account provisioned for your workspace.")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Email"), "admin@orhun.local");
  await user.type(screen.getByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));

  expect(await screen.findByText(longSummary)).toBeInTheDocument();
  expect(screen.getByText(longSummary).closest(".email-row-summary")).toHaveAttribute("title", longSummary);

  await user.click(screen.getByText("Supplier quotation request"));
  const dialog = await screen.findByRole("dialog", { name: "Read message" });
  const detailSummary = dialog.querySelector(".detail-summary-copy");
  expect(detailSummary).toHaveTextContent(longSummary);
  expect(detailSummary).toHaveAttribute("title", longSummary);

  await user.click(screen.getByRole("button", { name: /menu/i }));
  expect(document.querySelector(".sidebar-backdrop")).not.toBeNull();

  await user.click(screen.getByRole("button", { name: "Logout" }));
  expect(await screen.findByText("Mail login")).toBeInTheDocument();
  expect(document.querySelector(".sidebar-backdrop")).toBeNull();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  await user.type(screen.getByLabelText("Email"), "admin@orhun.local");
  await user.type(screen.getByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));

  expect(await screen.findByText("Supplier quotation request")).toBeInTheDocument();
  expect(document.querySelector(".sidebar-backdrop")).toBeNull();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("opens the AI reply modal from a hover quick action", async () => {
  installFetchMock({
    "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
    ...authenticatedRoutes(adminUser),
  });

  const user = userEvent.setup();
  render(<App />);

  await screen.findByText("Mail login");
  await user.type(screen.getByLabelText("Email"), "admin@orhun.local");
  await user.type(screen.getByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));

  const replyAiButton = await screen.findByRole("button", { name: "Reply with AI" });
  await user.click(replyAiButton);

  const dialog = await screen.findByRole("dialog", { name: "Reply preview" });
  expect(dialog).toBeInTheDocument();
  expect(within(dialog).getByLabelText("To")).toHaveValue("sales@supplier.com");
  expect(within(dialog).getByLabelText("CC")).toBeInTheDocument();
  expect(within(dialog).getByLabelText("BCC")).toBeInTheDocument();
  expect(within(dialog).getByLabelText(/Signature/)).toHaveValue("Best regards,\nAdmin User");
  await user.click(within(dialog).getByRole("button", { name: "Close" }));
});

it("shows a visible error when login fails", async () => {
  installFetchMock({
    "POST /api/auth/login": { status: 401, body: { error_code: "auth_required", message: "Invalid credentials" } },
  });

  const user = userEvent.setup();
  render(<App />);

  await screen.findByText("Mail login");
  await user.type(screen.getByLabelText("Email"), "admin@orhun.local");
  await user.type(screen.getByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
  expect(localStorage.getItem("oma_token")).toBeNull();
});

it("shows the setup wizard when the backend reports setup_required", async () => {
  installFetchMock({
    "GET /api/setup/status": { status: 503, body: { error_code: "setup_required", message: "Setup is required before this request can be processed" } },
  });

  render(<App />);

  expect(await screen.findByText("Configure Mail Agent")).toBeInTheDocument();
});

it("keeps network failures separate from auth failures", async () => {
  localStorage.setItem("oma_token", "token-from-storage");
  installFetchMock({
    "GET /api/setup/status": { body: { completed: true } },
    "GET /api/auth/me": { throws: new TypeError("Failed to fetch") },
  });

  render(<App />);

  expect(await screen.findByText("Mail login")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Network error while reaching API");
  expect(localStorage.getItem("oma_token")).toBe("token-from-storage");
});

it("renders mailbox-context errors without logging the user out", async () => {
  installFetchMock({
    "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
    ...authenticatedRoutes(adminUser),
    "POST /api/emails/42/status": { status: 409, body: { error_code: "mailbox_context_mismatch", message: "Mailbox context does not match the requested email" } },
  });

  const user = userEvent.setup();
  render(<App />);

  await user.type(await screen.findByLabelText("Email"), "admin@orhun.local");
  await user.type(await screen.findByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));
  await screen.findByText("Supplier quotation request");

  await user.click(screen.getByRole("button", { name: "Archive" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Mailbox context does not match the requested email");
  expect(localStorage.getItem("oma_token")).toBe("token-123");
});

it("returns to login when auth bootstrap rejects an expired token and can recover with a fresh login", async () => {
  localStorage.setItem("oma_token", "expired-token");
  installFetchMock({
    ...authenticatedRoutes(adminUser),
    "GET /api/auth/me": [
      { status: 401, body: { detail: "Invalid or expired token" } },
      { body: { user: adminUser } },
    ],
    "POST /api/auth/refresh": { status: 401, body: { detail: "Invalid or expired token" } },
    "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
  });

  const user = userEvent.setup();
  render(<App />);

  expect(await screen.findByText("Mail login")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Session expired. Please sign in again.");
  expect(localStorage.getItem("oma_token")).toBeNull();

  await user.type(screen.getByLabelText("Email"), "admin@orhun.local");
  await user.type(screen.getByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));

  expect(await screen.findByText("Supplier quotation request")).toBeInTheDocument();
});

it("switches between inbox and settings and toggles language", async () => {
  installFetchMock({
    "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
    ...authenticatedRoutes(adminUser),
  });

  const user = userEvent.setup();
  render(<App />);

  await user.type(await screen.findByLabelText("Email"), "admin@orhun.local");
  await user.type(await screen.findByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));
  await screen.findByText("Supplier quotation request");

  await user.click(screen.getByRole("button", { name: "Settings" }));
  expect(await screen.findByText("Language")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "RU" }));
  expect(screen.getByText("Язык изменен.")).toBeInTheDocument();
});

it("offers summary generation for sent emails without analysis", async () => {
  const sentEmail = {
    id: 99,
    subject: "Outbound follow-up",
    sender_email: "admin@orhun.local",
    sender_name: "Admin User",
    status: "replied",
    priority: "medium",
    importance_score: 5,
    category: "Other",
    ai_analyzed: true,
    requires_reply: false,
    is_spam: false,
    date_received: "2026-04-03T08:00:00Z",
    ai_summary: "",
    body_text: "Following up on our prior discussion.",
    direction: "sent",
    folder: "Sent",
    attachment_count: 0,
    preferred_reply_language: "en",
  };

  installFetchMock({
  "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
    "GET /api/auth/me": { body: { user: adminUser } },
    "GET /api/settings": { body: createSettingsResponse() },
    "GET /api/emails?limit=60&direction=inbound": { body: [] },
    "GET /api/emails?limit=60&direction=sent": { body: [sentEmail] },
    "GET /api/emails/99": { body: { ...sentEmail, thread_id: "thread-99", created_at: "2026-04-03T08:00:00Z", updated_at: "2026-04-03T08:00:00Z" } },
    "GET /api/emails/99/thread": {
      body: {
        thread_id: "thread-99",
        emails: [
          { ...sentEmail, thread_id: "thread-99", created_at: "2026-04-03T08:00:00Z", updated_at: "2026-04-03T08:00:00Z" },
        ],
      },
    },
    "GET /api/emails/99/attachments": { body: [] },
  });

  const user = userEvent.setup();
  render(<App />);

  await user.type(await screen.findByLabelText("Email"), "admin@orhun.local");
  await user.type(await screen.findByLabelText("Password"), "admin123");
  await user.click(screen.getByRole("button", { name: /sign in/i }));

  await user.click(screen.getByRole("button", { name: "Sent" }));
  await screen.findByText("Outbound follow-up");

  await user.click(screen.getByText("Outbound follow-up"));
  const dialog = await screen.findByRole("dialog", { name: "Read message" });
  expect(within(dialog).getByRole("button", { name: "Generate summary" })).toBeInTheDocument();
});

it("bootstraps from stored token and keeps the auth header on requests", async () => {
  localStorage.setItem("oma_token", "token-from-storage");
  const calls = installFetchMock(authenticatedRoutes(adminUser));

  render(<App />);

  expect(await screen.findByText("Supplier quotation request")).toBeInTheDocument();
  await waitFor(() => {
    expect(calls.find((call) => call.method === "GET" && call.path === "/api/auth/me")?.authorization).toBe("Bearer token-from-storage");
  });
});
