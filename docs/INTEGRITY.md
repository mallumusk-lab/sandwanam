# Integrity checklist

Everything that protects Gold Loan Desk from a bad change, in one place: every automated test with
the rule it protects, the grep gates, and the few manual checks that need a person. For the rules
themselves see [ARCHITECTURE.md](ARCHITECTURE.md); for the workflow see [CLAUDE.md](../CLAUDE.md).

**This file must list every test.** `BackendPython/tests/test_integrity_doc.py` fails when a backend
test method or a frontend `test(…)` is missing from it, so a new test is not done until it has a line
here. Keep each line to one plain sentence about what would break if the test went away.

How to run everything (all offline, nothing touches a database or the network):

```bash
# BackendPython/
py -m unittest discover -s tests -t .        # every backend test below
py -m compileall -q app scripts tests        # syntax check

# Frontend/
node scripts/run-tests.mjs                   # every frontend test below (= npm test)
node scripts/check-bundle.mjs                # bundles offline, rejects unexpected imports (= npm run check)
node node_modules/vite/bin/vite.js build     # production build (= npm run build)
npm run lint                                 # eslint, zero warnings
```

## 1. Backend tests (`BackendPython/tests/`)

### `test_aeszip.py`

#### `AesZip`
- `test_round_trip_with_the_password`: the emailed ZIP opens with the right password and gives back the exact bytes.
- `test_wrong_or_missing_password_fails`: a wrong or empty password cannot read the ZIP.
- `test_method_is_aes_256_and_content_is_not_readable`: entries are AES-256 + Deflate and no plain text shows in the file.
- `test_bad_input_is_refused`: unsafe entry names, an empty password and pre-1980 dates are refused.

#### `ReadBackupZip`
- `test_round_trip_with_encrypt_zip`: Import backup opens the emailed ZIP in memory and gets back the exact backup bytes, also with a non-ASCII password.
- `test_wrong_password_is_a_plain_error`: a wrong password is a plain `zip_password` error ("The ZIP password is wrong."), never a 500, and the message never repeats the password.
- `test_the_zip_must_hold_exactly_one_backup_json`: a ZIP with no, two or a nested `backup_*.json`, or a file that is not a ZIP or is cut short, is refused as `invalid_backup`.
- `test_size_is_capped_before_and_after_unpacking`: the ZIP and the unpacked backup each stay under the size cap, so a ZIP bomb is refused, and a header that understates the size never yields more than it declares.
- `test_without_pyzipper_the_server_says_so`: without pyzipper, ZIP import is a plain "upload the .json instead" error, not a crash.

### `test_backup_email.py`

#### `Settings`
- `test_superadmin_sets_the_address_and_head_office_reads_it`: only the SuperAdmin changes the backup email address; head office can read it; the change is audited.
- `test_invalid_addresses_are_refused`: anything but exactly one valid address is a plain `invalid_email` error.
- `test_settings_never_travel_in_backups`: the email address and send status are never exported or restored, nor put in any emailed ZIP.
- `test_an_older_test_status_is_ignored_and_dropped`: a status saved by the old "Send test email" is ignored (it does not rate-limit "Email backup now") and dropped on the next save.

#### `SendNow`
- `test_head_office_emails_a_backup_now_and_keeps_the_nightly_status`: HQ and the SuperAdmin can press "Email backup now"; it emails a fresh v3 backup ZIP (kind `manual`, made by them), is audited `EMAIL_BACKUP_NOW` and never overwrites the nightly status; branch users are refused.
- `test_rate_limit_and_failures`: "Email backup now" is limited to once per 10 minutes for everyone, and a failed send is recorded and audited, not raised.
- `test_not_configured_or_no_address`: without server mail settings (`email_not_configured`) or an address (`email_no_recipient`) nothing is sent, for HQ and SuperAdmin alike.

#### `Nightly`
- `test_sent`: the nightly email carries a freshly built canonical v3 backup (kind `scheduled`) in an encrypted ZIP with a README that explains Import backup, records "sent" and audits the file name and sha256.
- `test_skipped_when_off_or_not_set_up`: a turned-off or unconfigured email is skipped with a clear result, without even building a backup.
- `test_already_sent_today`: a second nightly run on the same IST day does not send again.
- `test_failed_send_is_recorded_and_never_raises`: a mail server failure is recorded and audited and never fails the job.
- `test_too_large_sends_a_notice_without_the_file`: a backup over 15 MB sends a notice without the attachment that says nothing is stored in the app.
- `test_password_is_never_in_the_email`: the ZIP password appears nowhere in the message.
- `test_status_store_failure_still_returns_the_result`: failing to save the status still returns the send result.

### `test_backup_service.py`

#### `Files`
- `test_backup_bytes_are_canonical_v3_and_nothing_is_stored`: a backup is built in memory as canonical v3 JSON with its sha256, writes nothing (no audit, no data), and no snapshot code or storage exists any more.
- `test_a_damaged_or_edited_file_is_refused`: a damaged, cut-short or edited file (gzip or JSON) is refused by Check and restore as `invalid_backup`, and nothing changes.
- `test_old_v2_files_still_check_and_restore`: files made before format v3 (as `.json.gz` or `.json`) still check and restore exactly.

#### `Check`
- `test_check_reports_without_changing_anything`: Check reports counts, branches and checksum and writes nothing (no audit, no data).
- `test_missing_branches_make_a_file_not_restorable`: a file that refers to branches that don't exist is reported as not restorable.
- `test_a_cash_day_for_a_missing_branch_is_refused_before_anything_changes`: a cash day for a branch that doesn't exist makes the file not restorable, and restore refuses it with `unknown_branches` (not a 500) before writing anything.
- `test_a_branch_counter_for_a_missing_branch_is_refused_before_anything_changes`: a branch counter for a branch that no longer exists makes the file not restorable, and restore refuses it with `unknown_branches` (not a 500 from the foreign key) before writing anything; the counter alone does not add the branch to "Branches in the file".
- `test_bad_sources_are_plain_errors`: zero or several sources, a ZIP password without a ZIP or a ZIP without one, bad base64 or bad gzip give plain errors, never a 500.

#### `Restore`
- `test_restore_from_a_gzip_upload_round_trips`: restoring a base64 gzip upload brings back exactly the exported data and is audited with the IP and request id.
- `test_restore_keeps_no_copy_of_the_old_data`: by the user's decision a restore stores nothing extra: the replaced data is gone, the only write besides the data is the `RESTORE_BACKUP` audit line, and the result is just the counts and when the backup was taken.
- `test_restore_still_checks_branches_logos_and_confirmation`: restore still needs the SuperAdmin, "RESTORE", existing branches and valid logos.
- `test_duplicate_keys_in_a_file_are_a_plain_error`: duplicate customer, phone, loan or entry keys are named in a plain error, not a 409.
- `test_restore_round_trips_the_cash_ledger`: cash days and entries come back exactly, later days are replaced, id counters move on and carry forward still works.

#### `ZipImport`
- `test_the_emailed_zip_checks_and_restores_with_its_password`: the emailed ZIP itself, with its password, checks (counts, taken at, checksum verified) for HQ and SuperAdmin and restores exactly; the password is never stored or audited.
- `test_zip_password_and_access_are_checked_before_anything_changes`: a wrong ZIP password is a plain `zip_password` error, and a branch user, HQ restoring, or a missing RESTORE are refused before the ZIP is even opened.

