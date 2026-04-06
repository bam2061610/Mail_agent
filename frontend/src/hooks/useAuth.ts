import { useCallback, useEffect, useState } from "react";
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

export function useAuth(): UseAuthResult {
  const [authToken, setAuthToken] = useState<string>(() => getStoredAuthToken());
  const [currentUser, setCurrentUser] = useState<UserItem | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loginForm, setLoginForm] = useState<LoginFormState>(initialLoginForm);
  const [authError, setAuthError] = useState("");
  const [authSuccess, setAuthSuccess] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const bootstrapAuth = useCallback(async () => {
    setAuthLoading(true);
    try {
      if (!authToken) {
        setCurrentUser(null);
        setAuthError("");
        return;
      }
      const me = await apiGet<AuthMeResponse>("/api/auth/me");
      setCurrentUser(me.user);
      setAuthError("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearStoredAuthToken();
        setAuthToken("");
        setAuthError("Session expired. Please sign in again.");
      } else {
        setAuthError(getErrorMessage(error, "Unable to verify your session. Please sign in again."));
      }
      setCurrentUser(null);
    } finally {
      setAuthLoading(false);
    }
  }, [authToken]);

  const handleLogin = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    setAuthError("");
    setAuthSuccess("");
    if (!loginForm.email.trim() || !loginForm.password) {
      setAuthError("Email and password are required.");
      return;
    }
    setActionLoading("auth-login");
    try {
      const response = await apiPost<AuthLoginResponse>("/api/auth/login", loginForm);
      saveStoredAuthToken(response.access_token);
      setAuthToken(response.access_token);
      setCurrentUser(response.user);
      setAuthSuccess("Logged in.");
    } catch (error) {
      setAuthError(getErrorMessage(error, "Login failed."));
    } finally {
      setActionLoading(null);
    }
  }, [loginForm]);

  const handleLogout = useCallback(async () => {
    setActionLoading("auth-logout");
    try {
      await apiPost("/api/auth/logout", {});
    } catch {
      // best effort logout
    } finally {
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
