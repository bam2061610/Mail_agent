import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, FormEvent, SetStateAction } from "react";
import { AUTH_TOKEN_CLEARED_EVENT, AUTH_TOKEN_UPDATED_EVENT, ApiError, apiGet, apiPost, clearStoredAuthToken, getErrorMessage, getStoredAuthToken, saveStoredAuthToken } from "../api";
import { initialLoginForm, type AuthLoginResponse, type AuthMeResponse, type LoginFormState, type UserItem } from "../types";

type UseAuthResult = {
  authToken: string;
  currentUser: UserItem | null;
  authLoading: boolean;
  loginForm: LoginFormState;
  setLoginForm: Dispatch<SetStateAction<LoginFormState>>;
  bootstrapAuth: () => Promise<void>;
  handleLogin: (event: FormEvent) => Promise<void>;
  handleLogout: () => Promise<void>;
  authError: string;
  authSuccess: string;
  actionLoading: string | null;
};

export function useAuth(enabled = true): UseAuthResult {
  const [authToken, setAuthToken] = useState<string>(() => getStoredAuthToken());
  const [currentUser, setCurrentUser] = useState<UserItem | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loginForm, setLoginForm] = useState<LoginFormState>(initialLoginForm);
  const [authError, setAuthError] = useState("");
  const [authSuccess, setAuthSuccess] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const authMutationVersionRef = useRef(0);

  const bootstrapAuth = useCallback(async () => {
    const mutationVersion = authMutationVersionRef.current;
    setAuthLoading(true);
    try {
      if (!enabled) {
        if (mutationVersion !== authMutationVersionRef.current) return;
        setCurrentUser(null);
        setAuthError("");
        return;
      }
      if (!authToken) {
        if (mutationVersion !== authMutationVersionRef.current) return;
        setCurrentUser(null);
        return;
      }
      const me = await apiGet<AuthMeResponse>("/api/auth/me");
      if (mutationVersion !== authMutationVersionRef.current) return;
      setCurrentUser(me.user);
      setAuthError("");
    } catch (error) {
      if (mutationVersion !== authMutationVersionRef.current) return;
      if (error instanceof ApiError && error.status === 401) {
        clearStoredAuthToken();
        setAuthToken("");
        setAuthError("Session expired. Please sign in again.");
      } else {
        setAuthError(getErrorMessage(error, "Unable to verify your session. Please sign in again."));
      }
      setCurrentUser(null);
    } finally {
      if (mutationVersion !== authMutationVersionRef.current) return;
      setAuthLoading(false);
    }
  }, [authToken, enabled]);

  const handleLogin = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    setAuthError("");
    setAuthSuccess("");
    if (!enabled) {
      setAuthError("Setup is required before sign-in.");
      return;
    }
    if (!loginForm.email.trim() || !loginForm.password) {
      setAuthError("Email and password are required.");
      return;
    }
    setActionLoading("auth-login");
    try {
      const response = await apiPost<AuthLoginResponse>("/api/auth/login", loginForm);
      authMutationVersionRef.current += 1;
      saveStoredAuthToken(response.access_token);
      setAuthToken(response.access_token);
      setCurrentUser(response.user);
      setAuthLoading(false);
      setAuthSuccess("Logged in.");
    } catch (error) {
      setAuthError(getErrorMessage(error, "Login failed."));
    } finally {
      setActionLoading(null);
    }
  }, [enabled, loginForm]);

  const handleLogout = useCallback(async () => {
    setActionLoading("auth-logout");
    try {
      await apiPost("/api/auth/logout", {});
    } catch {
      // best effort logout
    } finally {
      authMutationVersionRef.current += 1;
      clearStoredAuthToken();
      setAuthToken("");
      setCurrentUser(null);
      setAuthError("");
      setAuthSuccess("");
      setActionLoading(null);
    }
  }, []);

  useEffect(() => {
    const handleTokenUpdate = () => setAuthToken(getStoredAuthToken());
    window.addEventListener(AUTH_TOKEN_UPDATED_EVENT, handleTokenUpdate);
    window.addEventListener(AUTH_TOKEN_CLEARED_EVENT, handleTokenUpdate);
    return () => {
      window.removeEventListener(AUTH_TOKEN_UPDATED_EVENT, handleTokenUpdate);
      window.removeEventListener(AUTH_TOKEN_CLEARED_EVENT, handleTokenUpdate);
    };
  }, []);

  useEffect(() => {
    void bootstrapAuth();
  }, [bootstrapAuth]);

  return {
    authToken,
    currentUser,
    authLoading,
    loginForm,
    setLoginForm,
    bootstrapAuth,
    handleLogin,
    handleLogout,
    authError,
    authSuccess,
    actionLoading,
  };
}