#### `Routes`
- `test_backup_routes_and_request_bodies`: only `/backup/check`, `/backup/restore`, `/backup/email` and `/backup/email/send` remain; the router hands ZIPs to `app.infra.aeszip.read_backup_zip`; `snapshot_id` is refused and the ZIP password must be 12–128 characters.

#### `DailyJob`
- `test_daily_job_emails_a_v3_zip_and_stores_nothing`: the daily job emails a v3 ZIP built in memory (sha256 recorded in the status), its result has no `snapshot_id`, and nothing but the email status is written.
- `test_daily_job_survives_mail_failure_and_missing_setup`: the daily job succeeds when mail fails or is not set up, and its result lists only its own steps.
- `test_daily_job_closes_and_purges_the_cash_ledger_and_survives_its_failure`: the daily job auto-closes and purges cash days before building the emailed backup, and a failing cash step never stops the rest of the job.

### `test_cash.py`

#### `DomainRules`
- `test_totals_ignore_voided_entries_and_show_differences`: cash in, cash out and expected skip voided entries, and differences are counted minus expected (negative is a shortage).
- `test_categories_and_other_needs_a_description`: the fixed category list and directions, and "Other" needs a description; text is trimmed.
- `test_counted_amounts_may_be_zero_but_not_negative`: a drawer count may be ₹0 but never negative or past 2 decimals.
- `test_retention_keeps_today_and_the_previous_thirteen_days`: the 14-day window is today plus the previous 13 days.

#### `DayFlow`
- `test_overview_shape_before_and_after_the_day_starts`: the overview has every field the page reads, before and after the day starts.
- `test_first_day_carries_zero_and_records_the_opening_difference`: a branch's first day carries ₹0.00 and stores the opening difference.
- `test_carry_forward_chain_uses_the_last_counted_closing`: each day carries forward the last closed day's counted cash.
- `test_second_start_is_refused_and_a_replayed_start_is_not`: a second start today is `day_already_started`; the same request id replayed returns the overview.
- `test_entries_are_idempotent_by_request_id`: a retried entry is stored once; a request id reused for something else is refused.
- `test_voided_entries_stop_counting_and_need_a_reason`: a voided entry stays listed with its reason and no longer counts.
- `test_closed_day_refuses_entries_voids_and_a_second_close`: a closed day is locked against entries, voids and closing again.
- `test_only_todays_open_day_takes_entries`: entries, voids and closes only work on today's open day.
- `test_close_checks_the_shown_expected_amount`: closing with an expected figure that has moved is 409 `cash_changed` and changes nothing.
- `test_a_drawer_below_zero_can_still_be_counted_and_closed`: a day whose expected cash is below zero can still be counted and closed.
- `test_reopen_is_head_office_only_today_only_latest_only`: only head office reopens, and only the branch's latest day when it is today.
- `test_start_day_auto_closes_a_stale_open_day`: starting a day closes an earlier forgotten day automatically at its expected figure.
- `test_daily_job_auto_closes_and_purges_keeping_each_branchs_latest_day`: the nightly step auto-closes old open days and deletes days past 14, keeping each branch's latest day.
- `test_suggestions_are_custom_descriptions_most_used_first`: description suggestions are "Other" descriptions from the window, most used first.
- `test_invalid_entries_change_nothing`: a refused entry writes nothing and names its field.
- `test_every_write_is_audited`: every cash write is in the audit log; automatic closes are logged as `system`.

#### `Access`
- `test_branch_staff_see_only_their_own_drawer`: a branch sees only its own drawer, and another branch's day or entry is a 404.
- `test_head_office_works_on_one_branch_at_a_time`: head office must choose one branch (`branch_required`) and never sees a combined drawer.
- `test_superadmin_is_refused`: the SuperAdmin cannot use the cash ledger at all.
- `test_a_branch_without_the_feature_is_refused`: a branch with the Cash ledger switched off is refused and nothing is written.
- `test_new_branches_get_the_cash_ledger_by_default`: `cashbook` is in the default permissions, and migration 005's column default matches the code.
- `test_a_branch_with_cash_days_cannot_be_deleted`: a branch that has cash ledger days cannot be deleted (`branch_in_use`, not a 500).

#### `RequestBodies`
- `test_cash_bodies_reject_unknown_and_malformed_fields`: the cash request bodies reject unknown fields and bad values (runs where pydantic is installed).

### `test_dates.py`

#### `BusinessDates`
- `test_early_morning_ist_is_still_today_in_ist`: 00:30 IST counts as today in India, not yesterday in UTC.
- `test_day_bounds_cover_whole_ist_days`: report ranges cover whole IST days as half-open UTC ranges.
- `test_iso_strings_with_z`: ISO timestamps ending in `Z` parse as UTC.
- `test_naive_values_are_treated_as_utc`: timestamps without a zone are read as UTC.
- `test_past_days_are_stored_at_ist_noon`: past business days (history import) are stored at IST noon.
- `test_today_is_stored_at_the_current_instant`: entries dated today are stored at the real current time.
- `test_strict_date_parsing`: only real `YYYY-MM-DD` dates are accepted.

### `test_follow_up.py`

#### `Rules`
- `test_defaults_and_boundaries`: the automatic follow-up is loan date + 364, overdue starts after loan date + 365, and the dashboard lists follow-ups 10 days ahead.
- `test_effective_follow_up`: a stored date wins, open loans otherwise get the automatic date, closed loans get none.

#### `Portfolio`
- `test_follow_up_listed_from_10_days_before_day_364_and_overdue_after_day_365`: a loan shows under follow-ups from day 354 (10 days before its day-364 follow-up) with the days left (10, 4, 0, then −1 once passed), not on day 353, and as overdue only after day 365.
- `test_overdue_loan_counts_the_days_to_its_follow_up`: an overdue loan with a staff-set follow-up carries the days to it (5, 0, then −3 once passed); only a date still ahead counts as followed up.
- `test_imported_old_loan_is_overdue_at_once`: an imported loan older than a year is overdue straight away.
- `test_closed_loan_has_no_follow_up`: closed loans have no follow-up date and never appear in either list.
- `test_stored_date_wins_and_clearing_restores_the_automatic_date`: a staff-set date wins and clearing it brings back the automatic one.
- `test_follow_ups_are_sorted_by_date_then_loan_number`: the dashboard's follow-ups are ordered by date, then loan number.

### `test_history_parity.py`

Each `Parity` scenario runs the same loan twice on separate in-memory databases: live (every entry
posted on its own date, the daily job compounding on each anniversary and today) and imported (one
history-import commit today). Every ledger row, the statement with its calculations, the loan detail,
the stored loan, today's closing quote and the customer's loan status must be identical.

