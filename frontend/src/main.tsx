import React, { useCallback, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { useTranslation } from "react-i18next";
import i18n from "./i18n";
import { apiDelete, apiGet, apiPost, apiPut, buildReplyPayload, getErrorMessage, isSetupRequiredError } from "./api";
import { useAuth } from "./hooks/useAuth";
import { LoginScreen } from "./components/LoginScreen";
import { SetupWizard } from "./components/SetupWizard";
import { Sidebar } from "./components/Sidebar";
import { EmailList } from "./components/EmailList";
import { EmailDetail } from "./components/EmailDetail";
import { SettingsPanel } from "./components/SettingsPanel";
import {
  initialMailboxForm,
  type AttachmentItem,
  type DraftGenerationResponse,
  type EmailItem,
  type MailView,
  type MailboxFormState,
  type MailboxItem,
  type SettingsResponse,
  type SetupStatusResponse,
  type ThreadResponse,
} from "./types";
import "./styles.css";

function splitRecipients(value: string): string[] {
  return value
    .split(/[,;\n]/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildReplySubject(subject?: string | null): string {
  if (!subject) return "Re: No subject";
  return subject.toLowerCase().startsWith("re:") ? subject : `Re: ${subject}`;
}

function normalizeReplyLanguage(value?: string | null): "ru" | "en" | "tr" {
  const normalized = (value || "").trim().toLowerCase();
  if (normalized === "en" || normalized === "english") return "en";
  if (normalized === "tr" || normalized === "turkish") return "tr";
  if (normalized === "ru" || normalized === "russian") return "ru";
  return "ru";
}

function normalizeDateInput(value?: string | null): string {
  const raw = (value || "").trim();
  if (!raw) return "";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw.slice(0, 10);
  return parsed.toISOString().slice(0, 10);
}

function buildScanSinceDateIso(value: string): string | null {
  const raw = value.trim();
  if (!raw) return null;
  const parsed = new Date(`${raw}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function filterEmailsForView(view: MailView, emails: EmailItem[]): EmailItem[] {
  if (view !== "inbox") return emails;
  return emails.filter((item) => item.status !== "spam" && item.status !== "archived" && item.status !== "reply_later" && item.status !== "processed");
}

function buildReplyBody(draftText: string, signature: string, originalEmail: EmailItem | null): string {
  const parts = [draftText.trim()];
  if (signature.trim()) parts.push(signature.trim());
  const originalText = originalEmail?.body_text || originalEmail?.body_html || "";
  if (originalText.trim()) {
    parts.push(`--- Original message ---\n${originalText.trim()}`);
  }
  return parts.filter(Boolean).join("\n\n");
}

export function App() {
  const { t } = useTranslation();
  const [setupState, setSetupState] = useState<"loading" | "required" | "ready">("loading");
  const [setupError, setSetupError] = useState("");
  const { authLoading, currentUser, loginForm, setLoginForm, handleLogin, handleLogout, authError, authSuccess, actionLoading } = useAuth(setupState === "ready");
  const [view, setView] = useState<MailView>("inbox");
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [selectedEmailId, setSelectedEmailId] = useState<number | null>(null);
  const [selectedEmail, setSelectedEmail] = useState<EmailItem | null>(null);
  const [thread, setThread] = useState<EmailItem[]>([]);
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [search, setSearch] = useState("");
  const [draftText, setDraftText] = useState("");
  const [replyLanguage, setReplyLanguage] = useState<"ru" | "en" | "tr">("ru");
  const [replyTo, setReplyTo] = useState("");
  const [replyCc, setReplyCc] = useState("");
  const [replyBcc, setReplyBcc] = useState("");
  const [replySubject, setReplySubject] = useState("");
  const [replyPrompt, setReplyPrompt] = useState("");
  const [replySignature, setReplySignature] = useState("");
  const [settingsSignature, setSettingsSignature] = useState("");
  const [summaryLanguage, setSummaryLanguage] = useState<"ru" | "en" | "tr">("ru");
  const [autoSpamEnabled, setAutoSpamEnabled] = useState(true);
  const [followupOverdueDays, setFollowupOverdueDays] = useState("3");
  const [scanSinceDate, setScanSinceDate] = useState("");
  const [savingSignature, setSavingSignature] = useState(false);
  const [mailboxes, setMailboxes] = useState<MailboxItem[]>([]);
  const [mailboxesLoading, setMailboxesLoading] = useState(false);
  const [mailboxSaving, setMailboxSaving] = useState(false);
  const [mailboxActionLoadingId, setMailboxActionLoadingId] = useState<string | null>(null);
  const [editingMailboxId, setEditingMailboxId] = useState<string | null>(null);
  const [mailboxForm, setMailboxForm] = useState<MailboxFormState>(initialMailboxForm);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [mailActionLoading, setMailActionLoading] = useState<string | null>(null);
  const [appError, setAppError] = useState("");
  const [appSuccess, setAppSuccess] = useState("");
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [modalMode, setModalMode] = useState<"read" | "reply" | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<SetupStatusResponse>("/api/setup/status")
      .then((response) => {
        if (cancelled) return;
        setSetupState(response.completed ? "ready" : "required");
        setSetupError("");
      })
      .catch((error) => {
        if (cancelled) return;
        if (isSetupRequiredError(error)) {
          setSetupState("required");
          setSetupError("");
          return;
        }
        setSetupState("loading");
        setSetupError(getErrorMessage(error, "Could not check setup status."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!appError) return;
    const timeout = window.setTimeout(() => setAppError(""), 4200);
    return () => window.clearTimeout(timeout);
  }, [appError]);

  useEffect(() => {
    if (!appSuccess) return;
    const timeout = window.setTimeout(() => setAppSuccess(""), 3200);
    return () => window.clearTimeout(timeout);
  }, [appSuccess]);

  useEffect(() => {
    setMobileSidebarOpen(false);
    setModalMode(null);
    setSelectedEmailId(null);
    setSelectedEmail(null);
    setThread([]);
    setAttachments([]);
    setMailActionLoading(null);
    if (!currentUser) {
      setView("inbox");
      setEmails([]);
      setDraftText("");
      setReplyLanguage("ru");
      setReplyTo("");
      setReplyCc("");
      setReplyBcc("");
      setReplySubject("");
      setReplyPrompt("");
      setReplySignature("");
      setSettingsSignature("");
      setSummaryLanguage("ru");
      setAutoSpamEnabled(true);
      setFollowupOverdueDays("3");
      setScanSinceDate("");
      setMailboxes([]);
      setMailboxesLoading(false);
      setMailboxSaving(false);
      setMailboxActionLoadingId(null);
      setEditingMailboxId(null);
      setMailboxForm(initialMailboxForm);
      setSavingSignature(false);
      setModalMode(null);
    }
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser) return;
    apiGet<SettingsResponse>("/api/settings")
      .then((settings) => {
        const interfaceLanguage = normalizeReplyLanguage(settings.interface_language || settings.summary_language || "ru");
        void i18n.changeLanguage(interfaceLanguage);
        setSettingsSignature((settings.signature || "").trim());
        setSummaryLanguage(normalizeReplyLanguage(settings.summary_language || settings.interface_language || "ru"));
        setAutoSpamEnabled(settings.auto_spam_enabled ?? true);
        setFollowupOverdueDays(String(settings.followup_overdue_days ?? 3));
        setScanSinceDate(normalizeDateInput(settings.scan_since_date));
      })
      .catch(() => {
        setSettingsSignature("");
        setSummaryLanguage("ru");
        setAutoSpamEnabled(true);
        setFollowupOverdueDays("3");
        setScanSinceDate("");
      });
  }, [currentUser]);

  const resetMailboxEditor = useCallback(() => {
    setEditingMailboxId(null);
    setMailboxForm(initialMailboxForm);
  }, []);

  const loadMailboxes = useCallback(async () => {
    if (!currentUser) return;
    setMailboxesLoading(true);
    try {
      const items = await apiGet<MailboxItem[]>("/api/mailboxes");
      setMailboxes(items);
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not load mailboxes."));
    } finally {
      setMailboxesLoading(false);
    }
  }, [currentUser]);

  useEffect(() => {
    if (modalMode === "reply" && settingsSignature && !replySignature.trim()) {
      setReplySignature(settingsSignature);
    }
  }, [modalMode, replySignature, settingsSignature]);

  useEffect(() => {
    if (!currentUser || view !== "settings") return;
    void loadMailboxes();
  }, [currentUser, loadMailboxes, view]);

  const initializeReplyState = useCallback(
    (detail: EmailItem, threadItems: EmailItem[]) => {
      const latest = threadItems[threadItems.length - 1] || detail;
      const inferredLanguage = normalizeReplyLanguage(latest.preferred_reply_language || latest.detected_source_language || detail.preferred_reply_language || "ru");
      setReplyLanguage(inferredLanguage);
      setReplyTo(detail.sender_email || "");
      setReplyCc("");
      setReplyBcc("");
      setReplySubject(buildReplySubject(detail.subject));
      setReplyPrompt("");
      setReplySignature(settingsSignature || currentUser?.full_name || currentUser?.email || "");
      setDraftText(detail.ai_draft_reply || "");
      return inferredLanguage;
    },
    [currentUser, settingsSignature]
  );

  const loadEmails = useCallback(async () => {
    if (!currentUser || view === "settings") return;
    setLoadingList(true);
    setAppError("");
    try {
      const params = new URLSearchParams({ limit: "60" });
      if (view === "sent") {
        params.set("direction", "sent");
      } else if (view === "spam") {
        params.set("status", "spam");
      } else if (view === "processed") {
        params.set("status", "processed");
      } else {
        params.set("direction", "inbound");
      }
      if (search.trim()) {
        params.set("search", search.trim());
      }
      const items = await apiGet<EmailItem[]>(`/api/emails?${params.toString()}`);
      const filtered = filterEmailsForView(view, items);
      setEmails(filtered);
      if (selectedEmailId != null && !filtered.some((item) => item.id === selectedEmailId)) {
        setSelectedEmailId(null);
        setSelectedEmail(null);
        setThread([]);
        setAttachments([]);
      }
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not load emails."));
    } finally {
      setLoadingList(false);
    }
  }, [currentUser, view, search, selectedEmailId]);

  const reloadSelectedEmail = useCallback(
    async (emailId: number) => {
      if (!currentUser) return;
      const [detail, threadPayload, attachmentPayload] = await Promise.all([
        apiGet<EmailItem>(`/api/emails/${emailId}`),
        apiGet<ThreadResponse>(`/api/emails/${emailId}/thread`),
        apiGet<AttachmentItem[]>(`/api/emails/${emailId}/attachments`).catch(() => []),
      ]);
      setSelectedEmail(detail);
      setThread(threadPayload.emails);
      setAttachments(attachmentPayload);
      return initializeReplyState(detail, threadPayload.emails);
    },
    [currentUser, initializeReplyState]
  );

  const generateDraftForEmail = useCallback(
    async (emailId: number, options?: { targetLanguage?: "ru" | "en" | "tr"; customPrompt?: string; showSuccess?: boolean }) => {
      setMailActionLoading("draft");
      setDraftText("");
      try {
        const targetLanguage = options?.targetLanguage || summaryLanguage || replyLanguage;
        const response = await apiPost<DraftGenerationResponse>(`/api/emails/${emailId}/generate-draft`, {
          target_language: targetLanguage,
          custom_prompt: options?.customPrompt?.trim() || undefined,
        });
        setDraftText(response.draft_reply);
        setReplyLanguage(normalizeReplyLanguage(response.target_language));
        setModalMode("reply");
        if (options?.showSuccess) {
          setAppSuccess(t("success.draftGenerated"));
        }
      } finally {
        setMailActionLoading(null);
      }
    },
    [replyLanguage, summaryLanguage, t]
  );

  const openEmailModal = useCallback(
    async (emailId: number, mode: "read" | "reply" = "read", autoGenerate = false) => {
      if (!currentUser) return;
      setSelectedEmailId(emailId);
      setModalMode(mode);
      setLoadingDetail(true);
      setAppError("");
      // Failsafe: if the API doesn't respond in 15 s, close the loading modal
      // so the user isn't stuck staring at a skeleton screen forever.
      let timeoutId: ReturnType<typeof window.setTimeout> | undefined;
      const timeoutPromise = new Promise<never>((_, reject) => {
        timeoutId = window.setTimeout(() => {
          reject(new Error(t("errors.loadTimeout") || "Request timed out. Please try again."));
        }, 15000);
      });
      try {
        await Promise.race([reloadSelectedEmail(emailId), timeoutPromise]);
        window.clearTimeout(timeoutId);
        if (mode === "reply" && autoGenerate) {
          setAppSuccess("");
          await generateDraftForEmail(emailId, { targetLanguage: summaryLanguage, customPrompt: "", showSuccess: false });
        }
      } catch (error) {
        window.clearTimeout(timeoutId);
        setAppError(getErrorMessage(error, autoGenerate ? "Could not generate draft." : "Could not load the selected email."));
        setSelectedEmailId(null);
        setSelectedEmail(null);
        setModalMode(null);
      } finally {
        setLoadingDetail(false);
      }
    },
    [currentUser, generateDraftForEmail, reloadSelectedEmail, summaryLanguage, t]
  );

  useEffect(() => {
    void loadEmails();
  }, [loadEmails]);

  useEffect(() => {
    if (!currentUser || view === "settings") return;
    const interval = window.setInterval(() => {
      void loadEmails();
    }, 300000);
    return () => window.clearInterval(interval);
  }, [currentUser, loadEmails, view]);

  const handleViewChange = useCallback(
    (nextView: MailView) => {
      setView(nextView);
      setAppError("");
      setAppSuccess("");
      setMobileSidebarOpen(false);
      setModalMode(null);
      setSelectedEmailId(null);
      setSelectedEmail(null);
      setThread([]);
      setAttachments([]);
    },
    []
  );

  const closeModal = useCallback(() => {
    setModalMode(null);
    setSelectedEmailId(null);
    setSelectedEmail(null);
    setThread([]);
    setAttachments([]);
    setDraftText("");
    setReplyTo("");
    setReplyCc("");
    setReplyBcc("");
    setReplySubject("");
    setReplyPrompt("");
    setReplySignature("");
    setLoadingDetail(false);
    setMailActionLoading(null);
  }, []);

  async function refreshCurrentView() {
    await loadEmails();
    if (selectedEmailId != null && view !== "settings") {
      await reloadSelectedEmail(selectedEmailId);
    }
  }

  function applyOptimisticStatus(emailId: number, status: string) {
    const patch = (email: EmailItem): EmailItem => {
      const next: EmailItem = { ...email, status };
      if (status === "spam") {
        next.is_spam = true;
        next.folder = "Spam";
      } else if (status === "archived") {
        next.folder = "Archive";
      } else if (status === "processed") {
        next.folder = "Processed";
      } else if (status === "reply_later") {
        next.folder = "Reply Later";
      } else if (status === "new") {
        next.is_spam = false;
        next.folder = "INBOX";
      }
      return next;
    };

    setEmails((prev) => filterEmailsForView(view, prev.map((item) => (item.id === emailId ? patch(item) : item))));
    setSelectedEmail((prev) => (prev && prev.id === emailId ? patch(prev) : prev));
    setThread((prev) => prev.map((item) => (item.id === emailId ? patch(item) : item)));
  }

  async function updateStatus(emailId: number, status: string, successMessage: string) {
    const snapshotEmails = emails;
    const snapshotSelectedEmail = selectedEmail;
    const snapshotThread = thread;
    const shouldCloseDetail = selectedEmailId === emailId;
    setAppError("");
    setAppSuccess("");
    applyOptimisticStatus(emailId, status);
    try {
      await apiPost(`/api/emails/${emailId}/status`, { status });
      setAppSuccess(successMessage);
      if (shouldCloseDetail && (status === "spam" || status === "archived" || status === "reply_later" || status === "processed")) {
        closeModal();
      }
      await refreshCurrentView();
    } catch (error) {
      setEmails(snapshotEmails);
      setSelectedEmail(snapshotSelectedEmail);
      setThread(snapshotThread);
      setAppError(getErrorMessage(error, "Could not update message status."));
    }
  }

  async function markProcessed(emailId: number) {
    const snapshotEmails = emails;
    const snapshotSelectedEmail = selectedEmail;
    const snapshotThread = thread;
    const shouldCloseDetail = selectedEmailId === emailId;
    setAppError("");
    setAppSuccess("");
    applyOptimisticStatus(emailId, "processed");
    try {
      await apiPost(`/api/emails/${emailId}/status`, { status: "processed" });
      setAppSuccess(t("success.markProcessed"));
      if (shouldCloseDetail) {
        closeModal();
      }
      await refreshCurrentView();
    } catch (error) {
      setEmails(snapshotEmails);
      setSelectedEmail(snapshotSelectedEmail);
      setThread(snapshotThread);
      setAppError(getErrorMessage(error, "Could not mark message as processed."));
    }
  }

  async function moveReplyLater(emailId: number) {
    const snapshotEmails = emails;
    const snapshotSelectedEmail = selectedEmail;
    const snapshotThread = thread;
    setAppError("");
    setAppSuccess("");
    applyOptimisticStatus(emailId, "reply_later");
    try {
      await apiPost(`/api/emails/${emailId}/reply-later`, {});
      setAppSuccess(t("success.movedLater"));
      if (selectedEmailId === emailId) closeModal();
      await refreshCurrentView();
    } catch (error) {
      setEmails(snapshotEmails);
      setSelectedEmail(snapshotSelectedEmail);
      setThread(snapshotThread);
      setAppError(getErrorMessage(error, "Could not move message to Reply Later."));
    }
  }

  async function generateDraft() {
    if (!selectedEmailId) return;
    setAppError("");
    setAppSuccess("");
    try {
      await generateDraftForEmail(selectedEmailId, {
        targetLanguage: summaryLanguage,
        customPrompt: replyPrompt,
        showSuccess: true,
      });
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not generate draft."));
    }
  }

  async function translateDraft(targetLang: "ru" | "en" | "tr") {
    if (!selectedEmailId || !draftText.trim()) return;
    setAppError("");
    setMailActionLoading("draft");
    try {
      const response = await apiPost<DraftGenerationResponse>(
        `/api/emails/${selectedEmailId}/rewrite-draft`,
        {
          current_draft: draftText,
          instruction: `translate to ${targetLang}`,
          target_language: targetLang,
        }
      );
      setDraftText(response.draft_reply);
      setReplyLanguage(targetLang);
    } catch (error) {
      setAppError(getErrorMessage(error, t("errors.translateFailed")));
    } finally {
      setMailActionLoading(null);
    }
  }

  async function regenerateSummary() {
    if (!selectedEmailId || !selectedEmail) return;
    setAppError("");
    setAppSuccess("");
    setMailActionLoading("summary");
    try {
      const response = await apiPost<EmailItem>(`/api/emails/${selectedEmailId}/regenerate-summary`, {
        target_language: summaryLanguage,
      });
      setSelectedEmail(response);
      await reloadSelectedEmail(selectedEmailId);
      setAppSuccess(t("success.summaryRegenerated"));
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not regenerate summary."));
    } finally {
      setMailActionLoading(null);
    }
  }

  async function sendReply() {
    if (!selectedEmailId || !selectedEmail) return;
    setAppError("");
    setAppSuccess("");
    setMailActionLoading("reply");
    try {
      const payload = buildReplyPayload({
        body: buildReplyBody(draftText, replySignature, selectedEmail),
        to: splitRecipients(replyTo),
        cc: splitRecipients(replyCc),
        bcc: splitRecipients(replyBcc),
        subject: replySubject.trim() || undefined,
        save_as_sent_record: true,
      });
      await apiPost(`/api/emails/${selectedEmailId}/reply`, payload);
      setAppSuccess(t("success.replySent"));
      closeModal();
      await loadEmails();
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not send reply."));
    } finally {
      setMailActionLoading(null);
    }
  }

  async function saveSignature() {
    setAppError("");
    setAppSuccess("");
    setSavingSignature(true);
    try {
      await apiPost("/api/settings", {
        signature: settingsSignature,
      });
      setAppSuccess(t("settings.signatureSaved"));
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not save signature."));
    } finally {
      setSavingSignature(false);
    }
  }

  async function saveSummaryLanguage(language: "ru" | "en" | "tr") {
    setAppError("");
    try {
      await apiPost("/api/settings", {
        interface_language: language,
        summary_language: language,
      });
      setSummaryLanguage(language);
      setAppSuccess(language === "ru" ? "Язык изменен." : language === "tr" ? "Dil güncellendi." : "Language updated.");
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not save language preference."));
    }
  }

  async function saveAutoSpamEnabled(nextValue: boolean) {
    const previousValue = autoSpamEnabled;
    setAppError("");
    setAutoSpamEnabled(nextValue);
    try {
      await apiPost("/api/settings", {
        auto_spam_enabled: nextValue,
      });
    } catch (error) {
      setAutoSpamEnabled(previousValue);
      setAppError(getErrorMessage(error, "Could not save auto-spam preference."));
    }
  }

  async function saveScanSinceDate(nextValue: string) {
    const previousValue = scanSinceDate;
    setAppError("");
    setScanSinceDate(nextValue);
    try {
      await apiPost("/api/settings", {
        scan_since_date: buildScanSinceDateIso(nextValue),
      });
    } catch (error) {
      setScanSinceDate(previousValue);
      setAppError(getErrorMessage(error, "Could not save scan start date."));
    }
  }

  async function saveFollowupOverdueDays(nextValue: string) {
    const normalized = nextValue.replace(/[^\d]/g, "");
    const previousValue = followupOverdueDays;
    setAppError("");
    setFollowupOverdueDays(normalized);
    if (!normalized) return;
    try {
      await apiPost("/api/settings", {
        followup_overdue_days: Number(normalized),
      });
    } catch (error) {
      setFollowupOverdueDays(previousValue);
      setAppError(getErrorMessage(error, "Could not save follow-up workflow setting."));
    }
  }

  function startMailboxEdit(mailbox: MailboxItem) {
    setEditingMailboxId(mailbox.id);
    setMailboxForm({
      name: mailbox.name,
      email_address: mailbox.email_address,
      imap_host: mailbox.imap_host,
      imap_port: String(mailbox.imap_port),
      imap_username: mailbox.imap_username,
      imap_password: "",
      smtp_host: mailbox.smtp_host,
      smtp_port: String(mailbox.smtp_port),
      smtp_username: mailbox.smtp_username,
      smtp_password: "",
      smtp_use_tls: mailbox.smtp_use_tls,
      smtp_use_ssl: mailbox.smtp_use_ssl,
      enabled: mailbox.enabled,
      is_default_outgoing: mailbox.is_default_outgoing,
    });
  }

  async function saveMailbox() {
    const normalizedEmail = mailboxForm.email_address.trim().toLowerCase();
    if (!normalizedEmail || !mailboxForm.imap_host.trim() || !mailboxForm.smtp_host.trim()) {
      setAppError("Mailbox email, IMAP host, and SMTP host are required.");
      return;
    }
    if (!editingMailboxId && (!mailboxForm.imap_password.trim() || !mailboxForm.smtp_password.trim())) {
      setAppError("IMAP and SMTP passwords are required when creating a mailbox.");
      return;
    }

    const payload: Record<string, unknown> = {
      name: mailboxForm.name.trim() || normalizedEmail,
      email_address: normalizedEmail,
      imap_host: mailboxForm.imap_host.trim(),
      imap_port: Number(mailboxForm.imap_port || "993"),
      imap_username: mailboxForm.imap_username.trim() || normalizedEmail,
      smtp_host: mailboxForm.smtp_host.trim(),
      smtp_port: Number(mailboxForm.smtp_port || "465"),
      smtp_username: mailboxForm.smtp_username.trim() || normalizedEmail,
      smtp_use_tls: mailboxForm.smtp_use_tls,
      smtp_use_ssl: mailboxForm.smtp_use_ssl,
      enabled: mailboxForm.enabled,
      is_default_outgoing: mailboxForm.is_default_outgoing,
    };
    if (mailboxForm.imap_password.trim()) payload.imap_password = mailboxForm.imap_password.trim();
    if (mailboxForm.smtp_password.trim()) payload.smtp_password = mailboxForm.smtp_password.trim();

    setAppError("");
    setMailboxSaving(true);
    try {
      if (editingMailboxId) {
        await apiPut(`/api/mailboxes/${editingMailboxId}`, payload);
        setAppSuccess("Mailbox updated.");
      } else {
        await apiPost("/api/mailboxes", payload);
        setAppSuccess("Mailbox added.");
      }
      resetMailboxEditor();
      await loadMailboxes();
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not save mailbox."));
    } finally {
      setMailboxSaving(false);
    }
  }

  async function deleteMailbox(mailboxId: string) {
    setAppError("");
    setMailboxActionLoadingId(mailboxId);
    try {
      await apiDelete(`/api/mailboxes/${mailboxId}`);
      if (editingMailboxId === mailboxId) {
        resetMailboxEditor();
      }
      setAppSuccess("Mailbox deleted.");
      await loadMailboxes();
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not delete mailbox."));
    } finally {
      setMailboxActionLoadingId(null);
    }
  }

  async function testMailbox(mailboxId: string) {
    setAppError("");
    setMailboxActionLoadingId(mailboxId);
    try {
      await apiPost(`/api/mailboxes/${mailboxId}/test-connection`, {});
      setAppSuccess("Mailbox connection verified.");
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not test mailbox connection."));
    } finally {
      setMailboxActionLoadingId(null);
    }
  }

  async function scanMailbox(mailboxId: string) {
    setAppError("");
    setMailboxActionLoadingId(mailboxId);
    try {
      await apiPost(`/api/mailboxes/${mailboxId}/scan`, {});
      setAppSuccess("Mailbox scan started.");
      await loadEmails();
    } catch (error) {
      setAppError(getErrorMessage(error, "Could not start mailbox scan."));
    } finally {
      setMailboxActionLoadingId(null);
    }
  }

  const shellClass = `app-shell${mobileSidebarOpen ? " sidebar-open" : ""}`;

  if (setupState === "loading" || (setupState === "ready" && authLoading)) {
    return <div className="boot-state">{setupError || t("auth.checking")}</div>;
  }

  if (setupState === "required") {
    return <SetupWizard onCompleted={() => setSetupState("ready")} />;
  }

  if (!currentUser) {
    return (
      <LoginScreen
        loginForm={loginForm}
        actionLoading={actionLoading}
        errorMessage={authError}
        successMessage={authSuccess}
        onChange={setLoginForm}
        onSubmit={handleLogin}
      />
    );
  }

  return (
    <div className={shellClass}>
      <Sidebar view={view} open={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)} onViewChange={handleViewChange} />
      <main className="app-content">
        <header className="topbar">
          <div className="topbar-left">
            <button className="button button-ghost mobile-menu" type="button" onClick={() => setMobileSidebarOpen((current) => !current)}>
              <span className="sr-only">{t("app.mobileMenu")}</span>
              ☰
            </button>
            <div>
              <p className="eyebrow">{t("app.workspace")}</p>
              <h2>
                {view === "settings"
                  ? t("views.settings.title")
                  : view === "sent"
                    ? t("views.sent.title")
                    : view === "spam"
                      ? t("views.spam.title")
                      : view === "processed"
                        ? t("nav.processed")
                      : t("nav.inbox", { defaultValue: "Inbox" })}
              </h2>
            </div>
          </div>
          <div className="topbar-actions">
            {view !== "settings" ? (
              <button className="button button-ghost" type="button" onClick={() => void loadEmails()} disabled={loadingList}>
                ↻
              </button>
            ) : null}
            <div className="user-chip">{currentUser.full_name || currentUser.email}</div>
            <button className="button button-ghost" type="button" onClick={() => void handleLogout()} disabled={actionLoading === "auth-logout"}>
              {actionLoading === "auth-logout" ? t("app.signingOut") : t("app.logout")}
            </button>
          </div>
        </header>

        <div className="toast-stack" aria-live="polite" aria-atomic="true">
          {authError ? <div className="toast toast-error" role="alert">{authError}</div> : null}
          {appError ? <div className="toast toast-error" role="alert">{appError}</div> : null}
          {appSuccess ? <div className="toast toast-success">{appSuccess}</div> : null}
        </div>

        {view === "settings" ? (
          <SettingsPanel
            currentUser={currentUser}
            language={i18n.language.startsWith("ru") ? "ru" : i18n.language.startsWith("tr") ? "tr" : "en"}
            onLanguageChange={(language) => {
              void i18n.changeLanguage(language);
              void saveSummaryLanguage(language);
            }}
            autoSpamEnabled={autoSpamEnabled}
            onAutoSpamChange={(value) => {
              void saveAutoSpamEnabled(value);
            }}
            followupOverdueDays={followupOverdueDays}
            onFollowupOverdueDaysChange={(value) => {
              void saveFollowupOverdueDays(value);
            }}
            scanSinceDate={scanSinceDate}
            onScanSinceDateChange={(value) => {
              void saveScanSinceDate(value);
            }}
            signature={settingsSignature}
            onSignatureChange={setSettingsSignature}
            onSaveSignature={() => void saveSignature()}
            savingSignature={savingSignature}
            mailboxes={mailboxes}
            mailboxesLoading={mailboxesLoading}
            mailboxForm={mailboxForm}
            editingMailboxId={editingMailboxId}
            mailboxSaving={mailboxSaving}
            mailboxActionLoadingId={mailboxActionLoadingId}
            onMailboxFormChange={setMailboxForm}
            onMailboxEdit={startMailboxEdit}
            onMailboxCancelEdit={resetMailboxEditor}
            onMailboxSave={() => void saveMailbox()}
            onMailboxDelete={(mailboxId) => void deleteMailbox(mailboxId)}
            onMailboxScan={(mailboxId) => void scanMailbox(mailboxId)}
            onMailboxTest={(mailboxId) => void testMailbox(mailboxId)}
            onLogout={() => void handleLogout()}
            actionLoading={actionLoading}
          />
        ) : (
          <div className="mail-layout">
            <EmailList
              view={view}
              emails={emails}
              selectedEmailId={selectedEmailId}
              loading={loadingList}
              search={search}
              onSearchChange={setSearch}
              onSelectEmail={(emailId) => {
                void openEmailModal(emailId, "read");
              }}
              onArchiveEmail={(emailId) => void updateStatus(emailId, "archived", t("success.archived"))}
              onMarkProcessed={(emailId) => void markProcessed(emailId)}
              onSpamEmail={(emailId) => void updateStatus(emailId, "spam", t("success.movedSpam"))}
              onRestoreEmail={(emailId) => void updateStatus(emailId, "new", t("success.restored"))}
              onReplyLaterEmail={(emailId) => void moveReplyLater(emailId)}
              onReplyWithAi={(emailId) => void openEmailModal(emailId, "reply", true)}
            />
          </div>
        )}

        <EmailDetail
          open={selectedEmailId != null && view !== "settings"}
          mode={modalMode || "read"}
          selectedEmail={selectedEmail}
          thread={thread}
          attachments={attachments}
          loading={loadingDetail}
          actionLoading={mailActionLoading}
          draftText={draftText}
          replyLanguage={replyLanguage}
          replyTo={replyTo}
          replyCc={replyCc}
          replyBcc={replyBcc}
          replySubject={replySubject}
          replyPrompt={replyPrompt}
          replySignature={replySignature}
          summaryLanguage={summaryLanguage}
          onClose={closeModal}
          onModeChange={(nextMode) => setModalMode(nextMode)}
          onDraftChange={setDraftText}
          onReplyToChange={setReplyTo}
          onReplyCcChange={setReplyCc}
          onReplyBccChange={setReplyBcc}
          onReplySubjectChange={setReplySubject}
          onReplyPromptChange={setReplyPrompt}
          onReplySignatureChange={setReplySignature}
          onReplyLanguageChange={setReplyLanguage}
          onGenerateDraft={() => void generateDraft()}
          onTranslateDraft={(lang) => void translateDraft(lang)}
          onSendReply={() => void sendReply()}
          onRegenerateSummary={() => void regenerateSummary()}
          onArchive={() => selectedEmailId ? void updateStatus(selectedEmailId, "archived", t("success.archived")) : undefined}
          onSpam={() => selectedEmailId ? void updateStatus(selectedEmailId, "spam", t("success.movedSpam")) : undefined}
          onReplyLater={() => selectedEmailId ? void moveReplyLater(selectedEmailId) : undefined}
        />
      </main>
    </div>
  );
}

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}
