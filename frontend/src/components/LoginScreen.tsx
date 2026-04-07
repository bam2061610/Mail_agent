import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Field } from "./common/Field";
import type { LoginFormState } from "../types";

type LoginScreenProps = {
  loginForm: LoginFormState;
  actionLoading: string | null;
  errorMessage?: string;
  successMessage?: string;
  onChange: (next: LoginFormState) => void;
  onSubmit: (event: FormEvent) => void;
};

export function LoginScreen(props: LoginScreenProps) {
  const { t } = useTranslation();

  return (
    <section className="auth-shell">
      <div className="auth-card">
        <div className="auth-mark" />
        <div className="auth-copy">
          <h1>{t("auth.teamLogin")}</h1>
          <p>{t("auth.signinHint")}</p>
        </div>
        {props.errorMessage ? <div className="banner banner-error" role="alert">{props.errorMessage}</div> : null}
        {props.successMessage ? <div className="banner banner-success">{props.successMessage}</div> : null}
        <form className="auth-form" onSubmit={props.onSubmit}>
          <Field label={t("auth.email")} full>
            <input
              value={props.loginForm.email}
              onChange={(event) => props.onChange({ ...props.loginForm, email: event.target.value })}
              autoComplete="username"
              placeholder="name@example.com"
            />
          </Field>
          <Field label={t("auth.password")} full>
            <input
              type="password"
              value={props.loginForm.password}
              onChange={(event) => props.onChange({ ...props.loginForm, password: event.target.value })}
              autoComplete="current-password"
              placeholder="••••••••"
            />
          </Field>
          <button className="button button-primary" type="submit" disabled={props.actionLoading === "auth-login"}>
            {props.actionLoading === "auth-login" ? t("auth.signingIn") : t("auth.signin")}
          </button>
          <p className="helper-text">{t("auth.provisioningHint")}</p>
        </form>
      </div>
    </section>
  );
}