#### `Parity`
- `test_interest_only_part_payments`: payments smaller than the interest import exactly as live.
- `test_part_principal_payments`: payments that reduce principal import exactly as live.
- `test_top_ups`: added principal imports exactly as live.
- `test_window_payment_then_nothing_until_after_the_first_anniversary`: a day 1–7 payment then nothing until the first compounding settles the week the same way.
- `test_payment_the_day_before_an_anniversary`: a payment the day before an anniversary comes before the compounding, as live.
- `test_payment_on_an_anniversary`: on an anniversary the loan compounds first, then the payment, the same day.
- `test_payment_the_day_after_an_anniversary`: a payment the day after an anniversary comes after the compounding, as live.
- `test_two_years_of_compounding_with_part_payments_and_a_top_up`: several years of compounding mixed with payments and a top-up match live.
- `test_leap_year_loan_dated_29_february`: a loan dated 29 February compounds on the same days as live.
- `test_same_day_payment_and_top_up`: a payment and a top-up on the same day keep their order and figures.
- `test_still_open_loan_with_trailing_compounding_to_today`: an open loan gets every compounding up to today, as live.
- `test_users_window_case_pay_day_two_add_day_four_close_day_five`: the agreed example (pay day 2, add day 4, close day 5) imports as closed with the same ₹414.25 interest.
- `test_close_on_day_three_with_no_entries`: a day-3 closing charges the 7-day minimum, as live.
- `test_close_on_day_seven`: a day-7 closing after a payment matches live.
- `test_close_on_day_eight`: a day-8 closing settles the first week and matches live.
- `test_close_on_day_ten`: a day-10 closing charges the peak week plus the extra days, as live.
- `test_close_after_compounding`: a closing after a compounding matches live and adds no compounding after it.
- `test_close_with_a_confirmed_write_off`: a short closing with the write-off confirmed writes off the same principal and interest as live.
- `test_close_with_nothing_received_writes_off_everything`: a closing with ₹0 received writes off everything, as live.
- `test_settling_via_close_with_full_payment`: a closing that pays everything owed matches live.
- `test_close_with_shortfall_and_no_write_off_is_refused_identically`: a short closing without confirmation is refused with the same `writeoff_not_confirmed` message and amount as live, and writes nothing.
- `test_explicit_compounding_in_history`: an explicit compounding entry in history imports identically to live.

#### `ImportCloseRules`
- `test_close_must_be_the_last_entry`: a closing listed or dated before another entry is `close_not_last`.
- `test_a_loan_is_closed_only_once`: a second closing is `close_twice`.
- `test_only_a_close_may_have_a_zero_amount`: only a closing may have ₹0 received; the preview then shows the amount to write off.
- `test_overpayment_on_close_is_refused`: receiving more than owed at an imported closing is refused, as live.
- `test_settling_payment_still_needs_a_close_entry`: a payment that would settle the loan must be entered as a closing (`settle_with_close`).
- `test_open_import_preview_has_no_closing_fields`: an open-loan preview has no closing date, remainder or write-off figures.
- `test_same_day_payment_before_a_zero_close_keeps_its_own_receipt`: an imported payment on the same day as a ₹0 close keeps an ordinary payment receipt, and the write-off's receipt shows ₹0 received.
- `test_imported_close_with_a_payment_still_prints_one_closing_receipt`: an imported close with cash received still pairs its payment and write-off into one closing receipt, and an earlier same-day payment stays separate.
- `test_full_settlement_has_no_remainder_and_no_trailing_compounding`: a full closing shows its date, no remainder, and no compounding after it.
- `test_request_body_accepts_a_close_with_write_off`: the request body accepts `close` and `write_off_remaining` and rejects unknown kinds (runs where pydantic is installed).

### `test_integrity_doc.py`

#### `IntegrityDoc`
- `test_every_backend_test_is_listed`: every backend test method is listed in this file under its own test file and class.
- `test_every_frontend_test_is_listed`: every frontend `test(…)` name is listed in this file under its own test file.

### `test_interest_vectors.py`

#### `SharedInterestVectors`
- `test_every_vector`: the server's interest functions reproduce every case in `test-vectors/interest.json`.

### `test_ledger.py`

#### `DayCounting`
- `test_customer_periods_are_inclusive`: a period ending in a customer event counts (end − start) + 1 days.
- `test_consecutive_periods_double_count_the_boundary_day`: the agreed rule that a boundary day is charged in both periods.
- `test_compounding_periods_are_exact`: compounding periods count exact days.
- `test_backwards_period_is_rejected`: a period that ends before it starts is an error.
- `test_closing_minimum`: closing within 7 days charges at least 7 days of interest in total.

#### `Collections`
- `test_interest_is_settled_before_principal`: after day 7 a payment settles interest first, then principal.
- `test_partial_interest_payment_leaves_interest_owed`: a payment smaller than the interest leaves the rest owed.
- `test_settling_in_full_must_use_close`: paying everything owed must go through Close loan.
- `test_first_week_payment_reduces_principal_by_its_full_amount`: in days 1–7 a payment goes wholly to principal and records no daily interest.
- `test_backdated_entry_is_rejected`: an entry dated before the loan's latest entry is refused.
- `test_zero_negative_and_fractional_paise_are_rejected`: amounts must be positive whole paise.
- `test_legacy_interest_credit_never_makes_interest_paid_negative`: an earlier-system interest credit never shows as negative interest paid.

#### `TopUps`
- `test_top_up_keeps_accrued_interest_owed`: adding principal keeps the interest accrued so far owed.

#### `Compounding`
- `test_anniversaries_are_anchored_to_the_loan_date`: compounding falls on loan date + 365·k, not on the last entry.
- `test_missed_anniversary_is_dated_on_the_latest_entry`: a late compounding is never dated before the latest entry.

#### `Closing`
- `test_full_settlement_records_the_cash_received`: a full closing records exactly the cash received.
- `test_short_payment_requires_confirmation`: paying less than owed needs an explicit write-off confirmation.
- `test_short_payment_writes_off_the_rest_once`: a confirmed short payment writes off the remainder once, split into principal and interest.
- `test_full_write_off_carries_the_accrual`: writing off everything carries the accrued interest into the write-off.
- `test_receiving_more_than_owed_is_rejected`: taking more cash than owed at closing is refused.
- `test_nothing_owed_closes_without_entries`: a loan owing nothing closes without ledger entries.
- `test_days_already_charged_counts_legacy_rows_exactly`: interest days already charged by earlier-system rows are counted exactly.

#### `FirstWeek`
- `test_users_scenario_closes_on_day_five_with_seven_days_on_the_peak`: the agreed example (₹1,00,000; pay ₹30,000 on day 2; add ₹50,000 on day 4; close on day 5) owes ₹414.25, payoff ₹1,20,414.25.
- `test_users_scenario_closed_on_day_ten_adds_the_days_after_day_seven`: the same loan closed on day 10 owes 7 days on the peak plus 3 days on the current principal (₹591.78).
- `test_day_two_payment_then_close_on_day_five`: a day-2 payment then a day-5 closing charges 7 days on the original principal.
- `test_closing_on_day_three_without_events`: a loan closed on day 3 with no other entries owes exactly 7 days (₹230.14).
- `test_day_eight_rounds_the_two_parts_once`: the first entry after day 7 adds the two parts and rounds once (₹263.01 on day 8).
- `test_first_event_after_day_seven_settles_and_inclusive_counting_resumes`: the first entry after day 7 settles the week and normal inclusive counting resumes.
- `test_peak_ignores_payments_and_display_shows_peak_interest_so_far`: payments never lower the peak, and the day 1–7 quote shows peak × days so far.
- `test_top_up_in_the_window_accrues_nothing_and_raises_the_peak`: a top-up in days 1–7 records no interest and raises the peak.
- `test_payment_that_clears_the_principal_is_refused`: a day 1–7 payment that would clear the principal is refused with `first_week_clears_principal`.
- `test_compounding_settles_an_unsettled_first_week`: a compounding that comes before any later entry settles the first week.
- `test_loans_begun_under_the_earlier_rule_are_not_charged_twice`: loans already in their first week at release are not charged twice.
- `test_history_import_follows_the_same_rule`: history import replays the first-7-days rule the same way.

