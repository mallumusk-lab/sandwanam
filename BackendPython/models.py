from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime

class AuthRequest(BaseModel):
    userName: str
    password: str

class LoanDataCreate(BaseModel):
    customerId: int
    particulars: str
    particulars_qty: Optional[str] = None
    number_of_items: str
    weight: Decimal
    net_weight: Decimal
    principle_amount: Decimal
    interest: Decimal
    tenure: int
    loan_number: str
    loanStatus: str
    role: str
    date: datetime
    loanType: str
    refreshprincipleamount: Decimal
    refreshinterest: Decimal
    deduction: Decimal

class StatementCreate(BaseModel):
    loan_number: str
    amountPaid: Optional[Decimal] = Decimal("0")
    date: Optional[datetime] = None
    currentPrincipal: Optional[Decimal] = Decimal("0")
    currentInterest: Optional[Decimal] = Decimal("0")
    principleBalance: Optional[Decimal] = Decimal("0")
    interestBalance: Optional[Decimal] = Decimal("0")
    transactionType: Optional[str] = None

class CustomerCreate(BaseModel):
    customerName: str
    phone: str
    address: str
    loanStatus: str
    role: str = 'user'
    user_id: str

class EditLoanRequest(BaseModel):
    particulars: Optional[str] = None
    principleAmount: str
    transactionType: Optional[str] = None
    role: str

class CollectionRequest(BaseModel):
    amountPaid: Decimal
    date: Optional[str] = None
    transactionType: str
    role: str
    is_closing: Optional[bool] = False

class HistoryCollection(BaseModel):
    date: datetime
    amount: Decimal
    type: str

class HistoryImportRequest(BaseModel):
    customerType: str # "new" or "existing"
    customerData: Optional[dict] = None
    selectedCustomerId: Optional[int] = None
    loanData: dict
    collections: List[HistoryCollection]
    role: str

class BranchCreate(BaseModel):
    userName: str
    password: str
    display_name: str
    address: Optional[str] = None
    logo: Optional[str] = None  # base64 encoded image
    permissions: Optional[str] = "newcustomer,userlist,form1,analytics,report,history,backup"

class BranchUpdate(BaseModel):
    display_name: Optional[str] = None
    address: Optional[str] = None
    logo: Optional[str] = None  # base64 encoded image
    permissions: Optional[str] = None

class ResetPasswordRequest(BaseModel):
    new_password: str
