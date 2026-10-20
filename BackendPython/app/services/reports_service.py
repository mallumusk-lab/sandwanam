"""Dashboard, performance and transaction reports (definitions: app/domain/reports.py)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from ..domain import dates, reports
from ..domain.money import ZERO, AmountError, money, parse_amount
from ..errors import Invalid
from . import serialize
from .context import Actor, Scope, resolve_scope
from .loans_service import live_quote, terms_of

DETAIL_LIMIT = 1000
EXPORT_LIMIT = 20000
GOLD_RATE_KEY = "gold_rate"
INACTIVE_AFTER_DAYS = 90


async def _scope(repos, actor: Actor, branch: str | None) -> Scope:
    actor.require("analytics")
    return resolve_scope(actor, branch, await repos.users.branch_prefixes())


def _period(start: str | None, end: str | None, today: date) -> tuple[date, date]:
    try:
        return reports.resolve_period(start, end, today)
    except reports.PeriodError as exc:
        raise Invalid(str(exc), code="invalid_period") from exc


async def gold_rate(repos) -> dict | None:
    setting = await repos.settings.get(GOLD_RATE_KEY)
    if not setting:
        return None
    return {
        "per_gram": serialize.money(Decimal(str(setting["value"]["per_gram"]))),
        "updated_at": serialize.stamp(setting["updated_at"]),
        "updated_by": setting["updated_by"],
    }


def _ltv(outstanding: Decimal, net_weight: Decimal, rate: Decimal | None) -> str | None:
    if rate is None or rate <= 0 or net_weight <= 0:
        return None
    return str((outstanding / (net_weight * rate) * 100).quantize(Decimal("0.1")))


async def portfolio(repos, actor: Actor, branch: str | None, now: datetime) -> dict:
    """Live position of every open loan in scope, as if settled today."""
    scope = await _scope(repos, actor, branch)
    today = dates.business_date(now)
    rows = await repos.loans.open_with_position(scope.branch)
    rate_info = await gold_rate(repos)
    rate = Decimal(rate_info["per_gram"]) if rate_info else None

    principal = interest = weight = ZERO
    aging: dict[str, int] = {label: 0 for _, _, label in reports.AGING_BUCKETS}
    by_branch: dict[str, dict] = defaultdict(lambda: {"loans": 0, "principal": ZERO, "interest": ZERO})
    overdue, inactive, loans = [], [], []
    for row in rows:
        q = live_quote(row, today)
        if q is None:
            continue
        net = row.get("net_weight") or ZERO
        principal += q.principal
        interest += q.interest
        weight += net
        last_payment = dates.business_date(row["last_payment_at"]) if row.get("last_payment_at") else terms_of(row).start_date
        idle_days = max(0, (today - last_payment).days)
        aging[reports.aging_bucket(idle_days)] += 1
        branch_totals = by_branch[row["branch_prefix"]]
        branch_totals["loans"] += 1
        branch_totals["principal"] += q.principal
        branch_totals["interest"] += q.interest
        due = dates.add_months(terms_of(row).start_date, int(row.get("tenure") or 0))
        follow_up = row.get("follow_up_date")
        entry = {
            "loan_number": row["loan_number"],
            "customer_id": row["customerid"],
            "customer_name": row["customername"],
            "phone": row["phone"],
            "branch": row["branch_prefix"],
            "loan_date": terms_of(row).start_date.isoformat(),
            "due_date": due.isoformat(),
            "last_payment": last_payment.isoformat(),
            "days_since_payment": idle_days,
            "principal": serialize.money(q.principal),
            "interest": serialize.money(q.interest),
            "total": serialize.money(q.total),
            "net_weight": serialize.money(net),
            "ltv": _ltv(q.total, net, rate),
            "follow_up_date": follow_up.isoformat() if follow_up else None,
        }
        loans.append(entry)
        if due < today:
            overdue.append({**entry, "days_overdue": (today - due).days,
                            "followed_up": bool(follow_up and follow_up > today)})
        if idle_days > INACTIVE_AFTER_DAYS:
            inactive.append(entry)

    overdue.sort(key=lambda e: (e["followed_up"], -e["days_overdue"]))
    inactive.sort(key=lambda e: -e["days_since_payment"])
    loans.sort(key=lambda e: -Decimal(e["total"]))
    names = {b["branch_prefix"]: b.get("display_name") or b["username"] for b in await repos.users.branches()}
    return {
        "as_of": today.isoformat(),
        "open_loans": len(loans),
        "principal": serialize.money(principal),
        "interest": serialize.money(interest),
        "total": serialize.money(principal + interest),
        "net_weight": serialize.money(weight),
        "ltv": _ltv(principal + interest, weight, rate),
        "gold_rate": rate_info,
        "aging": [{"bucket": label, "loans": count} for label, count in aging.items()],
        "branches": [
            {"code": code, "name": names.get(code, code), "loans": t["loans"],
             "principal": serialize.money(t["principal"]), "interest": serialize.money(t["interest"])}
            for code, t in sorted(by_branch.items())
        ],
        "overdue": overdue,
        "inactive": inactive,
        "loans": loans,
    }


def _totals_view(row: dict) -> dict:
    return {
        "disbursed": serialize.money(money(row["new_principal"]) + money(row["top_ups"])),
        "new_loans": int(row["new_loans"]),
        "interest_collected": serialize.money(row["interest_collected"]),
        "principal_collected": serialize.money(row["principal_collected"]),
        "total_collected": serialize.money(row["total_collected"]),
        "collections": int(row["collections"]),
        "compounded": serialize.money(row["compounded"]),
        "compounded_loans": int(row["compounded_loans"]),
        "written_off": serialize.money(row["written_off"]),
        "closures": int(row["closures"]),
        "gold_pledged": serialize.money(row["gold_pledged"]),
        "gold_released": serialize.money(row["gold_released"]),
    }


async def performance(repos, actor: Actor, branch: str | None, start: str | None, end: str | None, now: datetime) -> dict:
    scope = await _scope(repos, actor, branch)
    first, last = _period(start, end, dates.business_date(now))
    lower, upper = dates.ist_day_bounds_utc(first, last)
    totals = await repos.reports.period_totals(scope.branch, lower, upper)
    return {"from": first.isoformat(), "to": last.isoformat(), **_totals_view(totals)}


def _detail_row(metric: str, row: dict) -> dict:
    base = {
        "loan_number": row["loan_number"],
        "customer_name": row.get("customername"),
        "phone": row.get("phone"),
        "branch": row.get("branch_prefix"),
    }
    if metric == "disbursed":
        return {**base, "date": serialize.day(row["date"]), "kind": row["kind"], "amount": serialize.money(row["amount"])}
    if metric in ("new_loans", "gold_pledged", "closures", "gold_released"):
        when = row.get("closed_at") if metric in ("closures", "gold_released") else row.get("date")
        return {**base, "date": serialize.day(when), "principal": serialize.money(row["principle_amount"]),
                "rate": serialize.money(row["interest"]), "net_weight": serialize.money(row["net_weight"])}
    if metric == "written_off":
        legacy = row.get("writeoff_principal") is None
        amount = row["principlebalance"] if legacy else (row["writeoff_principal"] or ZERO) + (row["writeoff_interest"] or ZERO)
        return {**base, "date": serialize.day(row["date"]), "amount": serialize.money(amount), "legacy": legacy}
    if metric == "compounded":
        return {**base, "date": serialize.day(row["date"]), "amount": serialize.money(row["currentprincipal"]),
                "new_principal": serialize.money(row["principlebalance"])}
    return {
        **base,
        "date": serialize.day(row["date"]),
        "amount": serialize.money(row["amountpaid"]),
        "interest": serialize.money(row["currentinterest"]),
        "principal": serialize.money(-(row["currentprincipal"] or ZERO)),
    }


async def details(repos, actor: Actor, metric: str, branch: str | None, start: str | None, end: str | None,
                  now: datetime) -> dict:
    if metric not in reports.PERIOD_METRICS:
        raise Invalid(f"Unknown metric '{metric}'.", code="invalid_metric")
    scope = await _scope(repos, actor, branch)
    first, last = _period(start, end, dates.business_date(now))
    lower, upper = dates.ist_day_bounds_utc(first, last)
    rows = await repos.reports.details(metric, scope.branch, lower, upper, DETAIL_LIMIT + 1)
    return {
        "metric": metric,
        "from": first.isoformat(),
        "to": last.isoformat(),
        "rows": [_detail_row(metric, r) for r in rows[:DETAIL_LIMIT]],
        "truncated": len(rows) > DETAIL_LIMIT,
    }


async def trends(repos, actor: Actor, branch: str | None, now: datetime, months: int = 6) -> list[dict]:
    scope = await _scope(repos, actor, branch)
    today = dates.business_date(now)
    starts = reports.month_starts(today, months)
    lower, upper = dates.ist_day_bounds_utc(starts[0], today)
    flows = {r["month"]: r for r in await repos.reports.monthly_flows(scope.branch, lower, upper)}
    result = []
    for start in starts:
        key = start.strftime("%Y-%m")
        row = flows.get(key, {})
        result.append({
            "month": key,
            "label": start.strftime("%b %Y"),
            "disbursed": serialize.money(row.get("disbursed") or ZERO),
            "collected": serialize.money(row.get("collected") or ZERO),
        })
    return result


async def dashboard(repos, actor: Actor, branch: str | None, now: datetime) -> dict:
    scope = await _scope(repos, actor, branch)
    today = dates.business_date(now)
    lower, upper = dates.ist_day_bounds_utc(today, today)
    counts = await repos.reports.loan_counts(scope.branch)
    recent = await repos.reports.recent(scope.branch, 8)
    return {
        "branch": scope.branch,
        "today": {"date": today.isoformat(), **_totals_view(await repos.reports.period_totals(scope.branch, lower, upper))},
        "counts": {k: int(v or 0) for k, v in counts.items()},
        "portfolio": await portfolio(repos, actor, scope.branch, now),
        "trends": await trends(repos, actor, scope.branch, now),
        "recent": [
            {"id": r["statementid"], "loan_number": r["loan_number"], "kind": r["transactiontype"],
             "date": serialize.day(r["date"]), "amount": serialize.money(_recent_amount(r)),
             "customer_name": r["customername"], "customer_id": r["customerid"], "branch": r["branch_prefix"]}
            for r in recent
        ],
    }


def _recent_amount(row: dict) -> Decimal:
    kind = row["transactiontype"]
    if kind == "addColl" or kind == "modify":
        return row["amountpaid"] or ZERO
    if kind in ("disbursement", "compounding"):
        return row["currentprincipal"] or ZERO
    if kind == "writeoff":
        if row.get("writeoff_principal") is None:  # the earlier system stored the closing balance
            return row.get("principlebalance") or ZERO
        return (row.get("writeoff_principal") or ZERO) + (row.get("writeoff_interest") or ZERO)
    return ZERO


async def transactions(repos, actor: Actor, *, branch: str | None, start: str | None, end: str | None,
                       term: str | None, kind: str | None, page: int, page_size: int, now: datetime) -> dict:
    actor.require("report")
    scope = resolve_scope(actor, branch, await repos.users.branch_prefixes())
    first, last = _period(start, end, dates.business_date(now))
    lower, upper = dates.ist_day_bounds_utc(first, last)
    if kind and kind not in ("newLoan", "addColl", "disbursement", "compounding", "writeoff", "modify"):
        raise Invalid("Unknown entry type.", code="invalid_kind")
    size = max(1, min(page_size, 200))
    current = max(1, page)
    cleaned = " ".join((term or "").split())[:60] or None
    rows, total = await repos.reports.transactions(scope.branch, lower, upper, cleaned, kind, size, (current - 1) * size)
    return {
        "from": first.isoformat(),
        "to": last.isoformat(),
        "items": [_transaction_view(r) for r in rows],
        "total": total,
        "page": current,
        "page_size": size,
    }


def _transaction_view(row: dict) -> dict:
    view = serialize.statement(row)
    view.update({"customer_name": row["customername"], "customer_number": row["user_id"], "branch": row["branch_prefix"]})
    return view


async def transactions_csv(repos, actor: Actor, *, branch: str | None, start: str | None, end: str | None,
                           term: str | None, kind: str | None, now: datetime) -> tuple[str, str]:
    actor.require("report")
    scope = resolve_scope(actor, branch, await repos.users.branch_prefixes())
    first, last = _period(start, end, dates.business_date(now))
    lower, upper = dates.ist_day_bounds_utc(first, last)
    cleaned = " ".join((term or "").split())[:60] or None
    rows, _ = await repos.reports.transactions(scope.branch, lower, upper, cleaned, kind, EXPORT_LIMIT, 0)
    headers = ["Date", "Loan", "Customer", "Customer no.", "Branch", "Type", "Amount paid", "Interest paid",
               "Principal change", "Principal balance", "Interest balance", "Written off"]
    body = []
    for row in rows:
        v = _transaction_view(row)
        body.append([v["date"], v["loan_number"], v["customer_name"], v["customer_number"], v["branch"], v["kind"],
                     v["amount_paid"], v["interest_paid"], v["principal_change"], v["principal_balance"],
                     v["interest_balance"], v["written_off"] or ""])
    filename = f"transactions_{first.isoformat()}_{last.isoformat()}.csv"
    return filename, reports.to_csv(headers, body)


async def set_gold_rate(repos, actor: Actor, per_gram: str) -> dict:
    actor.require_head_office()
    try:
        rate = parse_amount(per_gram, field="Gold rate")
    except AmountError as exc:
        raise Invalid(str(exc), code="invalid_gold_rate") from exc
    await repos.settings.put(GOLD_RATE_KEY, {"per_gram": str(rate)}, actor.username)
    await repos.audit.log(username=actor.username, action="SET_GOLD_RATE", entity_type="SETTING",
                          entity_id=GOLD_RATE_KEY, details=f"Gold rate set to {rate} per gram")
    return await gold_rate(repos)