#### `HistorySimulation`
- `test_replay_compounds_between_events_and_up_to_today`: imported history compounds between its entries and up to today.
- `test_events_out_of_range_are_rejected`: imported entries before the loan date or after today are refused.
- `test_replayed_close_uses_the_live_closing_rules_and_stops_compounding`: an imported closing uses the live closing rules (7-day minimum, write-off only when confirmed) and nothing compounds after it.
- `test_replayed_close_must_be_last_and_only_once`: the replay refuses a closing that is not last, or a second closing.

### `test_middleware_config.py`

#### `ApiPrefix`
- `test_strips_only_the_api_segment`: `/api/...` reaches the routes and nothing else in the path changes.

#### `RequestContext`
- `test_adds_request_id_and_security_headers`: every response has a request id, the CSP and the other security headers.
- `test_keeps_a_safe_incoming_request_id_only`: only a well-formed incoming request id is reused.
- `test_rejects_oversized_bodies`: request bodies over the size limit are refused.

#### `OriginGuard`
- `test_cross_site_writes_are_blocked_but_reads_are_not`: changes sent from another site are blocked; reads are not.
- `test_same_origin_and_trusted_origins_pass`: the app's own origin and configured trusted origins pass.

#### `Config`
- `test_development_defaults`: development defaults use the `__Host-` cookie, allow the dev server origin and keep API docs off.
- `test_production_requires_secrets`: production refuses to start without its secrets or with insecure cookies.
- `test_plain_http_development_cookie`: `COOKIE_SECURE=false` switches to a plain cookie name for local http.
- `test_mail_settings_are_optional_and_never_fatal`: missing or bad mail settings never stop the API and are listed in plain words.

#### `Mailer`
- `test_starttls_comes_before_login_and_send`: on port 587 STARTTLS happens before login and sending.
- `test_port_465_uses_tls_from_the_start`: port 465 uses TLS from the first byte.
- `test_no_encryption_means_nothing_is_sent`: a server without STARTTLS gets nothing, not even the login.
- `test_recipients_are_exactly_one_checked_address`: mail goes to exactly the one checked recipient.
- `test_errors_and_repr_never_show_secrets`: passwords never appear in errors or `repr`.
- `test_not_configured_lists_what_is_missing`: an unconfigured mailer lists the missing settings.

### `test_particulars_validation.py`

#### `Particulars`
- `test_both_legacy_delimiters_parse_the_same`: earlier-system item lists parse the same with or without spaces.
- `test_oldest_quantity_first_format`: the oldest "2 Ring" style still parses.
- `test_items_without_quantity_default_to_one`: an item without a quantity counts as one.
- `test_round_trip`: items turn into display text and back unchanged.
- `test_validate`: empty names, zero or boolean quantities and non-lists are refused.

#### `Validation`
- `test_phone`: phone numbers are normalised to 10 digits and invalid ones refused.
- `test_weights`: weights are two-decimal, positive, and the deduction is less than gross.
- `test_rate_and_tenure`: rates and tenures stay in range with the right precision.
- `test_password_policy`: passwords are long enough, not common and do not contain the username.
- `test_branch_prefix_and_username`: branch prefixes are letters only and usernames have no spaces.
- `test_logo_checks_magic_bytes_and_size`: logos must really be PNG/JPEG/WebP and small enough.

### `test_reports_codec.py`

#### `Periods`
- `test_defaults_to_today`: a report without dates covers today in IST.
- `test_month_starts`: month presets start on the 1st.
- `test_rejects_bad_ranges`: future, reversed, too-long and malformed ranges are refused.
- `test_aging_buckets`: days since the last payment fall into the right dashboard bucket.

#### `Csv`
- `test_formula_injection_is_neutralised`: CSV cells that start like a formula cannot run in a spreadsheet.

#### `BackupCodec`
- `test_round_trip_including_follow_up_dates`: a backup round-trips every table, follow-up dates included.
- `test_legacy_and_tampered_files_are_rejected`: old-format files, injected column names, extra tables and wrong value types are refused.

#### `BackupFormatV3`
- `test_v3_document_has_manifest_schema_and_checksum`: a v3 file carries per-table counts and sha256, a schema fingerprint and a checksum.
- `test_only_nightly_and_manual_kinds_are_written_but_older_files_still_read`: new backups are only `scheduled` or `manual`, while files from before (kinds `pre_restore`, `export`) still check and restore; an unknown kind is refused.
- `test_tampering_is_rejected`: any changed byte of a v3 file fails its checksum.
- `test_v2_files_still_decode_identically`: v2 files decode exactly as before.
- `test_gzip_plain_and_bom_inputs_are_equal`: `.json`, `.json.gz` and a file with a BOM read the same.
- `test_bad_bytes_are_refused`: non-JSON, NaN, duplicate keys and trailing data are refused.
- `test_decompression_bomb_is_refused`: a file that expands past the size cap is refused; the upload cap is the only one (no stored-snapshot cap remains).
- `test_each_unique_key_is_checked`: each unique key (customer, phone, user id, loan, loan number, entry, request id, opening entry) is checked.
- `test_floats_in_items_round_trip`: item weights inside JSON columns round-trip without float damage.
- `test_local_settings_are_never_exported_or_restored`: the backup email settings stay on this server.
- `test_inspect_reports_counts_and_loose_ends`: Check reports counts, branches and orphan warnings.
- `test_file_stamp_is_ist`: file names use the IST date and time.
- `test_cash_ledger_tables_round_trip_and_are_checked`: cash days and entries round-trip, their unique keys are checked, and an entry whose day is missing is refused.

### `test_repositories.py`

