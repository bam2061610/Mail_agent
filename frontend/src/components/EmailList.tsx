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

function cleanText(raw: string | null | undefined): string {
  if (!raw) return "";
  // Remove HTML tags and collapse whitespace for safe preview rendering.
  const stripped = raw.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  // Drop likely JSON garbage returned by analysis.
  if (stripped.startsWith("{") || stripped.startsWith("[")) return "";
  return stripped;
}

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
          <p className="section-subtitle">{props.emails.length} {t("queue.emailsCount")}</p>
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
          const rawSummary = cleanText(email.ai_summary);
          const rawBody = cleanText(email.body_text);
          const isAnalyzing = !email.ai_analyzed;
          const summary = isAnalyzing
            ? t("queue.analyzing")
            : rawSummary || rawBody || t("queue.noPreview");
          return (
            <article
              key={email.id}
              className={`email-row${isSelected ? " is-selected" : ""}${email.priority === "critical" ? " priority-critical" : email.priority === "high" ? " priority-high" : ""}`}
              onClick={() => props.onSelectEmail(email.id)}
            >
              <div className="email-row-main">
                <div className="email-row-title">
                  <div>
                    <h4 title={email.subject || t("queue.noSubject")}>{email.subject || t("queue.noSubject")}</h4>
                    <p title={email.sender_name || email.sender_email || t("queue.unknownSender")}>{email.sender_name || email.sender_email || t("queue.unknownSender")}</p>
                  </div>
                  <Badge tone={email.status === "spam" ? "danger" : email.direction === "sent" ? "accent" : "neutral"}>
                    {email.direction === "sent" ? t("status.sent") : email.status}
                  </Badge>
                </div>
                <p className={`email-row-summary${isAnalyzing ? " summary-analyzing" : ""}`}>
                  {summary}
                </p>
                <div className="email-row-meta">
                  <span>{email.date_received ? new Date(email.date_received).toLocaleString() : t("queue.justNow")}</span>
                  {email.attachment_count ? <span>{t("queue.attachments", { count: email.attachment_count })}</span> : null}
                </div>
              </div>
              <div className="email-row-actions">
                {props.view === "spam" ? (
                  <button
                    className="button button-ghost icon-action"
                    type="button"
                    title={t("detail.restoreActive")}
                    aria-label={t("detail.restoreActive")}
                    onClick={(event) => {
                      event.stopPropagation();
                      props.onRestoreEmail(email.id);
                    }}
                  >
                    ↩
                  </button>
                ) : (
                  <>
                    <button
                      className="button button-ghost icon-action"
                      type="button"
                      title={t("detail.archive")}
                      aria-label={t("detail.archive")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onArchiveEmail(email.id);
                      }}
                    >
                      🗄
                    </button>
                    <button
                      className="button button-ghost icon-action"
                      type="button"
                      title={t("detail.markSpam")}
                      aria-label={t("detail.markSpam")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onSpamEmail(email.id);
                      }}
                    >
                      🚫
                    </button>
                    <button
                      className="button button-ghost icon-action"
                      type="button"
                      title={t("detail.later")}
                      aria-label={t("detail.later")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onReplyLaterEmail(email.id);
                      }}
                    >
                      ⏰
                    </button>
                    <button
                      className="button button-secondary icon-action"
                      type="button"
                      title={t("detail.replyWithAi")}
                      aria-label={t("detail.replyWithAi")}
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onReplyWithAi(email.id);
                      }}
                    >
                      ✦
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
