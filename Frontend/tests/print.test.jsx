// Receipts (shared sheet descriptions, the Share button) and the Backups page (file check,
// Import backup, backup email), server-rendered like pages.test.jsx.
import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { Route, Routes } from "react-router-dom";
import { StaticRouter } from "react-router-dom/server";
import { AuthContext } from "../src/auth/AuthContext.jsx";
import BackupPage, { CheckReport, EmailDetails, ImportBackup } from "../src/features/backup/BackupPage.jsx";
import EntryReceiptPage, { entrySheet } from "../src/print/EntryReceiptPage.jsx";
import LoanReceiptPage, { loanSheet } from "../src/print/LoanReceiptPage.jsx";
import { Sheet } from "../src/print/printing.jsx";
import { mailtoLink, pdfFileName, whatsappLink } from "../src/print/ShareReceipt.jsx";
import { ToastProvider } from "../src/ui/feedback.jsx";

globalThis.document ??= { title: "" };

const ALL = ["dashboard", "userlist", "newcustomer", "report", "history", "performance"];
const BRANCH_USER = {
  username: "User1", display_name: "Santhwanam", account_type: "branch", branch: "SAN", is_head_office: false,
  is_superadmin: false, permissions: ["userlist", "newcustomer", "report"], must_change_password: false,
};
const HQ_USER = { ...BRANCH_USER, username: "hq", account_type: "hq", branch: null, is_head_office: true, permissions: ALL };
const SUPERADMIN = { ...HQ_USER, username: "root", account_type: "superadmin", is_superadmin: true, permissions: ["newcustomer", "userlist"] };

function renderAt(path, element, user = BRANCH_USER, pattern = path) {
  const auth = { status: "signed-in", user, branch: user.branch ?? "", setBranch() {}, login() {}, logout() {}, changePassword() {}, restore() {} };
  return renderToStaticMarkup(
    <StaticRouter location={path}>
      <ToastProvider>
        <AuthContext.Provider value={auth}>
          <Routes>
            <Route path={pattern} element={element} />
          </Routes>
        </AuthContext.Provider>
      </ToastProvider>
    </StaticRouter>,
  );
}

const render = (node) => renderToStaticMarkup(<StaticRouter location="/"><ToastProvider>{node}</ToastProvider></StaticRouter>);

const LETTERHEAD = { name: "Santhwanam", legal_name: "Santhwanam Gold Loans", address: "Main Road", email: null, phone: "9876543210", logo: null };
const CUSTOMER = { name: "Anu", phone: "9876543210", customer_number: "SAN12", address: "Kochi" };
const LOAN = {
  loan_number: "SAN1L1", date: "2026-10-20", tenure_months: 12, items_text: "Ring", item_count: 1, rate: "18.00",
  gross_weight: "10.00", deduction: "0.50", net_weight: "9.50", principal: "100000.00",
};
const LOAN_RECEIPT = { letterhead: LETTERHEAD, customer: CUSTOMER, loan: LOAN, printed_on: "2026-10-21" };

function entryReceipt(entry, extra = {}) {
  return {
    letterhead: LETTERHEAD, customer: CUSTOMER, loan: LOAN, is_closing: false, closing_writeoff: null, ...extra,
    entry: {
      id: 7, kind: "addColl", date: "2026-10-22", amount_paid: "30000.00", interest_paid: "0.00", principal_change: "-30000.00",
      principal_balance: "70000.00", interest_balance: "0.00", accrued_days: 0, in_first_week: true, ...entry,
    },
  };
}

test("receipt toolbars put Share beside Print, disabled until the receipt loads", () => {
  for (const html of [
    renderAt("/print/loan/SAN1L1", <LoanReceiptPage />, BRANCH_USER, "/print/loan/:loanNumber"),
    renderAt("/print/entry/7", <EntryReceiptPage />, BRANCH_USER, "/print/entry/:statementId"),
  ]) {
    const toolbar = /<div class="print-toolbar no-print">[\s\S]*?<\/div><\/div>/.exec(html)[0];
    assert.match(toolbar, /<button type="button" class="btn btn-secondary" disabled="">[\s\S]*?Share<\/button><button type="button" class="btn btn-primary">[\s\S]*?Print<\/button>/);
  }
});

