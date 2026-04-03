import { useTranslation } from "react-i18next";
import type { EmailItem, MailView } from "../types";
import { Badge } from "./common/Badge";

type EmailListProps = {
  view: MailView;
  emails: EmailItem[];
  selectedEmailId: number | null;
  loading: boolean;
  search: string;
  onSearchChange: (value: string) => void;
  onSelectEmail: (emailId: number) => void;
  onArchiveEmail: (emailId: number) => void;
  onSpamEmail: (emailId: number) => void;
  onRestoreEmail: (emailId: number) => void;
  onReplyLaterEmail: (emailId: number) => void;
  onReplyWithAi: (emailId: number) => void;
};

export function EmailList(props: EmailListProps) {
  const { t } = useTranslation();
  const heading = props.view === "inbox"
    ? t("nav.inbox", { defaultValue: "Inbox" })
    : props.view === "sent"
      ? t("nav.sent")
      : props.view === "spam"
        ? t("nav.spam")
        : t("nav.settings");

  return (
    <section className="list-panel">
      <div className="list-toolbar">
        <div>
          <h3 className="section-title">{heading}</h3>
          <p className="section-subtitle">{props.emails.length} emails</p>
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
        {!props.loading && props.emails.length === 0 ? (
          <div className="empty-state">
            <strong>{t("queue.clear")}</strong>
            <p>{t("queue.clearDesc")}</p>
          </div>
        ) : null}
        {props.emails.map((email) => {
          const isSelected = props.selectedEmailId === email.id;
          const summary = email.ai_summary || email.body_text || t("queue.noPreview");
          return (
            <article
              key={email.id}
              className={`email-row${isSelected ? " is-selected" : ""}`}
              onClick={() => props.onSelectEmail(email.id)}
            >
              <div className="email-row-main">
                <div className="email-row-title">
                  <div>
                    <h4 title={email.subject || t("queue.noSubject")}>{email.subject || t("queue.noSubject")}</h4>
                    <p title={email.sender_name || email.sender_email || t("queue.unknownSender")}>{email.sender_name || email.sender_email || t("queue.unknownSender")}</p>
                  </div>
                  <Badge tone={email.status === "spam" ? "danger" : email.direction === "sent" ? "accent" : "neutral"}>
                    {email.direction === "sent" ? "Sent" : email.status}
                  </Badge>
                </div>
                <p className="email-row-summary">{summary}</p>
                <div className="email-row-meta">
                  <span>{email.date_received ? new Date(email.date_received).toLocaleString() : "Just now"}</span>
                  {email.attachment_count ? <span>{t("queue.attachments", { count: email.attachment_count })}</span> : null}
                </div>
              </div>
              <div className="email-row-actions">
                {props.view === "spam" ? (
                  <button
                    className="button button-ghost quick-action"
                    type="button"
                    data-tooltip={t("detail.restoreActive")}
                    onClick={(event) => {
                      event.stopPropagation();
                      props.onRestoreEmail(email.id);
                    }}
                  >
                    {t("detail.restoreActive")}
                  </button>
                ) : (
                  <>
                    <button
                      className="button button-ghost quick-action"
                      type="button"
                      data-tooltip={t("detail.archive")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onArchiveEmail(email.id);
                      }}
                    >
                      {t("detail.archive")}
                    </button>
                    <button
                      className="button button-ghost quick-action"
                      type="button"
                      data-tooltip={t("detail.markSpam")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onSpamEmail(email.id);
                      }}
                    >
                      {t("detail.markSpam")}
                    </button>
                    <button
                      className="button button-ghost quick-action"
                      type="button"
                      data-tooltip={t("detail.later")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onReplyLaterEmail(email.id);
                      }}
                    >
                      {t("detail.later")}
                    </button>
                    <button
                      className="button button-secondary quick-action"
                      type="button"
                      data-tooltip={t("detail.replyWithAi")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onReplyWithAi(email.id);
                      }}
                    >
                      {t("detail.replyWithAi")}
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
