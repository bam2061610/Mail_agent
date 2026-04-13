import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Archive, Ban, Clock, Sparkles } from "lucide-react";
import type { AttachmentItem, EmailItem } from "../types";
import { Badge } from "./common/Badge";
import { Field } from "./common/Field";
import { ImportanceBadge } from "./common/ImportanceBadge";
import { SummaryPoint } from "./common/SummaryPoint";

type EmailDetailProps = {
  open: boolean;
  mode: "read" | "reply";
  selectedEmail: EmailItem | null;
  thread: EmailItem[];
  attachments: AttachmentItem[];
  loading: boolean;
  actionLoading: string | null;
  draftText: string;
  replyLanguage: "ru" | "en" | "tr";
  replyTo: string;
  replyCc: string;
  replyBcc: string;
  replySubject: string;
  replyPrompt: string;
  replySignature: string;
  summaryLanguage: "ru" | "en" | "tr";
  onClose: () => void;
  onModeChange: (mode: "read" | "reply") => void;
  onDraftChange: (value: string) => void;
  onReplyToChange: (value: string) => void;
  onReplyCcChange: (value: string) => void;
  onReplyBccChange: (value: string) => void;
  onReplySubjectChange: (value: string) => void;
  onReplyPromptChange: (value: string) => void;
  onReplySignatureChange: (value: string) => void;
  onReplyLanguageChange: (value: "ru" | "en" | "tr") => void;
  onGenerateDraft: () => void;
  onTranslateDraft: (lang: "ru" | "en" | "tr") => void;
  onSendReply: () => void;
  onRegenerateSummary: () => void;
  onArchive: () => void;
  onSpam: () => void;
  onReplyLater: () => void;
};