test("the loan voucher sheet shows the loan, the terms in Malayalam and the signatures", () => {
  const sheet = loanSheet(LOAN_RECEIPT, "Customer");
  assert.equal(sheet.title, "Loan voucher · Customer copy");
  assert.deepEqual(sheet.total, { label: "Loan amount", value: "₹1,00,000.00" });
  const html = render(<Sheet sheet={sheet} />);
  assert.match(html, /<article class="sheet" aria-label="Customer copy">/);
  assert.match(html, /Santhwanam Gold Loans[\s\S]*Main Road[\s\S]*Phone: 9876543210/);
  assert.match(html, /<dt>Loan number<\/dt><dd>SAN1L1<\/dd>/);
  assert.match(html, /<dt>Net weight<\/dt><dd>9.50 g<\/dd>/);
  assert.match(html, /<ul lang="ml">/);
  assert.match(html, /<div>Customer signature<\/div><div>Office seal<\/div><div>Authorised signatory<\/div>/);
});

test("a first-week payment receipt says the payment went to principal", () => {
  const firstWeek = entrySheet(entryReceipt({}), "Customer");
  assert.deepEqual(firstWeek.fields.find(([label]) => label === "First 7 days"), ["First 7 days", "Payment goes to principal"]);
  assert.deepEqual(firstWeek.total, { label: "Total received", value: "₹30,000.00" });
  assert.equal(firstWeek.signatures.left, "Received by");
  assert.equal(firstWeek.terms, false);
  assert.match(render(<Sheet sheet={firstWeek} />), /<dt>First 7 days<\/dt><dd>Payment goes to principal<\/dd>/);

  const later = entrySheet(entryReceipt({ in_first_week: false, accrued_days: 12 }), "Office");
  assert.equal(later.fields.some(([label]) => label === "First 7 days"), false);
  assert.equal(later.signatures.left, "Customer signature");
  const closing = entrySheet(entryReceipt({}, { is_closing: true }), "Customer");
  assert.equal(closing.fields.some(([label]) => label === "First 7 days"), false);
  assert.match(closing.title, /^Loan closure receipt/);
  const topUp = entrySheet(entryReceipt({ kind: "disbursement", principal_change: "50000.00" }), "Customer");
  assert.equal(topUp.fields.some(([label]) => label === "First 7 days"), false);
});

test("entry receipt uses branch receipt_no when present and falls back to entry id", () => {
  const withBranchReceipt = entrySheet(entryReceipt({ receipt_no: 1 }), "Customer");
  assert.deepEqual(withBranchReceipt.fields.find(([label]) => label === "Receipt number"), ["Receipt number", "R1"]);
  const legacyReceipt = entrySheet(entryReceipt({ receipt_no: null, id: 42 }), "Customer");
  assert.deepEqual(legacyReceipt.fields.find(([label]) => label === "Receipt number"), ["Receipt number", "R42"]);
});

test("share links carry a short message only, and WhatsApp only for a valid mobile number", () => {
  assert.equal(whatsappLink("9876543210"), "https://wa.me/919876543210?text=Your%20receipt%20is%20attached%20as%20a%20PDF.");
  assert.equal(whatsappLink("+91 98765-43210"), "https://wa.me/919876543210?text=Your%20receipt%20is%20attached%20as%20a%20PDF.");
  assert.equal(whatsappLink("12345"), null);
  assert.equal(whatsappLink(null), null);
  const mail = mailtoLink("Payment receipt");
  assert.ok(mail.startsWith("mailto:?subject=Payment%20receipt&body="));
  assert.doesNotMatch(mail + whatsappLink("9876543210"), /SAN1L1|30000|Anu/);
  assert.equal(pdfFileName("Receipt-R7-SAN1L1.pdf"), "Receipt-R7-SAN1L1.pdf");
  assert.equal(pdfFileName("Loan-voucher-A/B 1.pdf"), "Loan-voucher-A-B-1.pdf");
});

