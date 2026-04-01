import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";

type ViewKey = "focus" | "active" | "waiting" | "spam" | "settings";
type EmailItem = {
  id: number;
  subject?: string | null;
  sender_email?: string | null;
  sender_name?: string | null;
  date_received?: string | null;
  status: string;
  priority?: string | null;
  category?: string | null;
  ai_analyzed: boolean;
  requires_reply: boolean;
  is_spam: boolean;
  spam_source?: string | null;
  spam_reason?: string | null;
  applied_rules_json?: string | null;
  focus_flag?: boolean;
  spam_action_at?: string | null;
  spam_action_actor?: string | null;
  ai_summary?: string | null;
  body_text?: string | null;
  ai_draft_reply?: string | null;
  action_description?: string | null;
  direction?: string;
  waiting_state?: string | null;
  wait_days?: number | null;
};
type WaitingItem = {
  task_id: number;
  email_id?: number | null;
  thread_id: string;
  state: string;
  title: string;
  subtitle?: string | null;
  started_at?: string | null;
  expected_reply_by?: string | null;
  wait_days: number;
  latest_email_id?: number | null;
  latest_subject?: string | null;
  latest_sender_email?: string | null;
  latest_sender_name?: string | null;
  latest_ai_summary?: string | null;
  followup_draft?: string | null;
};
type ThreadResponse = { thread_id: string; emails: EmailItem[] };
type StatsResponse = { new_count: number; waiting_reply_count: number; analyzed_today_count: number; total_inbox_count: number; spam_count: number; waiting_count: number; overdue_count: number; followup_due_today_count: number };
type DigestResponse = { date: string; emails_received_today: number; important_emails: number; unanswered_emails: number; analyzed_count: number };
type SettingsResponse = {
  app_name: string; app_env: string; debug: boolean; database_url: string; imap_host: string; imap_port: number; imap_user: string;
  smtp_host: string; smtp_port: number; smtp_user: string; smtp_use_tls: boolean; smtp_use_ssl: boolean; deepseek_base_url: string;
  deepseek_model: string; scan_interval_minutes: number; followup_overdue_days: number; cors_origins: string[]; has_imap_password: boolean; has_smtp_password: boolean; has_openai_api_key: boolean;
};
type ContactListResponse = { items: Array<{ id: number; email: string; name?: string | null; company?: string | null }>; total: number; limit: number; offset: number };
type ScanResponse = { imported_count: number; analyzed_count: number; errors: string[] };
type PreferenceProfile = { version: number; generated_at?: string | null; summary_lines: string[]; draft_preferences: Record<string, unknown>; decision_preferences: Record<string, unknown> };
type AutomationRule = {
  id: string;
  name: string;
  enabled: boolean;
  order: number;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};
type QuickRuleTemplate = "always-high" | "always-archive" | "always-spam" | "never-spam" | "always-focus";

const initialSettingsForm = {
  app_name: "", app_env: "development", debug: false, imap_host: "", imap_port: "993", imap_user: "", imap_password: "",
  smtp_host: "", smtp_port: "465", smtp_user: "", smtp_password: "", smtp_use_tls: true, smtp_use_ssl: true,
  deepseek_base_url: "", deepseek_model: "", openai_api_key: "", scan_interval_minutes: "5", followup_overdue_days: "3", cors_origins: ""
};

