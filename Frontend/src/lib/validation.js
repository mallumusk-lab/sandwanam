// Client-side checks give instant feedback; the server repeats every one of them.

import { amountError, compare, normaliseAmount } from "./money.js";

export const PHONE_PATTERN = /^[6-9]\d{9}$/;
export const PASSWORD_MIN = 10;

export function phoneError(value) {
  const digits = String(value ?? "").replace(/[\s-]/g, "").replace(/^\+91/, "");
  if (!digits) return "Enter the mobile number.";
  return PHONE_PATTERN.test(digits) ? "" : "Enter a 10-digit mobile number starting with 6, 7, 8 or 9.";
}

export function nameError(value) {
  const text = String(value ?? "").trim().replace(/\s+/g, " ");
  if (!text) return "Enter the name.";
  return text.length >= 2 && text.length <= 100 ? "" : "Names must be 2 to 100 characters.";
}

export function addressError(value) {
  const text = String(value ?? "").trim();
  if (!text) return "Enter the address.";
  return text.length >= 3 && text.length <= 255 ? "" : "Addresses must be 3 to 255 characters.";
}

export function weightErrors(gross, deduction) {
  const errors = { gross: "", deduction: "" };
  errors.gross = amountError(gross, { label: "Gross weight" });
  if (String(deduction ?? "").trim() === "") {
    errors.deduction = "Enter the deduction (0 if none).";
  } else if (normaliseAmount(deduction) === null) {
    errors.deduction = "Deduction must be a number with at most 2 decimal places.";
  } else if (!errors.gross && compare(normaliseAmount(deduction), normaliseAmount(gross)) >= 0) {
    errors.deduction = "Deduction must be less than the gross weight.";
  }
  return errors;
}

export function rateError(value) {
  const error = amountError(value, { label: "Interest rate" });
  if (error) return error;
  return compare(normaliseAmount(value), "100") > 0 ? "The interest rate cannot be more than 100 % p.a." : "";
}

export function tenureError(value) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 1 && number <= 120 ? "" : "Tenure must be 1 to 120 whole months.";
}

export function passwordError(password, username = "") {
  if (!password || password.length < PASSWORD_MIN) return `Use at least ${PASSWORD_MIN} characters.`;
  if (password.length > 128) return "Use at most 128 characters.";
  if (new Set(password).size < 4) return "This password is too easy to guess.";
  if (username && password.toLowerCase().includes(username.toLowerCase())) return "Don't include your username.";
  return "";
}

// One address only (mirrors domain/validation.email_recipient), so a typo can't fan out.
const EMAIL_PATTERN = /^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/;

export function emailError(value) {
  const text = String(value ?? "").trim();
  const ok = text.length > 0 && text.length <= 254 && EMAIL_PATTERN.test(text) && text.split("@")[0].length <= 64;
  return ok ? "" : "Enter one email address, for example backups@example.com.";
}