test("Backups: SuperAdmin sees the backup email card and Import backup, with nothing stored or downloaded", () => {
  const html = renderAt("/backup", <BackupPage />, SUPERADMIN);
  assert.match(html, /Every night the app emails a password-protected backup to the address below\. Nothing is stored in the app\./);
  assert.match(html, /<h2 class="card-title">Backup email<\/h2>[\s\S]*<h2 class="card-title">Import backup<\/h2>/);
  assert.match(html, /Check it first, then import it\./);
  assert.match(html, /accept="\.zip,\.json,\.gz,\.json\.gz,application\/zip,application\/json,application\/gzip"/);
  assert.match(html, /Choose a backup file/);
  assert.match(html, /<button type="submit" class="btn btn-secondary" disabled="">[\s\S]*?Check<\/button>/);
  assert.doesNotMatch(html, /Save a snapshot now|Download current data|Snapshots|snapshot|Check or restore a file|Daily backup email/);
  assert.doesNotMatch(html, /icon-download|>Download</);
});

test("Backups: head office can check a file but not import it", () => {
  const html = renderAt("/backup", <BackupPage />, HQ_USER);
  assert.match(html, /<h2 class="card-title">Import backup<\/h2>/);
  assert.match(html, /Only the SuperAdmin can import\./);
  assert.doesNotMatch(html, /Check it first, then import it/);
  assert.match(html, /Backup email/);
  assert.doesNotMatch(html, /Save a snapshot now|Download current data/);
});

test("Import backup asks for the ZIP password only when a ZIP is chosen", () => {
  const zip = render(<ImportBackup user={SUPERADMIN} initialFile={{ name: "backup_2026-10-23_0001IST.zip", type: "application/zip", size: 1200 }} />);
  assert.match(zip, /Chosen file: <strong>backup_2026-10-23_0001IST\.zip<\/strong>/);
  assert.match(zip, /<label class="field-label" for="[^"]+">ZIP password/);
  assert.match(zip, /type="password"[^>]*autocomplete="off"/i);
  assert.match(zip, /aria-label="Show password"/);
  assert.match(zip, /It is used only to open this file and is never saved\./);
  assert.match(zip, /<button type="submit" class="btn btn-secondary">[\s\S]*?Check<\/button>/);
  for (const file of [{ name: "backup_2026-10-23_0001IST.json", type: "application/json" }, { name: "backup.json.gz", type: "application/gzip" }]) {
    const html = render(<ImportBackup user={HQ_USER} initialFile={file} />);
    assert.match(html, new RegExp(`Chosen file: <strong>${file.name.replace(/\./g, "\\.")}</strong>`));
    assert.doesNotMatch(html, /ZIP password/);
  }
});

const EMAIL = {
  configured: true, missing: [], recipient: "backups@example.com", enabled: true,
  status: {
    nightly: { at: "2026-10-22T18:30:05+00:00", ok: true, result: "sent", message: "Backup emailed.", size_bytes: 1200 },
    manual: { at: "2026-10-22T05:00:00+00:00", ok: false, result: "failed", message: "The mail server refused the sign-in.", by: "hq" },
  },
};

