import { useMemo } from "react";
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

export function EmailDetail(props: EmailDetailProps) {
  const { t } = useTranslation();

  const summaryText = useMemo(
    () => props.selectedEmail?.ai_summary || props.thread.find((item) => item.ai_summary)?.ai_summary || "",
    [props.selectedEmail, props.thread]
  );

  const quoteText = useMemo(() => {
    const selected = props.selectedEmail;
    if (!selected) return "";
    return selected.body_text || selected.body_html || "";
  }, [props.selectedEmail]);

  const selected = props.selectedEmail;
  const isOutbound = selected ? selected.direction === "sent" || selected.direction === "outbound" : false;
  const recipientList = splitValue(props.replyTo);
  const ccList = splitValue(props.replyCc);
  const bccList = splitValue(props.replyBcc);
  const attachmentCount = props.attachments.length || selected?.attachment_count || 0;
  const summaryFallback = selected && !selected.ai_analyzed ? t("queue.analyzing") : t("detail.noAnalysis");

  if (!props.open) {
    return (
      <section className="detail-panel email-detail-panel" aria-label={props.mode === "reply" ? t("detail.replyTitle") : t("detail.readTitle")}>
        <div className="detail-empty">
          <div className="empty-state">
            <strong>{t("detail.selectItem")}</strong>
            <p>{t("detail.selectItemDesc")}</p>
          </div>
        </div>
      </section>
    );
  }

  if (props.loading) {
    return (
      <section
        className="detail-panel email-detail-panel"
        role="dialog"
        aria-modal="true"
        aria-label={props.mode === "reply" ? t("detail.replyTitle") : t("detail.readTitle")}
      >
        <div className="modal-body modal-skeleton">
          <div className="skeleton skeleton-line skeleton-line-title" />
          <div className="skeleton skeleton-line skeleton-line-summary" />
          <div className="skeleton-stack">
            <div className="skeleton skeleton-panel" />
            <div className="skeleton skeleton-panel" />
            <div className="skeleton skeleton-panel" />
          </div>
        </div>
      </section>
    );
  }

  if (!selected) {
    return (
      <section
        className="detail-panel email-detail-panel"
        role="dialog"
        aria-modal="true"
        aria-label={props.mode === "reply" ? t("detail.replyTitle") : t("detail.readTitle")}
      >
        <div className="detail-empty">
          <div className="empty-state">
            <strong>{t("detail.selectItem")}</strong>
            <p>{t("detail.selectItemDesc")}</p>
          </div>
        </div>
      </section>
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

  return (
    <section
      className="detail-panel email-detail-panel"
      role="dialog"
      aria-modal="true"
      aria-label={props.mode === "reply" ? t("detail.replyTitle") : t("detail.readTitle")}
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
          <button className="button button-ghost mobile-back" type="button" onClick={props.onClose}>
            ← {t("detail.backToList")}
          </button>
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
          <p className={`detail-summary-copy${summaryText ? "" : " is-fallback"}`}>{summaryText || summaryFallback}</p>
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

                <div className="quote-block">
                  <div className="section-title-row">
                    <h5>{t("detail.originalMessage")}</h5>
                    <Badge tone="neutral">{t("detail.includeOriginal")}</Badge>
                  </div>
                  <blockquote>{quoteText || t("queue.noPreview")}</blockquote>
                </div>

                <div className="compose-actions">
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
                </div>
                <div className="read-preview">
                  <Field label={selected.ai_draft_reply ? t("detail.reply") : t("detail.originalMessage")} full hint={t("detail.replyHint")}>
                    <p className="read-preview-copy">{selected.ai_draft_reply || selected.body_text || selected.body_html || t("queue.noPreview")}</p>
                  </Field>
                  <div className="detail-meta-grid">
                    <SummaryPoint label={t("detail.to")} value={recipientList.length ? recipientList.join(", ") : "—"} />
                    <SummaryPoint label={t("detail.cc")} value={ccList.length ? ccList.join(", ") : "—"} />
                    <SummaryPoint label={t("detail.bcc")} value={bccList.length ? bccList.join(", ") : "—"} />
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </section>
  );
}
