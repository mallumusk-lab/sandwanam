import { branches } from "../../api/endpoints.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useAsync } from "../../hooks/useAsync.js";

/** Letterhead for documents that aren't tied to a loan: the selected or own branch. */
export function useLetterhead() {
  const { user, branch } = useAuth();
  const { data } = useAsync((signal) => branches.list({ signal }), []);
  const code = branch || user.branch;
  return data?.find((b) => b.code === code) ?? data?.find((b) => b.is_head_office) ?? null;
}
