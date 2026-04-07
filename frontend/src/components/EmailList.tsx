import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Archive, Ban, Check, Clock, Sparkles, Undo2 } from "lucide-react";
import type { EmailItem, MailView } from "../types";
import { Badge } from "./common/Badge";
import { ImportanceBadge } from "./common/ImportanceBadge";

type EmailListProps = {
  view: MailView;
  emails: EmailItem[];
  selectedEmailId: number | null;
  loading: boolean;
  search: string;
  onSearchChange: (value: string) => void;
  onSelectEmail: (emailId: number) => void;
  onArchiveEmail: (emailId: number) => void;
  onMarkProcessed: (emailId: number) => void;
  onSpamEmail: (emailId: number) => void;
  onRestoreEmail: (emailId: number) => void;
  onReplyLaterEmail: (emailId: number) => void;
  onReplyWithAi: (emailId: number) => void;
};

type EmailFilter = "all" | "important" | "needsReply";

function cleanText(raw: string | null | undefined): string {
  if (!raw) return "";
  const stripped = raw.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  if (stripped.startsWith("{") || stripped.startsWith("[")) return "";
  return stripped;
}

export function EmailList(props: EmailListProps) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<EmailFilter>("all");

  const heading = props.view === "inbox"
    ? t("nav.inbox", { defaultValue: "Inbox" })
    : props.view === "sent"
      ? t("nav.sent")
      : props.view === "spam"
        ? t("nav.spam")
        : props.view === "processed"
          ? t("nav.processed")
        : t("nav.settings");

  useEffect(() => {
    setFilter("all");
  }, [props.view]);

  const visibleEmails = useMemo(() => {
    const filtered = props.emails.filter((email) => {
      if (filter === "important") {
        return (email.importance_score ?? 0) >= 7;
      }
      if (filter === "needsReply") {
        return email.requires_reply;
      }
      return true;
    });

    return [...filtered].sort((left, right) => {
      const leftScore = left.importance_score ?? -1;
      const rightScore = right.importance_score ?? -1;
      if (leftScore !== rightScore) {
        return rightScore - leftScore;
      }

      const leftDate = left.date_received ? Date.parse(left.date_received) : 0;
      const rightDate = right.date_received ? Date.parse(right.date_received) : 0;
      if (leftDate !== rightDate) {
        return rightDate - leftDate;
      }

      return right.id - left.id;
    });
  }, [filter, props.emails]);

  const filterOptions: Array<{ value: EmailFilter; label: string }> = [
    { value: "all", label: t("queue.filterAll") },
    { value: "important", label: t("queue.filterImportant") },
    { value: "needsReply", label: t("queue.needsReply") },
  ];

  return (
    <section className="list-panel">
      <div className="list-toolbar">
        <div>
          <h3 className="section-title">{heading}</h3>
          <p className="section-subtitle">{visibleEmails.length} {t("queue.emailsCount")}</p>
        </div>
        <label className="search">
          <span className="sr-only">{t("queue.searchPlaceholder")}</span>
          <input
            value={props.search}
            onChange={(event) => props.onSearchChange(event.target.value)}
            placeholder={t("queue.searchPlaceholder")}
          />
        </label>
      </div>

      <div className="list-filter-bar" role="toolbar" aria-label={t("queue.filtersLabel")}>
        {filterOptions.map((option) => (
          <button
            key={option.value}
            className={`button button-ghost list-filter-button${filter === option.value ? " is-active" : ""}`}
            type="button"
            aria-pressed={filter === option.value}
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="email-list">
        {props.loading ? (
          <div className="email-skeleton-list" aria-hidden="true">
            {Array.from({ length: 4 }).map((_, index) => (
              <article key={index} className="email-row skeleton-row">
                <div className="email-row-main">
                  <div className="skeleton skeleton-line skeleton-line-title" />
                  <div className="skeleton skeleton-line skeleton-line-subtitle" />
                  <div className="skeleton skeleton-line skeleton-line-summary" />
                  <div className="email-row-meta">
                    <div className="skeleton skeleton-chip" />
                    <div className="skeleton skeleton-chip" />
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : null}
        {!props.loading && visibleEmails.length === 0 ? (
          <div className="empty-state">
            <strong>{t("queue.clear")}</strong>
            <p>{t("queue.clearDesc")}</p>
          </div>
        ) : null}
        {visibleEmails.map((email) => {
          const isSelected = props.selectedEmailId === email.id;
          const summaryFromAi = cleanText(email.ai_summary);
          const summary = summaryFromAi || t("queue.analyzing");
          const showAiPrefix = Boolean(summaryFromAi);

          return (
            <article
              key={email.id}
              className={`email-row${isSelected ? " is-selected" : ""}${email.priority === "critical" ? " priority-critical" : email.priority === "high" ? " priority-high" : ""}`}
              onClick={() => props.onSelectEmail(email.id)}
            >
              <div className="email-row-main">
                <div className="email-row-title">
                  <div className="email-row-title-copy">
                    <div className="email-row-subject-line">
                      <h4 title={email.subject || t("queue.noSubject")}>{email.subject || t("queue.noSubject")}</h4>
                      {email.requires_reply ? <Badge tone="danger">{t("queue.needsReply")}</Badge> : null}
                    </div>
                    <p title={email.sender_name || email.sender_email || t("queue.unknownSender")}>{email.sender_name || email.sender_email || t("queue.unknownSender")}</p>
                  </div>
                  <Badge tone={email.status === "spam" ? "danger" : email.direction === "sent" || email.direction === "outbound" ? "accent" : "neutral"}>
                    {email.direction === "sent" || email.direction === "outbound" ? t("status.sent") : email.status}
                  </Badge>
                  {email.status === "spam" ? (
                    <Badge tone={email.spam_source === "ai_auto" ? "warning" : "neutral"}>
                      {email.spam_source === "ai_auto" ? t("spam.aiAuto") : t("spam.manual")}
                    </Badge>
                  ) : null}
                </div>
                <p className="email-row-summary" title={summary}>
                  {showAiPrefix ? (
                    <span className="email-row-summary-prefix">
                      <Sparkles size={12} aria-hidden="true" />
                      <span>{t("queue.aiLabel")}</span>
                    </span>
                  ) : null}
                  <span>{summary}</span>
                </p>
                <div className="email-row-meta">
                  <span>{email.date_received ? new Date(email.date_received).toLocaleString() : t("queue.justNow")}</span>
                  <ImportanceBadge score={email.importance_score} label={t("detail.importance")} />
                  {email.attachment_count ? <span>{t("queue.attachments", { count: email.attachment_count })}</span> : null}
                </div>
              </div>
              <div className="email-row-actions">
                {props.view === "spam" || props.view === "processed" ? (
                  <button
                    className="button button-ghost quick-action icon-action"
                    type="button"
                    data-tooltip={t("detail.restoreActive")}
                    aria-label={t("detail.restoreActive")}
                    onClick={(event) => {
                      event.stopPropagation();
                      props.onRestoreEmail(email.id);
                    }}
                  >
                    <Undo2 size={16} aria-hidden="true" />
                    <span className="icon-action-label">{t("detail.restoreActive")}</span>
                  </button>
                ) : (
                  <>
                    <button
                      className="button button-ghost quick-action icon-action"
                      type="button"
                      data-tooltip={t("detail.archive")}
                      aria-label={t("detail.archive")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onArchiveEmail(email.id);
                      }}
                    >
                      <Archive size={16} aria-hidden="true" />
                      <span className="icon-action-label">{t("detail.archive")}</span>
                    </button>
                    <button
                      className="button button-ghost quick-action icon-action"
                      type="button"
                      data-tooltip={t("detail.markProcessed")}
                      aria-label={t("detail.markProcessed")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onMarkProcessed(email.id);
                      }}
                    >
                      <Check size={16} aria-hidden="true" />
                      <span className="icon-action-label">{t("detail.markProcessed")}</span>
                    </button>
                    <button
                      className="button button-ghost quick-action icon-action"
                      type="button"
                      data-tooltip={t("detail.markSpam")}
                      aria-label={t("detail.markSpam")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onSpamEmail(email.id);
                      }}
                    >
                      <Ban size={16} aria-hidden="true" />
                      <span className="icon-action-label">{t("detail.markSpam")}</span>
                    </button>
                    <button
                      className="button button-ghost quick-action icon-action"
                      type="button"
                      data-tooltip={t("detail.later")}
                      aria-label={t("detail.later")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onReplyLaterEmail(email.id);
                      }}
                    >
                      <Clock size={16} aria-hidden="true" />
                      <span className="icon-action-label">{t("detail.later")}</span>
                    </button>
                    <button
                      className="button button-secondary quick-action icon-action"
                      type="button"
                      data-tooltip={t("detail.replyWithAi")}
                      aria-label={t("detail.replyWithAi")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onReplyWithAi(email.id);
                      }}
                    >
                      <Sparkles size={16} aria-hidden="true" />
                      <span className="icon-action-label">{t("detail.replyWithAi")}</span>
                    </button>
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
