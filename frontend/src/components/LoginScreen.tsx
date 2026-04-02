import React from "react";
import { Field } from "./common/Field";
import type { LoginFormState } from "../types";

type LoginScreenProps = {
  loginForm: LoginFormState;
  actionLoading: string | null;
  errorMessage?: string;
  successMessage?: string;
  onChange: (next: LoginFormState) => void;
  onSubmit: (event: React.FormEvent) => void;
};

export function LoginScreen(props: LoginScreenProps) {
  return (
    <section className="panel" style={{ maxWidth: 480, margin: "48px auto" }}>
      <div className="panel-header">
        <div>
          <h3 className="panel-title">Team login</h3>
          <p className="panel-subtitle">Sign in to access Orhun Mail Agent workspace.</p>
        </div>
      </div>
      <div className="panel-body">
        {props.errorMessage ? <div className="error-banner" role="alert" style={{ marginBottom: 12 }}>{props.errorMessage}</div> : null}
        {props.successMessage ? <div className="success-banner" style={{ marginBottom: 12 }}>{props.successMessage}</div> : null}
        <form onSubmit={props.onSubmit}>
          <div className="settings-grid">
            <Field label="Email" full>
              <input
                value={props.loginForm.email}
                onChange={(event) => props.onChange({ ...props.loginForm, email: event.target.value })}
                autoComplete="username"
              />
            </Field>
            <Field label="Password" full>
              <input
                type="password"
                value={props.loginForm.password}
                onChange={(event) => props.onChange({ ...props.loginForm, password: event.target.value })}
                autoComplete="current-password"
              />
            </Field>
          </div>
          <div className="detail-toolbar full" style={{ marginTop: 16 }}>
            <button className="primary-button" type="submit" disabled={props.actionLoading === "auth-login"}>
              {props.actionLoading === "auth-login" ? "Signing in..." : "Sign in / Войти"}
            </button>
          </div>
          <p className="panel-subtitle" style={{ marginTop: 8, fontSize: 12 }}>
            Default credentials on first run: admin@orhun.local / admin123
          </p>
        </form>
      </div>
    </section>
  );
}