#### `PlaceholderChecks`
- `test_check_arguments`: a statement's `$n` placeholders must match its arguments exactly.
- `test_like_pattern_escapes_wildcards`: `%`, `_` and `\` typed by users match literally.

#### `EveryRepositoryMethod`
- `test_users_sessions_throttle`: account, session and throttle SQL is parameterised and never contains user input.
- `test_customers_loans_statements`: customer, loan and ledger SQL is parameterised and never contains user input.
- `test_first_week_totals_come_from_the_whole_ledger`: the peak principal and interest collected for the first-7-days rule are read from the whole ledger.
- `test_reports`: report SQL is parameterised and selects what the serializers need.
- `test_admin`: branch admin, backup and restore SQL is parameterised and uses only constant table names; no repository mentions `backup_snapshots` and migration 005 drops that table.
- `test_cash_ledger`: every `CashRepo` method is parameterised and never contains user input; the day is locked `FOR UPDATE`, inserts are idempotent, the purge keeps each branch's latest day, and no statement touches a loan table.
- `test_cash_tables_are_backed_up_and_restored_children_last`: backups export both cash tables; restore truncates them, inserts days before entries and resets both id counters.

### `test_security.py`

#### `Passwords`
- `test_round_trip_and_unicode`: PBKDF2 hashes verify, including non-ASCII passwords.
- `test_salts_differ`: the same password never hashes the same twice.
- `test_legacy_formats_verify_and_need_rehash`: older hash formats still verify and are marked for upgrade.
- `test_plaintext_and_garbage_are_never_accepted`: plaintext or malformed stored passwords never verify.
- `test_known_defaults_are_detected`: published default passwords are recognised so the account can be disabled.

#### `Sessions`
- `test_tokens_are_random_and_hashed`: session tokens are random and only their hash is stored.
- `test_csrf_is_bound_to_the_session`: a CSRF token works only with its own session.
- `test_expiry_rules`: sessions end after 8 hours, or 60 minutes idle.

#### `Throttle`
- `test_backoff_grows_and_caps`: sign-in delays double and stop at the cap.
- `test_claims_count_before_verification`: parallel attempts are counted before the password is checked.
- `test_old_failures_expire`: old failures stop counting.
- `test_delays_never_overflow`: very many failures never overflow the delay.
- `test_trust_expires`: a usual device stays trusted for 30 days only.
- `test_client_ip`: the client address comes from proxy headers only when they are trusted.
- `test_ipv6_clients_are_grouped_by_64`: IPv6 addresses are throttled per /64.

### `test_services.py`

#### `AuthTests`
- `test_login_and_session`: signing in creates a session that resolves until its 8-hour limit.
- `test_unknown_inactive_and_passwordless_accounts_fail_identically`: wrong, inactive and passwordless accounts get the same answer.
- `test_failures_are_generic_and_throttled_per_ip`: failed sign-ins say nothing specific and are throttled per address.
- `test_guessing_from_many_addresses_hits_the_account_limit`: guessing from many addresses still hits the account limit.
- `test_usual_device_is_not_locked_out_by_strangers`: strangers cannot lock staff out of their usual device.
- `test_lockout_audited_only_when_the_attempt_fails`: lockouts are audited only on a failed attempt.
- `test_legacy_hash_is_upgraded_on_login`: an older password hash is upgraded at sign-in.
- `test_change_password_keeps_only_the_current_session`: changing a password ends every other session.
- `test_wrong_current_password_is_throttled`: guessing the current password on the account page is throttled.

#### `CustomerTests`
- `test_numbers_are_allocated_per_branch`: customer numbers count up per branch.
- `test_branches_cannot_see_each_other`: a branch gets 404 for another branch's customers.
- `test_duplicate_phone_does_not_leak_other_branch_ids`: the duplicate-phone message never reveals another branch's customer.
- `test_head_office_must_choose_a_real_branch`: head office must create a customer in a real branch.

#### `LoanTests`
- `test_create_allocates_number_and_opening_entry`: a new loan gets the next loan number and one opening entry.
- `test_collection_is_idempotent_and_checks_the_shown_amount`: a repeated request returns the first result and a changed amount gives `outstanding_changed`.
- `test_overpayment_and_backdating_are_rejected_without_side_effects`: overpaying, clearing the principal in days 1–7 and out-of-order entries are refused without writing anything.
- `test_daily_entries_are_dated_today_and_in_order`: every daily entry is dated today, in order.
- `test_same_day_quote_charges_one_day`: a quote on the loan date charges one day.
- `test_close_records_cash_received_and_write_off`: closing records the cash received and the confirmed write-off.
- `test_top_up_and_item_edit`: adding principal raises the principal, and editing items never touches the ledger.
- `test_other_branch_cannot_post`: a branch cannot post to another branch's loan.
- `test_cron_compounding_runs_once`: the daily job compounds a due loan exactly once.

#### `FirstWeekServiceTests`
- `test_users_scenario_closes_on_day_five`: the agreed example posted through the service closes at ₹1,20,414.25.
- `test_day_ten_charges_the_peak_week_plus_three_days_and_matches_the_live_quote`: on day 10 the posted interest equals the quote shown to staff.
- `test_payment_that_clears_the_principal_is_refused`: the service refuses a day 1–7 payment that would clear the principal.
- `test_import_preview_applies_the_first_week_rule`: the history-import preview uses the first-7-days rule.
- `test_earlier_rule_first_week_payment_is_not_flagged_on_its_receipt`: a day 1–7 payment posted under the earlier rule (it charged interest) is not labelled "First 7 days: payment goes to principal".
- `test_statement_explains_each_row_and_receipts_do_not`: loan detail adds a calculation to every row and receipts do not.

#### `DailyEntryDateTests`
- `test_daily_entry_bodies_have_no_date_field`: the request models for new loans, payments and top-ups have no date field.
- `test_request_bodies_reject_a_date_on_daily_entries`: sending a date on a daily entry is a 422 (runs where pydantic is installed).

#### `AccessTests`
- `test_superadmin_works_with_customers_and_loans_of_any_branch`: the SuperAdmin works with customers and loans of every branch.
- `test_superadmin_is_refused_analytics_reports_history_gold_rate_and_audit`: the SuperAdmin is refused the dashboard, reports, history import, gold rate and audit log.
- `test_head_office_keeps_every_feature_with_gold_rate_and_audit_log`: head office keeps every feature, the gold rate and the audit log.

#### `ImportTests`
- `test_preview_writes_nothing_and_matches_commit`: the import preview writes nothing and equals what commit stores.
- `test_commit_refuses_an_outdated_preview`: commit refuses a preview whose figures changed.
- `test_commit_requires_exactly_one_customer_choice`: commit needs exactly one of an existing or a new customer.
- `test_failed_import_leaves_no_partial_customer`: a failed import leaves no half-made customer.
- `test_retry_returns_the_original_import`: retrying an import returns the first result.

#### `ReportTests`
- `test_portfolio_is_live_and_branch_scoped`: the dashboard portfolio is quoted as of today and limited to the branch.
- `test_branch_users_cannot_set_the_gold_rate`: branch accounts cannot set the gold rate.

#### `AdminTests`
- `test_only_superadmin_manages_branches`: only the SuperAdmin creates and changes branches and accounts.
- `test_branch_with_customers_cannot_be_deleted`: a branch that has customers cannot be deleted.
- `test_receipts_come_from_the_ledger`: receipts show the stored ledger figures and another branch gets 404.
- `test_receipt_number_starts_from_one_for_each_branch`: each branch has its own receipt serial starting from 1.
- `test_restore_requires_superadmin_and_confirmation`: restore needs the SuperAdmin and the typed word RESTORE.

#### `ReviewFixes`
- `test_branch_directory_hides_usernames`: the branch list shown to staff never contains usernames.
- `test_branch_without_customer_access_cannot_use_loans`: a branch without customer access cannot use loans.
- `test_new_branches_do_not_get_history_import_by_default`: history import is opt-in for new branches.
- `test_request_id_cannot_be_replayed_for_another_customer`: a request id cannot be reused on another loan.
- `test_earlier_same_day_payment_keeps_its_own_receipt`: two payments on one day each keep their own receipt.
- `test_closing_a_loan_with_nothing_owed`: a loan with nothing owed closes cleanly.

### `test_statement_calc.py`

#### `Explain`
- `test_users_first_week_scenario`: the statement explains the agreed example as first-week rows and a 7-days-on-the-peak closing.
- `test_settlement_after_day_seven_then_inclusive_days`: the first row after day 7 shows the peak week plus extra days, then normal inclusive rows.
- `test_compounding_rows`: compounding rows show exact days and the interest added to principal.
- `test_write_offs`: write-off rows show what was written off.
- `test_legacy_rows_are_not_recalculated`: earlier-system rows say "Earlier system — not recalculated".
- `test_loan_begun_under_the_earlier_rule`: a loan begun under the earlier rule shows the interest already charged being subtracted.
- `test_mismatch_is_shown_as_recorded_and_nothing_raises`: rows the rules cannot reproduce are shown "as recorded" and nothing raises.
- `test_payment_after_day_seven_without_first_week_activity_uses_inclusive_period`: payments after day 7 without week-1 activity explain as standard period interest instead of splitting into first 7 days.

## 2. Frontend tests (`Frontend/tests/`)

### `backup.test.js`
- `isGzip looks at the gzip signature, not the file name`: a renamed file is still recognised correctly.
- `toBase64 matches Node's encoder, across chunk boundaries`: uploads are encoded exactly like the server expects.
- `gzipBytes compresses in the browser way and round-trips`: browser compression gives a valid gzip of the same bytes.
- `prepareUpload sends a .json.gz as it is and compresses a .json`: uploads always reach the server as gzip.
- `prepareUpload refuses files over the upload limit with a clear message`: files over Vercel's request limit get a plain message.
- `without CompressionStream a .json is sent as parsed JSON, up to 4 MB`: older browsers can still check and restore small files.
- `a ZIP is recognised by name or type to ask for the password, and by its bytes when sent`: choosing the emailed ZIP shows the password field, and a renamed ZIP is still sent as a ZIP.
- `the ZIP is sent as it is with its password, which must be 12 to 128 characters`: the ZIP goes to the server unchanged with its password, a missing or wrong-length password is caught in the browser like the server would, and a too-large ZIP gets the plain message.
- `emailError accepts exactly one address, like the server`: the email field checks the same rule as the server.