function splitValue(value: string): string[] {
  return value
    .split(/[,;\n]/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeLanguageCode(value?: string | null): "ru" | "en" | "tr" | null {
  const normalized = (value || "").trim().toLowerCase();
  if (normalized === "ru" || normalized === "russian") return "ru";
  if (normalized === "en" || normalized === "english") return "en";
  if (normalized === "tr" || normalized === "turkish") return "tr";
  return null;
}

export function EmailDetail(props: EmailDetailProps) {
  const { t } = useTranslation();
  const [showOriginal, setShowOriginal] = useState(false);

  const summaryText = useMemo(
    () => props.selectedEmail?.ai_summary || props.thread.find((item) => item.ai_summary)?.ai_summary || "",
    [props.selectedEmail, props.thread]
  );

  useEffect(() => {
    setShowOriginal(false);
  }, [props.selectedEmail?.id, props.mode]);

  // Close modal on Escape key
  useEffect(() => {
    if (!props.open) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        props.onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [props.open, props.onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (!props.open) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [props.open]);

  if (!props.open) return null;

  const selected = props.selectedEmail;
  const isOutbound = selected ? selected.direction === "sent" || selected.direction === "outbound" : false;
  const recipientList = splitValue(props.replyTo);
  const ccList = splitValue(props.replyCc);
  const bccList = splitValue(props.replyBcc);
  const attachmentCount = props.attachments.length || selected?.attachment_count || 0;
  const summaryFallback = selected && !selected.ai_analyzed ? t("queue.analyzing") : t("detail.noAnalysis");
  const originalHtml = selected?.body_html || "";
  const originalText = selected?.body_text || "";
  const hasOriginal = Boolean(originalHtml || originalText);
  const detectedLanguage = selected ? normalizeLanguageCode(selected.detected_source_language) : null;
  const hasSelectedSummary = Boolean(selected?.ai_summary);
  const shouldOfferSummaryRefresh = Boolean(selected && (isOutbound || !hasSelectedSummary || (detectedLanguage && detectedLanguage !== props.summaryLanguage)));
  const summaryLanguageLabelKey = props.summaryLanguage === "ru" ? "settings.russian" : props.summaryLanguage === "tr" ? "settings.turkish" : "settings.english";
  const summaryActionLabel = hasSelectedSummary
    ? t("detail.regenerateSummary", { language: t(summaryLanguageLabelKey) })
    : t("detail.generateSummary");

  function handleOverlayClick(event: React.MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) {
      props.onClose();
    }
  }

  if (props.loading) {
    return createPortal(
      <div className="modal-overlay" role="presentation" onClick={handleOverlayClick}>
        <div className="modal-card email-modal" role="dialog" aria-modal="true" aria-label={t("detail.loading")}>
          <div className="modal-body modal-skeleton">
            <div className="skeleton skeleton-line skeleton-line-title" />
            <div className="skeleton skeleton-line skeleton-line-summary" />
            <div className="skeleton-stack">
              <div className="skeleton skeleton-panel" />
              <div className="skeleton skeleton-panel" />
              <div className="skeleton skeleton-panel" />
            </div>
          </div>
        </div>
      </div>,
      document.body
    );
  }

  if (!selected) {
    return createPortal(
      <div className="modal-overlay" role="presentation" onClick={handleOverlayClick}>
        <div className="modal-card email-modal" role="dialog" aria-modal="true">
          <div className="modal-body">
            <div className="empty-state">
              <strong>{t("detail.selectItem")}</strong>
              <p>{t("detail.selectItemDesc")}</p>
            </div>
          </div>
        </div>
      </div>,
      document.body
    );
  }

  const threadSection = (
    <section className="detail-section-card">
      <div className="section-title-row">
        <h4 className="section-title">{t("detail.thread")}</h4>
        <div className="inline-badges">
          {isOutbound ? <Badge tone="accent">{t("status.sent")}</Badge> : <Badge tone="neutral">{t("nav.inbox", { defaultValue: "Inbox" })}</Badge>}
          {selected.attachment_count ? <Badge tone="neutral">{t("queue.attachments", { count: selected.attachment_count })}</Badge> : null}
        </div>
      </div>
      <div className="detail-feed">
        {props.thread.length === 0 ? (
          <div className="empty-state">
            <strong>{t("detail.thread")}</strong>
            <p>{t("detail.noAnalysis")}</p>
          </div>
        ) : null}
        {props.thread.map((message, index) => {
          const outbound = message.direction === "sent" || message.direction === "outbound";
          const open = index === props.thread.length - 1;

          return (
            <details key={message.id} className={`thread-card${outbound ? " thread-outbound" : ""}`} open={open}>
              <summary className="thread-summary">
                <div className="thread-summary-copy">
                  <strong>{message.sender_name || message.sender_email || t("queue.unknownSender")}</strong>
                  <p>{message.subject || t("queue.noSubject")}</p>
                </div>
                <span>{message.date_received ? new Date(message.date_received).toLocaleString() : ""}</span>
              </summary>
              <div className="thread-body">
                {message.ai_summary ? <div className="thread-note">{message.ai_summary}</div> : null}
                <div className="thread-label">{t("detail.originalMessage")}</div>
                <p className="thread-text">{message.body_text || message.body_html || t("queue.noPreview")}</p>
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );

  const attachmentsSection = (
    <section className="detail-section-card">
      <div className="section-title-row">
        <h4 className="section-title">{t("detail.attachmentsTitle")}</h4>
        <div className="inline-badges">
          <Badge tone="neutral">{attachmentCount}</Badge>
        </div>
      </div>
      <div className="attachment-strip">
        {props.attachments.length ? (
          props.attachments.map((item) => <Badge key={item.id}>{item.filename || item.content_type || "Attachment"}</Badge>)
        ) : (
          <span className="helper-text">{t("detail.noAttachments")}</span>
        )}
      </div>
    </section>
  );

  const originalMessageSection = (
    <section className="detail-section-card original-message-panel">
      <div className="section-title-row">
        <h4 className="section-title">{t("detail.originalMessage")}</h4>
        <button
          className="button button-ghost original-message-toggle"
          type="button"
          aria-expanded={showOriginal}
          onClick={() => setShowOriginal((current) => !current)}
        >
          {showOriginal ? t("detail.hideOriginal") : t("detail.showOriginal")}
        </button>
      </div>
      {showOriginal ? (
        hasOriginal ? (
          originalHtml ? (
            <iframe
              title={t("detail.originalMessage")}
              srcDoc={originalHtml}
              sandbox=""
              className="original-message-frame"
              style={{ maxHeight: "400px", overflow: "auto", width: "100%", border: "1px solid var(--line)", height: "400px" }}
            />
          ) : (
            <pre className="original-message-text" style={{ maxHeight: "400px", overflowY: "auto", whiteSpace: "pre-wrap" }}>
              {originalText}
            </pre>
          )
        ) : (
          <p className="helper-text">{t("queue.noPreview")}</p>
        )
      ) : null}
    </section>
  );

  const modalLabel = props.mode === "reply" ? t("detail.replyTitle") : t("detail.readTitle");

  return createPortal(
    <div
      className="modal-overlay"
      role="presentation"
      onClick={handleOverlayClick}
    >
      <div
        className="modal-card email-modal"
        role="dialog"
        aria-modal="true"
        aria-label={modalLabel}
      >
        <div className="modal-header">
          <div className="modal-heading">
            <p className="eyebrow">{props.mode === "reply" ? t("detail.replyTitle") : t("detail.readTitle")}</p>
            <h3 title={selected.subject || t("queue.noSubject")}>{selected.subject || t("queue.noSubject")}</h3>
            <p className="modal-subtitle" title={selected.sender_name || selected.sender_email || t("queue.unknownSender")}>
              {selected.sender_name || selected.sender_email || t("queue.unknownSender")}
            </p>
          </div>
          <div className="modal-header-actions">
            <button className="button button-secondary modal-mode-toggle" type="button" onClick={() => props.onModeChange(props.mode === "reply" ? "read" : "reply")}>
              {props.mode === "reply" ? t("detail.backToRead") : t("detail.replyNow")}
            </button>
            <button className="button button-ghost detail-close" type="button" onClick={props.onClose} aria-label={t("detail.closeModal")}>
              ×
            </button>
          </div>
        </div>

        <div className={`modal-body${props.mode === "reply" ? " modal-body-reply" : " modal-body-read"}`}>
          <div className="detail-summary">
            <div className="summary-heading-row">
              <div className="summary-heading">
                <Sparkles size={14} aria-hidden="true" />
                <span>{t("detail.summaryHeading")}</span>
              </div>
              <div className="summary-badges">
                <ImportanceBadge score={selected.importance_score} label={t("detail.importance")} />
                {selected.requires_reply ? <Badge tone="danger">{t("queue.needsReply")}</Badge> : null}
              </div>
            </div>
            <p className={`detail-summary-copy${summaryText ? "" : " is-fallback"}`} title={summaryText || summaryFallback}>
              {summaryText || summaryFallback}
            </p>
            {shouldOfferSummaryRefresh ? (
              <button
                className="button button-ghost summary-regenerate"
                type="button"
                onClick={props.onRegenerateSummary}
                disabled={props.actionLoading === "summary"}
              >
                {props.actionLoading === "summary"
                  ? t("detail.generating")
                  : summaryActionLabel}
              </button>
            ) : null}
            <div className="summary-grid">
              <SummaryPoint label={t("detail.reply")} value={props.replyLanguage.toUpperCase()} />
              <SummaryPoint label={t("detail.attachmentsTitle")} value={attachmentCount} />
              <SummaryPoint label={t("detail.thread")} value={props.thread.length} />
            </div>
          </div>

          {props.mode === "reply" ? (
            <div className="modal-columns">
              <div className="modal-column modal-thread-column">
                {threadSection}
              </div>

              <div className="modal-column modal-compose-column">
                <div className="section-title-row">
                  <h4 className="section-title">{t("detail.replyTitle")}</h4>
                  <div className="inline-badges">
                    <Badge tone="accent">{props.replyLanguage.toUpperCase()}</Badge>
                    {selected.preferred_reply_language ? <Badge tone="neutral">{selected.preferred_reply_language.toUpperCase()}</Badge> : null}
                  </div>
                </div>

                <div className="compose-panel">
                  <div className="compose-toolbar">
                    <button className="button button-ghost" type="button" onClick={() => props.onTranslateDraft("ru")} disabled={props.actionLoading === "draft" || !props.draftText.trim()}>
                      {t("detail.translateRu")}
                    </button>
                    <button className="button button-ghost" type="button" onClick={() => props.onTranslateDraft("en")} disabled={props.actionLoading === "draft" || !props.draftText.trim()}>
                      {t("detail.translateEn")}
                    </button>
                    <button className="button button-ghost" type="button" onClick={() => props.onTranslateDraft("tr")} disabled={props.actionLoading === "draft" || !props.draftText.trim()}>
                      {t("detail.translateTr")}
                    </button>
                    <button className="button button-secondary" type="button" onClick={props.onGenerateDraft} disabled={props.actionLoading === "draft"}>
                      {props.actionLoading === "draft" ? t("detail.generating") : t("detail.generateDraft")}
                    </button>
                  </div>

                  <Field label={t("detail.to")} full>
                    <input value={props.replyTo} onChange={(event) => props.onReplyToChange(event.target.value)} placeholder="recipient@example.com" />
                  </Field>

                  <div className="compose-two-up">
                    <Field label={t("detail.cc")} full>
                      <input value={props.replyCc} onChange={(event) => props.onReplyCcChange(event.target.value)} placeholder="cc@example.com" />
                    </Field>
                    <Field label={t("detail.bcc")} full>
                      <input value={props.replyBcc} onChange={(event) => props.onReplyBccChange(event.target.value)} placeholder="bcc@example.com" />
                    </Field>
                  </div>

                  <Field label={t("detail.subject")} full>
                    <input value={props.replySubject} onChange={(event) => props.onReplySubjectChange(event.target.value)} placeholder={t("queue.noSubject")} />
                  </Field>

                  <Field label={t("detail.customPrompt")} full hint={t("detail.customPromptHint")}>
                    <textarea
                      rows={4}
                      value={props.replyPrompt}
                      onChange={(event) => props.onReplyPromptChange(event.target.value)}
                      placeholder={t("detail.customPromptPlaceholder")}
                    />
                  </Field>

                  <Field label={t("detail.draftTitle")} full hint={t("detail.replyDraftHint")}>
                    {props.actionLoading === "draft" ? (
                      <div className="draft-skeleton">
                        <div className="skeleton skeleton-line" />
                        <div className="skeleton skeleton-line" />
                        <div className="skeleton skeleton-line" style={{ width: "60%" }} />
                      </div>
                    ) : (
                      <textarea
                        className="draft-textarea"
                        rows={8}
                        value={props.draftText}
                        onChange={(event) => props.onDraftChange(event.target.value)}
                        placeholder={t("detail.draftPlaceholder")}
                      />
                    )}
                  </Field>

                  <Field label={t("detail.signature")} full hint={t("detail.signatureHint")}>
                    <textarea rows={4} value={props.replySignature} onChange={(event) => props.onReplySignatureChange(event.target.value)} placeholder={t("detail.signaturePlaceholder")} />
                  </Field>

                  {originalMessageSection}

                  <div className="compose-actions">
                    {!isOutbound && (
                      <>
                        <button className="button button-ghost" type="button" onClick={props.onArchive}>
                          <Archive size={16} aria-hidden="true" />
                          {t("detail.archive")}
                        </button>
                        <button className="button button-ghost" type="button" onClick={props.onSpam}>
                          <Ban size={16} aria-hidden="true" />
                          {t("detail.markSpam")}
                        </button>
                        <button className="button button-ghost" type="button" onClick={props.onReplyLater}>
                          <Clock size={16} aria-hidden="true" />
                          {t("detail.later")}
                        </button>
                      </>
                    )}
                    <button className="button button-primary" type="button" onClick={props.onSendReply} disabled={props.actionLoading === "reply"}>
                      {props.actionLoading === "reply" ? t("detail.sending") : t("detail.sendDraft")}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="detail-read-stack">
              {threadSection}
              {attachmentsSection}
              <section className="detail-section-card read-preview-panel">
                <div className="read-panel">
                  <div className="read-actions">
                    {!isOutbound && (
                      <>
                        <button className="button button-ghost" type="button" onClick={props.onArchive}>
                          <Archive size={16} aria-hidden="true" />
                          {t("detail.archive")}
                        </button>
                        <button className="button button-ghost" type="button" onClick={props.onSpam}>
                          <Ban size={16} aria-hidden="true" />
                          {t("detail.markSpam")}
                        </button>
                        <button className="button button-ghost" type="button" onClick={props.onReplyLater}>
                          <Clock size={16} aria-hidden="true" />
                          {t("detail.later")}
                        </button>
                        <button className="button button-primary modal-primary-action" type="button" onClick={() => props.onModeChange("reply")}>
                          {t("detail.replyNow")}
                        </button>
                      </>
                    )}
                  </div>
                  <div className="read-preview">
                    <Field label={selected.ai_draft_reply ? t("detail.reply") : t("detail.aiSummary")} full hint={t("detail.replyHint")}>
                      <p className="read-preview-copy" title={selected.ai_draft_reply || summaryText || summaryFallback}>
                        {selected.ai_draft_reply || summaryText || summaryFallback}
                      </p>
                    </Field>
                    <div className="detail-meta-grid">
                      <SummaryPoint label={t("detail.to")} value={recipientList.length ? recipientList.join(", ") : "—"} />
                      <SummaryPoint label={t("detail.cc")} value={ccList.length ? ccList.join(", ") : "—"} />
                      <SummaryPoint label={t("detail.bcc")} value={bccList.length ? bccList.join(", ") : "—"} />
                    </div>
                  </div>
                  {originalMessageSection}
                </div>
              </section>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
