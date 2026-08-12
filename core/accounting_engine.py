"""
Accounting Engine for FinAnalyzer Enterprise v2.0.0.
Handles double-entry bookkeeping validation, journal entry posting, trial balance,
balance sheet, income statement (P&L), cash flow statement, period locking,
and multi-currency conversion.
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from core.models import (
    JournalEntry, Transaction, Account, AccountType, TransactionStatus, FiscalYear, Currency
)

class AccountingEngine:
    """Core double-entry bookkeeping and financial statement generator."""

    def __init__(self, session: Session, company_id: int):
        self.session = session
        self.company_id = company_id

    def post_journal_entry(
        self,
        entry_number: str,
        entry_date: date,
        description: str,
        lines: List[Dict[str, Any]], # [{'account_id': int, 'debit': Decimal, 'credit': Decimal, 'description': str}]
        created_by: Optional[str] = None,
        commit: bool = True,
    ) -> JournalEntry:
        """
        Post a balanced double-entry journal entry.
        Verifies that total debits equal total credits.
        """
        total_debit = sum(Decimal(str(l.get('debit', 0))) for l in lines)
        total_credit = sum(Decimal(str(l.get('credit', 0))) for l in lines)

        # Allow small floating point tolerance
        if abs(total_debit - total_credit) > Decimal('0.0001'):
            raise ValueError(f"Unbalanced journal entry: Total Debits ({total_debit}) != Total Credits ({total_credit})")

        # Check if fiscal year is closed
        if self._is_period_locked(entry_date):
            raise ValueError(f"Cannot post entry to locked fiscal period for date {entry_date}")

        entry = JournalEntry(
            company_id=self.company_id,
            entry_number=entry_number,
            date=entry_date,
            description=description,
            status=TransactionStatus.POSTED,
            created_by=created_by
        )
        self.session.add(entry)
        self.session.flush()

        for l in lines:
            tx = Transaction(
                journal_entry_id=entry.id,
                account_id=l['account_id'],
                debit=Decimal(str(l.get('debit', 0))),
                credit=Decimal(str(l.get('credit', 0))),
                description=l.get('description', description)
            )
            self.session.add(tx)

        if commit:
            self.session.commit()
        return entry

    def _is_period_locked(self, target_date: date) -> bool:
        """Check if the fiscal year containing target_date is closed."""
        fy = self.session.execute(
            select(FiscalYear).where(
                FiscalYear.company_id == self.company_id,
                FiscalYear.start_date <= target_date,
                FiscalYear.end_date >= target_date
            )
        ).scalar_one_or_none()
        
        return fy.is_closed if fy else False

    def calculate_trial_balance(self, as_of_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """Calculate trial balance for all accounts up to as_of_date."""
        stmt = (
            select(
                Account.id,
                Account.code,
                Account.name,
                Account.account_type,
                func.coalesce(func.sum(Transaction.debit), 0).label("total_debit"),
                func.coalesce(func.sum(Transaction.credit), 0).label("total_credit")
            )
            .outerjoin(Transaction, Account.id == Transaction.account_id)
            .outerjoin(JournalEntry, Transaction.journal_entry_id == JournalEntry.id)
            .where(Account.company_id == self.company_id)
        )
        
        if as_of_date:
            stmt = stmt.where(JournalEntry.date <= as_of_date)
            
        stmt = stmt.group_by(Account.id).order_by(Account.code)
        results = self.session.execute(stmt).all()

        trial_balance = []
        for r in results:
            debit = Decimal(r.total_debit)
            credit = Decimal(r.total_credit)
            
            # Normal balances
            net_balance = Decimal('0.0000')
            if r.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
                net_balance = debit - credit
            else:
                net_balance = credit - debit

            trial_balance.append({
                "account_id": r.id,
                "code": r.code,
                "name": r.name,
                "type": r.account_type.value,
                "debit": debit,
                "credit": credit,
                "net_balance": net_balance
            })

        return trial_balance

    def generate_balance_sheet(self, as_of_date: date) -> Dict[str, Any]:
        """Generate Balance Sheet: Assets = Liabilities + Equity."""
        tb = self.calculate_trial_balance(as_of_date)
        
        assets = [acc for acc in tb if acc["type"] == AccountType.ASSET.value]
        liabilities = [acc for acc in tb if acc["type"] == AccountType.LIABILITY.value]
        equity = [acc for acc in tb if acc["type"] == AccountType.EQUITY.value]

        total_assets = sum(a["net_balance"] for a in assets)
        total_liabilities = sum(l["net_balance"] for l in liabilities)
        total_equity = sum(e["net_balance"] for e in equity)

        return {
            "as_of_date": as_of_date.isoformat(),
            "assets": assets,
            "total_assets": total_assets,
            "liabilities": liabilities,
            "total_liabilities": total_liabilities,
            "equity": equity,
            "total_equity": total_equity,
            "total_liabilities_and_equity": total_liabilities + total_equity,
            "is_balanced": abs(total_assets - (total_liabilities + total_equity)) < Decimal('0.01')
        }

    def generate_income_statement(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """Generate Income Statement (Profit & Loss) for a date range."""
        # Filter transactions within range
        stmt = (
            select(
                Account.id,
                Account.code,
                Account.name,
                Account.account_type,
                func.coalesce(func.sum(Transaction.debit), 0).label("total_debit"),
                func.coalesce(func.sum(Transaction.credit), 0).label("total_credit")
            )
            .join(Transaction, Account.id == Transaction.account_id)
            .join(JournalEntry, Transaction.journal_entry_id == JournalEntry.id)
            .where(
                Account.company_id == self.company_id,
                JournalEntry.date >= start_date,
                JournalEntry.date <= end_date,
                Account.account_type.in_([AccountType.REVENUE, AccountType.EXPENSE])
            )
            .group_by(Account.id)
            .order_by(Account.code)
        )
        results = self.session.execute(stmt).all()

        revenues = []
        expenses = []
        
        for r in results:
            debit = Decimal(r.total_debit)
            credit = Decimal(r.total_credit)
            
            if r.account_type == AccountType.REVENUE:
                bal = credit - debit
                revenues.append({"code": r.code, "name": r.name, "amount": bal})
            else:
                bal = debit - credit
                expenses.append({"code": r.code, "name": r.name, "amount": bal})

        total_revenue = sum(r["amount"] for r in revenues)
        total_expense = sum(e["amount"] for e in expenses)
        net_income = total_revenue - total_expense

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "revenues": revenues,
            "total_revenue": total_revenue,
            "expenses": expenses,
            "total_expense": total_expense,
            "net_income": net_income
        }

    def close_fiscal_year(self, year: int, closing_account_id: int, commit: bool = True) -> FiscalYear:
        """Lock fiscal year and post year-end closing entries for retained earnings."""
        # Find fiscal year
        fy = self.session.execute(
            select(FiscalYear).where(
                FiscalYear.company_id == self.company_id,
                FiscalYear.year == year
            )
        ).scalar_one_or_none()

        if not fy:
            raise ValueError(f"Fiscal year {year} not found.")
        
        if fy.is_closed:
            raise ValueError(f"Fiscal year {year} is already closed.")

        # Generate P&L for the fiscal year
        pnl = self.generate_income_statement(fy.start_date, fy.end_date)
        net_income = pnl["net_income"]

        # Post closing entry if net income != 0
        if net_income != 0:
            closing_lines = []
            # Zero out revenues and expenses
            for r in pnl["revenues"]:
                # Find account id
                acc = self.session.execute(select(Account).where(Account.code == r["code"], Account.company_id == self.company_id)).scalar_one()
                closing_lines.append({"account_id": acc.id, "debit": r["amount"], "credit": 0, "description": f"Year-end close revenue {year}"})
            for e in pnl["expenses"]:
                acc = self.session.execute(select(Account).where(Account.code == e["code"], Account.company_id == self.company_id)).scalar_one()
                closing_lines.append({"account_id": acc.id, "debit": 0, "credit": e["amount"], "description": f"Year-end close expense {year}"})
            
            # Retained earnings adjustment
            closing_lines.append({"account_id": closing_account_id, "debit": 0 if net_income > 0 else abs(net_income), "credit": net_income if net_income > 0 else 0, "description": f"Retained earnings close {year}"})

            self.post_journal_entry(
                entry_number=f"CLOSE-{year}",
                entry_date=fy.end_date,
                description=f"Fiscal Year {year} Closing Entry",
                lines=closing_lines,
                created_by="System",
                commit=False,
            )

        fy.is_closed = True
        if commit:
            self.session.commit()
        return fy

    def convert_currency(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        """Convert amount between currencies using stored exchange rates."""
        if from_currency == to_currency:
            return amount

        fc = self.session.execute(select(Currency).where(Currency.code == from_currency)).scalar_one_or_none()
        tc = self.session.execute(select(Currency).where(Currency.code == to_currency)).scalar_one_or_none()

        if not fc or not tc:
            raise ValueError(f"Exchange rate not found for {from_currency} or {to_currency}")

        # Base currency is relative to 1.0
        amount_in_base = amount / fc.exchange_rate
        converted = amount_in_base * tc.exchange_rate
        return converted
