import React, { useCallback, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { useTranslation } from "react-i18next";
import i18n from "./i18n";
import { apiGet, apiPost, buildReplyPayload, getErrorMessage } from "./api";
import { useAuth } from "./hooks/useAuth";
import { LoginScreen } from "./components/LoginScreen";
import { Sidebar } from "./components/Sidebar";
import { EmailList } from "./components/EmailList";
import { EmailDetail } from "./components/EmailDetail";
import { SettingsPanel } from "./components/SettingsPanel";
import type { AttachmentItem, DraftGenerationResponse, EmailItem, MailView, SettingsResponse, ThreadResponse } from "./types";
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
  const normalized = (value || "").toLowerCase();
  if (normalized === "en" || normalized === "tr") return normalized;
  return "ru";
}

function filterEmailsForView(view: MailView, emails: EmailItem[]): EmailItem[] {
  if (view !== "inbox") return emails;
  return emails.filter((item) => item.status !== "spam" && item.status !== "archived" && item.status !== "reply_later");
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
  const { authLoading, currentUser, loginForm, setLoginForm, handleLogin, handleLogout, authError, authSuccess, actionLoading } = useAuth();
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
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [mailActionLoading, setMailActionLoading] = useState<string | null>(null);
  const [appError, setAppError] = useState("");
  const [appSuccess, setAppSuccess] = useState("");
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [modalMode, setModalMode] = useState<"read" | "reply" | null>(null);

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
    if (!currentUser) {
      setView("inbox");
      setEmails([]);
      setSelectedEmailId(null);
      setSelectedEmail(null);
      setThread([]);
      setAttachments([]);
      setDraftText("");
      setReplyLanguage("ru");
      setReplyTo("");
      setReplyCc("");
      setReplyBcc("");
      setReplySubject("");
      setReplyPrompt("");
      setReplySignature("");
      setSettingsSignature("");
      setModalMode(null);
    }
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser) return;
    apiGet<SettingsResponse>("/api/settings")
      .then((settings) => {
        setSettingsSignature((settings.signature || "").trim());
      })
      .catch(() => {
        setSettingsSignature("");
      });
  }, [currentUser]);

  useEffect(() => {
    if (modalMode === "reply" && settingsSignature && !replySignature.trim()) {
      setReplySignature(settingsSignature);
    }
  }, [modalMode, replySignature, settingsSignature]);

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
        const response = await apiPost<DraftGenerationResponse>(`/api/emails/${emailId}/generate-draft`, {
          target_language: options?.targetLanguage || replyLanguage,
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
    [replyLanguage, t]
  );

  const openEmailModal = useCallback(
    async (emailId: number, mode: "read" | "reply" = "read", autoGenerate = false) => {
      if (!currentUser) return;
      setSelectedEmailId(emailId);
      setModalMode(mode);
      setLoadingDetail(true);
      setAppError("");
      try {
        const inferredLanguage = await reloadSelectedEmail(emailId);
        if (mode === "reply" && autoGenerate) {
          setAppSuccess("");
          await generateDraftForEmail(emailId, { targetLanguage: inferredLanguage, customPrompt: "", showSuccess: false });
        }
      } catch (error) {
        setAppError(getErrorMessage(error, autoGenerate ? "Could not generate draft." : "Could not load the selected email."));
      } finally {
        setLoadingDetail(false);
      }
    },
    [currentUser, generateDraftForEmail, reloadSelectedEmail]
  );

  useEffect(() => {
    void loadEmails();
  }, [loadEmails]);

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
    if (selectedEmailId != null && modalMode && view !== "settings") {
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
      } else if (status === "reply_later") {
        next.folder = "Reply Later";
      } else if (status === "new") {
        next.is_spam = false;
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
    const shouldCloseModal = selectedEmailId === emailId && modalMode !== null;
    setAppError("");
    setAppSuccess("");
    applyOptimisticStatus(emailId, status);
    try {
      await apiPost(`/api/emails/${emailId}/status`, { status });
      setAppSuccess(successMessage);
      if (shouldCloseModal && (status === "spam" || status === "archived" || status === "reply_later")) {
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
      if (selectedEmailId === emailId && modalMode !== null) closeModal();
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
        targetLanguage: replyLanguage,
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

  const shellClass = `app-shell${mobileSidebarOpen ? " sidebar-open" : ""}`;

  if (authLoading) {
    return <div className="boot-state">{t("auth.checking")}</div>;
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
                      : t("nav.inbox", { defaultValue: "Inbox" })}
              </h2>
            </div>
          </div>
          <div className="topbar-actions">
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
              setAppSuccess(language === "ru" ? "Язык изменен." : language === "tr" ? "Dil güncellendi." : "Language updated.");
            }}
            onLogout={() => void handleLogout()}
            actionLoading={actionLoading}
          />
        ) : (
          <section className="inbox-stage">
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
              onSpamEmail={(emailId) => void updateStatus(emailId, "spam", t("success.movedSpam"))}
              onRestoreEmail={(emailId) => void updateStatus(emailId, "new", t("success.restored"))}
              onReplyLaterEmail={(emailId) => void moveReplyLater(emailId)}
              onReplyWithAi={(emailId) => void openEmailModal(emailId, "reply", true)}
            />

            <EmailDetail
              open={Boolean(selectedEmailId && modalMode)}
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
              onArchive={() => selectedEmailId ? void updateStatus(selectedEmailId, "archived", t("success.archived")) : undefined}
              onSpam={() => selectedEmailId ? void updateStatus(selectedEmailId, "spam", t("success.movedSpam")) : undefined}
              onReplyLater={() => selectedEmailId ? void moveReplyLater(selectedEmailId) : undefined}
            />
          </section>
        )}
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