test("backup email: SuperAdmin edits the address; status is shown in words with IST times", () => {
  const html = render(<EmailDetails settings={EMAIL} user={SUPERADMIN} onSaved={() => {}} />);
  assert.match(html, /<dt>Sent to<\/dt><dd>backups@example.com<\/dd>/);
  assert.match(html, /<dt>Nightly email<\/dt><dd>On<\/dd>/);
  assert.match(html, /<dt>Last nightly email<\/dt><dd>[\s\S]*?<span class="pill pill-success">Sent<\/span><span>23 Oct 2026, 12:00 am IST<\/span>/i);
  assert.match(html, /<dt>Last Email backup now<\/dt><dd>[\s\S]*?<span class="pill pill-danger">Failed<\/span>[\s\S]*by hq[\s\S]*The mail server refused the sign-in\./);
  assert.match(html, /Send backups to/);
  assert.match(html, /type="email"[^>]*value="backups@example.com"/);
  assert.match(html, /A password-protected ZIP is emailed every night at 00:00 IST\. The ZIP password is set on the server and is never emailed\./);
  assert.match(html, /type="checkbox" checked=""/);
  assert.match(html, /Send the nightly email/);
  assert.match(html, />Save<\/button>/);
  assert.match(html, /<button type="button" class="btn btn-secondary">[\s\S]*?Email backup now<\/button>/);
  assert.match(html, /Once every 10 minutes\./);
  assert.doesNotMatch(html, /isn&#x27;t set up on the server|Send test email now/);
});

test("backup email: head office sees status and Email backup now; missing server settings are listed", () => {
  const unset = { configured: false, missing: ["SMTP_HOST", "BACKUP_ZIP_PASSWORD"], recipient: null, enabled: false, status: { nightly: null, manual: null } };
  const html = render(<EmailDetails settings={unset} user={HQ_USER} onSaved={() => {}} />);
  assert.match(html, /Email isn&#x27;t set up on the server yet[\s\S]*<li>SMTP_HOST<\/li><li>BACKUP_ZIP_PASSWORD<\/li>/);
  assert.match(html, /<dd>No address set<\/dd>/);
  assert.equal(html.match(/<span class="pill">Not sent yet<\/span>/g).length, 2);
  assert.doesNotMatch(html, /Send backups to|<form/);
  assert.match(html, /<button type="button" class="btn btn-secondary" disabled="">[\s\S]*?Email backup now<\/button>/);
  const ready = render(<EmailDetails settings={EMAIL} user={HQ_USER} onSaved={() => {}} />);
  assert.match(ready, /<button type="button" class="btn btn-secondary">[\s\S]*?Email backup now<\/button>/);
  assert.doesNotMatch(ready, /Send backups to|<form/);
  const superHtml = render(<EmailDetails settings={unset} user={SUPERADMIN} onSaved={() => {}} />);
  assert.match(superHtml, /<button type="button" class="btn btn-secondary" disabled="">[\s\S]*?Email backup now/);
});

const REPORT = {
  format_version: 3, created_at: "2026-10-22T18:30:00+00:00", created_by: "system", kind: "scheduled", checksum: "verified",
  counts: { branches: 2, customers: 40, loans: 55, entries: 300, settings: 1 }, branch_prefixes: ["AD", "SAN"],
  warnings: [], missing_branches: [], restorable: true,
};

test("the file check shows what the backup holds and whether it can be restored", () => {
  const html = render(<CheckReport report={REPORT} canRestore />);
  assert.match(html, /<span class="pill pill-success">Checksum verified<\/span>/);
  assert.match(html, /<dt>Taken at<\/dt><dd>23 Oct 2026, 12:00 am IST<\/dd>/i);
  assert.match(html, /<dt>Made by<\/dt><dd>system<\/dd>/);
  assert.match(html, /<dt>Type<\/dt><dd>Nightly email<\/dd>/);
  assert.match(html, /<dt>Branches in the file<\/dt><dd>AD, SAN<\/dd>/);
  assert.match(html, /<dt>Customers<\/dt><dd>40<\/dd>[\s\S]*<dt>Ledger entries<\/dt><dd>300<\/dd>/);
  assert.doesNotMatch(html, /banner|Only the SuperAdmin/);
  assert.match(render(<CheckReport report={{ ...REPORT, kind: "manual" }} canRestore />), /<dt>Type<\/dt><dd>Email backup now<\/dd>/);
  assert.match(render(<CheckReport report={{ ...REPORT, kind: "export" }} canRestore />), /<dt>Type<\/dt><dd>export<\/dd>/);

  const old = render(<CheckReport report={{ ...REPORT, format_version: 2, checksum: "absent", kind: null, created_by: null,
    warnings: ["2 loans refer to customers that are not in the file."], missing_branches: ["KOL"], restorable: false }} canRestore />);
  assert.match(old, /<span class="pill pill-warning">Older file without checksum<\/span>/);
  assert.match(old, /class="banner banner-danger" role="alert"[\s\S]*branches that don&#x27;t exist here: KOL/);
  assert.match(old, /class="banner banner-warning"[\s\S]*<li>2 loans refer to customers that are not in the file\.<\/li>/);

  assert.match(render(<CheckReport report={REPORT} canRestore={false} />), /Only the SuperAdmin can restore a backup\./);
});
