import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { UserItem, ViewKey } from "../types";

type UseAppStateResult = {
  view: ViewKey;
  setView: Dispatch<SetStateAction<ViewKey>>;
  selectedEmailId: number | null;
  setSelectedEmailId: Dispatch<SetStateAction<number | null>>;
  loading: boolean;
  setLoading: Dispatch<SetStateAction<boolean>>;
  errorMessage: string;
  setErrorMessage: Dispatch<SetStateAction<string>>;
  successMessage: string;
  setSuccessMessage: Dispatch<SetStateAction<string>>;
  canRunScan: boolean;
  canSendReportEmail: boolean;
  canRunSentReview: boolean;
};

export function useAppState(currentUser: UserItem | null, _authToken: string): UseAppStateResult {
  const [view, setView] = useState<ViewKey>("focus");
  const [selectedEmailId, setSelectedEmailId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const canRunScan = useMemo(() => currentUser?.role !== "viewer", [currentUser]);
  const canRunSentReview = useMemo(
    () => currentUser?.role === "admin" || currentUser?.role === "manager",
    [currentUser]
  );
  const canSendReportEmail = useMemo(() => currentUser?.role !== "viewer", [currentUser]);

  return {
    view,
    setView,
    selectedEmailId,
    setSelectedEmailId,
    loading,
    setLoading,
    errorMessage,
    setErrorMessage,
    successMessage,
    setSuccessMessage,
    canRunScan,
    canSendReportEmail,
    canRunSentReview,
  };
}