### `cash.test.jsx`
- `cash ledger: with no day today the start card shows the carry forward and the counted field`: before the day starts, the page shows the server's carry forward and asks for the counted cash.
- `cash ledger: a branch's first day carries forward ₹0.00`: with no earlier closed day the page says the carry forward is ₹0.00.
- `cash ledger: differences are shown in words, not colour alone`: shortages, excesses and matches are labelled in words.
- `cash ledger: today's summary shows the server's figures and the add-entry form`: today's summary shows the server's totals, and the add-entry form has its labelled fields and categories.
- `cash ledger: a voided entry stays listed, struck through and labelled, with its reason`: a voided entry is still shown, struck through, labelled "Voided" and with its reason.
- `cash ledger: a closed day is locked; head office may reopen only when the server allows`: a closed day shows its counted figure and difference with no entry form, Close or Void buttons, and Reopen appears only when the server says `can_reopen`.
- `cash ledger: history days are collapsed disclosures that reveal each day's entries`: each earlier day is a collapsed button with `aria-expanded` that reveals that day's entries; earlier days have no Void button.
- `cash ledger: amounts are never added up in the browser`: the cash ledger code never adds amounts or uses float maths, inline styles or hex colours, and closing sends back the expected figure the server showed (handling `cash_changed`).

### `client.test.js`
- `buildUrl drops empty parameters`: empty filters are not sent.
- `unsafe requests carry the CSRF token; reads never do`: every change sends the CSRF token.
- `error envelopes become ApiError with field errors`: server errors reach the right form fields.
- `a 401 announces session expiry, except for the sign-in call itself`: an expired session returns to sign-in.
- `network failures and server errors get readable messages`: users see plain messages, never raw errors.
- `saveBlob saves through a temporary link; download uses it with the server's file name`: downloads keep the server's file name, with a fallback.

### `contrast.test.js`
- `${name} theme text contrast is at least 4.5:1`: every text colour pair meets WCAG AA in each theme.
- `${name} theme component contrast is at least 3:1`: borders, focus rings and controls meet WCAG AA in each theme.
- `the system dark theme matches the explicit dark theme`: the automatic and chosen dark themes are identical.

### `history.test.jsx`
- `history import entry types offer a loan closing on the last entry only`: "Loan closed (settled)" is offered only on the last entry.
- `history import closing entry asks for the closing date and amount received, and blocks later entries`: a closing entry asks for the closing date and amount received, and "Add an entry" is disabled after it.
- `history import review shows the closing rows, the closing date and the server's write-off amount`: the review shows the server's closing rows, "imported as closed on …" and the server's write-off amount to confirm.
- `history import review of an open loan has no closing text or write-off`: an open-loan review shows no closing text and no write-off checkbox.
- `history import payload sends write_off_remaining on the closing entry only`: only the closing entry carries `write_off_remaining`.
- `history import loan step calculates and shows net weight`: the loan step calculates net weight from gross weight and stones.
- `history import loan step renders compounding entry and sends amount 0 when blank`: a compounding entry sends amount 0 when left blank.
- `compounding date auto-calculates from start date and compounded interest is calculated on preview`: compounding date auto-calculates from loan start date and compounded interest is calculated on preview.

### `lib.test.js`
- `money: exact paise arithmetic`: money is added and compared in whole paise, never floats.
- `money: formatting and input normalisation`: amounts display as ₹ with Indian grouping and typed input is normalised.
- `dates: IST business day regardless of device timezone`: "today" is the IST day on any device.
- `interest: calculator matches the shared ledger vectors`: the calculator reproduces `test-vectors/interest.json`.
- `items: merge, count and validate`: pledged-item lists merge, count and validate like the server.
- `validation mirrors the server rules`: browser validation matches the server's rules.
- `permissions and ledger labels`: feature checks and ledger entry labels.
- `permissions: SuperAdmin has only what the server lists; head office staff have everything`: the UI shows the SuperAdmin only customers and loans, and head office everything.
- `ledger: calculation method labels`: each statement calculation method has a plain label.
- `permissions: the cash ledger is a branch feature; head office has it, SuperAdmin never does`: the Cash ledger feature follows the server's rule for each role.
- `permissions: a branch with only the cash ledger or history import starts on that page`: sign-in and the home redirect send such a branch to `/cash` or `/history`, not to the account page.

