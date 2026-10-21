// Interest projection for the loan calculator. It mirrors the server's ledger rules
// exactly (shared test vectors in /test-vectors/interest.json). Every other screen shows
// amounts computed by the server; this module is only for "what if" estimates.
//
// Rules: annual rate; interest = P × r × days ÷ 36500, rounded half-up to the paisa;
// customer periods count (end − start) + 1 days; compounding on start + 365·k with
// exact days; closing within 7 days charges at least 7 days.

import { addDays, daysBetween } from "./dates.js";
import { fromPaise, toPaise } from "./money.js";

export const DEFAULT_RATE = "18.00";
const COMPOUNDING_DAYS = 365;
const CLOSING_MINIMUM_DAYS = 7;
const DENOMINATOR = 36500n * 100n; // rate is in hundredths of a percent

function rateUnits(rate) {
  return toPaise(rate ?? DEFAULT_RATE); // "12.5" → 1250n
}

function roundedInterest(principalPaise, rate, days) {
  if (days <= 0 || principalPaise <= 0n) return 0n;
  const numerator = principalPaise * rateUnits(rate) * BigInt(days);
  return (2n * numerator + DENOMINATOR) / (2n * DENOMINATOR);
}

/** Quote for a loan with no payments, as of `asOf` (both "YYYY-MM-DD"). */
export function quote({ principal, rate, start, asOf, closing = false }) {
  let principalPaise = toPaise(principal);
  let interestPaise = 0n;
  let positionDay = start;
  let compoundings = 0;
  for (;;) {
    const due = addDays(start, COMPOUNDING_DAYS * (compoundings + 1));
    if (due > asOf) break;
    const days = daysBetween(positionDay, due);
    interestPaise += roundedInterest(principalPaise, rate, days);
    principalPaise += interestPaise;
    interestPaise = 0n;
    positionDay = due;
    compoundings += 1;
  }
  let periodDays = daysBetween(positionDay, asOf) + 1;
  if (closing && daysBetween(start, asOf) + 1 < CLOSING_MINIMUM_DAYS) {
    periodDays = Math.max(periodDays, CLOSING_MINIMUM_DAYS);
  }
  interestPaise += roundedInterest(principalPaise, rate, periodDays);
  return {
    principal: fromPaise(principalPaise),
    interest: fromPaise(interestPaise),
    total: fromPaise(principalPaise + interestPaise),
    // all interest since the loan date, including any already compounded into principal
    totalInterest: fromPaise(principalPaise + interestPaise - toPaise(principal)),
    periodDays,
    compoundings,
  };
}

/** Interest for one day on a principal, for the calculator's "per day" figure. */
export function dailyInterest(principal, rate) {
  return fromPaise(roundedInterest(toPaise(principal), rate, 1));
}

export function monthlyRate(annualRate) {
  return fromPaise((toPaise(annualRate ?? DEFAULT_RATE) + 6n) / 12n);
}
