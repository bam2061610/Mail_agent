import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { App } from "./main";

type RouteResponse = {
  status?: number;
  body: unknown;
};

type MockCall = {
  method: string;
  path: string;
  authorization: string | null;
  body?: string;
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

function installFetchMock(routes: Record<string, RouteResponse>): MockCall[] {
  const calls: MockCall[] = [];

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const parsed = new URL(url, "http://localhost");
    const method = (init?.method || "GET").toUpperCase();
    const path = `${parsed.pathname}${parsed.search}`;
    const headers = new Headers(init?.headers || {});
    const body = typeof init?.body === "string" ? init.body : undefined;

    calls.push({
      method,
      path,
      authorization: headers.get("Authorization"),
      body,
    });

    const key = `${method} ${path}`;
    const route = routes[key];
    if (!route) {
      throw new Error(`Unexpected fetch call: ${key}`);
    }

    return new Response(JSON.stringify(route.body), {
      status: route.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  }));

  return calls;
}

function buildAuthenticatedRoutes(user = adminUser): Record<string, RouteResponse> {
  return {
    "GET /api/auth/me": { body: { user } },
    "GET /api/stats": { body: { new_count: 0, waiting_reply_count: 0, analyzed_today_count: 0, total_inbox_count: 0, spam_count: 0, waiting_count: 0, overdue_count: 0, followup_due_today_count: 0 } },
    "GET /api/digest": { body: { date: "2026-04-02", emails_received_today: 0, important_emails: 0, unanswered_emails: 0, analyzed_count: 0 } },
    "GET /api/digest/catchup": { body: { generated_at: "2026-04-02T10:00:00Z", since: "2026-04-02T00:00:00Z", away_hours: 8, should_show: false, important_new: [], waiting_or_overdue: [], spam_review: [], recent_sent: [], followups_due: [], top_actions: [] } },
    "GET /api/emails?limit=60&direction=inbound": { body: [] },
    "GET /api/emails?limit=60&direction=sent": { body: [] },
    "GET /api/sent/reviews?limit=30": { body: [] },
    "GET /api/followups": { body: [] },
    "GET /api/spam?limit=40": { body: [] },
    "GET /api/contacts?limit=20": { body: { items: [], total: 0, limit: 20, offset: 0 } },
    "GET /api/settings": {
      body: {
        app_name: "Orhun Mail Agent",
        app_env: "development",
        debug: false,
        database_url: "sqlite:///./data/mail_agent.db",
        imap_host: "",
        imap_port: 993,
        imap_user: "",
        smtp_host: "",
        smtp_port: 465,
        smtp_user: "",
        smtp_use_tls: true,
        smtp_use_ssl: true,
        deepseek_base_url: "https://api.deepseek.com",
        deepseek_model: "deepseek-chat",
        scan_interval_minutes: 5,
        followup_overdue_days: 3,
        catchup_absence_hours: 8,
        sent_review_batch_limit: 20,
        cors_origins: ["http://localhost:3000"],
        has_imap_password: false,
        has_smtp_password: false,
        has_openai_api_key: false,
      },
    },
    "GET /api/preferences": { body: { version: 1, generated_at: null, summary_lines: [], draft_preferences: {}, decision_preferences: {} } },
    "GET /api/rules": { body: [] },
    "GET /api/templates": { body: [] },
    "GET /api/mailboxes": { body: [] },
    "GET /api/users": { body: [user] },
    "GET /api/admin/diagnostics": {
      body: {
        overall_status: "ok",
        server_time: "2026-04-02T10:00:00Z",
        app_env: "development",
        components: {},
        mailboxes: [],
        storage: {},
        jobs: {},
      },
    },
    "GET /api/admin/backups": { body: [] },
    "GET /api/admin/backups/status": { body: { backups_count: 0, latest_backup: null, backup_dir: "/tmp/backups" } },
  };
}

it("logs in successfully, stores token, and unlocks authenticated UI", async () => {
  const calls = installFetchMock({
    "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
    ...buildAuthenticatedRoutes(adminUser),
  });

  render(<App />);

  await screen.findByText("Team login");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

  await screen.findByText("Admin User (admin)");
  await screen.findByText("Focus workspace");

  expect(localStorage.getItem("oma_token")).toBe("token-123");
  expect(calls.find((call) => call.method === "POST" && call.path === "/api/auth/login")).toBeTruthy();
});

it("shows a visible error when login fails", async () => {
  installFetchMock({
    "POST /api/auth/login": { status: 401, body: { detail: "Invalid credentials" } },
  });

  render(<App />);

  await screen.findByText("Team login");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid credentials");
  expect(localStorage.getItem("oma_token")).toBeNull();
});

it("bootstraps user session from stored token via /api/auth/me", async () => {
  localStorage.setItem("oma_token", "token-from-storage");
  const calls = installFetchMock(buildAuthenticatedRoutes(adminUser));

  render(<App />);

  await screen.findByText("Admin User (admin)");
  await waitFor(() => {
    const meCall = calls.find((call) => call.method === "GET" && call.path === "/api/auth/me");
    expect(meCall?.authorization).toBe("Bearer token-from-storage");
  });
});

it("surfaces bootstrap failures and returns to login when stored token is invalid", async () => {
  localStorage.setItem("oma_token", "expired-token");
  installFetchMock({
    "GET /api/auth/me": { status: 401, body: { detail: "Invalid or expired token" } },
  });

  render(<App />);

  await screen.findByText("Team login");
  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or expired token");
  expect(localStorage.getItem("oma_token")).toBeNull();
});

it("shows sent mailbox with per-message summary and original body blocks", async () => {
  const sentItem = {
    id: 42,
    subject: "Re: Pricing update",
    sender_email: "ops@orhun.local",
    sender_name: "Ops Team",
    status: "replied",
    ai_analyzed: true,
    requires_reply: false,
    is_spam: false,
    date_received: "2026-04-02T12:00:00Z",
    ai_summary: "Shared final pricing confirmation and next delivery steps.",
    body_text: "Thanks for your patience. We confirmed pricing and timeline.",
  };
  installFetchMock({
    "POST /api/auth/login": { body: { access_token: "token-123", token_type: "bearer", user: adminUser } },
    ...buildAuthenticatedRoutes(adminUser),
    "GET /api/emails?limit=60&direction=sent": { body: [sentItem] },
    "GET /api/emails/42": { body: { ...sentItem, folder: "sent", direction: "sent", thread_id: "thread-42", created_at: "2026-04-02T11:50:00Z", updated_at: "2026-04-02T12:00:00Z" } },
    "GET /api/emails/42/thread": {
      body: {
        thread_id: "thread-42",
        emails: [{ ...sentItem, folder: "sent", direction: "sent", thread_id: "thread-42", created_at: "2026-04-02T11:50:00Z", updated_at: "2026-04-02T12:00:00Z" }],
      },
    },
    "GET /api/emails/42/attachments": { body: [] },
  });

  render(<App />);

  await screen.findByText("Team login");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
  await screen.findByText("Admin User (admin)");

  await userEvent.click(screen.getByRole("button", { name: "Sent" }));

  await screen.findByText("Re: Pricing update");
  await screen.findByText("Summary");
  await screen.findByText("Original message");
});