### `pages.test.jsx`
- `renders ${path}`: every page renders for an account allowed to open it.
- `the calculator's schedule table stacks into labelled cards on phones`: the calculator's "Amount due if the loan is closed after" table becomes labelled cards on phones instead of widening the page.
- `the application form page is gone; its old URL is an unknown page`: the removed application form stays removed.
- `data pages render their loading state`: data pages show a loading state first.
- `sign-in page supports password managers`: the sign-in fields carry the right autocomplete attributes.
- `forced password change replaces the page until done`: a temporary password must be changed before anything else.
- `navigation only shows what the account may use`: branch navigation matches the branch's features.
- `SuperAdmin navigation: customers, backups, branches and the all-branches picker`: the SuperAdmin menu has exactly its three areas.
- `head office navigation has every branch feature but not branch administration`: the head office menu has everything except Branches & Users.
- `the branch picker leaves out the head-office branch`: "Admin – all branches" replaces the separate head-office entry.
- `navigation: branch staff with the cash ledger see it under Branch operations`: "Cash ledger" sits under Branch operations for a branch that has it.
- `cash ledger: branch staff see their own drawer; head office picks one branch; SuperAdmin is refused`: the Cash ledger page for each role: a branch sees its own drawer, head office gets a branch select, and the SuperAdmin is refused.
- `pages a branch may not use explain why instead of rendering`: a refused page explains why.
- `guards: gold rate and audit log are head office staff only; backups include SuperAdmin`: page guards match the server's rules, including the Cash ledger (`cashbook`, never the SuperAdmin).
- `statement: Show calculation is a toggle that adds the server's working under each entry`: the statement toggle is a pressed/unpressed button that adds a row per entry.
- `statement: Loan details includes principal balance and interest balance`: statement loan details show principal balance, interest balance and amount due.
- `statement: letterhead and title bar are print-only, page header is no-print`: the statement letterhead and title bar are print-only, while the navigation page header is hidden when printing.
- `statement: ledger table date keeps day and month together to consume at most two lines`: the ledger table keeps the day and month together so date cells consume at most two vertical lines.
- `customer: topbar has circled back arrow and customer card has statement layout`: the customer page has a streamlined topbar and structured statement-style customer card.
- `report: transaction table has index, date with time, description badge, debit, credit and net totals`: the report table displays row index, date with time, transaction description badge, debit/credit columns, and net totals footer.
- `dashboard: portfolio cards show overdue loans, write-off amount, net vs gross weight, and find customer is removed`: the dashboard portfolio section displays overdue loans, write-off amount, net vs gross weight, and removes find customer and today activity cards.
- `customers: branch column is shown for head office admin and hidden for individual branch staff`: the customers list shows the Branch column only to head office admins and omits it for individual branch users.
- `calculation lines only format the server's figures`: the calculation lines show the server's numbers, never browser maths.
- `first-week banners show the server's amounts`: payment and closing dialogs show the server's first-week figures.
- `follow-up dialog starts on the staff-set date, else a week from today`: the follow-up dialog's starting date.
- `follow-ups read due in N days, due today or overdue by N days, and every one is listed`: the dashboard's follow-up labels and tones, shown on both cards from `follow_up_days` (the browser counts no days); both cards page through every row, 50 at a time, instead of stopping at 50.
- `the loan-created banner is gone; the toast and loan receipt button remain`: the removed banner stays removed.
- `every password input is a PasswordField with a show-password toggle`: every password field has the show-password eye.

### `pdf.test.js`
- `jpegInfo reads the frame size past fill bytes and standalone markers`: the receipt image size is read correctly.
- `jpegInfo refuses what isn't a supported JPEG`: unsupported images are refused, not turned into a broken PDF.
- `jpegToPdf writes a valid single-page PDF 1.4`: shared receipts are valid PDFs (offsets, xref, lengths, trailer).
- `the image is scaled to fit the page and centred; grey and CMYK colour spaces`: the receipt fits A4 in every colour space.
- `PDF titles are UTF-16BE hex, so the rupee sign and Malayalam survive`: PDF titles keep ₹ and Malayalam.
- `wrapText breaks at spaces, then between characters, and keeps line breaks`: long receipt text wraps without losing characters.
- `renderSheetJpeg draws the sheet's text with the live colours and returns the JPEG`: the PDF image is drawn from the same sheet as the screen.

### `print.test.jsx`
- `receipt toolbars put Share beside Print, disabled until the receipt loads`: Share sits next to Print and waits for the data.
- `the loan voucher sheet shows the loan, the terms in Malayalam and the signatures`: the loan voucher keeps its content.
- `a first-week payment receipt says the payment went to principal`: day 1–7 payment receipts say the payment went to principal.
- `entry receipt uses branch receipt_no when present and falls back to entry id`: receipts display branch receipt numbers starting from 1 with fallback.
- `share links carry a short message only, and WhatsApp only for a valid mobile number`: no receipt data goes into share URLs.
- `Backups: SuperAdmin sees the backup email card and Import backup, with nothing stored or downloaded`: the SuperAdmin's Backups page has "Backup email" then "Import backup" (ZIP, .json or .json.gz) and no snapshot list, "Save a snapshot now" or download button.
- `Backups: head office can check a file but not import it`: head office gets Import backup to check a file, told only the SuperAdmin can import.
- `Import backup asks for the ZIP password only when a ZIP is chosen`: a chosen ZIP shows the labelled "ZIP password" field with its show/hide toggle; a .json or .json.gz does not.
- `backup email: SuperAdmin edits the address; status is shown in words with IST times`: the SuperAdmin's backup email card shows the last nightly and "Email backup now" results in words with IST times, the address form and the "Email backup now" button.
- `backup email: head office sees status and Email backup now; missing server settings are listed`: head office sees status and "Email backup now" (disabled until mail is set up and an address exists) but not the address form.
- `the file check shows what the backup holds and whether it can be restored`: the Check report shows when the backup was taken, its type, counts, checksum and restorability.

### `ui.test.jsx`
- `text fields associate label, hint and error`: every field's label, hint and error are wired for screen readers.
- `optional fields are marked and not required`: optional fields say so.
- `busy buttons stay focusable and announce their state`: busy buttons keep focus and announce it.
- `icon-only buttons have an accessible name; icons are hidden`: icon buttons always have a name.
- `tables use header scope and label stacked cells`: tables stay readable when stacked on mobile.
- `tables can add a full-width detail row under a row`: the statement's detail row spans the table.
- `segmented controls are a labelled radio group`: segmented controls are a labelled radio group.
- `unit affixes are announced with the field`: ₹ and g affixes are read with the field.
- `pager buttons stay focusable at the ends`: pager buttons keep focus at the first and last page.
- `toasts render inside always-present live regions`: toasts are announced.
- `pagination, stepper and states`: pager, stepper, empty and error states render correctly.
- `charts keep identity out of colour alone and provide a table`: charts never rely on colour alone.
- `phone layout: charts, bars, stacked tables, dialogs and tiles keep content inside the screen`: the CSS rules from the mobile audit stay in place: charts have no default figure margin, bar fills show, table wrappers contain hidden header text, stacked tables have full-width captions and stacked row headers, long summary values wrap, the cash history day lets its table scroll inside, and narrow KPI tiles shrink their figure.

## 3. Grep gates

Each pattern must find nothing new. Existing exceptions are in brackets.

Under `Frontend/src`:

