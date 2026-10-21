import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { onSessionExpired, setCsrfToken } from "../api/client.js";
import { auth } from "../api/endpoints.js";

// The previous version kept the signed-in role in these keys, where anyone could edit it.
const LEGACY_KEYS = ["persist:root", "myfinData", "selectedUser"];
const BRANCH_KEY = "branch";

// Exported for tests, which render pages with a fixed signed-in user.
export const AuthContext = createContext(null);

function readBranch() {
  try {
    return sessionStorage.getItem(BRANCH_KEY) ?? "";
  } catch {
    return "";
  }
}

export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", user: null, notice: null, error: null });
  const [branch, setBranchState] = useState(readBranch);

  const lastUser = useRef(null);
  const clearBranch = useCallback(() => {
    setBranchState("");
    try {
      sessionStorage.removeItem(BRANCH_KEY);
    } catch {
      // ignore
    }
  }, []);

  const accept = useCallback(({ user, csrf_token: csrf }) => {
    if (lastUser.current && lastUser.current !== user.username) clearBranch();
    lastUser.current = user.username;
    setCsrfToken(csrf);
    setState({ status: "signed-in", user, notice: null, error: null });
    return user;
  }, [clearBranch]);

  const restore = useCallback(() => {
    setState((current) => ({ ...current, status: "loading", error: null }));
    auth
      .me()
      .then(accept)
      .catch((error) => {
        setCsrfToken(null);
        if (error.status === 401) setState({ status: "signed-out", user: null, notice: null, error: null });
        else setState({ status: "error", user: null, notice: null, error });
      });
  }, [accept]);

  useEffect(() => {
    for (const key of LEGACY_KEYS) {
      try {
        localStorage.removeItem(key);
      } catch {
        // Storage may be blocked; nothing sensitive is read from it any more.
      }
    }
    restore();
  }, [restore]);

  useEffect(
    () =>
      onSessionExpired(() => {
        setCsrfToken(null);
        clearBranch();
        setState({ status: "signed-out", user: null, notice: "Your session has ended. Please sign in again.", error: null });
      }),
    [clearBranch],
  );

  const login = useCallback(async (username, password) => accept(await auth.login(username, password)), [accept]);

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } finally {
      setCsrfToken(null);
      clearBranch();
      lastUser.current = null;
      setState({ status: "signed-out", user: null, notice: "You have signed out.", error: null });
    }
  }, [clearBranch]);

  const changePassword = useCallback(
    async (current, next) => accept(await auth.changePassword(current, next)),
    [accept],
  );

  const setBranch = useCallback((value) => {
    setBranchState(value);
    try {
      if (value) sessionStorage.setItem(BRANCH_KEY, value);
      else sessionStorage.removeItem(BRANCH_KEY);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo(
    () => ({
      ...state,
      // Branch accounts always see their own branch; head office may pick one ("" = all).
      branch: state.user?.is_head_office ? branch : state.user?.branch ?? "",
      setBranch,
      login,
      logout,
      changePassword,
      restore,
    }),
    [state, branch, setBranch, login, logout, changePassword, restore],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
