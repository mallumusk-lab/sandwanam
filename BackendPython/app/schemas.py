"""Request bodies. Unknown fields are rejected; amounts travel as strings (numbers are
accepted and converted) so no value passes through binary floating point."""
from __future__ import annotations

from datetime import date as Date
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field

RequestId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")]
Amount = Annotated[str, Field(min_length=1, max_length=20)]
ShortText = Annotated[str, Field(max_length=255)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)


class LoginIn(Body):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


class ChangePasswordIn(Body):
    current_password: Annotated[str, Field(max_length=256)]
    new_password: Annotated[str, Field(max_length=256)]


class CustomerIn(Body):
    name: Annotated[str, Field(max_length=100)]
    phone: Annotated[str, Field(max_length=20)]
    address: ShortText
    branch: Optional[Annotated[str, Field(max_length=10)]] = None


class ItemIn(Body):
    name: Annotated[str, Field(max_length=60)]
    qty: Annotated[int, Field(ge=1, le=999)]


class LoanIn(Body):
    customer_id: int
    items: Annotated[list[ItemIn], Field(min_length=1, max_length=50)]
    gross_weight: Amount
    deduction: Amount
    principal: Amount
    rate: Amount
    tenure_months: Annotated[int, Field(ge=1, le=120)]
    request_id: RequestId


class PostingIn(Body):
    amount: Amount
    expected_total: Optional[Amount] = None
    request_id: RequestId


class CloseIn(Body):
    amount_received: Amount
    write_off_remaining: bool = False
    expected_total: Amount
    request_id: RequestId


class ItemsIn(Body):
    items: Annotated[list[ItemIn], Field(min_length=1, max_length=50)]


class FollowUpIn(Body):
    follow_up_date: Optional[Date] = None


class HistoryLoanIn(Body):
    items: Annotated[list[ItemIn], Field(min_length=1, max_length=50)]
    gross_weight: Amount
    deduction: Amount
    principal: Amount
    rate: Amount
    tenure_months: Annotated[int, Field(ge=1, le=120)]
    loan_date: Date


class HistoryEntryIn(Body):
    date: Date
    kind: Annotated[str, Field(pattern=r"^(addColl|disbursement|compounding|close)$")]
    amount: Amount  # for a close or compounding: the amount (may be 0)
    write_off_remaining: bool = False  # close only: confirms writing off what remains unpaid


class ImportPreviewIn(Body):
    loan: HistoryLoanIn
    entries: Annotated[list[HistoryEntryIn], Field(max_length=500)]


class PreviewBalancesIn(Body):
    principal_balance: Amount
    interest_balance: Amount


class ImportIn(ImportPreviewIn):
    customer_id: Optional[int] = None
    new_customer: Optional[CustomerIn] = None
    expected: Optional[PreviewBalancesIn] = None
    request_id: RequestId


class GoldRateIn(Body):
    per_gram: Amount


class CashDayIn(Body):
    branch: Optional[Annotated[str, Field(max_length=10)]] = None  # head office only
    opening_counted: Amount
    request_id: RequestId


class CashEntryIn(Body):
    direction: Annotated[str, Field(pattern=r"^(in|out)$")]
    category: Annotated[str, Field(max_length=40)]
    description: Optional[ShortText] = None
    reference: Optional[Annotated[str, Field(max_length=40)]] = None
    amount: Amount
    request_id: RequestId


class CashVoidIn(Body):
    reason: Annotated[str, Field(min_length=3, max_length=255)]


class CashCloseIn(Body):
    closing_counted: Amount
    expected_total: Amount


class BranchFieldsIn(Body):
    display_name: Optional[Annotated[str, Field(max_length=100)]] = None
    legal_name: Optional[ShortText] = None
    address: Optional[Annotated[str, Field(max_length=500)]] = None
    phone: Optional[Annotated[str, Field(max_length=20)]] = None
    email: Optional[ShortText] = None
    logo: Optional[Annotated[str, Field(max_length=300_000)]] = None
    clear_logo: bool = False
    permissions: Optional[list[Annotated[str, Field(max_length=20)]]] = None


class BranchCreateIn(BranchFieldsIn):
    username: Annotated[str, Field(max_length=32)]
    branch_prefix: Annotated[str, Field(max_length=5)]
    temporary_password: Annotated[str, Field(max_length=256)]


class ResetPasswordIn(Body):
    temporary_password: Annotated[str, Field(max_length=256)]


class ActiveIn(Body):
    active: bool


class BackupSourceIn(Body):
    """Exactly one of: a backup object (a parsed .json), a gzipped file as base64, or the emailed
    password ZIP as base64 with its password. The password is used to decrypt only: it is never
    stored, logged or audited. Requests stay under the hosting limit (about 4.5 MB)."""
    model_config = ConfigDict(extra="forbid")

    backup: Optional[dict] = None
    backup_gzip: Optional[Annotated[str, Field(min_length=1, max_length=7_000_000)]] = None
    backup_zip: Optional[Annotated[str, Field(min_length=1, max_length=4_700_000)]] = None
    zip_password: Optional[Annotated[str, Field(min_length=12, max_length=128)]] = None


class RestoreIn(BackupSourceIn):
    confirmation: Annotated[str, Field(max_length=20)]


class BackupEmailIn(Body):
    recipient: Optional[Annotated[str, Field(max_length=254)]] = None
    enabled: bool