| Pattern | Why |
|---|---|
| `parseFloat`, `toFixed(`, `Number(` on amounts | float money |
| `toISOString().slice` | non-IST dates (only inside `lib/dates.js`) |
| `#[0-9a-fA-F]{3,6}` in `.jsx` | hard-coded colour (logo in `AppShell.jsx`) |
| `dangerouslySetInnerHTML`, `alert(`, `confirm(`, `console.log` | security, UX |
| `fetch(` outside `api/client.js` | bypasses CSRF, timeouts and errors |
| `localStorage` | only the theme (`ui/theme.js`) and the cleanup in `AuthContext.jsx` |
| `style="`, `<style`, `<script` | the CSP forbids inline styles and scripts |

Under `BackendPython/app`:

| Pattern | Why |
|---|---|
| `float(` | float money |
| `from fastapi` / `import asyncpg` in `services/`, `domain/`, `security/` | layering |
| `infra` imported from `services/`, `domain/`, `security/` | only routers build mailers; services get them as parameters |
| `smtplib`, `pyzipper` outside `app/infra/` | network and encryption code stays in one place |
| any non-standard-library import in `domain/`, `security/` | the rules stay pure |
| `f"SELECT` / `f"UPDATE` / `.format(` with SQL anywhere | SQL injection risk (f-strings only with constant names, checked by `test_repositories.py`) |
| `print(` | use `app/logs.py` |

## 4. Manual checks

These need a person, and you run them yourself. The cash ledger and closed-loan import checks need the app
running against a scratch (local or staging) database, never production data; the 7-Zip check is offline;
the "Email backup now" check runs on the live site, and the import check on a scratch database only.

**Cash ledger, one full day** (after changing anything under `features/cash/`, `cash_service.py` or
migration 005; run it on a local or staging copy, signed in as a branch user, then as head office):
1. Open **Cash ledger** under Branch operations. With no day yet, the "Start the day" card says what is
   carried forward (₹0.00 for a branch's first day) and from which day.
2. Type a counted amount different from the carry forward. The card shows "Shortage ₹…" or "Excess ₹…" in
   words; press **Start the day**. The Today card shows carried forward, opening counted and the difference.
3. Add a "Loan collection" (cash in), a "Bill payment" (cash out), and an "Other (type a description)" entry.
   "Other" refuses to save without a description; "Cash in drawer now" changes after each save. Tab through
   the form: every field has a visible label and errors appear under the field.
4. Press **Void** on one entry, try a 1-character reason (refused), then give a real reason. The line stays
   listed, struck through, labelled "Voided" with its reason, and the totals drop by its amount.
5. Press **Close the day**, enter the counted cash and confirm. The day shows "Closed", the counted figure
   and the difference; the entry form, Close and Void buttons are gone.
6. Sign in as head office, choose that branch in the **Branch** select. **Reopen** is offered for today's
   closed day; reopen it, add an entry, close it again. The SuperAdmin has no Cash ledger in the menu, and
   opening `/cash` shows "You don't have access to this page".
7. On a copy with earlier days (or the next day), the "Last 14 days" card lists one collapsed row per day;
   each opens with the keyboard (Enter/Space) to show that day's entries, with no Void buttons.

**Importing a closed loan** (after changing `HistoryImportPage.jsx`, `import_service.py` or `ledger.simulate`;
on a local or staging copy, as an account with History import):
1. Enter a customer and a loan dated a few months back, then a payment, and as the last entry choose
   **Loan closed (settled)**. The labels become "Closing date" and "Amount received at closing", and
   **Add an entry** is disabled with "A closed loan has no later entries."
2. Enter less than the amount owed and press **Preview**. The review lists the closing rows, says "This loan
   will be imported as closed on …" and offers "Write off the remaining ₹…" with the server's amount.
3. Press **Import loan** without ticking it: the server refuses with the same write-off confirmation
   message as Close loan, and nothing is saved. Tick it and import: the loan's statement shows the closing
   and write-off rows, the loan is Closed on that date, it has no follow-up, and no compounding row comes
   after the closing. (Live entries are always dated today, so the live-vs-import comparison is automated:
   `tests/test_history_parity.py` runs 21 scenarios both ways.)

**AES ZIP opens in 7-Zip** (after changing `app/infra/aeszip.py` or upgrading pyzipper). From
`BackendPython/`, make a sample ZIP in a temporary folder:

```bash
py -c "from datetime import datetime; from app.infra.aeszip import encrypt_zip, read_backup_zip; z = encrypt_zip([('backup_x.json', b'{}'), ('README.txt', b'hello')], 'a-long-test-password', modified=datetime(2026, 1, 1)); assert read_backup_zip(z, 'a-long-test-password', limit=10**6) == b'{}'; open(r'%TEMP%\sample.zip','wb').write(z)"
"C:/Program Files/7-Zip/7z.exe" t -pa-long-test-password "%TEMP%\sample.zip"     # expect: Everything is Ok
"C:/Program Files/7-Zip/7z.exe" l -slt -pa-long-test-password "%TEMP%\sample.zip" # expect: Encrypted = +, Method = AES-256 Deflate
"C:/Program Files/7-Zip/7z.exe" t -pwrong "%TEMP%\sample.zip"                     # expect: an error
```

Delete the sample afterwards. Windows Explorer cannot open AES ZIP files; use 7-Zip or WinZip.

**Email backup now** (after deploying a change to the mailer, the backup email or the email card):
1. In Vercel → Project → Settings → Environment Variables, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
   `SMTP_PASSWORD`, `SMTP_FROM` and `BACKUP_ZIP_PASSWORD` (see the [README](../README.md#environment-variables)),
   then redeploy.
2. Sign in as the SuperAdmin, open **Backups → Backup email**. The "not set up" banner must be gone.
3. Enter the address, tick "Send the nightly email", save, then press **Email backup now**. "Last Email backup
   now" shows **Sent** with an IST time; a second press within 10 minutes is refused with a plain message.
4. The email arrives with `backup_<date>_<time>IST.zip`. It opens in 7-Zip with `BACKUP_ZIP_PASSWORD` and holds
   `backup_<date>_<time>IST.json` and `README.txt`. The password is nowhere in the email.
5. Sign in as HQ: **Email backup now** works too, but there is no address form. The audit log shows `EMAIL_BACKUP_NOW`.
6. The next morning, "Last nightly email" shows **Sent** with an IST time (audited `EMAIL_BACKUP`).

**Import last night's emailed ZIP** (after changing Import backup, `backup_service.py`, `backup_codec.py` or
`aeszip.read_backup_zip`; on a **scratch** database only, never production):
1. Keep your own copy of the scratch data first (restoring replaces all data and the app stores no copy).
2. Sign in as the SuperAdmin, open **Backups → Import backup**, choose the emailed `.zip` as it is. The
   "ZIP password" field appears; type a wrong password and press **Check**: "The ZIP password is wrong." shows
   under the field and nothing changes.
3. Type the right password and press **Check**: the report shows when it was taken, "Checksum verified" and
   the counts.
4. Press **Import**, read the warning "Restoring replaces all data. Keep your own copy of the current data
   first.", type RESTORE and confirm. "Backup imported" shows the restored counts; customers, loans, ledger
   and cash ledger match the night of the backup. The audit log shows `RESTORE_BACKUP` and never the password.
5. Repeat with the `.json` taken out of the ZIP with 7-Zip (no password asked). As HQ, Check works but there
   is no Import button.
