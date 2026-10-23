import { api, download } from "./client.js";

const enc = encodeURIComponent;

export const auth = {
  me: (options) => api.get("/auth/me", options),
  login: (username, password) => api.post("/auth/login", { username, password }),
  logout: () => api.post("/auth/logout"),
  changePassword: (current_password, new_password) => api.post("/auth/change-password", { current_password, new_password }),
};

export const branches = {
  list: (options) => api.get("/branches", options),
};

export const customers = {
  search: (query, options) => api.get("/customers", { ...options, query }),
  get: (id, options) => api.get(`/customers/${enc(id)}`, options),
  create: (body) => api.post("/customers", body),
};

export const loans = {
  create: (body) => api.post("/loans", body),
  get: (loanNumber, options) => api.get(`/loans/${enc(loanNumber)}`, options),
  closingQuote: (loanNumber, options) => api.get(`/loans/${enc(loanNumber)}/closing-quote`, options),
  collect: (loanNumber, body) => api.post(`/loans/${enc(loanNumber)}/collections`, body),
  topUp: (loanNumber, body) => api.post(`/loans/${enc(loanNumber)}/top-ups`, body),
  close: (loanNumber, body) => api.post(`/loans/${enc(loanNumber)}/close`, body),
  setItems: (loanNumber, items) => api.put(`/loans/${enc(loanNumber)}/items`, { items }),
  setFollowUp: (loanNumber, follow_up_date) => api.put(`/loans/${enc(loanNumber)}/follow-up`, { follow_up_date }),
};

export const receipts = {
  loan: (loanNumber, options) => api.get(`/receipts/loans/${enc(loanNumber)}`, options),
  entry: (statementId, options) => api.get(`/receipts/statements/${enc(statementId)}`, options),
};

export const imports = {
  preview: (body) => api.post("/imports/preview", body),
  commit: (body) => api.post("/imports", body),
};

export const dashboard = {
  summary: (branch, options) => api.get("/dashboard", { ...options, query: { branch } }),
  performance: (query, options) => api.get("/dashboard/performance", { ...options, query }),
  details: (metric, query, options) => api.get(`/dashboard/details/${enc(metric)}`, { ...options, query }),
};

export const reports = {
  transactions: (query, options) => api.get("/reports/transactions", { ...options, query }),
  exportCsv: (query) => download("/reports/transactions.csv", query, "transactions.csv"),
};

export const settings = {
  goldRate: (options) => api.get("/settings/gold-rate", options),
  setGoldRate: (per_gram) => api.put("/settings/gold-rate", { per_gram }),
  auditLogs: (query, options) => api.get("/audit-logs", { ...options, query }),
};

export const backup = {
  check: (body) => api.post("/backup/check", body, { timeout: 120000 }),
  restore: (body) => api.post("/backup/restore", body, { timeout: 120000 }),
  emailSettings: (options) => api.get("/backup/email", options),
  setEmail: (body) => api.put("/backup/email", body),
  sendNow: () => api.post("/backup/email/send", undefined, { timeout: 120000 }),
};

export const cash = {
  overview: (branch, options) => api.get("/cash", { ...options, query: { branch } }),
  startDay: (body) => api.post("/cash/days", body),
  addEntry: (dayId, body) => api.post(`/cash/days/${enc(dayId)}/entries`, body),
  voidEntry: (entryId, reason) => api.post(`/cash/entries/${enc(entryId)}/void`, { reason }),
  closeDay: (dayId, body) => api.post(`/cash/days/${enc(dayId)}/close`, body),
  reopenDay: (dayId) => api.post(`/cash/days/${enc(dayId)}/reopen`),
};

export const admin = {
  accounts: (options) => api.get("/admin/accounts", options),
  createBranch: (body) => api.post("/admin/branches", body),
  update: (username, body) => api.patch(`/admin/accounts/${enc(username)}`, body),
  resetPassword: (username, temporary_password) => api.post(`/admin/accounts/${enc(username)}/reset-password`, { temporary_password }),
  setActive: (username, active) => api.post(`/admin/accounts/${enc(username)}/active`, { active }),
  unlock: (username) => api.post(`/admin/accounts/${enc(username)}/unlock`),
  remove: (username) => api.del(`/admin/accounts/${enc(username)}`),
};
