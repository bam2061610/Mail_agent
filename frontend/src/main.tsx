import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";

type ViewKey = "focus" | "active" | "waiting" | "spam" | "reports" | "settings";
type UserRole = "admin" | "manager" | "operator" | "viewer";
type EmailItem = {
  id: number;
  subject?: string | null;
  sender_email?: string | null;
  sender_name?: string | null;
  mailbox_id?: string | null;
  mailbox_name?: string | null;
  mailbox_address?: string | null;
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
  detected_source_language?: string | null;
  preferred_reply_language?: string | null;
  has_attachments?: boolean;
  attachment_count?: number;
  direction?: string;
  waiting_state?: string | null;
  wait_days?: number | null;
  assigned_to_user_id?: number | null;
  assigned_by_user_id?: number | null;
  assigned_at?: string | null;
  sent_review_summary?: string | null;
  sent_review_status?: string | null;
  sent_review_issues_json?: string | null;
  sent_review_score?: number | null;
  sent_review_suggested_improvement?: string | null;
  sent_reviewed_at?: string | null;
};
type AttachmentItem = {
  id: number;
  email_id: number;
  filename?: string | null;
  content_type?: string | null;
  size_bytes: number;
  is_inline: boolean;
  created_at: string;
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
type CatchupItem = { email_id?: number | null; task_id?: number | null; thread_id?: string | null; subject?: string | null; sender_email?: string | null; sender_name?: string | null; mailbox_name?: string | null; state?: string | null; priority?: string | null; status?: string | null; date_received?: string | null; expected_reply_by?: string | null; };
type CatchupDigestResponse = { generated_at: string; since: string; away_hours: number; should_show: boolean; important_new: CatchupItem[]; waiting_or_overdue: CatchupItem[]; spam_review: CatchupItem[]; recent_sent: CatchupItem[]; followups_due: CatchupItem[]; top_actions: string[]; };
type SettingsResponse = {
  app_name: string; app_env: string; debug: boolean; database_url: string; imap_host: string; imap_port: number; imap_user: string;
  smtp_host: string; smtp_port: number; smtp_user: string; smtp_use_tls: boolean; smtp_use_ssl: boolean; deepseek_base_url: string;
  deepseek_model: string; scan_interval_minutes: number; followup_overdue_days: number; catchup_absence_hours: number; sent_review_batch_limit: number; cors_origins: string[]; has_imap_password: boolean; has_smtp_password: boolean; has_openai_api_key: boolean;
};
type ContactListResponse = { items: Array<{ id: number; email: string; name?: string | null; company?: string | null }>; total: number; limit: number; offset: number };
type ScanResponse = { imported_count: number; analyzed_count: number; errors: string[] };
type SentReviewRunResponse = { selected_count: number; reviewed_count: number; failed_count: number; errors: string[] };
type UserItem = { id: number; email: string; full_name: string; role: UserRole; is_active: boolean; timezone?: string | null; language?: string | null; last_login_at?: string | null; created_at: string; updated_at: string; };
type AuthLoginResponse = { access_token: string; token_type: "bearer"; user: UserItem };
type AuthMeResponse = { user: UserItem };
type ReportResponse = { report_type: string; generated_at: string; filters: Record<string, unknown>; summary: Record<string, unknown>; rows: Array<Record<string, unknown>> };
type BackupItem = { backup_name: string; created_at?: string | null; include_attachments: boolean; size_bytes: number; path: string; manifest?: Record<string, unknown> };
type BackupStatusResponse = { backups_count: number; latest_backup?: BackupItem | null; backup_dir: string };
type AdminMailboxStatus = {
  mailbox_id: string;
  mailbox_name: string;
  email_address?: string | null;
  enabled: boolean;
  last_checked_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_error?: string | null;
  connection_ok?: boolean | null;
  connection_error?: string | null;
};
type AdminHealthResponse = {
  overall_status: string;
  server_time: string;
  app_env: string;
  components: Record<string, unknown>;
  mailboxes: AdminMailboxStatus[];
  storage: Record<string, unknown>;
  jobs: Record<string, unknown>;
};
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
type MessageTemplate = {
  id: string;
  name: string;
  category: string;
  language: "ru" | "en" | "tr";
  subject_template?: string | null;
  body_template: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};
type TemplateFormState = {
  name: string;
  category: string;
  language: "ru" | "en" | "tr";
  subject_template: string;
  body_template: string;
};
type MailboxItem = {
  id: string;
  name: string;
  email_address: string;
  imap_host: string;
  imap_port: number;
  imap_username: string;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  enabled: boolean;
  is_default_outgoing: boolean;
  created_at: string;
  updated_at: string;
  has_imap_password: boolean;
  has_smtp_password: boolean;
};
type MailboxFormState = {
  name: string;
  email_address: string;
  imap_host: string;
  imap_port: string;
  imap_username: string;
  imap_password: string;
  smtp_host: string;
  smtp_port: string;
  smtp_username: string;
  smtp_password: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  enabled: boolean;
  is_default_outgoing: boolean;
};

const initialSettingsForm = {
  app_name: "", app_env: "development", debug: false, imap_host: "", imap_port: "993", imap_user: "", imap_password: "",
  smtp_host: "", smtp_port: "465", smtp_user: "", smtp_password: "", smtp_use_tls: true, smtp_use_ssl: true,
  deepseek_base_url: "", deepseek_model: "", openai_api_key: "", scan_interval_minutes: "5", followup_overdue_days: "3", catchup_absence_hours: "8", sent_review_batch_limit: "20", cors_origins: ""
};
const initialTemplateForm: TemplateFormState = { name: "", category: "general", language: "en", subject_template: "", body_template: "" };
const initialLoginForm = { email: "admin@orhun.local", password: "admin123" };
const initialUserForm = { email: "", full_name: "", password: "", role: "operator" as UserRole };
const initialMailboxForm: MailboxFormState = {
  name: "",
  email_address: "",
  imap_host: "",
  imap_port: "993",
  imap_username: "",
  imap_password: "",
  smtp_host: "",
  smtp_port: "465",
  smtp_username: "",
  smtp_password: "",
  smtp_use_tls: true,
  smtp_use_ssl: true,
  enabled: true,
  is_default_outgoing: false,
};

function App() {
  const [authToken, setAuthToken] = useState<string>(() => localStorage.getItem("oma_token") || "");
  const [currentUser, setCurrentUser] = useState<UserItem | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loginForm, setLoginForm] = useState(initialLoginForm);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [userForm, setUserForm] = useState(initialUserForm);
  const [view, setView] = useState<ViewKey>("focus");
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [digest, setDigest] = useState<DigestResponse | null>(null);
  const [catchupDigest, setCatchupDigest] = useState<CatchupDigestResponse | null>(null);
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [sentReviews, setSentReviews] = useState<EmailItem[]>([]);
  const [waitingItems, setWaitingItems] = useState<WaitingItem[]>([]);
  const [spamEmails, setSpamEmails] = useState<EmailItem[]>([]);
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [templates, setTemplates] = useState<MessageTemplate[]>([]);
  const [mailboxes, setMailboxes] = useState<MailboxItem[]>([]);
  const [adminHealth, setAdminHealth] = useState<AdminHealthResponse | null>(null);
  const [adminBackups, setAdminBackups] = useState<BackupItem[]>([]);
  const [backupStatus, setBackupStatus] = useState<BackupStatusResponse | null>(null);
  const [backupIncludeAttachments, setBackupIncludeAttachments] = useState(false);
  const [restoreBackupName, setRestoreBackupName] = useState("");
  const [restoreConfirmation, setRestoreConfirmation] = useState("");
  const [selectedMailboxId, setSelectedMailboxId] = useState<string>("all");
  const [selectedEmailId, setSelectedEmailId] = useState<number | null>(null);
  const [selectedEmail, setSelectedEmail] = useState<EmailItem | null>(null);
  const [thread, setThread] = useState<EmailItem[]>([]);
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [contacts, setContacts] = useState<ContactListResponse | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [preferences, setPreferences] = useState<PreferenceProfile | null>(null);
  const [settingsForm, setSettingsForm] = useState(initialSettingsForm);
  const [templateForm, setTemplateForm] = useState<TemplateFormState>(initialTemplateForm);
  const [mailboxForm, setMailboxForm] = useState<MailboxFormState>(initialMailboxForm);
  const [draftText, setDraftText] = useState("");
  const [replyLanguage, setReplyLanguage] = useState<"ru" | "en" | "tr">("ru");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");
  const [search, setSearch] = useState("");
  const [queueFilter, setQueueFilter] = useState("needs-reply");
  const [reportType, setReportType] = useState("activity");
  const [reportDateFrom, setReportDateFrom] = useState("");
  const [reportDateTo, setReportDateTo] = useState("");
  const [reportData, setReportData] = useState<ReportResponse | null>(null);
  const [reportMailTo, setReportMailTo] = useState("");
  const [reportLoading, setReportLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [saveSettingsLoading, setSaveSettingsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  async function bootstrapAuth() {
    setAuthLoading(true);
    try {
      if (!authToken) {
        setCurrentUser(null);
        return;
      }
      const me = await apiGet<AuthMeResponse>("/api/auth/me");
      setCurrentUser(me.user);
    } catch {
      localStorage.removeItem("oma_token");
      setAuthToken("");
      setCurrentUser(null);
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleLogin(event: React.FormEvent) {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");
    setActionLoading("auth-login");
    try {
      const response = await apiPost<AuthLoginResponse>("/api/auth/login", loginForm);
      localStorage.setItem("oma_token", response.access_token);
      setAuthToken(response.access_token);
      setCurrentUser(response.user);
      setSuccessMessage("Logged in.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Login failed."));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleLogout() {
    setActionLoading("auth-logout");
    try {
      await apiPost("/api/auth/logout", {});
    } catch {
      // best effort logout
    } finally {
      localStorage.removeItem("oma_token");
      setAuthToken("");
      setCurrentUser(null);
      setActionLoading(null);
    }
  }

  useEffect(() => { void bootstrapAuth(); }, [authToken]);
  useEffect(() => { if (currentUser) void loadInitialData(); }, [currentUser]);
  useEffect(() => {
    if (selectedEmailId == null) { setSelectedEmail(null); setThread([]); setDraftText(""); setAttachments([]); return; }
    void loadEmailDetail(selectedEmailId);
  }, [selectedEmailId]);
  useEffect(() => {
    if (!loading) {
      void refreshMailbox(null);
    }
  }, [selectedMailboxId]);
  useEffect(() => {
    if (view === "reports" && currentUser) {
      void handleLoadReport();
    }
  }, [view, reportType, reportDateFrom, reportDateTo, selectedMailboxId, currentUser]);

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

  const mailboxQuery = selectedMailboxId !== "all" ? `&mailbox_id=${encodeURIComponent(selectedMailboxId)}` : "";
  const canRunScan = currentUser?.role !== "viewer";
  const canRunSentReview = currentUser?.role === "admin" || currentUser?.role === "manager";
  const canSendReportEmail = currentUser?.role !== "viewer";

  async function loadInitialData() {
    setLoading(true); setErrorMessage("");
    try {
      const [statsData, digestData, catchupData, emailData, sentReviewData, followupData, spamData, contactData, settingsData, preferenceData, rulesData, templatesData, mailboxData, usersData] = await Promise.all([
        apiGet<StatsResponse>("/api/stats"),
        apiGet<DigestResponse>("/api/digest"),
        apiGet<CatchupDigestResponse>("/api/digest/catchup").catch(() => null),
        apiGet<EmailItem[]>(`/api/emails?limit=60${mailboxQuery}`),
        apiGet<EmailItem[]>(`/api/sent/reviews?limit=30${mailboxQuery}`).catch(() => []),
        apiGet<WaitingItem[]>("/api/followups").catch(() => []),
        apiGet<EmailItem[]>(`/api/spam?limit=40${mailboxQuery}`).catch(() => []),
        apiGet<ContactListResponse>("/api/contacts?limit=20"),
        apiGet<SettingsResponse>("/api/settings"),
        apiGet<PreferenceProfile>("/api/preferences").catch(() => ({ version: 1, summary_lines: [], draft_preferences: {}, decision_preferences: {} })),
        apiGet<AutomationRule[]>("/api/rules").catch(() => []),
        apiGet<MessageTemplate[]>("/api/templates").catch(() => []),
        apiGet<MailboxItem[]>("/api/mailboxes").catch(() => []),
        apiGet<UserItem[]>("/api/users").catch(() => []),
      ]);
      setStats(statsData);
      setDigest(digestData);
      setCatchupDigest(catchupData);
      setEmails(emailData);
      setSentReviews(sentReviewData);
      setWaitingItems(followupData);
      setSpamEmails(spamData);
      setContacts(contactData);
      setSettings(settingsData);
      hydrateSettingsForm(settingsData);
      setPreferences(preferenceData);
      setRules(rulesData);
      setTemplates(templatesData.filter((item) => item.enabled));
      setMailboxes(mailboxData);
      setUsers(usersData);
      if (currentUser?.role === "admin") {
        await loadAdminData();
      } else {
        setAdminHealth(null);
        setAdminBackups([]);
        setBackupStatus(null);
      }
      if (selectedMailboxId === "all" && mailboxData.length === 1) {
        setSelectedMailboxId(mailboxData[0].id);
      }
      const candidate = emailData.find((item) => item.focus_flag && !item.is_spam) || emailData.find((item) => item.requires_reply && !item.is_spam) || emailData[0] || spamData[0] || null;
      setSelectedEmailId(candidate?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not load dashboard data."));
    } finally { setLoading(false); }
  }

  async function loadAdminData() {
    try {
      const [healthData, backupsData, backupStatusData] = await Promise.all([
        apiGet<AdminHealthResponse>("/api/admin/diagnostics").catch(() => null),
        apiGet<BackupItem[]>("/api/admin/backups").catch(() => []),
        apiGet<BackupStatusResponse>("/api/admin/backups/status").catch(() => null),
      ]);
      setAdminHealth(healthData);
      setAdminBackups(backupsData);
      setBackupStatus(backupStatusData);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not load admin diagnostics."));
    }
  }

  async function loadEmailDetail(emailId: number) {
    setDetailLoading(true); setErrorMessage("");
    try {
      const [detail, threadData, attachmentData] = await Promise.all([
        apiGet<EmailItem>(`/api/emails/${emailId}`),
        apiGet<ThreadResponse>(`/api/emails/${emailId}/thread`).catch(() => ({ thread_id: `email-${emailId}`, emails: [] })),
        apiGet<AttachmentItem[]>(`/api/emails/${emailId}/attachments`).catch(() => []),
      ]);
      setSelectedEmail(detail);
      setThread(threadData.emails?.length ? threadData.emails : [detail]);
      setAttachments(attachmentData);
      setDraftText(detail.ai_draft_reply || "");
      setReplyLanguage((detail.preferred_reply_language || detail.detected_source_language || "ru") as "ru" | "en" | "tr");
      setSelectedTemplateId("");
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

  async function handleReplyLanguageChange(language: "ru" | "en" | "tr") {
    if (!selectedEmail) return;
    setReplyLanguage(language);
    setActionLoading(`reply-language-${language}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/set-reply-language`, { language });
      setSuccessMessage(`Reply language set to ${language.toUpperCase()}.`);
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not update reply language."));
    } finally { setActionLoading(null); }
  }

  async function handleGenerateDraft() {
    if (!selectedEmail) return;
    setActionLoading("generate-draft"); setErrorMessage(""); setSuccessMessage("");
    try {
      const result = await apiPost<{ draft_reply: string; subject?: string | null; target_language: "ru" | "en" | "tr" }>(`/api/emails/${selectedEmail.id}/generate-draft`, {
        target_language: replyLanguage,
        template_id: selectedTemplateId || undefined,
      });
      setDraftText(result.draft_reply);
      setReplyLanguage(result.target_language);
      setSuccessMessage("Draft generated.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not generate draft."));
    } finally { setActionLoading(null); }
  }

  async function handleRewriteDraft(instruction: string, targetLanguage?: "ru" | "en" | "tr") {
    if (!selectedEmail || !draftText.trim()) return;
    setActionLoading(`rewrite-${instruction}`); setErrorMessage(""); setSuccessMessage("");
    try {
      const result = await apiPost<{ draft_reply: string; subject?: string | null; target_language: "ru" | "en" | "tr" }>(`/api/emails/${selectedEmail.id}/rewrite-draft`, {
        current_draft: draftText,
        instruction,
        target_language: targetLanguage || replyLanguage,
      });
      setDraftText(result.draft_reply);
      setReplyLanguage(result.target_language);
      setSuccessMessage("Draft updated.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not rewrite the draft."));
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

  async function handleAssignEmail(userId: number) {
    if (!selectedEmail) return;
    setActionLoading(`assign-${userId}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/assign`, { user_id: userId });
      setSuccessMessage("Email assigned.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not assign email."));
    } finally { setActionLoading(null); }
  }

  async function handleUnassignEmail() {
    if (!selectedEmail) return;
    setActionLoading("unassign"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${selectedEmail.id}/unassign`, {});
      setSuccessMessage("Email unassigned.");
      await refreshMailbox(selectedEmail.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not unassign email."));
    } finally { setActionLoading(null); }
  }

  async function handleCreateUser(event: React.FormEvent) {
    event.preventDefault();
    setActionLoading("user-create"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost<UserItem>("/api/users", userForm);
      setUserForm(initialUserForm);
      setSuccessMessage("User created.");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not create user."));
    } finally { setActionLoading(null); }
  }

  async function handleDisableUser(userId: number) {
    setActionLoading(`user-disable-${userId}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost<UserItem>(`/api/users/${userId}/disable`, {});
      setSuccessMessage("User disabled.");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not disable user."));
    } finally { setActionLoading(null); }
  }

  async function handleRefreshAdminDiagnostics() {
    if (currentUser?.role !== "admin") return;
    setActionLoading("admin-refresh");
    setErrorMessage("");
    try {
      await loadAdminData();
      setSuccessMessage("Admin diagnostics refreshed.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not refresh admin diagnostics."));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleCreateBackup() {
    if (currentUser?.role !== "admin") return;
    setActionLoading("backup-create");
    setErrorMessage("");
    try {
      await apiPost("/api/admin/backups/create", { include_attachments: backupIncludeAttachments, keep_last: 10 });
      await loadAdminData();
      setSuccessMessage("Backup created.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Backup creation failed."));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRestoreBackup() {
    if (currentUser?.role !== "admin") return;
    if (!restoreBackupName.trim()) {
      setErrorMessage("Select a backup to restore.");
      return;
    }
    setActionLoading("backup-restore");
    setErrorMessage("");
    try {
      await apiPost("/api/admin/backups/restore", {
        backup_name: restoreBackupName.trim(),
        confirmation: restoreConfirmation.trim(),
        restore_attachments: false,
      });
      setSuccessMessage("Restore completed. Reload the page to refresh data.");
      setRestoreConfirmation("");
      await loadAdminData();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Restore failed."));
    } finally {
      setActionLoading(null);
    }
  }

  function buildReportQuery() {
    const query = new URLSearchParams();
    if (reportDateFrom) query.set("date_from", reportDateFrom);
    if (reportDateTo) query.set("date_to", reportDateTo);
    if (selectedMailboxId !== "all") query.set("mailbox_id", selectedMailboxId);
    return query.toString() ? `?${query.toString()}` : "";
  }

  function reportEndpoint() {
    if (reportType === "followups") return "/api/reports/followups";
    if (reportType === "sent-review") return "/api/reports/sent-review";
    if (reportType === "team-activity") return "/api/reports/team-activity";
    return "/api/reports/activity";
  }

  async function handleLoadReport() {
    setReportLoading(true);
    setErrorMessage("");
    try {
      const payload = await apiGet<ReportResponse>(`${reportEndpoint()}${buildReportQuery()}`);
      setReportData(payload);
      setSuccessMessage("Report loaded.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not load report."));
    } finally {
      setReportLoading(false);
    }
  }

  async function handleExportReport(format: "csv" | "pdf") {
    setActionLoading(`report-export-${format}`);
    setErrorMessage("");
    try {
      if (!["activity", "followups"].includes(reportType)) {
        throw new Error("Export is currently available for activity and follow-ups reports.");
      }
      const exportBase = reportType === "followups" ? "/api/reports/followups/export" : "/api/reports/activity/export";
      await apiDownload(`${exportBase}?format=${format}${buildReportQuery().replace("?", "&")}`, `${reportType}-report.${format}`);
      setSuccessMessage(`Report exported as ${format.toUpperCase()}.`);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Export failed."));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleSendReport() {
    if (!canSendReportEmail) {
      setErrorMessage("Viewer role cannot send reports by email.");
      return;
    }
    if (!reportMailTo.trim()) {
      setErrorMessage("Provide recipient email.");
      return;
    }
    setActionLoading("report-send");
    setErrorMessage("");
    try {
      await apiPost("/api/reports/send", {
        report_type: reportType,
        to: [reportMailTo.trim()],
        date_from: reportDateFrom || null,
        date_to: reportDateTo || null,
        mailbox_id: selectedMailboxId !== "all" ? selectedMailboxId : null,
      });
      setSuccessMessage("Report emailed.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not send report email."));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleManualScan() {
    if (!canRunScan) {
      setErrorMessage("Viewer role cannot trigger manual scan.");
      return;
    }
    setScanLoading(true); setErrorMessage(""); setSuccessMessage("");
    try {
      const result = await apiPost<ScanResponse>("/api/scan", {});
      setSuccessMessage(`Check completed: ${result.imported_count} imported, ${result.analyzed_count} analyzed.`);
      await loadInitialData();
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not trigger scan."));
    } finally { setScanLoading(false); }
  }

  async function handleMarkDigestSeen() {
    setActionLoading("digest-seen"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost("/api/digest/mark-seen", {});
      setSuccessMessage("Catch-up marked as seen.");
      const refreshed = await apiGet<CatchupDigestResponse>("/api/digest/catchup").catch(() => null);
      setCatchupDigest(refreshed);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not mark digest as seen."));
    } finally { setActionLoading(null); }
  }

  async function handleRunSentReview() {
    if (!canRunSentReview) {
      setErrorMessage("This action requires manager or admin role.");
      return;
    }
    setActionLoading("sent-review-run"); setErrorMessage(""); setSuccessMessage("");
    try {
      const result = await apiPost<SentReviewRunResponse>("/api/sent/review/run", {});
      setSuccessMessage(`Sent review completed: ${result.reviewed_count}/${result.selected_count} reviewed.`);
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not run sent review."));
    } finally { setActionLoading(null); }
  }

  async function handleDismissSentReview(emailId: number) {
    setActionLoading(`sent-review-dismiss-${emailId}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${emailId}/sent-review/dismiss`, {});
      setSuccessMessage("Sent review dismissed.");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not dismiss sent review."));
    } finally { setActionLoading(null); }
  }

  async function handleHelpfulSentReview(emailId: number) {
    setActionLoading(`sent-review-helpful-${emailId}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost(`/api/emails/${emailId}/sent-review/helpful`, {});
      setSuccessMessage("Sent review feedback saved.");
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not save sent review feedback."));
    } finally { setActionLoading(null); }
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
        catchup_absence_hours: Number(settingsForm.catchup_absence_hours),
        sent_review_batch_limit: Number(settingsForm.sent_review_batch_limit),
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

  async function handleTemplateCreate(event: React.FormEvent) {
    event.preventDefault();
    setActionLoading("template-create"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost<MessageTemplate>("/api/templates", templateForm);
      setTemplateForm(initialTemplateForm);
      setSuccessMessage("Template created.");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not create template."));
    } finally { setActionLoading(null); }
  }

  async function handleTemplateToggle(template: MessageTemplate) {
    setActionLoading(`template-toggle-${template.id}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPut<MessageTemplate>(`/api/templates/${template.id}`, { enabled: !template.enabled });
      setSuccessMessage(`Template ${template.enabled ? "disabled" : "enabled"}.`);
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not update template."));
    } finally { setActionLoading(null); }
  }

  async function handleTemplateDelete(templateId: string) {
    setActionLoading(`template-delete-${templateId}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiDelete(`/api/templates/${templateId}`);
      setSuccessMessage("Template deleted.");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not delete template."));
    } finally { setActionLoading(null); }
  }

  async function handleMailboxCreate(event: React.FormEvent) {
    event.preventDefault();
    setActionLoading("mailbox-create"); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPost<MailboxItem>("/api/mailboxes", {
        ...mailboxForm,
        imap_port: Number(mailboxForm.imap_port),
        smtp_port: Number(mailboxForm.smtp_port),
      });
      setMailboxForm(initialMailboxForm);
      setSuccessMessage("Mailbox added.");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not add mailbox."));
    } finally { setActionLoading(null); }
  }

  async function handleMailboxToggle(mailbox: MailboxItem) {
    setActionLoading(`mailbox-toggle-${mailbox.id}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPut<MailboxItem>(`/api/mailboxes/${mailbox.id}`, { enabled: !mailbox.enabled });
      setSuccessMessage(`Mailbox ${mailbox.enabled ? "disabled" : "enabled"}.`);
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not update mailbox."));
    } finally { setActionLoading(null); }
  }

  async function handleMailboxSetDefault(mailbox: MailboxItem) {
    setActionLoading(`mailbox-default-${mailbox.id}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiPut<MailboxItem>(`/api/mailboxes/${mailbox.id}`, { is_default_outgoing: true });
      setSuccessMessage("Default outgoing mailbox updated.");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not set default mailbox."));
    } finally { setActionLoading(null); }
  }

  async function handleMailboxDelete(mailboxId: string) {
    setActionLoading(`mailbox-delete-${mailboxId}`); setErrorMessage(""); setSuccessMessage("");
    try {
      await apiDelete(`/api/mailboxes/${mailboxId}`);
      setSuccessMessage("Mailbox deleted.");
      if (selectedMailboxId === mailboxId) setSelectedMailboxId("all");
      await refreshMailbox(selectedEmail?.id ?? null);
    } catch (error) {
      setErrorMessage(getErrorMessage(error, "Could not delete mailbox."));
    } finally { setActionLoading(null); }
  }

  async function refreshMailbox(preserveEmailId?: number | null) {
    const mailboxQuery = selectedMailboxId !== "all" ? `&mailbox_id=${encodeURIComponent(selectedMailboxId)}` : "";
    const [statsData, digestData, catchupData, emailData, sentReviewData, followupData, spamData, rulesData, templatesData, mailboxData, usersData] = await Promise.all([
      apiGet<StatsResponse>("/api/stats"),
      apiGet<DigestResponse>("/api/digest"),
      apiGet<CatchupDigestResponse>("/api/digest/catchup").catch(() => null),
      apiGet<EmailItem[]>(`/api/emails?limit=60${mailboxQuery}`),
      apiGet<EmailItem[]>(`/api/sent/reviews?limit=30${mailboxQuery}`).catch(() => []),
      apiGet<WaitingItem[]>("/api/followups").catch(() => []),
      apiGet<EmailItem[]>(`/api/spam?limit=40${mailboxQuery}`).catch(() => []),
      apiGet<AutomationRule[]>("/api/rules").catch(() => []),
      apiGet<MessageTemplate[]>("/api/templates").catch(() => []),
      apiGet<MailboxItem[]>("/api/mailboxes").catch(() => []),
      apiGet<UserItem[]>("/api/users").catch(() => []),
    ]);
    setStats(statsData);
    setDigest(digestData);
    setCatchupDigest(catchupData);
    setEmails(emailData);
    setSentReviews(sentReviewData);
    setWaitingItems(followupData);
    setSpamEmails(spamData);
    setRules(rulesData);
    setTemplates(templatesData);
    setMailboxes(mailboxData);
    setUsers(usersData);
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
      openai_api_key: "", scan_interval_minutes: String(data.scan_interval_minutes), followup_overdue_days: String(data.followup_overdue_days), catchup_absence_hours: String(data.catchup_absence_hours), sent_review_batch_limit: String(data.sent_review_batch_limit), cors_origins: data.cors_origins.join(", ")
    });
  }

  if (authLoading) {
    return (
      <div className="app-shell">
        <main className="content-shell">
          <div className="panel">
            <div className="loading-state">Checking authentication...</div>
          </div>
        </main>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className="app-shell">
        <main className="content-shell">
          <section className="panel" style={{ maxWidth: 480, margin: "48px auto" }}>
            <div className="panel-header">
              <div>
                <h3 className="panel-title">Team login</h3>
                <p className="panel-subtitle">Sign in to access Orhun Mail Agent workspace.</p>
              </div>
            </div>
            <div className="panel-body">
              <form onSubmit={(event) => void handleLogin(event)}>
                <div className="settings-grid">
                  <Field label="Email" full>
                    <input
                      value={loginForm.email}
                      onChange={(event) => setLoginForm((current) => ({ ...current, email: event.target.value }))}
                      autoComplete="username"
                    />
                  </Field>
                  <Field label="Password" full>
                    <input
                      type="password"
                      value={loginForm.password}
                      onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
                      autoComplete="current-password"
                    />
                  </Field>
                </div>
                <div className="detail-toolbar full" style={{ marginTop: 16 }}>
                  <button className="primary-button" type="submit" disabled={actionLoading === "auth-login"}>
                    {actionLoading === "auth-login" ? "Signing in..." : "Sign in"}
                  </button>
                </div>
              </form>
            </div>
          </section>
        </main>
      </div>
    );
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
            <NavButton label="Reports" active={view === "reports"} onClick={() => setView("reports")} />
            <NavButton label="Settings" active={view === "settings"} badge={rules.length} onClick={() => setView("settings")} />
          </div>
        </div>
        <div className="sidebar-actions">
          <div className="sidebar-card">
            <h3 style={{ margin: 0 }}>Check now</h3>
            <p>Run inbox scan and AI analysis on demand.</p>
            <div style={{ marginTop: 14 }}>
              <button className="primary-button" onClick={() => void handleManualScan()} disabled={scanLoading || !canRunScan}>{scanLoading ? "Checking..." : "Scan now"}</button>
            </div>
            {!canRunScan ? <div className="tiny" style={{ marginTop: 8 }}>Viewer role can monitor data but cannot trigger scans.</div> : null}
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
            <select value={selectedMailboxId} onChange={(event) => setSelectedMailboxId(event.target.value)}>
              <option value="all">All mailboxes</option>
              {mailboxes.map((mailbox) => <option key={mailbox.id} value={mailbox.id}>{mailbox.name}</option>)}
            </select>
            <span className="badge">{currentUser.full_name} ({currentUser.role})</span>
            {contacts?.items?.length ? <span className="badge">{contacts.items.length} key contacts loaded</span> : null}
            {selectedEmail?.focus_flag ? <span className="badge">focus</span> : null}
            {selectedEmail?.priority ? <span className={`badge priority-${normalizePriority(selectedEmail.priority)}`}>{selectedEmail.priority}</span> : null}
            <button className="ghost-button" onClick={() => void handleLogout()} disabled={actionLoading === "auth-logout"}>
              {actionLoading === "auth-logout" ? "Signing out..." : "Logout"}
            </button>
          </div>
        </header>

        {errorMessage ? <div className="error-banner">{errorMessage}</div> : null}
        {successMessage ? <div className="success-banner">{successMessage}</div> : null}

        {loading ? <div className="panel"><div className="loading-state">Loading dashboard...</div></div> : (
          view === "settings" ? (
            <div className="column">
              <SettingsPanel settings={settings} preferences={preferences} rules={rules} templates={templates} mailboxes={mailboxes} users={users} currentUser={currentUser} userForm={userForm} onUserFormChange={setUserForm} onCreateUser={(event) => void handleCreateUser(event)} onDisableUser={(userId) => void handleDisableUser(userId)} form={settingsForm} mailboxForm={mailboxForm} templateForm={templateForm} onChange={setSettingsForm} onMailboxFormChange={setMailboxForm} onTemplateFormChange={setTemplateForm} onSubmit={(event) => void handleSettingsSave(event)} onMailboxSubmit={(event) => void handleMailboxCreate(event)} onTemplateSubmit={(event) => void handleTemplateCreate(event)} saveSettingsLoading={saveSettingsLoading} onToggleRule={(rule) => void handleRuleToggle(rule)} onDeleteRule={(ruleId) => void handleRuleDelete(ruleId)} onToggleTemplate={(template) => void handleTemplateToggle(template)} onDeleteTemplate={(templateId) => void handleTemplateDelete(templateId)} onToggleMailbox={(mailbox) => void handleMailboxToggle(mailbox)} onDeleteMailbox={(mailboxId) => void handleMailboxDelete(mailboxId)} onSetDefaultMailbox={(mailbox) => void handleMailboxSetDefault(mailbox)} adminHealth={adminHealth} adminBackups={adminBackups} backupStatus={backupStatus} backupIncludeAttachments={backupIncludeAttachments} restoreBackupName={restoreBackupName} restoreConfirmation={restoreConfirmation} onBackupIncludeAttachmentsChange={setBackupIncludeAttachments} onRestoreBackupNameChange={setRestoreBackupName} onRestoreConfirmationChange={setRestoreConfirmation} onRefreshAdminDiagnostics={() => void handleRefreshAdminDiagnostics()} onCreateBackup={() => void handleCreateBackup()} onRestoreBackup={() => void handleRestoreBackup()} actionLoading={actionLoading} />
              {currentUser?.role === "admin" ? <AdminOpsPanel adminHealth={adminHealth} adminBackups={adminBackups} backupStatus={backupStatus} backupIncludeAttachments={backupIncludeAttachments} restoreBackupName={restoreBackupName} restoreConfirmation={restoreConfirmation} onBackupIncludeAttachmentsChange={setBackupIncludeAttachments} onRestoreBackupNameChange={setRestoreBackupName} onRestoreConfirmationChange={setRestoreConfirmation} onRefreshAdminDiagnostics={() => void handleRefreshAdminDiagnostics()} onCreateBackup={() => void handleCreateBackup()} onRestoreBackup={() => void handleRestoreBackup()} actionLoading={actionLoading} /> : null}
            </div>
          ) : view === "reports" ? (
            <ReportsPanel reportType={reportType} reportDateFrom={reportDateFrom} reportDateTo={reportDateTo} reportMailTo={reportMailTo} reportData={reportData} reportLoading={reportLoading} actionLoading={actionLoading} currentUser={currentUser} canSendEmail={canSendReportEmail} onReportTypeChange={setReportType} onDateFromChange={setReportDateFrom} onDateToChange={setReportDateTo} onMailToChange={setReportMailTo} onLoad={() => void handleLoadReport()} onExport={(format) => void handleExportReport(format)} onSend={() => void handleSendReport()} />
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
                    <CatchupPanel digest={catchupDigest} actionLoading={actionLoading} onMarkSeen={() => void handleMarkDigestSeen()} onOpenEmail={(id) => setSelectedEmailId(id)} />
                    <SentReviewPanel items={sentReviews} actionLoading={actionLoading} canRunBatch={canRunSentReview} onOpenEmail={(id) => setSelectedEmailId(id)} onRunBatch={() => void handleRunSentReview()} onDismiss={(id) => void handleDismissSentReview(id)} onMarkHelpful={(id) => void handleHelpfulSentReview(id)} />
                  </div>
                  <div className="layout-grid">
                    <QueuePanel items={activeEmails} search={search} queueFilter={queueFilter} selectedEmailId={selectedEmailId} onQueueFilterChange={setQueueFilter} onSearchChange={setSearch} onSelectEmail={setSelectedEmailId} title="Needs reply now" subtitle="Action-oriented queue with AI hints, rule-based focus, urgency badges, and waiting signals." />
                    <DetailPanel selectedEmail={selectedEmail} thread={thread} attachments={attachments} users={users} currentUser={currentUser} draftText={draftText} replyLanguage={replyLanguage} selectedTemplateId={selectedTemplateId} templates={templates} onReplyLanguageChange={(language) => void handleReplyLanguageChange(language)} onTemplateChange={setSelectedTemplateId} onDraftChange={setDraftText} onSendReply={() => void handleReplySend()} onGenerateDraft={() => void handleGenerateDraft()} onRewriteDraft={(instruction, targetLanguage) => void handleRewriteDraft(instruction, targetLanguage)} onStatusUpdate={(status) => void handleStatusUpdate(status)} onStartWaiting={() => void handleWaitingStart()} onCloseWaiting={() => void handleWaitingClose()} onGenerateFollowup={() => void handleGenerateFollowup()} onFeedback={(decisionType, verdict, details) => void handleFeedback(decisionType, verdict, details)} onDraftFeedback={(verdict) => void handleDraftFeedback(verdict)} onRestoreSpam={() => void handleSpamRestore()} onConfirmSpam={() => void handleConfirmSpam()} onCreateQuickRule={(template) => void handleQuickRuleCreate(template)} onAssignEmail={(userId) => void handleAssignEmail(userId)} onUnassignEmail={() => void handleUnassignEmail()} loading={detailLoading} actionLoading={actionLoading} />
                  </div>
                </>
              ) : view === "active" ? (
                <>
                  <QueuePanel items={activeEmails} search={search} queueFilter={queueFilter} selectedEmailId={selectedEmailId} onQueueFilterChange={setQueueFilter} onSearchChange={setSearch} onSelectEmail={setSelectedEmailId} title="Active queue" subtitle="Browse live work, then move directly into draft, automation, and action mode." />
                  <DetailPanel selectedEmail={selectedEmail} thread={thread} attachments={attachments} users={users} currentUser={currentUser} draftText={draftText} replyLanguage={replyLanguage} selectedTemplateId={selectedTemplateId} templates={templates} onReplyLanguageChange={(language) => void handleReplyLanguageChange(language)} onTemplateChange={setSelectedTemplateId} onDraftChange={setDraftText} onSendReply={() => void handleReplySend()} onGenerateDraft={() => void handleGenerateDraft()} onRewriteDraft={(instruction, targetLanguage) => void handleRewriteDraft(instruction, targetLanguage)} onStatusUpdate={(status) => void handleStatusUpdate(status)} onStartWaiting={() => void handleWaitingStart()} onCloseWaiting={() => void handleWaitingClose()} onGenerateFollowup={() => void handleGenerateFollowup()} onFeedback={(decisionType, verdict, details) => void handleFeedback(decisionType, verdict, details)} onDraftFeedback={(verdict) => void handleDraftFeedback(verdict)} onRestoreSpam={() => void handleSpamRestore()} onConfirmSpam={() => void handleConfirmSpam()} onCreateQuickRule={(template) => void handleQuickRuleCreate(template)} onAssignEmail={(userId) => void handleAssignEmail(userId)} onUnassignEmail={() => void handleUnassignEmail()} loading={detailLoading} actionLoading={actionLoading} />
                </>
              ) : view === "waiting" ? (
                <>
                  <WaitingPanel items={waitingItems} onSelectEmail={setSelectedEmailId} />
                  <DetailPanel selectedEmail={selectedEmail} thread={thread} attachments={attachments} users={users} currentUser={currentUser} draftText={draftText} replyLanguage={replyLanguage} selectedTemplateId={selectedTemplateId} templates={templates} onReplyLanguageChange={(language) => void handleReplyLanguageChange(language)} onTemplateChange={setSelectedTemplateId} onDraftChange={setDraftText} onSendReply={() => void handleReplySend()} onGenerateDraft={() => void handleGenerateDraft()} onRewriteDraft={(instruction, targetLanguage) => void handleRewriteDraft(instruction, targetLanguage)} onStatusUpdate={(status) => void handleStatusUpdate(status)} onStartWaiting={() => void handleWaitingStart()} onCloseWaiting={() => void handleWaitingClose()} onGenerateFollowup={() => void handleGenerateFollowup()} onFeedback={(decisionType, verdict, details) => void handleFeedback(decisionType, verdict, details)} onDraftFeedback={(verdict) => void handleDraftFeedback(verdict)} onRestoreSpam={() => void handleSpamRestore()} onConfirmSpam={() => void handleConfirmSpam()} onCreateQuickRule={(template) => void handleQuickRuleCreate(template)} onAssignEmail={(userId) => void handleAssignEmail(userId)} onUnassignEmail={() => void handleUnassignEmail()} loading={detailLoading} actionLoading={actionLoading} />
                </>
              ) : (
                <>
                  <SpamPanel items={spamEmails} onSelectEmail={setSelectedEmailId} />
                  <DetailPanel selectedEmail={selectedEmail} thread={thread} attachments={attachments} users={users} currentUser={currentUser} draftText={draftText} replyLanguage={replyLanguage} selectedTemplateId={selectedTemplateId} templates={templates} onReplyLanguageChange={(language) => void handleReplyLanguageChange(language)} onTemplateChange={setSelectedTemplateId} onDraftChange={setDraftText} onSendReply={() => void handleReplySend()} onGenerateDraft={() => void handleGenerateDraft()} onRewriteDraft={(instruction, targetLanguage) => void handleRewriteDraft(instruction, targetLanguage)} onStatusUpdate={(status) => void handleStatusUpdate(status)} onStartWaiting={() => void handleWaitingStart()} onCloseWaiting={() => void handleWaitingClose()} onGenerateFollowup={() => void handleGenerateFollowup()} onFeedback={(decisionType, verdict, details) => void handleFeedback(decisionType, verdict, details)} onDraftFeedback={(verdict) => void handleDraftFeedback(verdict)} onRestoreSpam={() => void handleSpamRestore()} onConfirmSpam={() => void handleConfirmSpam()} onCreateQuickRule={(template) => void handleQuickRuleCreate(template)} onAssignEmail={(userId) => void handleAssignEmail(userId)} onUnassignEmail={() => void handleUnassignEmail()} loading={detailLoading} actionLoading={actionLoading} allowSpamReview />
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
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">{props.title}</h3><p className="panel-subtitle">{props.subtitle}</p></div></div><div className="panel-body"><div className="queue-toolbar"><input value={props.search} onChange={(event) => props.onSearchChange(event.target.value)} placeholder="Search sender, subject, summary, attachment name" /><select value={props.queueFilter} onChange={(event) => props.onQueueFilterChange(event.target.value)}><option value="needs-reply">Needs reply</option><option value="focus">Focus senders</option><option value="waiting">Waiting</option><option value="all">All active</option></select></div><div className="queue-list">{props.items.length === 0 ? <div className="empty-state"><strong>Queue is clear</strong><p>No active items match the current filter.</p></div> : props.items.map((item) => <button key={item.id} className={`queue-item ${item.id === props.selectedEmailId ? "active" : ""}`} onClick={() => props.onSelectEmail(item.id)}><div className="queue-meta"><span className={`badge priority-${normalizePriority(item.priority)}`}>{item.priority || "medium"}</span><span className={`badge status-${item.status}`}>{item.status}</span>{item.category ? <span className="badge">{item.category}</span> : null}{item.mailbox_name || item.mailbox_address ? <span className="badge">{item.mailbox_name || item.mailbox_address}</span> : null}{item.assigned_to_user_id ? <span className="badge">owner #{item.assigned_to_user_id}</span> : null}{item.has_attachments ? <span className="badge">attachments {item.attachment_count || 0}</span> : null}{item.focus_flag ? <span className="badge">focus</span> : null}{item.waiting_state ? <span className={`badge ${item.waiting_state}`}>{item.waiting_state}</span> : null}</div><div className="queue-main"><div><h4>{item.sender_name || item.sender_email || "Unknown sender"}</h4><p>{item.subject || "No subject"}</p><p>{item.ai_summary || item.body_text?.slice(0, 120) || "No preview available."}</p></div><div className="queue-time">{item.wait_days != null ? `${item.wait_days}d wait` : formatDate(item.date_received)}</div></div></button>)}</div></div></section>;
}

function WaitingPanel(props: { items: WaitingItem[]; onSelectEmail: (id: number) => void }) {
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Waiting queue</h3><p className="panel-subtitle">Tracked conversations waiting for the other side. Overdue items should be followed up first.</p></div></div><div className="panel-body"><div className="log-list">{props.items.length === 0 ? <div className="empty-state"><strong>No waiting threads</strong><p>Threads marked as waiting for reply will appear here.</p></div> : props.items.map((item) => <div key={item.task_id} className="log-item"><div className="queue-main"><div><h4>{item.latest_sender_name || item.latest_sender_email || "Unknown sender"}</h4><p>{item.latest_subject || item.title}</p><p>{item.latest_ai_summary || item.subtitle || "No AI summary available."}</p></div><div className="queue-time">{item.wait_days}d wait</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className={`badge ${item.state}`}>{item.state}</span>{item.expected_reply_by ? <span className="badge">Due {formatDate(item.expected_reply_by)}</span> : null}{item.latest_email_id ? <button className="secondary-button" onClick={() => props.onSelectEmail(item.latest_email_id!)}>Open thread</button> : null}</div></div>)}</div></div></section>;
}

function DetailPanel(props: { selectedEmail: EmailItem | null; thread: EmailItem[]; attachments: AttachmentItem[]; users: UserItem[]; currentUser: UserItem | null; draftText: string; replyLanguage: "ru" | "en" | "tr"; selectedTemplateId: string; templates: MessageTemplate[]; onReplyLanguageChange: (language: "ru" | "en" | "tr") => void; onTemplateChange: (templateId: string) => void; onDraftChange: (value: string) => void; onSendReply: () => void; onGenerateDraft: () => void; onRewriteDraft: (instruction: string, targetLanguage?: "ru" | "en" | "tr") => void; onStatusUpdate: (status: string) => void; onStartWaiting: () => void; onCloseWaiting: () => void; onGenerateFollowup: () => void; onFeedback: (decisionType: string, verdict: string, details?: Record<string, unknown>) => void; onDraftFeedback: (verdict: "useful" | "bad") => void; onRestoreSpam: () => void; onConfirmSpam: () => void; onCreateQuickRule: (template: QuickRuleTemplate) => void; onAssignEmail: (userId: number) => void; onUnassignEmail: () => void; loading: boolean; actionLoading: string | null; allowSpamReview?: boolean }) {
  const appliedRules = parseAppliedRules(props.selectedEmail?.applied_rules_json);
  const availableTemplates = props.templates.filter((item) => item.enabled && item.language === props.replyLanguage);
  const role = props.currentUser?.role || "viewer";
  const canSend = ["admin", "manager", "operator"].includes(role);
  const canAssign = ["admin", "manager"].includes(role);
  const canManageRules = ["admin", "manager"].includes(role);
  const canSpamReview = ["admin", "manager", "operator"].includes(role);
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Thread detail</h3><p className="panel-subtitle">Review message context, AI summary, draft, language, templates, rules, and follow-up state before acting.</p></div></div><div className="panel-body">{props.loading ? <div className="loading-state">Loading detail...</div> : !props.selectedEmail ? <div className="empty-state"><strong>Select an item</strong><p>Pick a thread from the queue to review the draft workflow.</p></div> : <div className="detail-panel"><div className="detail-head"><div className="detail-title"><h3>{props.selectedEmail.subject || "No subject"}</h3><div className="detail-meta"><span className={`badge priority-${normalizePriority(props.selectedEmail.priority)}`}>{props.selectedEmail.priority || "medium"}</span><span className={`badge status-${props.selectedEmail.status}`}>{props.selectedEmail.status}</span>{props.selectedEmail.category ? <span className="badge">{props.selectedEmail.category}</span> : null}<span className="badge">{props.selectedEmail.sender_name || props.selectedEmail.sender_email || "Unknown sender"}</span>{props.selectedEmail.mailbox_name || props.selectedEmail.mailbox_address ? <span className="badge">{props.selectedEmail.mailbox_name || props.selectedEmail.mailbox_address}</span> : null}{props.selectedEmail.has_attachments ? <span className="badge">attachments {props.selectedEmail.attachment_count || props.attachments.length}</span> : null}{props.selectedEmail.focus_flag ? <span className="badge">focus</span> : null}{props.selectedEmail.detected_source_language ? <span className="badge">in {props.selectedEmail.detected_source_language.toUpperCase()}</span> : null}{props.selectedEmail.waiting_state ? <span className={`badge ${props.selectedEmail.waiting_state}`}>{props.selectedEmail.waiting_state}</span> : null}</div></div><div className="tiny">{props.selectedEmail.wait_days != null ? `Waiting ${props.selectedEmail.wait_days} days` : formatDate(props.selectedEmail.date_received)}</div></div><div className="detail-section"><h4>Assignment</h4><div className="queue-meta">{props.selectedEmail.assigned_to_user_id ? <span className="badge">Assigned to #{props.selectedEmail.assigned_to_user_id}</span> : <span className="badge">Unassigned</span>}{props.selectedEmail.assigned_at ? <span className="badge">{formatDate(props.selectedEmail.assigned_at)}</span> : null}</div>{canAssign ? <div className="detail-toolbar" style={{ marginTop: 10 }}><select defaultValue="" onChange={(event) => { const value = Number(event.target.value); if (value) props.onAssignEmail(value); }}><option value="">Assign to user</option>{props.users.filter((user) => user.is_active).map((user) => <option key={user.id} value={user.id}>{user.full_name} ({user.role})</option>)}</select><button className="ghost-button" onClick={props.onUnassignEmail} disabled={Boolean(props.actionLoading)}>Unassign</button></div> : null}</div><div className="assistant-grid"><div className="detail-section"><h4>AI summary</h4><div className="detail-copy"><p>{props.selectedEmail.ai_summary || "Analysis is not available for this item yet."}</p></div><div className="detail-toolbar full"><button className="secondary-button" onClick={() => props.onFeedback("summary", "useful")} disabled={!canSend}>Summary helpful</button><button className="ghost-button" onClick={() => props.onFeedback("summary", "bad")} disabled={!canSend}>Summary off</button></div></div><div className="detail-section"><h4>Suggested next step</h4><div className="detail-copy"><p>{props.selectedEmail.action_description || (props.selectedEmail.requires_reply ? "Reply expected. Review and send draft." : props.selectedEmail.waiting_state ? "Conversation is being tracked while waiting for the other side." : "No immediate action suggested.")}</p>{props.selectedEmail.spam_source || props.selectedEmail.spam_reason ? <p><strong>Spam source:</strong> {props.selectedEmail.spam_source || "unknown"} {props.selectedEmail.spam_reason ? `- ${props.selectedEmail.spam_reason}` : ""}</p> : null}</div><div className="detail-toolbar full"><button className="secondary-button" onClick={() => props.onFeedback("priority", "mark_important", { new_priority: "high" })} disabled={!canSend}>Mark important</button><button className="ghost-button" onClick={() => props.onFeedback("priority", "mark_not_important", { new_priority: "low" })} disabled={!canSend}>Not important</button></div></div></div><div className="detail-section"><h4>Thread</h4><div className="detail-thread">{(props.thread.length ? props.thread : [props.selectedEmail]).map((item) => <div key={item.id} className="thread-item"><div className="thread-meta"><span className="badge">{item.sender_name || item.sender_email || "Unknown sender"}</span><span className="badge">{formatDate(item.date_received)}</span>{item.mailbox_name || item.mailbox_address ? <span className="badge">{item.mailbox_name || item.mailbox_address}</span> : null}</div><h4>{item.subject || "No subject"}</h4><p>{item.body_text || item.ai_summary || "No body text available."}</p></div>)}</div></div><div className="detail-section"><h4>Attachments</h4>{props.attachments.length === 0 ? <div className="tiny">No attachments for this email.</div> : <div className="log-list">{props.attachments.map((attachment) => <div key={attachment.id} className="log-item"><div className="queue-main"><div><h4>{attachment.filename || `attachment-${attachment.id}`}</h4><p>{attachment.content_type || "application/octet-stream"}</p></div><div className="queue-time">{Math.max(1, Math.round(attachment.size_bytes / 1024))} KB</div></div><div className="queue-meta" style={{ marginTop: 10 }}><a className="secondary-button" href={`/api/emails/attachments/${attachment.id}/download`} target="_blank" rel="noreferrer">Download</a>{attachment.is_inline ? <span className="badge">inline</span> : null}</div></div>)}</div>}</div><div className="detail-section"><h4>Automation trace</h4>{appliedRules.length === 0 ? <div className="tiny">No explicit user rule matched this email yet.</div> : <div className="queue-meta">{appliedRules.map((rule) => <span key={rule.id} className="badge">{rule.name}</span>)}</div>}{canManageRules ? <div className="detail-toolbar" style={{ marginTop: 12 }}><button className="secondary-button" onClick={() => props.onCreateQuickRule("always-high")} disabled={Boolean(props.actionLoading)}>Always high</button><button className="secondary-button" onClick={() => props.onCreateQuickRule("always-focus")} disabled={Boolean(props.actionLoading)}>Always focus</button><button className="secondary-button" onClick={() => props.onCreateQuickRule("always-archive")} disabled={Boolean(props.actionLoading)}>Always archive</button><button className="danger-button" onClick={() => props.onCreateQuickRule("always-spam")} disabled={Boolean(props.actionLoading)}>Always spam</button><button className="ghost-button" onClick={() => props.onCreateQuickRule("never-spam")} disabled={Boolean(props.actionLoading)}>Never spam</button></div> : <div className="tiny">Rule management is available for admin and manager roles.</div>}</div><div className="detail-section"><div className="split-note"><div><h4>{props.selectedEmail.waiting_state ? "Follow-up / reply draft" : "Draft reply"}</h4><div className="tiny">Detected: {(props.selectedEmail.detected_source_language || "ru").toUpperCase()} | Reply: {props.replyLanguage.toUpperCase()}</div></div><span className="badge">{props.draftText.length} chars</span></div><div className="queue-toolbar" style={{ marginBottom: 12 }}><select value={props.replyLanguage} onChange={(event) => props.onReplyLanguageChange(event.target.value as "ru" | "en" | "tr")} disabled={!canSend}><option value="ru">Russian</option><option value="en">English</option><option value="tr">Turkish</option></select><select value={props.selectedTemplateId} onChange={(event) => props.onTemplateChange(event.target.value)} disabled={!canSend}><option value="">No template</option>{availableTemplates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select></div><div className="detail-toolbar" style={{ marginBottom: 12 }}><button className="secondary-button" onClick={props.onGenerateDraft} disabled={Boolean(props.actionLoading) || !canSend}>{props.actionLoading === "generate-draft" ? "Generating..." : "Generate draft"}</button><button className="secondary-button" onClick={() => props.onRewriteDraft("shorter")} disabled={Boolean(props.actionLoading) || !canSend}>Shorter</button><button className="secondary-button" onClick={() => props.onRewriteDraft("more formal")} disabled={Boolean(props.actionLoading) || !canSend}>More formal</button><button className="secondary-button" onClick={() => props.onRewriteDraft("softer")} disabled={Boolean(props.actionLoading) || !canSend}>Softer</button><button className="secondary-button" onClick={() => props.onRewriteDraft("stronger deadline emphasis")} disabled={Boolean(props.actionLoading) || !canSend}>Deadline emphasis</button></div><div className="detail-toolbar" style={{ marginBottom: 12 }}><button className="ghost-button" onClick={() => props.onRewriteDraft("translate to Russian", "ru")} disabled={Boolean(props.actionLoading) || !canSend}>Translate to RU</button><button className="ghost-button" onClick={() => props.onRewriteDraft("translate to English", "en")} disabled={Boolean(props.actionLoading) || !canSend}>Translate to EN</button><button className="ghost-button" onClick={() => props.onRewriteDraft("translate to Turkish", "tr")} disabled={Boolean(props.actionLoading) || !canSend}>Translate to TR</button></div><textarea rows={10} value={props.draftText} onChange={(event) => props.onDraftChange(event.target.value)} placeholder="Draft reply..." readOnly={!canSend} /><div className="detail-toolbar full"><button className="secondary-button" onClick={() => props.onDraftFeedback("useful")} disabled={!canSend}>Draft helpful</button><button className="ghost-button" onClick={() => props.onDraftFeedback("bad")} disabled={!canSend}>Draft needs work</button></div></div><div className="detail-toolbar"><button className="primary-button" onClick={props.onSendReply} disabled={props.actionLoading === "reply" || !canSend}>{props.actionLoading === "reply" ? "Sending..." : "Send draft"}</button><button className="secondary-button" onClick={props.onGenerateFollowup} disabled={Boolean(props.actionLoading) || !canSend}>{props.actionLoading === "followup-draft" ? "Generating..." : "Generate follow-up"}</button><button className="secondary-button" onClick={props.selectedEmail.waiting_state ? props.onCloseWaiting : props.onStartWaiting} disabled={Boolean(props.actionLoading) || !canSend}>{props.selectedEmail.waiting_state ? "Close waiting" : "Waiting for reply"}</button><button className="secondary-button" onClick={() => props.onStatusUpdate("replied")} disabled={Boolean(props.actionLoading) || !canSend}>I will reply myself</button><button className="secondary-button" onClick={() => props.onStatusUpdate("archived")} disabled={Boolean(props.actionLoading) || !canSend}>Archive</button>{props.allowSpamReview ? <button className="secondary-button" onClick={props.onRestoreSpam} disabled={Boolean(props.actionLoading) || !canSpamReview}>{props.actionLoading === "spam-restore" ? "Restoring..." : "Restore to active"}</button> : <button className="danger-button" onClick={() => props.onStatusUpdate("spam")} disabled={Boolean(props.actionLoading) || !canSpamReview}>Mark spam</button>}{props.allowSpamReview ? <button className="danger-button" onClick={props.onConfirmSpam} disabled={Boolean(props.actionLoading) || !canSpamReview}>{props.actionLoading === "spam-confirm" ? "Confirming..." : "Confirm spam"}</button> : <button className="ghost-button" onClick={() => props.onStatusUpdate("read")} disabled={Boolean(props.actionLoading) || !canSend}>Later / snooze</button>}</div>{!canSend ? <div className="tiny" style={{ marginTop: 10 }}>Viewer role is read-only. Ask a manager/admin to assign or action this thread.</div> : null}</div>}</div></section>;
}

function SpamPanel(props: { items: EmailItem[]; onSelectEmail: (id: number) => void }) {
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Spam log</h3><p className="panel-subtitle">Review suspicious items, inspect AI or rule source, and restore anything that should return to the queue.</p></div></div><div className="panel-body"><div className="log-list">{props.items.length === 0 ? <div className="empty-state"><strong>No spam logged</strong><p>Spam-classified items will appear here.</p></div> : props.items.map((item) => <div key={item.id} className="log-item"><div className="queue-main"><div><h4>{item.sender_name || item.sender_email || "Unknown sender"}</h4><p>{item.subject || "No subject"}</p><p>{item.spam_reason || "No spam reason recorded."}</p></div><div className="queue-time">{formatDate(item.spam_action_at || item.date_received)}</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className="badge priority-spam">{item.spam_source || "spam"}</span>{item.spam_action_actor ? <span className="badge">{item.spam_action_actor}</span> : null}<button className="secondary-button" onClick={() => props.onSelectEmail(item.id)}>Review</button></div></div>)}</div></div></section>;
}

function CatchupPanel(props: { digest: CatchupDigestResponse | null; actionLoading: string | null; onMarkSeen: () => void; onOpenEmail: (id: number) => void }) {
  const shouldShow = Boolean(props.digest?.should_show);
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Catch-up mode</h3><p className="panel-subtitle">Quick operational view after inactivity.</p></div></div><div className="panel-body">{!props.digest ? <div className="empty-state"><strong>Catch-up unavailable</strong><p>Digest service is not available right now.</p></div> : <><div className="settings-note">{shouldShow ? `You were away for ${props.digest.away_hours}h. Review these items first.` : `No long inactivity detected (${props.digest.away_hours}h away).`}</div><div className="queue-meta" style={{ margin: "10px 0" }}>{props.digest.top_actions.map((item, index) => <span key={`${index}-${item}`} className="badge">{item}</span>)}</div><div className="log-list">{props.digest.important_new.slice(0, 3).map((item) => <div key={`imp-${item.email_id || item.thread_id}`} className="log-item"><div className="queue-main"><div><h4>{item.sender_name || item.sender_email || "Unknown sender"}</h4><p>{item.subject || "No subject"}</p></div><div className="queue-time">{formatDate(item.date_received)}</div></div><div className="queue-meta" style={{ marginTop: 10 }}>{item.email_id ? <button className="secondary-button" onClick={() => props.onOpenEmail(item.email_id!)}>Open</button> : null}</div></div>)}</div><div className="detail-toolbar full" style={{ marginTop: 12 }}><button className="secondary-button" onClick={props.onMarkSeen} disabled={Boolean(props.actionLoading)}>{props.actionLoading === "digest-seen" ? "Saving..." : "Mark catch-up seen"}</button></div></>}</div></section>;
}

function SentReviewPanel(props: { items: EmailItem[]; actionLoading: string | null; canRunBatch: boolean; onOpenEmail: (id: number) => void; onRunBatch: () => void; onDismiss: (id: number) => void; onMarkHelpful: (id: number) => void }) {
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Sent quality review</h3><p className="panel-subtitle">Post-send quality checks for tone, completeness, and action clarity.</p></div><button className="secondary-button" onClick={props.onRunBatch} disabled={Boolean(props.actionLoading) || !props.canRunBatch}>{props.actionLoading === "sent-review-run" ? "Reviewing..." : "Run review"}</button></div><div className="panel-body">{!props.canRunBatch ? <div className="tiny" style={{ marginBottom: 10 }}>Only manager/admin can start batch sent-review runs.</div> : null}<div className="log-list">{props.items.length === 0 ? <div className="empty-state"><strong>No sent reviews yet</strong><p>Send a reply and run review to see outgoing quality notes.</p></div> : props.items.slice(0, 8).map((item) => <div key={`sent-${item.id}`} className="log-item"><div className="queue-main"><div><h4>{item.subject || "No subject"}</h4><p>{item.sent_review_summary || "Pending review."}</p><p>{item.sent_review_suggested_improvement || ""}</p></div><div className="queue-time">{formatDate(item.sent_reviewed_at || item.date_received)}</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className={`badge ${item.sent_review_status === "good" ? "status-replied" : item.sent_review_status === "problematic" ? "priority-spam" : "status-new"}`}>{item.sent_review_status || "pending"}</span>{item.sent_review_score != null ? <span className="badge">{Math.round(item.sent_review_score)}</span> : null}<button className="secondary-button" onClick={() => props.onOpenEmail(item.id)}>Open</button><button className="ghost-button" onClick={() => props.onMarkHelpful(item.id)} disabled={Boolean(props.actionLoading)}>Helpful</button><button className="ghost-button" onClick={() => props.onDismiss(item.id)} disabled={Boolean(props.actionLoading)}>Dismiss</button></div></div>)}</div></div></section>;
}

function AdminOpsPanel(props: { adminHealth: AdminHealthResponse | null; adminBackups: BackupItem[]; backupStatus: BackupStatusResponse | null; backupIncludeAttachments: boolean; restoreBackupName: string; restoreConfirmation: string; onBackupIncludeAttachmentsChange: (value: boolean) => void; onRestoreBackupNameChange: (value: string) => void; onRestoreConfirmationChange: (value: string) => void; onRefreshAdminDiagnostics: () => void; onCreateBackup: () => void; onRestoreBackup: () => void; actionLoading: string | null }) {
  const backupPreviewText = props.restoreBackupName ? `RESTORE ${props.restoreBackupName}` : "RESTORE backup_name";
  const components = props.adminHealth?.components || {};
  const imapScan = (components["imap_scan"] as Record<string, unknown> | undefined) || {};
  const aiAnalyzer = (components["ai_analyzer"] as Record<string, unknown> | undefined) || {};
  const scheduler = (components["scheduler"] as Record<string, unknown> | undefined) || {};
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Admin diagnostics & recovery</h3><p className="panel-subtitle">Operational health, backup creation, and controlled restore for production safety.</p></div><div className="queue-meta"><button className="secondary-button" onClick={props.onRefreshAdminDiagnostics} disabled={props.actionLoading === "admin-refresh"}>{props.actionLoading === "admin-refresh" ? "Refreshing..." : "Refresh diagnostics"}</button></div></div><div className="panel-body"><div className="stats-grid"><StatCard label="Overall status" value={props.adminHealth?.overall_status === "ok" ? 1 : 0} /><StatCard label="Backups" value={props.backupStatus?.backups_count || 0} /><StatCard label="Scheduler running" value={scheduler["running"] ? 1 : 0} /><StatCard label="Known mailboxes" value={props.adminHealth?.mailboxes?.length || 0} /></div><div className="log-list" style={{ marginTop: 16 }}><div className="log-item"><div className="queue-main"><div><h4>Scheduler</h4><p>Last job success: {String(scheduler["last_job_success_at"] || "n/a")}</p><p>Last job failure: {String(scheduler["last_job_failure_at"] || "n/a")}</p></div><div className="queue-time">{scheduler["running"] ? "running" : "stopped"}</div></div></div><div className="log-item"><div className="queue-main"><div><h4>IMAP scan</h4><p>Last success: {String(imapScan["last_success_at"] || "n/a")}</p><p>Last failure: {String(imapScan["last_failure_at"] || "n/a")}</p></div><div className="queue-time">{imapScan["ok"] ? "ok" : "degraded"}</div></div></div><div className="log-item"><div className="queue-main"><div><h4>AI analyzer</h4><p>Last success: {String(aiAnalyzer["last_success_at"] || "n/a")}</p><p>Last failure: {String(aiAnalyzer["last_failure_at"] || "n/a")}</p></div><div className="queue-time">{aiAnalyzer["ok"] ? "ok" : "degraded"}</div></div></div></div><div className="detail-section" style={{ marginTop: 18 }}><h4>Create backup</h4><div className="queue-meta"><label className="tiny"><input type="checkbox" checked={props.backupIncludeAttachments} onChange={(event) => props.onBackupIncludeAttachmentsChange(event.target.checked)} /> Include attachments folder</label><button className="primary-button" onClick={props.onCreateBackup} disabled={props.actionLoading === "backup-create"}>{props.actionLoading === "backup-create" ? "Creating..." : "Create backup"}</button></div><div className="tiny" style={{ marginTop: 8 }}>Latest backup: {props.backupStatus?.latest_backup?.backup_name || "none"} ({props.backupStatus?.latest_backup?.created_at || "n/a"})</div></div><div className="detail-section" style={{ marginTop: 18 }}><h4>Restore backup</h4><div className="settings-grid"><Field label="Backup"><select value={props.restoreBackupName} onChange={(event) => props.onRestoreBackupNameChange(event.target.value)}><option value="">Select backup</option>{props.adminBackups.map((item) => <option key={item.backup_name} value={item.backup_name}>{item.backup_name}</option>)}</select></Field><Field label="Confirmation text"><input value={props.restoreConfirmation} onChange={(event) => props.onRestoreConfirmationChange(event.target.value)} placeholder={backupPreviewText} /></Field></div><div className="detail-toolbar full" style={{ marginTop: 12 }}><button className="danger-button" onClick={props.onRestoreBackup} disabled={props.actionLoading === "backup-restore"}>{props.actionLoading === "backup-restore" ? "Restoring..." : "Restore selected backup"}</button></div><div className="tiny" style={{ marginTop: 8 }}>Restore requires exact confirmation text: <strong>{backupPreviewText}</strong></div></div><div className="detail-section" style={{ marginTop: 18 }}><h4>Mailbox status</h4><div className="log-list">{(props.adminHealth?.mailboxes || []).length === 0 ? <div className="empty-state"><strong>No mailbox diagnostics yet</strong><p>Refresh diagnostics to populate mailbox health status.</p></div> : (props.adminHealth?.mailboxes || []).map((mailbox) => <div key={mailbox.mailbox_id} className="log-item"><div className="queue-main"><div><h4>{mailbox.mailbox_name}</h4><p>{mailbox.email_address}</p><p>Last success: {mailbox.last_success_at || "n/a"} | Last failure: {mailbox.last_failure_at || "n/a"}</p></div><div className="queue-time">{mailbox.enabled ? "enabled" : "disabled"}</div></div><div className="queue-meta" style={{ marginTop: 10 }}>{mailbox.last_error ? <span className="badge priority-spam">error</span> : <span className="badge status-new">ok</span>}{mailbox.last_error ? <span className="tiny">{mailbox.last_error}</span> : null}</div></div>)}</div></div></div></section>;
}

function ReportsPanel(props: { reportType: string; reportDateFrom: string; reportDateTo: string; reportMailTo: string; reportData: ReportResponse | null; reportLoading: boolean; actionLoading: string | null; currentUser: UserItem | null; canSendEmail: boolean; onReportTypeChange: (value: string) => void; onDateFromChange: (value: string) => void; onDateToChange: (value: string) => void; onMailToChange: (value: string) => void; onLoad: () => void; onExport: (format: "csv" | "pdf") => void; onSend: () => void }) {
  const canTeamReport = props.currentUser?.role === "admin" || props.currentUser?.role === "manager";
  const summaryEntries = Object.entries(props.reportData?.summary || {});
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Operational reports</h3><p className="panel-subtitle">Select period, preview metrics, export CSV/PDF, and optionally email report snapshots.</p></div></div><div className="panel-body"><div className="queue-toolbar"><select value={props.reportType} onChange={(event) => props.onReportTypeChange(event.target.value)}><option value="activity">Activity</option><option value="followups">Follow-ups</option><option value="sent-review">Sent review</option>{canTeamReport ? <option value="team-activity">Team activity</option> : null}</select><input type="date" value={props.reportDateFrom} onChange={(event) => props.onDateFromChange(event.target.value)} /><input type="date" value={props.reportDateTo} onChange={(event) => props.onDateToChange(event.target.value)} /><button className="secondary-button" onClick={props.onLoad} disabled={props.reportLoading}>{props.reportLoading ? "Loading..." : "Load report"}</button></div><div className="detail-toolbar" style={{ marginTop: 12 }}><button className="secondary-button" onClick={() => props.onExport("csv")} disabled={Boolean(props.actionLoading)}>Export CSV</button><button className="secondary-button" onClick={() => props.onExport("pdf")} disabled={Boolean(props.actionLoading)}>Export PDF</button><input value={props.reportMailTo} onChange={(event) => props.onMailToChange(event.target.value)} placeholder="report recipient email" disabled={!props.canSendEmail} /><button className="primary-button" onClick={props.onSend} disabled={props.actionLoading === "report-send" || !props.canSendEmail}>{props.actionLoading === "report-send" ? "Sending..." : "Email report"}</button></div>{!props.canSendEmail ? <div className="tiny" style={{ marginTop: 8 }}>Viewer role can view/export reports but cannot email them.</div> : null}<div className="detail-section" style={{ marginTop: 16 }}><h4>Summary</h4>{summaryEntries.length === 0 ? <div className="tiny">No summary yet. Load a report first.</div> : <div className="log-list">{summaryEntries.map(([key, value]) => <div key={key} className="log-item"><div className="queue-main"><div><h4>{key}</h4><p>{String(value)}</p></div></div></div>)}</div>}</div><div className="detail-section" style={{ marginTop: 16 }}><h4>Rows preview</h4><div className="log-list">{!(props.reportData?.rows?.length) ? <div className="empty-state"><strong>No rows for selected filters</strong><p>Try changing report type or date range.</p></div> : props.reportData!.rows.slice(0, 25).map((row, idx) => <div key={`${props.reportData?.report_type}-${idx}`} className="log-item"><div className="queue-main"><div><h4>{String(row["subject"] || row["thread_id"] || row["user_email"] || `row-${idx + 1}`)}</h4><p>{Object.entries(row).slice(0, 5).map(([k, v]) => `${k}: ${String(v)}`).join(" | ")}</p></div></div></div>)}</div></div></div></section>;
}

function SettingsPanel(props: { settings: SettingsResponse | null; preferences: PreferenceProfile | null; rules: AutomationRule[]; templates: MessageTemplate[]; mailboxes: MailboxItem[]; users: UserItem[]; currentUser: UserItem | null; userForm: typeof initialUserForm; onUserFormChange: React.Dispatch<React.SetStateAction<typeof initialUserForm>>; onCreateUser: (event: React.FormEvent) => void; onDisableUser: (userId: number) => void; form: typeof initialSettingsForm; mailboxForm: MailboxFormState; templateForm: TemplateFormState; onChange: React.Dispatch<React.SetStateAction<typeof initialSettingsForm>>; onMailboxFormChange: React.Dispatch<React.SetStateAction<MailboxFormState>>; onTemplateFormChange: React.Dispatch<React.SetStateAction<TemplateFormState>>; onSubmit: (event: React.FormEvent) => void; onMailboxSubmit: (event: React.FormEvent) => void; onTemplateSubmit: (event: React.FormEvent) => void; saveSettingsLoading: boolean; onToggleRule: (rule: AutomationRule) => void; onDeleteRule: (ruleId: string) => void; onToggleTemplate: (template: MessageTemplate) => void; onDeleteTemplate: (templateId: string) => void; onToggleMailbox: (mailbox: MailboxItem) => void; onDeleteMailbox: (mailboxId: string) => void; onSetDefaultMailbox: (mailbox: MailboxItem) => void; adminHealth: AdminHealthResponse | null; adminBackups: BackupItem[]; backupStatus: BackupStatusResponse | null; backupIncludeAttachments: boolean; restoreBackupName: string; restoreConfirmation: string; onBackupIncludeAttachmentsChange: (value: boolean) => void; onRestoreBackupNameChange: (value: string) => void; onRestoreConfirmationChange: (value: string) => void; onRefreshAdminDiagnostics: () => void; onCreateBackup: () => void; onRestoreBackup: () => void; actionLoading: string | null }) {
  const canManageSettings = props.currentUser?.role === "admin";
  const canManageRules = props.currentUser?.role === "admin" || props.currentUser?.role === "manager";
  const canManageMailboxes = props.currentUser?.role === "admin";
  return <section className="panel"><div className="panel-header"><div><h3 className="panel-title">Connection settings</h3><p className="panel-subtitle">Edit safe operational settings, learned preferences, active automation rules, and multilingual templates.</p></div></div><div className="panel-body"><form onSubmit={props.onSubmit}><div className="settings-grid"><Field label="App name"><input value={props.form.app_name} onChange={(event) => props.onChange((current) => ({ ...current, app_name: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="Environment"><select value={props.form.app_env} onChange={(event) => props.onChange((current) => ({ ...current, app_env: event.target.value }))} disabled={!canManageSettings}><option value="development">development</option><option value="production">production</option></select></Field><Field label="IMAP host"><input value={props.form.imap_host} onChange={(event) => props.onChange((current) => ({ ...current, imap_host: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="IMAP port"><input value={props.form.imap_port} onChange={(event) => props.onChange((current) => ({ ...current, imap_port: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="IMAP user"><input value={props.form.imap_user} onChange={(event) => props.onChange((current) => ({ ...current, imap_user: event.target.value }))} disabled={!canManageSettings} /></Field><Field label={`IMAP password ${props.settings?.has_imap_password ? "(stored)" : ""}`}><input type="password" value={props.form.imap_password} onChange={(event) => props.onChange((current) => ({ ...current, imap_password: event.target.value }))} placeholder="Leave blank to keep current" disabled={!canManageSettings} /></Field><Field label="SMTP host"><input value={props.form.smtp_host} onChange={(event) => props.onChange((current) => ({ ...current, smtp_host: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="SMTP port"><input value={props.form.smtp_port} onChange={(event) => props.onChange((current) => ({ ...current, smtp_port: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="SMTP user"><input value={props.form.smtp_user} onChange={(event) => props.onChange((current) => ({ ...current, smtp_user: event.target.value }))} disabled={!canManageSettings} /></Field><Field label={`SMTP password ${props.settings?.has_smtp_password ? "(stored)" : ""}`}><input type="password" value={props.form.smtp_password} onChange={(event) => props.onChange((current) => ({ ...current, smtp_password: event.target.value }))} placeholder="Leave blank to keep current" disabled={!canManageSettings} /></Field><Field label="DeepSeek base URL"><input value={props.form.deepseek_base_url} onChange={(event) => props.onChange((current) => ({ ...current, deepseek_base_url: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="DeepSeek model"><input value={props.form.deepseek_model} onChange={(event) => props.onChange((current) => ({ ...current, deepseek_model: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="Follow-up overdue days"><input value={props.form.followup_overdue_days} onChange={(event) => props.onChange((current) => ({ ...current, followup_overdue_days: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="Catch-up threshold (hours)"><input value={props.form.catchup_absence_hours} onChange={(event) => props.onChange((current) => ({ ...current, catchup_absence_hours: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="Sent review batch size"><input value={props.form.sent_review_batch_limit} onChange={(event) => props.onChange((current) => ({ ...current, sent_review_batch_limit: event.target.value }))} disabled={!canManageSettings} /></Field><Field label={`AI API key ${props.settings?.has_openai_api_key ? "(stored)" : ""}`}><input type="password" value={props.form.openai_api_key} onChange={(event) => props.onChange((current) => ({ ...current, openai_api_key: event.target.value }))} placeholder="Leave blank to keep current" disabled={!canManageSettings} /></Field><Field label="Scan interval (minutes)"><input value={props.form.scan_interval_minutes} onChange={(event) => props.onChange((current) => ({ ...current, scan_interval_minutes: event.target.value }))} disabled={!canManageSettings} /></Field><Field label="CORS origins" full><input value={props.form.cors_origins} onChange={(event) => props.onChange((current) => ({ ...current, cors_origins: event.target.value }))} placeholder="http://localhost:3000, http://localhost:5173" disabled={!canManageSettings} /></Field></div><div className="settings-note" style={{ marginTop: 16 }}>Follow-up overdue days controls when waiting threads automatically move into the overdue queue.</div><div className="settings-note" style={{ marginTop: 16 }}><strong>Learned preferences</strong><div className="tiny" style={{ marginTop: 8 }}>{props.preferences?.summary_lines?.length ? props.preferences.summary_lines.join(" ") : "No learned preference summary yet. Use feedback controls and send edited drafts to build it."}</div></div><div className="detail-toolbar full" style={{ marginTop: 18 }}><button className="primary-button" type="submit" disabled={props.saveSettingsLoading || !canManageSettings}>{props.saveSettingsLoading ? "Saving..." : "Save settings"}</button></div>{!canManageSettings ? <div className="tiny" style={{ marginTop: 8 }}>Only admin can update platform settings.</div> : null}</form>{props.currentUser?.role === "admin" ? <div className="detail-section" style={{ marginTop: 18 }}><h4>Team users</h4><form onSubmit={props.onCreateUser}><div className="settings-grid"><Field label="Email"><input value={props.userForm.email} onChange={(event) => props.onUserFormChange((current) => ({ ...current, email: event.target.value }))} /></Field><Field label="Full name"><input value={props.userForm.full_name} onChange={(event) => props.onUserFormChange((current) => ({ ...current, full_name: event.target.value }))} /></Field><Field label="Password"><input type="password" value={props.userForm.password} onChange={(event) => props.onUserFormChange((current) => ({ ...current, password: event.target.value }))} /></Field><Field label="Role"><select value={props.userForm.role} onChange={(event) => props.onUserFormChange((current) => ({ ...current, role: event.target.value as UserRole }))}><option value="admin">admin</option><option value="manager">manager</option><option value="operator">operator</option><option value="viewer">viewer</option></select></Field></div><div className="detail-toolbar full" style={{ marginTop: 12 }}><button className="secondary-button" type="submit">Create user</button></div></form><div className="log-list" style={{ marginTop: 12 }}>{props.users.map((user) => <div key={user.id} className="log-item"><div className="queue-main"><div><h4>{user.full_name}</h4><p>{user.email} · {user.role}</p></div><div className="queue-time">{user.is_active ? "active" : "disabled"}</div></div><div className="queue-meta" style={{ marginTop: 10 }}>{user.is_active ? <button className="ghost-button" onClick={() => props.onDisableUser(user.id)}>Disable</button> : null}</div></div>)}</div></div> : null}<div className="detail-section" style={{ marginTop: 18 }}><h4>Add mailbox</h4><form onSubmit={props.onMailboxSubmit}><div className="settings-grid"><Field label="Name"><input value={props.mailboxForm.name} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, name: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="Email address"><input value={props.mailboxForm.email_address} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, email_address: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="IMAP host"><input value={props.mailboxForm.imap_host} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, imap_host: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="IMAP port"><input value={props.mailboxForm.imap_port} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, imap_port: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="IMAP username"><input value={props.mailboxForm.imap_username} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, imap_username: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="IMAP password"><input type="password" value={props.mailboxForm.imap_password} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, imap_password: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="SMTP host"><input value={props.mailboxForm.smtp_host} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, smtp_host: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="SMTP port"><input value={props.mailboxForm.smtp_port} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, smtp_port: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="SMTP username"><input value={props.mailboxForm.smtp_username} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, smtp_username: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="SMTP password"><input type="password" value={props.mailboxForm.smtp_password} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, smtp_password: event.target.value }))} disabled={!canManageMailboxes} /></Field><Field label="SMTP TLS"><select value={String(props.mailboxForm.smtp_use_tls)} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, smtp_use_tls: event.target.value === "true" }))} disabled={!canManageMailboxes}><option value="true">enabled</option><option value="false">disabled</option></select></Field><Field label="SMTP SSL"><select value={String(props.mailboxForm.smtp_use_ssl)} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, smtp_use_ssl: event.target.value === "true" }))} disabled={!canManageMailboxes}><option value="true">enabled</option><option value="false">disabled</option></select></Field><Field label="Enabled"><select value={String(props.mailboxForm.enabled)} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, enabled: event.target.value === "true" }))} disabled={!canManageMailboxes}><option value="true">enabled</option><option value="false">disabled</option></select></Field><Field label="Default outgoing"><select value={String(props.mailboxForm.is_default_outgoing)} onChange={(event) => props.onMailboxFormChange((current) => ({ ...current, is_default_outgoing: event.target.value === "true" }))} disabled={!canManageMailboxes}><option value="false">no</option><option value="true">yes</option></select></Field></div><div className="detail-toolbar full" style={{ marginTop: 14 }}><button className="secondary-button" type="submit" disabled={!canManageMailboxes}>Add mailbox</button></div>{!canManageMailboxes ? <div className="tiny" style={{ marginTop: 8 }}>Only admin can manage mailbox connections.</div> : null}</form></div><div className="detail-section" style={{ marginTop: 18 }}><h4>Connected mailboxes</h4><div className="log-list">{props.mailboxes.length === 0 ? <div className="empty-state"><strong>No mailbox connected</strong><p>Add one mailbox to start scanning and sending from account context.</p></div> : props.mailboxes.map((mailbox) => <div key={mailbox.id} className="log-item"><div className="queue-main"><div><h4>{mailbox.name}</h4><p>{mailbox.email_address}</p><p>IMAP {mailbox.imap_host}:{mailbox.imap_port} · SMTP {mailbox.smtp_host}:{mailbox.smtp_port}</p></div><div className="queue-time">{mailbox.is_default_outgoing ? "default" : "secondary"}</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className={`badge ${mailbox.enabled ? "status-new" : "status-archived"}`}>{mailbox.enabled ? "enabled" : "disabled"}</span>{mailbox.has_imap_password ? <span className="badge">imap secret</span> : null}{mailbox.has_smtp_password ? <span className="badge">smtp secret</span> : null}<button className="secondary-button" onClick={() => props.onToggleMailbox(mailbox)} disabled={!canManageMailboxes}>{mailbox.enabled ? "Disable" : "Enable"}</button><button className="secondary-button" onClick={() => props.onSetDefaultMailbox(mailbox)} disabled={!canManageMailboxes}>Set default</button><button className="ghost-button" onClick={() => props.onDeleteMailbox(mailbox.id)} disabled={!canManageMailboxes}>Delete</button></div></div>)}</div></div><div className="detail-section" style={{ marginTop: 18 }}><h4>Automation rules</h4><div className="log-list">{props.rules.length === 0 ? <div className="empty-state"><strong>No rules yet</strong><p>Create simple sender/domain rules from an email detail view.</p></div> : props.rules.map((rule) => <div key={rule.id} className="log-item"><div className="queue-main"><div><h4>{rule.name}</h4><p>{describeRule(rule)}</p></div><div className="queue-time">order {rule.order}</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className={`badge ${rule.enabled ? "status-new" : "status-archived"}`}>{rule.enabled ? "enabled" : "disabled"}</span><button className="secondary-button" onClick={() => props.onToggleRule(rule)} disabled={!canManageRules}>{rule.enabled ? "Disable" : "Enable"}</button><button className="ghost-button" onClick={() => props.onDeleteRule(rule.id)} disabled={!canManageRules}>Delete</button></div></div>)}</div>{!canManageRules ? <div className="tiny" style={{ marginTop: 8 }}>Rule editing is available for admin and manager roles.</div> : null}</div><div className="detail-section" style={{ marginTop: 18 }}><h4>Create template</h4><form onSubmit={props.onTemplateSubmit}><div className="settings-grid"><Field label="Name"><input value={props.templateForm.name} onChange={(event) => props.onTemplateFormChange((current) => ({ ...current, name: event.target.value }))} disabled={!canManageRules} /></Field><Field label="Category"><input value={props.templateForm.category} onChange={(event) => props.onTemplateFormChange((current) => ({ ...current, category: event.target.value }))} disabled={!canManageRules} /></Field><Field label="Language"><select value={props.templateForm.language} onChange={(event) => props.onTemplateFormChange((current) => ({ ...current, language: event.target.value as "ru" | "en" | "tr" }))} disabled={!canManageRules}><option value="ru">Russian</option><option value="en">English</option><option value="tr">Turkish</option></select></Field><Field label="Subject template"><input value={props.templateForm.subject_template} onChange={(event) => props.onTemplateFormChange((current) => ({ ...current, subject_template: event.target.value }))} disabled={!canManageRules} /></Field><Field label="Body template" full><textarea rows={5} value={props.templateForm.body_template} onChange={(event) => props.onTemplateFormChange((current) => ({ ...current, body_template: event.target.value }))} disabled={!canManageRules} /></Field></div><div className="detail-toolbar full" style={{ marginTop: 14 }}><button className="secondary-button" type="submit" disabled={!canManageRules}>Save template</button></div></form></div><div className="detail-section" style={{ marginTop: 18 }}><h4>Reusable templates</h4><div className="log-list">{props.templates.length === 0 ? <div className="empty-state"><strong>No templates loaded</strong><p>Create one or use the seeded multilingual starter set.</p></div> : props.templates.map((template) => <div key={template.id} className="log-item"><div className="queue-main"><div><h4>{template.name}</h4><p>{template.category} · {template.language.toUpperCase()}</p><p>{template.subject_template || template.body_template.slice(0, 120)}</p></div><div className="queue-time">{template.language.toUpperCase()}</div></div><div className="queue-meta" style={{ marginTop: 10 }}><span className={`badge ${template.enabled ? "status-new" : "status-archived"}`}>{template.enabled ? "enabled" : "disabled"}</span><button className="secondary-button" onClick={() => props.onToggleTemplate(template)} disabled={!canManageRules}>{template.enabled ? "Disable" : "Enable"}</button><button className="ghost-button" onClick={() => props.onDeleteTemplate(template.id)} disabled={!canManageRules}>Delete</button></div></div>)}</div></div></div></section>;
}

function NavButton(props: { label: string; active: boolean; badge?: number; onClick: () => void }) { return <button className={`nav-button ${props.active ? "active" : ""}`} onClick={props.onClick}><span>{props.label}</span>{typeof props.badge === "number" ? <span className="nav-badge">{props.badge}</span> : null}</button>; }
function StatCard(props: { label: string; value: number }) { return <div className="stat-card"><span>{props.label}</span><strong>{props.value}</strong></div>; }
function SummaryPoint(props: { title: string; value: string }) { return <div className="summary-point"><strong>{props.title}</strong><span>{props.value}</span></div>; }
function Field(props: { label: string; children: React.ReactNode; full?: boolean }) { return <div className={`field ${props.full ? "full" : ""}`}><label>{props.label}</label>{props.children}</div>; }

function buildApiHeaders(includeJson: boolean): Record<string, string> {
  const headers: Record<string, string> = {};
  if (includeJson) headers["Content-Type"] = "application/json";
  const token = localStorage.getItem("oma_token");
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function apiGet<T>(url: string): Promise<T> { const response = await fetch(url, { headers: buildApiHeaders(false) }); return parseResponse<T>(response); }
async function apiPost<T = unknown>(url: string, body: unknown): Promise<T> { const response = await fetch(url, { method: "POST", headers: buildApiHeaders(true), body: JSON.stringify(body) }); return parseResponse<T>(response); }
async function apiPut<T = unknown>(url: string, body: unknown): Promise<T> { const response = await fetch(url, { method: "PUT", headers: buildApiHeaders(true), body: JSON.stringify(body) }); return parseResponse<T>(response); }
async function apiDelete<T = unknown>(url: string): Promise<T> { const response = await fetch(url, { method: "DELETE", headers: buildApiHeaders(false) }); return parseResponse<T>(response); }
async function apiDownload(url: string, filename: string): Promise<void> {
  const response = await fetch(url, { headers: buildApiHeaders(false) });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { const data = (await response.json()) as { detail?: string }; if (data?.detail) detail = data.detail; } catch { }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}
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
function getViewTitle(view: ViewKey) { if (view === "focus") return "Focus workspace"; if (view === "active") return "Active queue"; if (view === "waiting") return "Waiting queue"; if (view === "spam") return "Spam review log"; if (view === "reports") return "Reports and exports"; return "System settings"; }
function getViewSubtitle(view: ViewKey, focusSummary: string) { if (view === "focus") return focusSummary; if (view === "active") return "Move from AI analysis to a sent reply without leaving the board."; if (view === "waiting") return "Track outbound conversations, overdue threads, and suggested follow-ups."; if (view === "spam") return "Audit blocked messages, see AI or rule source, and restore mistakes quickly."; if (view === "reports") return "Generate period-based activity and follow-up reports, then export or email them."; return "Manage connection settings, learned preferences, and operational rules."; }

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
