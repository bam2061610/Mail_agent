export type ViewKey = "focus" | "active" | "sent" | "waiting" | "spam" | "reports" | "settings";
export type MailView = "inbox" | "sent" | "spam" | "processed" | "settings";
export type UserRole = "admin" | "manager" | "operator" | "viewer";

export type EmailItem = {
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
  importance_score?: number | null;
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
  body_html?: string | null;
  folder?: string | null;
  thread_id?: string | null;
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
  sent_by_user_id?: number | null;
  sent_review_summary?: string | null;
  sent_review_status?: string | null;
  sent_review_issues_json?: string | null;
  sent_review_score?: number | null;
  sent_review_suggested_improvement?: string | null;
  sent_reviewed_at?: string | null;
};

export type AttachmentItem = {
  id: number;
  email_id: number;
  filename?: string | null;
  content_type?: string | null;
  size_bytes: number;
  is_inline: boolean;
  created_at: string;
};

export type WaitingItem = {
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

export type ThreadResponse = { thread_id: string; emails: EmailItem[] };
export type StatsResponse = { new_count: number; waiting_reply_count: number; analyzed_today_count: number; total_inbox_count: number; spam_count: number; waiting_count: number; overdue_count: number; followup_due_today_count: number };
export type DigestResponse = { date: string; emails_received_today: number; important_emails: number; unanswered_emails: number; analyzed_count: number };
export type CatchupItem = { email_id?: number | null; task_id?: number | null; thread_id?: string | null; subject?: string | null; sender_email?: string | null; sender_name?: string | null; mailbox_name?: string | null; state?: string | null; priority?: string | null; status?: string | null; date_received?: string | null; expected_reply_by?: string | null };
export type CatchupDigestResponse = { generated_at: string; since: string; away_hours: number; should_show: boolean; important_new: CatchupItem[]; waiting_or_overdue: CatchupItem[]; spam_review: CatchupItem[]; recent_sent: CatchupItem[]; followups_due: CatchupItem[]; top_actions: string[] };

export type SettingsResponse = {
  app_name: string;
  app_env: string;
  debug: boolean;
  database_url: string;
  imap_host: string;
  imap_port: number;
  imap_user: string;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  deepseek_base_url: string;
  deepseek_model: string;
  ai_analysis_enabled: boolean;
  interface_language: string;
  summary_language: string;
  scan_since_date: string | null;
  auto_spam_enabled: boolean;
  scheduler_interval_minutes: number;
  followup_overdue_days: number;
  catchup_absence_hours: number;
  sent_review_batch_limit: number;
  max_emails_per_scan: number;
  cors_origins: string[];
  signature?: string | null;
  has_imap_password: boolean;
  has_smtp_password: boolean;
  has_deepseek_api_key: boolean;
  has_openai_api_key: boolean;
};

export interface SetupStatusResponse {
  completed: boolean;
}

export interface SetupAccountFormState {
  email: string;
  full_name: string;
  password: string;
  confirm_password: string;
}

export interface SetupAiFormState {
  deepseek_api_key: string;
  deepseek_model: string;
  deepseek_base_url: string;
}

export interface SetupMailboxFormState {
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
}

export interface SetupCompletePayload {
  admin: SetupAccountFormState;
  ai: SetupAiFormState;
  mailbox: {
    name: string;
    email_address: string;
    imap_host: string;
    imap_port: number;
    imap_username: string;
    imap_password: string;
    smtp_host: string;
    smtp_port: number;
    smtp_username: string;
    smtp_password: string;
    smtp_use_tls: boolean;
    smtp_use_ssl: boolean;
    enabled: boolean;
    is_default_outgoing: boolean;
  };
  scheduler_interval_minutes: number;
  followup_overdue_days: number;
  max_emails_per_scan: number;
  ai_analysis_enabled: boolean;
}

export type ContactListResponse = { items: Array<{ id: number; email: string; name?: string | null; company?: string | null }>; total: number; limit: number; offset: number };
export type ScanResponse = { imported_count: number; analyzed_count: number; errors: string[] };
export type SentReviewRunResponse = { selected_count: number; reviewed_count: number; failed_count: number; errors: string[] };

export type UserItem = {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  timezone?: string | null;
  language?: string | null;
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type AuthLoginResponse = { access_token: string; token_type: "bearer"; user: UserItem };
export type AuthMeResponse = { user: UserItem };
export type ReportResponse = { report_type: string; generated_at: string; filters: Record<string, unknown>; summary: Record<string, unknown>; rows: Array<Record<string, unknown>> };

export type BackupItem = { backup_name: string; created_at?: string | null; include_attachments: boolean; size_bytes: number; path: string; manifest?: Record<string, unknown> };
export type BackupStatusResponse = { backups_count: number; latest_backup?: BackupItem | null; backup_dir: string };

export type AdminMailboxStatus = {
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

export type AdminHealthResponse = {
  overall_status: string;
  server_time: string;
  app_env: string;
  components: Record<string, unknown>;
  mailboxes: AdminMailboxStatus[];
  storage: Record<string, unknown>;
  jobs: Record<string, unknown>;
};

export type PreferenceProfile = { version: number; generated_at?: string | null; summary_lines: string[]; draft_preferences: Record<string, unknown>; decision_preferences: Record<string, unknown> };

export type AutomationRule = {
  id: string;
  name: string;
  enabled: boolean;
  order: number;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type QuickRuleTemplate = "always-high" | "always-archive" | "always-spam" | "never-spam" | "always-focus";

export type MessageTemplate = {
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

export type TemplateFormState = {
  name: string;
  category: string;
  language: "ru" | "en" | "tr";
  subject_template: string;
  body_template: string;
};

export type MailboxItem = {
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

export type MailboxFormState = {
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

export type LoginFormState = { email: string; password: string };
export type UserFormState = { email: string; full_name: string; password: string; role: UserRole };
export type DraftGenerationResponse = {
  draft_reply: string;
  subject?: string | null;
  target_language: string;
  template_id?: string | null;
};

export const initialSettingsForm = {
  app_name: "",
  app_env: "development",
  debug: false,
  imap_host: "",
  imap_port: "993",
  imap_user: "",
  imap_password: "",
  smtp_host: "",
  smtp_port: "465",
  smtp_user: "",
  smtp_password: "",
  smtp_use_tls: true,
  smtp_use_ssl: true,
  deepseek_base_url: "",
  deepseek_model: "",
  openai_api_key: "",
  scan_since_date: "",
  auto_spam_enabled: true,
  scan_interval_minutes: "5",
  followup_overdue_days: "3",
  catchup_absence_hours: "8",
  sent_review_batch_limit: "20",
  cors_origins: "",
};

export const initialTemplateForm: TemplateFormState = {
  name: "",
  category: "general",
  language: "en",
  subject_template: "",
  body_template: "",
};

export const initialLoginForm: LoginFormState = { email: "", password: "" };
export const initialUserForm: UserFormState = { email: "", full_name: "", password: "", role: "operator" };
export const initialSetupAccountForm: SetupAccountFormState = {
  email: "",
  full_name: "",
  password: "",
  confirm_password: "",
};
export const initialSetupAiForm: SetupAiFormState = {
  deepseek_api_key: "",
  deepseek_model: "deepseek-chat",
  deepseek_base_url: "https://api.deepseek.com",
};
export const initialSetupMailboxForm: SetupMailboxFormState = {
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
};

export const initialMailboxForm: MailboxFormState = {
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