function App() {
  const [view, setView] = useState<ViewKey>("focus");
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [digest, setDigest] = useState<DigestResponse | null>(null);
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [waitingItems, setWaitingItems] = useState<WaitingItem[]>([]);
  const [spamEmails, setSpamEmails] = useState<EmailItem[]>([]);
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [selectedEmailId, setSelectedEmailId] = useState<number | null>(null);
  const [selectedEmail, setSelectedEmail] = useState<EmailItem | null>(null);
  const [thread, setThread] = useState<EmailItem[]>([]);
  const [contacts, setContacts] = useState<ContactListResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [preferences, setPreferences] = useState<PreferenceProfile | null>(null);
  const [settingsForm, setSettingsForm] = useState(initialSettingsForm);
  const [draftText, setDraftText] = useState("");
  const [search, setSearch] = useState("");
  const [queueFilter, setQueueFilter] = useState("needs-reply");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [saveSettingsLoading, setSaveSettingsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => { void loadInitialData(); }, []);
  useEffect(() => {
    if (selectedEmailId == null) { setSelectedEmail(null); setThread([]); setDraftText(""); return; }
    void loadEmailDetail(selectedEmailId);
  }, [selectedEmailId]);

  const activeEmails = useMemo(() => {
    let items = emails.filter((item) => item.direction !== "sent");
    if (queueFilter === "needs-reply") items = items.filter((item) => item.requires_reply && item.status !== "replied" && !item.is_spam);
    else if (queueFilter === "waiting") items = items.filter((item) => item.waiting_state === "waiting_reply" || item.waiting_state === "overdue_reply");
    else if (queueFilter === "focus") items = items.filter((item) => item.focus_flag && !item.is_spam);
    else if (queueFilter === "all") items = items.filter((item) => !item.is_spam);
    if (search.trim()) {
      const term = search.toLowerCase();
      items = items.filter((item) =>
        [item.subject, item.sender_email, item.sender_name, item.ai_summary, item.body_text].filter(Boolean).some((value) => String(value).toLowerCase().includes(term))
      );
    }
    return items;
  }, [emails, queueFilter, search]);

  const focusSummary = useMemo(() => {
    if (!stats || !digest) return "Load the queue to see the current operating picture for Orhun Medical.";
    return `${stats.waiting_count} conversations are being tracked for reply. ${stats.overdue_count} are overdue, ${stats.spam_count} items are in spam review, and ${digest.important_emails} important emails landed today.`;
  }, [digest, stats]);

  async function loadInitialData() {
    setLoading(true); setErrorMessage("");
    try {
      const [statsData, digestData, emailData, followupData, spamData, contactData, settingsData, preferenceData, rulesData] = await Promise.all([
        apiGet<StatsResponse>("/api/stats"),
        apiGet<DigestResponse>("/api/digest"),
        apiGet<EmailItem[]>("/api/emails?limit=60"),
        apiGet<WaitingItem[]>("/api/followups").catch(() => []),
        apiGet<EmailItem[]>("/api/spam?limit=40").catch(() => []),
        apiGet<ContactListResponse>("/api/contacts?limit=20"),
        apiGet<SettingsResponse>("/api/settings"),
        apiGet<PreferenceProfile>("/api/preferences").catch(() => ({ version: 1, summary_lines: [], draft_preferences: {}, decision_preferences: {} })),
        apiGet<AutomationRule[]>("/api/rules").catch(() => []),
      ]);
      setStats(statsData);
      setDigest(digestData);
      setEmails(emailData);
      setWaitingItems(followupData);
      setSpamEmails(spamData);
      setContacts(contactData);
      setSettings(settingsData);
      hydrateSettingsForm(settingsData);
      setPreferences(preferenceData);
      setRules(rulesData);
      const candidate = emailData.find((item) => item.focus_flag && !item.is_spam) || emailData.find((item) => item.requires_reply && !item.is_spam) || emailData[0] || spamData[0] || null;
      setSelectedEmailId(candidate?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not load dashboard data."));
    } finally { setLoading(false); }
  }

  async function loadEmailDetail(emailId: number) {
    setDetailLoading(true); setErrorMessage("");
    try {
      const [detail, threadData] = await Promise.all([
        apiGet<EmailItem>(`/api/emails/${emailId}`),
        apiGet<ThreadResponse>(`/api/emails/${emailId}/thread`).catch(() => ({ thread_id: `email-${emailId}`, emails: [] }))
      ]);
      setSelectedEmail(detail);
      setThread(threadData.emails?.length ? threadData.emails : [detail]);
      setDraftText(detail.ai_draft_reply || "");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not load the selected email."));
    } finally { setDetailLoading(false); }
  }

  async function handleStatusUpdate(status: string) {
    if (!selectedEmail) return;
    setActionLoading(status); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/status`, { status });
      setSuccessMessage(`Email moved to ${status}.`);
      await refreshMailbox(selectedEmail.id);
      if (status === "spam") setView("spam");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not update email status."));
    } finally { setActionLoading(null); }
  }

  async function handleReplySend() {
    if (!selectedEmail || !draftText.trim()) { setErrorMessage("Draft reply is empty."); return; }
    setActionLoading("reply"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/reply`, { body: draftText, save_as_sent_record: true });
      setSuccessMessage("Reply sent and waiting-for-reply tracking started.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not send the reply."));
    } finally { setActionLoading(null); }
  }

  async function handleWaitingStart() {
    if (!selectedEmail) return;
    setActionLoading("waiting-start"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/waiting/start`, {});
      setSuccessMessage("Thread marked as waiting for reply.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not start waiting tracking."));
    } finally { setActionLoading(null); }
  }

  async function handleWaitingClose() {
    if (!selectedEmail) return;
    setActionLoading("waiting-close"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/waiting/close`, { reason: "closed_by_user" });
      setSuccessMessage("Waiting state closed.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not close waiting state."));
    } finally { setActionLoading(null); }
  }

  async function handleGenerateFollowup() {
    if (!selectedEmail) return;
    setActionLoading("followup-draft"); setErrorMessage(""); setSuccessMessage("");
    try {
      const result = await apiPost<{ thread_id: string; draft_reply: string }>(`/api/emails/${selectedEmail.id}/followup-draft`, {});
      setDraftText(result.draft_reply);
      setSuccessMessage("Suggested follow-up draft generated.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not generate follow-up draft."));
    } finally { setActionLoading(null); }
  }

  async function handleFeedback(decisionType: string, verdict: string, details?: Record<string, unknown>) {
    if (!selectedEmail) return;
    setActionLoading(`feedback-${decisionType}-${verdict}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/feedback`, { decision_type: decisionType, verdict, details });
      setSuccessMessage("Feedback recorded.");
      await refreshMailbox(selectedEmail.id);
      setPreferences(await apiPost<PreferenceProfile>("/api/preferences/rebuild", {}));
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not save feedback."));
    } finally { setActionLoading(null); }
  }

  async function handleDraftFeedback(verdict: "useful" | "bad") {
    if (!selectedEmail) return;
    setActionLoading(`draft-${verdict}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/draft-feedback`, {
        original_draft: selectedEmail.ai_draft_reply,
        final_draft: draftText,
        send_status: "reviewed",
      });
      await apiPost(`/api/emails/${selectedEmail.id}/feedback`, { decision_type: "draft", verdict });
      setSuccessMessage("Draft feedback recorded.");
      setPreferences(await apiPost<PreferenceProfile>("/api/preferences/rebuild", {}));
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not save draft feedback."));
    } finally { setActionLoading(null); }
  }

  async function handleSpamRestore() {
    if (!selectedEmail) return;
    setActionLoading("spam-restore"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/restore`, {});
      setSuccessMessage("Email restored from spam.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not restore the email."));
    } finally { setActionLoading(null); }
  }

  async function handleConfirmSpam() {
    if (!selectedEmail) return;
    setActionLoading("spam-confirm"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/confirm-spam`, {});
      setSuccessMessage("Spam decision confirmed.");
      await refreshMailbox(selectedEmail.id);
      setView("spam");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not confirm spam."));
    } finally { setActionLoading(null); }
  }

  async function handleManualScan() {
    setScanLoading(true); setErrorMessage(""); setSuccessMessage("");
    try {
      const result = await apiPost<ScanResponse>("/api/scan", {});
      setSuccessMessage(`Check completed: ${result.imported_count} imported, ${result.analyzed_count} analyzed.`);
      await loadInitialData();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not trigger scan."));
    } finally { setScanLoading(false); }
  }

  async function handleSettingsSave(event: React.FormEvent) {
    event.preventDefault(); setSaveSettingsLoading(true); setErrorMessage(""); setSuccessMessage("");
    try {
      const updated = await apiPost<SettingsResponse>("/api/settings", {
        ...settingsForm,
        imap_port: Number(settingsForm.imap_port),
        smtp_port: Number(settingsForm.smtp_port),
        scan_interval_minutes: Number(settingsForm.scan_interval_minutes),
        followup_overdue_days: Number(settingsForm.followup_overdue_days),
        cors_origins: settingsForm.cors_origins.split(",").map((item) => item.trim()).filter(Boolean)
      });
      setSettings(updated);
      hydrateSettingsForm(updated);
      setSuccessMessage("Settings saved.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not save settings."));
    } finally { setSaveSettingsLoading(false); }
  }

  async function handleQuickRuleCreate(template: QuickRuleTemplate) {
    if (!selectedEmail) return;
    const payload = buildQuickRulePayload(selectedEmail, template);
    if (!payload) {
      setErrorMessage("This email does not have enough sender information to build a rule.");
      return;
    }
    setActionLoading(`rule-${template}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost<AutomationRule>("/api/rules", payload);
      setSuccessMessage("Automation rule created.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not create the rule."));
    } finally { setActionLoading(null); }
  }

  async function handleRuleToggle(rule: AutomationRule) {
    setActionLoading(`rule-toggle-${rule.id}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPut<AutomationRule>(`/api/rules/${rule.id}`, { enabled: !rule.enabled });
      setSuccessMessage(`Rule ${rule.enabled ? "disabled" : "enabled"}.`);
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not update the rule."));
    } finally { setActionLoading(null); }
  }

  async function handleRuleDelete(ruleId: string) {
    setActionLoading(`rule-delete-${ruleId}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiDelete(`/api/rules/${ruleId}`);
      setSuccessMessage("Rule deleted.");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not delete the rule."));
    } finally { setActionLoading(null); }
  }

  async function refreshMailbox(preserveEmailId?: number | null) {
    const [statsData, digestData, emailData, followupData, spamData, rulesData] = await Promise.all([
      apiGet<StatsResponse>("/api/stats"),
      apiGet<DigestResponse>("/api/digest"),
      apiGet<EmailItem[]>("/api/emails?limit=60"),
      apiGet<WaitingItem[]>("/api/followups").catch(() => []),
      apiGet<EmailItem[]>("/api/spam?limit=40").catch(() => []),
      apiGet<AutomationRule[]>("/api/rules").catch(() => []),
    ]);
    setStats(statsData);
    setDigest(digestData);
    setEmails(emailData);
    setWaitingItems(followupData);
    setSpamEmails(spamData);
    setRules(rulesData);
    const stillExists = preserveEmailId ? emailData.find((item) => item.id === preserveEmailId) || spamData.find((item) => item.id === preserveEmailId) : null;
    if (stillExists) {
      setSelectedEmailId(stillExists.id);
      void loadEmailDetail(stillExists.id);
    }
    else setSelectedEmailId((emailData.find((item) => item.focus_flag && !item.is_spam) || emailData.find((item) => item.requires_reply && !item.is_spam) || emailData[0] || spamData[0] || null)?.id ?? null);
  }

  function hydrateSettingsForm(data: SettingsResponse) {
    setSettingsForm({
      app_name: data.app_name, app_env: data.app_env, debug: data.debug, imap_host: data.imap_host, imap_port: String(data.imap_port), imap_user: data.imap_user,
      imap_password: "", smtp_host: data.smtp_host, smtp_port: String(data.smtp_port), smtp_user: data.smtp_user, smtp_password: "",
      smtp_use_tls: data.smtp_use_tls, smtp_use_ssl: data.smtp_use_ssl, deepseek_base_url: data.deepseek_base_url, deepseek_model: data.deepseek_model,
      openai_api_key: "", scan_interval_minutes: String(data.scan_interval_minutes), followup_overdue_days: String(data.followup_overdue_days), cors_origins: data.cors_origins.join(", ")
    });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <h1>Orhun Mail Agent</h1>
          <p>Action dashboard for intake, drafting, automation, and review control.</p>
        </div>
        <div className="nav-section">
          <div className="nav-label">Workspace</div>
          <div className="nav-list">
            <NavButton label="Focus" active={view === "focus"} badge={stats?.waiting_reply_count} onClick={() => setView("focus")} />
            <NavButton label="Active Queue" active={view === "active"} badge={activeEmails.length} onClick={() => setView("active")} />
            <NavButton label="Waiting Queue" active={view === "waiting"} badge={stats?.overdue_count ?? waitingItems.length} onClick={() => setView("waiting")} />
            <NavButton label="Spam Log" active={view === "spam"} badge={spamEmails.length} onClick={() => setView("spam")} />
            <NavButton label="Settings" active={view === "settings"} badge={rules.length} onClick={() => setView("settings")} />
          </div>
        </div>
        <div className="sidebar-actions">
          <div className="sidebar-card">
            <h3 style={{ margin: 0 }}>Check now</h3>
            <p>Run inbox scan and AI analysis on demand.</p>
            <div style={{ marginTop: 14 }}>
              <button className="primary-button" onClick={() => void handleManualScan()} disabled={scanLoading}>{scanLoading ? "Checking..." : "Scan now"}</button>
            </div>
          </div>
          <div className="sidebar-card">
            <h3 style={{ margin: 0 }}>Automation rules</h3>
            <p>{rules.length} active rules are shaping focus, priority, archive, and spam review.</p>
          </div>
        </div>
      </aside>

      <main className="content-shell">
        <header className="topbar">
          <div>
            <h2>{getViewTitle(view)}</h2>
            <p>{getViewSubtitle(view, focusSummary)}</p>
          </div>
          <div className="topbar-actions">
            {contacts?.items?.length ? <span className="badge">{contacts.items.length} key contacts loaded</span> : null}
            {selectedEmail?.focus_flag ? <span className="badge">focus</span> : null}
            {selectedEmail?.priority ? <span className={`badge priority-${normalizePriority(selectedEmail.priority)}`}>{selectedEmail.priority}</span> : null}
          </div>
        </header>

        {errorMessage ? <div className="error-banner">{errorMessage}</div> : null}
        {successMessage ? <div className="success-banner">{successMessage}</div> : null}

        {loading ? <div className="panel"><div className="loading-state">Loading dashboard...</div></div> : (
          view === "settings" ? (
            <SettingsPanel settings={settings} preferences={preferences} rules={rules} form={settingsForm} onChange={setSettingsForm} onSubmit={(event) => void handleSettingsSave(event)} saveSettingsLoading={saveSettingsLoading} onToggleRule={(rule) => void handleRuleToggle(rule)} onDeleteRule={(ruleId) => void handleRuleDelete(ruleId)} />
          ) : (
            <div className={view === "focus" ? "column" : "layout-grid"}>
              {view === "focus" ? (
                <>
                  <div className="panel"><div className="panel-body"><div className="stats-grid">
                    <StatCard label="Needs reply" value={stats?.waiting_reply_count ?? 0} />
                    <StatCard label="Waiting" value={stats?.waiting_count ?? 0} />
                    <StatCard label="Overdue" value={stats?.overdue_count ?? 0} />
                    <StatCard label="Spam review" value={stats?.spam_count ?? 0} />
                  </div></div></div>
                  <div className="focus-grid">
                    <div className="panel"><div className="panel-body"><div className="summary-box"><h3>Daily focus summary</h3><p>{digest ? `${stats?.overdue_count ?? 0} conversations need a follow-up check. ${digest.unanswered_emails} unanswered items remain on the board. ${spamEmails.length} items are waiting in spam review.` : "Digest data is not available yet."}</p></div></div></div>
                    <div className="column">
                      <SummaryPoint title="Important arrivals" value={`${digest?.important_emails ?? 0} today`} />
                      <SummaryPoint title="Queue size" value={`${stats?.total_inbox_count ?? 0} inbound emails`} />
                      <SummaryPoint title="Automation rules" value={`${rules.filter((rule) => rule.enabled).length} enabled`} />
                      <SummaryPoint title="Suggested focus" value={activeEmails.find((item) => item.focus_flag)?.subject || activeEmails[0]?.subject || "Open the active queue to begin triage."} />
                    </div>
                  </div>
                  <div className="layout-grid">
                    <QueuePanel items={activeEmails} search={search} queueFilter={queueFilter} selectedEmailId={selectedEmailId} onQueueFilterChange={setQueueFilter} onSearchChange={setSearch} onSelectEmail={setSelectedEmailId} title="Needs reply now" subtitle="Action-oriented queue with AI hints, rule-based focus, urgency badges, and waiting signals." />
                    <DetailPanel selectedEmail={selectedEmail} thread={thread} draftText={draftText} onDraftChange={setDraftText} onSendReply={() => void handleReplySend()} onStatusUpdate={(status) => void handleStatusUpdate(status)} onStartWaiting={() => void handleWaitingStart()} onCloseWaiting={() => void handleWaitingClose()} onGenerateFollowup={() => void handleGenerateFollowup()} onFeedback={(decisionType, verdict, details) => void handleFeedback(decisionType, verdict, details)} onDraftFeedback={(verdict) => void handleDraftFeedback(verdict)} onRestoreSpam={() => void handleSpamRestore()} onConfirmSpam={() => void handleConfirmSpam()} onCreateQuickRule={(template) => void handleQuickRuleCreate(template)} loading={detailLoading} actionLoading={actionLoading} />
                  </div>
                </>
              ) : view === "active" ? (
                <>
                  <QueuePanel items={activeEmails} search={search} queueFilter={queueFilter} selectedEmailId={selectedEmailId} onQueueFilterChange={setQueueFilter} onSearchChange={setSearch} onSelectEmail={setSelectedEmailId} title="Active queue" subtitle="Browse live work, then move directly into draft, automation, and action mode." />
                  <DetailPanel selectedEmail={selectedEmail} thread={thread} draftText={draftText} onDraftChange={setDraftText} onSendReply={() => void handleReplySend()} onStatusUpdate={(status) => void handleStatusUpdate(status)} onStartWaiting={() => void handleWaitingStart()} onCloseWaiting={() => void handleWaitingClose()} onGenerateFollowup={() => void handleGenerateFollowup()} onFeedback={(decisionType, verdict, details) => void handleFeedback(decisionType, verdict, details)} onDraftFeedback={(verdict) => void handleDraftFeedback(verdict)} onRestoreSpam={() => void handleSpamRestore()} onConfirmSpam={() => void handleConfirmSpam()} onCreateQuickRule={(template) => void handleQuickRuleCreate(template)} loading={detailLoading} actionLoading={actionLoading} />
                </>
              ) : view === "waiting" ? (
                <>
                  <WaitingPanel items={waitingItems} onSelectEmail={setSelectedEmailId} />
                  <DetailPanel selectedEmail={selectedEmail} thread={thread} draftText={draftText} onDraftChange={setDraftText} onSendReply={() => void handleReplySend()} onStatusUpdate={(status) => void handleStatusUpdate(status)} onStartWaiting={() => void handleWaitingStart()} onCloseWaiting={() => void handleWaitingClose()} onGenerateFollowup={() => void handleGenerateFollowup()} onFeedback={(decisionType, verdict, details) => void handleFeedback(decisionType, verdict, details)} onDraftFeedback={(verdict) => void handleDraftFeedback(verdict)} onRestoreSpam={() => void handleSpamRestore()} onConfirmSpam={() => void handleConfirmSpam()} onCreateQuickRule={(template) => void handleQuickRuleCreate(template)} loading={detailLoading} actionLoading={actionLoading} />
                </>
              ) : (
                <>
                  <SpamPanel items={spamEmails} onSelectEmail={setSelectedEmailId} />
                  <DetailPanel selectedEmail={selectedEmail} thread={thread} draftText={draftText} onDraftChange={setDraftText} onSendReply={() => void handleReplySend()} onStatusUpdate={(status) => void handleStatusUpdate(status)} onStartWaiting={() => void handleWaitingStart()} onCloseWaiting={() => void handleWaitingClose()} onGenerateFollowup={() => void handleGenerateFollowup()} onFeedback={(decisionType, verdict, details) => void handleFeedback(decisionType, verdict, details)} onDraftFeedback={(verdict) => void handleDraftFeedback(verdict)} onRestoreSpam={() => void handleSpamRestore()} onConfirmSpam={() => void handleConfirmSpam()} onCreateQuickRule={(template) => void handleQuickRuleCreate(template)} loading={detailLoading} actionLoading={actionLoading} allowSpamReview />
                </>
              )}
            </div>
          )
        )}
      </main>
    </div>
  );
}

function QueuePanel(props: { title: string; subtitle: string; items: EmailItem[]; search: string; queueFilter: string; selectedEmailId: number | null; onQueueFilterChange: (value: string) => void; onSearchChange: (value: string) => void; onSelectEmail: (id: number) => void }) {
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">{props.title}</h3><p className="panel-subtitle">{props.subtitle}</p></div></div><div className="panel-body"><div className="queue-toolbar"><input value={props.search} onChange={(event) => props.onSearchChange(event.target.value)} placeholder="Search sender, subject, summary" /><select value={props.queueFilter} onChange={(event) => props.onQueueFilterChange(event.target.value)}><option value="needs-reply">Needs reply</option><option value="focus">Focus senders</option><option value="waiting">Waiting</option><option value="all">All active</option></select></div><div className="queue-list">{props.items.length === 0 ? <div className="empty-state"><strong>Queue is clear</strong><p>No active items match the current filter.</p></div> : props.items.map((item) => <button key={item.id} className={`queue-item ${item.id === props.selectedEmailId ? "active" : ""}`} onClick={() => props.onSelectEmail(item.id)}><div className="queue-meta"><span className={`badge priority-${normalizePriority(item.priority)}`}>{item.priority || "medium"}</span><span className={`badge status-${item.status}`}>{item.status}</span>{item.category ? <span className="badge">{item.category}</span> : null}{item.focus_flag ? <span className="badge">focus</span> : null}{item.waiting_state ? <span className={`badge ${item.waiting_state}`}>{item.waiting_state}</span> : null}</div><div className="queue-main"><div><h4>{item.sender_name || item.sender_email || "Unknown sender"}</h4><p>{item.subject || "No subject"}</p><p>{item.ai_summary || item.body_text?.slice(0, 120) || "No preview available."}</p></div><div className="queue-time">{item.wait_days != null ? `${item.wait_days}d wait` : formatDate(item.date_received)}</div></div></button>)}</div></div></section>;
}

function WaitingPanel(props: { items: WaitingItem[]; onSelectEmail: (id: number) => void }) {
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Waiting queue</h3><p className="panel-subtitle">Tracked conversations waiting for the other side. Overdue items should be followed up first.</p></div></div><div className="panel-body"><div className="log-list">{props.items.length === 0 ? <div className="empty-state"><strong>No waiting threads</strong><p>Threads marked as waiting for reply will appear here.</p></div> : props.items.map((item) => <div key={item.task_id} className="log-item"><div className="queue-main"><div><h4>{item.latest_sender_name || item.latest_sender_email || "Unknown sender"}</h4><p>{item.latest_subject || item.title}</p><p>{item.latest_ai_summary || item.subtitle || "No AI summary available."}</p></div><div className="queue-time">{item.wait_days}d wait</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className={`badge ${item.state}`}>{item.state}</span>{item.expected_reply_by ? <span className="badge">Due {formatDate(item.expected_reply_by)}</span> : null}{item.latest_email_id ? <button className="secondary-button" onClick={() => props.onSelectEmail(item.latest_email_id!)}>Open thread</button> : null}</div></div>)}</div></div></section>;
}

function DetailPanel(props: { selectedEmail: EmailItem | null; thread: EmailItem[]; draftText: string; onDraftChange: (value: string) => void; onSendReply: () => void; onStatusUpdate: (status: string) => void; onStartWaiting: () => void; onCloseWaiting: () => void; onGenerateFollowup: () => void; onFeedback: (decisionType: string, verdict: string, details?: Record<string, unknown>) => void; onDraftFeedback: (verdict: "useful" | "bad") => void; onRestoreSpam: () => void; onConfirmSpam: () => void; onCreateQuickRule: (template: QuickRuleTemplate) => void; loading: boolean; actionLoading: string | null; allowSpamReview?: boolean }) {
  const appliedRules = parseAppliedRules(props.selectedEmail?.applied_rules_json);
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Thread detail</h3><p className="panel-subtitle">Review message context, AI summary, draft, rules, and follow-up state before acting.</p></div></div><div className="panel-body">{props.loading ? <div className="loading-state">Loading detail...</div> : !props.selectedEmail ? <div className="empty-state"><strong>Select an item</strong><p>Pick a thread from the queue to review the draft workflow.</p></div> : <div className="detail-panel"><div className="detail-head"><div className="detail-title"><h3>{props.selectedEmail.subject || "No subject"}</h3><div className="detail-meta"><span className={`badge priority-${normalizePriority(props.selectedEmail.priority)}`}>{props.selectedEmail.priority || "medium"}</span><span className={`badge status-${props.selectedEmail.status}`}>{props.selectedEmail.status}</span>{props.selectedEmail.category ? <span className="badge">{props.selectedEmail.category}</span> : null}<span className="badge">{props.selectedEmail.sender_name || props.selectedEmail.sender_email || "Unknown sender"}</span>{props.selectedEmail.focus_flag ? <span className="badge">focus</span> : null}{props.selectedEmail.waiting_state ? <span className={`badge ${props.selectedEmail.waiting_state}`}>{props.selectedEmail.waiting_state}</span> : null}</div></div><div className="tiny">{props.selectedEmail.wait_days != null ? `Waiting ${props.selectedEmail.wait_days} days` : formatDate(props.selectedEmail.date_received)}</div></div><div className="assistant-grid"><div className="detail-section"><h4>AI summary</h4><div className="detail-copy"><p>{props.selectedEmail.ai_summary || "Analysis is not available for this item yet."}</p></div><div className="detail-toolbar full"><button className="secondary-button" onClick={() => props.onFeedback("summary", "useful")}>Summary helpful</button><button className="ghost-button" onClick={() => props.onFeedback("summary", "bad")}>Summary off</button></div></div><div className="detail-section"><h4>Suggested next step</h4><div className="detail-copy"><p>{props.selectedEmail.action_description || (props.selectedEmail.requires_reply ? "Reply expected. Review and send draft." : props.selectedEmail.waiting_state ? "Conversation is being tracked while waiting for the other side." : "No immediate action suggested.")}</p>{props.selectedEmail.spam_source || props.selectedEmail.spam_reason ? <p><strong>Spam source:</strong> {props.selectedEmail.spam_source || "unknown"} {props.selectedEmail.spam_reason ? `- ${props.selectedEmail.spam_reason}` : ""}</p> : null}</div><div className="detail-toolbar full"><button className="secondary-button" onClick={() => props.onFeedback("priority", "mark_important", { new_priority: "high" })}>Mark important</button><button className="ghost-button" onClick={() => props.onFeedback("priority", "mark_not_important", { new_priority: "low" })}>Not important</button></div></div></div><div className="detail-section"><h4>Thread</h4><div className="detail-thread">{(props.thread.length ? props.thread : [props.selectedEmail]).map((item) => <div key={item.id} className="thread-item"><div className="thread-meta"><span className="badge">{item.sender_name || item.sender_email || "Unknown sender"}</span><span className="badge">{formatDate(item.date_received)}</span></div><h4>{item.subject || "No subject"}</h4><p>{item.body_text || item.ai_summary || "No body text available."}</p></div>)}</div></div><div className="detail-section"><h4>Automation trace</h4>{appliedRules.length === 0 ? <div className="tiny">No explicit user rule matched this email yet.</div> : <div className="queue-meta">{appliedRules.map((rule) => <span key={rule.id} className="badge">{rule.name}</span>)}</div>}<div className="detail-toolbar" style={{ marginTop: 12 }}><button className="secondary-button" onClick={() => props.onCreateQuickRule("always-high")} disabled={Boolean(props.actionLoading)}>Always high</button><button className="secondary-button" onClick={() => props.onCreateQuickRule("always-focus")} disabled={Boolean(props.actionLoading)}>Always focus</button><button className="secondary-button" onClick={() => props.onCreateQuickRule("always-archive")} disabled={Boolean(props.actionLoading)}>Always archive</button><button className="danger-button" onClick={() => props.onCreateQuickRule("always-spam")} disabled={Boolean(props.actionLoading)}>Always spam</button><button className="ghost-button" onClick={() => props.onCreateQuickRule("never-spam")} disabled={Boolean(props.actionLoading)}>Never spam</button></div></div><div className="detail-section"><div className="split-note"><div><h4>{props.selectedEmail.waiting_state ? "Follow-up / reply draft" : "Draft reply"}</h4><div className="tiny">Edit the current draft, send a follow-up, or switch the thread into waiting mode.</div></div><span className="badge">{props.draftText.length} chars</span></div><textarea rows={10} value={props.draftText} onChange={(event) => props.onDraftChange(event.target.value)} placeholder="Draft reply..." /><div className="detail-toolbar full"><button className="secondary-button" onClick={() => props.onDraftFeedback("useful")}>Draft helpful</button><button className="ghost-button" onClick={() => props.onDraftFeedback("bad")}>Draft needs work</button></div></div><div className="detail-toolbar"><button className="primary-button" onClick={props.onSendReply} disabled={props.actionLoading === "reply"}>{props.actionLoading === "reply" ? "Sending..." : "Send draft"}</button><button className="secondary-button" onClick={props.onGenerateFollowup} disabled={Boolean(props.actionLoading)}>{props.actionLoading === "followup-draft" ? "Generating..." : "Generate follow-up"}</button><button className="secondary-button" onClick={props.selectedEmail.waiting_state ? props.onCloseWaiting : props.onStartWaiting} disabled={Boolean(props.actionLoading)}>{props.selectedEmail.waiting_state ? "Close waiting" : "Waiting for reply"}</button><button className="secondary-button" onClick={() => props.onStatusUpdate("replied")} disabled={Boolean(props.actionLoading)}>I will reply myself</button><button className="secondary-button" onClick={() => props.onStatusUpdate("archived")} disabled={Boolean(props.actionLoading)}>Archive</button>{props.allowSpamReview ? <button className="secondary-button" onClick={props.onRestoreSpam} disabled={Boolean(props.actionLoading)}>{props.actionLoading === "spam-restore" ? "Restoring..." : "Restore to active"}</button> : <button className="danger-button" onClick={() => props.onStatusUpdate("spam")} disabled={Boolean(props.actionLoading)}>Mark spam</button>}{props.allowSpamReview ? <button className="danger-button" onClick={props.onConfirmSpam} disabled={Boolean(props.actionLoading)}>{props.actionLoading === "spam-confirm" ? "Confirming..." : "Confirm spam"}</button> : <button className="ghost-button" onClick={() => props.onStatusUpdate("read")} disabled={Boolean(props.actionLoading)}>Later / snooze</button>}{!props.allowSpamReview ? null : null}</div></div>}</div></section>;
}

function SpamPanel(props: { items: EmailItem[]; onSelectEmail: (id: number) => void }) {
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Spam log</h3><p className="panel-subtitle">Review suspicious items, inspect AI or rule source, and restore anything that should return to the queue.</p></div></div><div className="panel-body"><div className="log-list">{props.items.length === 0 ? <div className="empty-state"><strong>No spam logged</strong><p>Spam-classified items will appear here.</p></div> : props.items.map((item) => <div key={item.id} className="log-item"><div className="queue-main"><div><h4>{item.sender_name || item.sender_email || "Unknown sender"}</h4><p>{item.subject || "No subject"}</p><p>{item.spam_reason || "No spam reason recorded."}</p></div><div className="queue-time">{formatDate(item.spam_action_at || item.date_received)}</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className="badge priority-spam">{item.spam_source || "spam"}</span>{item.spam_action_actor ? <span className="badge">{item.spam_action_actor}</span> : null}<button className="secondary-button" onClick={() => props.onSelectEmail(item.id)}>Review</button></div></div>)}</div></div></section>;
}

function SettingsPanel(props: { settings: SettingsResponse | null; preferences: PreferenceProfile | null; rules: AutomationRule[]; form: typeof initialSettingsForm; onChange: React.Dispatch<React.SetStateAction<typeof initialSettingsForm>>; onSubmit: (event: React.FormEvent) => void; saveSettingsLoading: boolean; onToggleRule: (rule: AutomationRule) => void; onDeleteRule: (ruleId: string) => void }) {
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Connection settings</h3><p className="panel-subtitle">Edit safe operational settings, learned preferences, and active automation rules.</p></div></div><div className="panel-body"><form onSubmit={props.onSubmit}><div className="settings-grid"><Field label="App name"><input value={props.form.app_name} onChange={(event) => props.onChange((current) => ({ ...current, app_name: event.target.value }))} /></Field><Field label="Environment"><select value={props.form.app_env} onChange={(event) => props.onChange((current) => ({ ...current, app_env: event.target.value }))}><option value="development">development</option><option value="production">production</option></select></Field><Field label="IMAP host"><input value={props.form.imap_host} onChange={(event) => props.onChange((current) => ({ ...current, imap_host: event.target.value }))} /></Field><Field label="IMAP port"><input value={props.form.imap_port} onChange={(event) => props.onChange((current) => ({ ...current, imap_port: event.target.value }))} /></Field><Field label="IMAP user"><input value={props.form.imap_user} onChange={(event) => props.onChange((current) => ({ ...current, imap_user: event.target.value }))} /></Field><Field label={`IMAP password ${props.settings?.has_imap_password ? "(stored)" : ""}`}><input type="password" value={props.form.imap_password} onChange={(event) => props.onChange((current) => ({ ...current, imap_password: event.target.value }))} placeholder="Leave blank to keep current" /></Field><Field label="SMTP host"><input value={props.form.smtp_host} onChange={(event) => props.onChange((current) => ({ ...current, smtp_host: event.target.value }))} /></Field><Field label="SMTP port"><input value={props.form.smtp_port} onChange={(event) => props.onChange((current) => ({ ...current, smtp_port: event.target.value }))} /></Field><Field label="SMTP user"><input value={props.form.smtp_user} onChange={(event) => props.onChange((current) => ({ ...current, smtp_user: event.target.value }))} /></Field><Field label={`SMTP password ${props.settings?.has_smtp_password ? "(stored)" : ""}`}><input type="password" value={props.form.smtp_password} onChange={(event) => props.onChange((current) => ({ ...current, smtp_password: event.target.value }))} placeholder="Leave blank to keep current" /></Field><Field label="DeepSeek base URL"><input value={props.form.deepseek_base_url} onChange={(event) => props.onChange((current) => ({ ...current, deepseek_base_url: event.target.value }))} /></Field><Field label="DeepSeek model"><input value={props.form.deepseek_model} onChange={(event) => props.onChange((current) => ({ ...current, deepseek_model: event.target.value }))} /></Field><Field label="Follow-up overdue days"><input value={props.form.followup_overdue_days} onChange={(event) => props.onChange((current) => ({ ...current, followup_overdue_days: event.target.value }))} /></Field><Field label={`AI API key ${props.settings?.has_openai_api_key ? "(stored)" : ""}`}><input type="password" value={props.form.openai_api_key} onChange={(event) => props.onChange((current) => ({ ...current, openai_api_key: event.target.value }))} placeholder="Leave blank to keep current" /></Field><Field label="Scan interval (minutes)"><input value={props.form.scan_interval_minutes} onChange={(event) => props.onChange((current) => ({ ...current, scan_interval_minutes: event.target.value }))} /></Field><Field label="CORS origins" full><input value={props.form.cors_origins} onChange={(event) => props.onChange((current) => ({ ...current, cors_origins: event.target.value }))} placeholder="http://localhost:3000, http://localhost:5173" /></Field></div><div className="settings-note" style={{ marginTop: 16 }}>Follow-up overdue days controls when waiting threads automatically move into the overdue queue.</div><div className="settings-note" style={{ marginTop: 16 }}><strong>Learned preferences</strong><div className="tiny" style={{ marginTop: 8 }}>{props.preferences?.summary_lines?.length ? props.preferences.summary_lines.join(" ") : "No learned preference summary yet. Use feedback controls and send edited drafts to build it."}</div></div><div className="detail-toolbar full" style={{ marginTop: 18 }}><button className="primary-button" type="submit" disabled={props.saveSettingsLoading}>{props.saveSettingsLoading ? "Saving..." : "Save settings"}</button></div></form><div className="detail-section" style={{ marginTop: 18 }}><h4>Automation rules</h4><div className="log-list">{props.rules.length === 0 ? <div className="empty-state"><strong>No rules yet</strong><p>Create simple sender/domain rules from an email detail view.</p></div> : props.rules.map((rule) => <div key={rule.id} className="log-item"><div className="queue-main"><div><h4>{rule.name}</h4><p>{describeRule(rule)}</p></div><div className="queue-time">order {rule.order}</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className={`badge ${rule.enabled ? "status-new" : "status-archived"}`}>{rule.enabled ? "enabled" : "disabled"}</span><button className="secondary-button" onClick={() => props.onToggleRule(rule)}>{rule.enabled ? "Disable" : "Enable"}</button><button className="ghost-button" onClick={() => props.onDeleteRule(rule.id)}>Delete</button></div></div>)}</div></div></div></section>;
}

function NavButton(props: { label: string; active: boolean; badge?: number; onClick: () => void }) { return <button className={`nav-button ${props.active ? "active" : ""}`} onClick={props.onClick}><span>{props.label}</span>{typeof props.badge === "number" ? <span className="nav-badge">{props.badge}</span> : null}</button>; }
function StatCard(props: { label: string; value: number }) { return <div className="stat-card"><span>{props.label}</span><strong>{props.value}</strong></div>; }
function SummaryPoint(props: { title: string; value: string }) { return <div className="summary-point"><strong>{props.title}</strong><span>{props.value}</span></div>; }
function Field(props: { label: string; children: React.ReactNode; full?: boolean }) { return <div className={`field ${props.full ? "full" : ""}`}><label>{props.label}</label>{props.children}</div>; }

async function apiGet<T>(url: string): Promise<T> { const response = await fetch(url); return parseResponse<T>(response); }
async function apiPost<T = unknown>(url: string, body: unknown): Promise<T> { const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); return parseResponse<T>(response); }
async function apiPut<T = unknown>(url: string, body: unknown): Promise<T> { const response = await fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); return parseResponse<T>(response); }
async function apiDelete<T = unknown>(url: string): Promise<T> { const response = await fetch(url, { method: "DELETE" }); return parseResponse<T>(response); }
async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { const data = (await response.json()) as { detail?: string }; if (data?.detail) detail = data.detail; } catch { }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}
function getErrorMessage(error: unknown, fallback: string) { return error instanceof Error && error.message ? error.message : fallback; }
function formatDate(value?: string | null) { if (!value) return "No date"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }
function normalizePriority(priority?: string | null) { const normalized = (priority || "medium").toLowerCase(); return ["critical", "high", "medium", "low", "spam"].includes(normalized) ? normalized : "medium"; }
function getViewTitle(view: ViewKey) { if (view === "focus") return "Focus workspace"; if (view === "active") return "Active queue"; if (view === "waiting") return "Waiting queue"; if (view === "spam") return "Spam review log"; return "System settings"; }
function getViewSubtitle(view: ViewKey, focusSummary: string) { if (view === "focus") return focusSummary; if (view === "active") return "Move from AI analysis to a sent reply without leaving the board."; if (view === "waiting") return "Track outbound conversations, overdue threads, and suggested follow-ups."; if (view === "spam") return "Audit blocked messages, see AI or rule source, and restore mistakes quickly."; return "Manage connection settings, learned preferences, and operational rules."; }

function buildQuickRulePayload(email: EmailItem, template: QuickRuleTemplate): { name: string; conditions: Record<string, unknown>; actions: Record<string, unknown> } | null {
  const senderEmail = (email.sender_email || "").trim().toLowerCase();
  const senderDomain = senderEmail.includes("@") ? senderEmail.split("@")[1] : "";
  const senderLabel = senderDomain || senderEmail;
  if (!senderLabel) return null;
  if (template === "always-high") return { name: `${senderLabel} always high priority`, conditions: senderDomain ? { sender_domain: senderDomain } : { sender_email: senderEmail }, actions: { set_priority: "high", move_to_focus: true } };
  if (template === "always-focus") return { name: `${senderLabel} always in focus`, conditions: senderDomain ? { sender_domain: senderDomain } : { sender_email: senderEmail }, actions: { move_to_focus: true, never_spam: true } };
  if (template === "always-archive") return { name: `${senderLabel} auto archive`, conditions: { sender_email: senderEmail || senderLabel }, actions: { archive: true, set_priority: "low" } };
  if (template === "always-spam") return { name: `${senderLabel} always spam`, conditions: { sender_email: senderEmail || senderLabel }, actions: { mark_spam: true } };
  return { name: `${senderLabel} never spam`, conditions: senderDomain ? { sender_domain: senderDomain } : { sender_email: senderEmail }, actions: { never_spam: true, move_to_focus: true } };
}

function parseAppliedRules(raw?: string | null): Array<{ id: string; name: string }> {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as Array<{ id?: string; name?: string }>;
    return Array.isArray(parsed) ? parsed.filter((item) => item?.id && item?.name).map((item) => ({ id: String(item.id), name: String(item.name) })) : [];
  } catch {
    return [];
  }
}

function describeRule(rule: AutomationRule): string {
  const conditions = Object.entries(rule.conditions || {}).map(([key, value]) => `${key}=${String(value)}`).join(", ");
  const actions = Object.entries(rule.actions || {}).map(([key, value]) => `${key}=${String(value)}`).join(", ");
  return `If ${conditions || "matched"} then ${actions || "no-op"}.`;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
