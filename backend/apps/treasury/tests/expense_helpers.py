"""Outils communs aux tests des dépenses et de l'assistance sociale (tâche 2.2).

Les dettes sont créées par un montant dû échu sur un type obligatoire
(`Due`, comme le fait la génération mensuelle), les régularisations par un
paiement validé et scellé via les services du grand livre : le solde reste
toujours calculé par `apps.treasury.services`, jamais simulé.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.treasury import services
from apps.treasury.models import ContributionType, Due, Expense, Payment, Transaction
from apps.treasury.tests.factories import ContributionTypeFactory

PDF_CONTENT = b"%PDF-1.4\n%justificatif de test\n%%EOF\n"


def pdf_file(name: str = "justificatif.pdf", content: bytes = PDF_CONTENT) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def text_file() -> SimpleUploadedFile:
    return SimpleUploadedFile("faux.pdf", b"ceci n'est pas un PDF", content_type="application/pdf")


def club_today(ctx) -> datetime.date:
    return services.get_club_today(ctx.club)


def make_category(ctx, **kwargs):
    params = {"name": kwargs.pop("name", "Transport"), **kwargs}
    return services.create_expense_category(club=ctx.club, created_by=ctx.treasurer.user, **params)


def mandatory_type(ctx, amount="10"):
    return ContributionTypeFactory(
        club=ctx.club,
        created_by=ctx.president.user,
        amount=Decimal(amount),
        nature=ContributionType.Nature.MANDATORY,
    )


def put_in_debt(ctx, membership, *, amount="10", due_date=None, ctype=None):
    """Crée un montant dû échu : le joueur est en dette de ``amount``."""

    ctype = ctype or mandatory_type(ctx, amount)
    due_date = due_date or (club_today(ctx) - datetime.timedelta(days=20))
    Due(
        club=ctx.club,
        membership=membership,
        contribution_type=ctype,
        period=datetime.date(due_date.year, due_date.month, 1),
        amount=Decimal(amount),
        due_date=due_date,
        source=Due.Source.SCHEDULER,
        created_at=timezone.now(),
    ).save()
    return ctype


def pay_mandatory(ctx, membership, ctype, *, amount="10", paid_on=None) -> Payment:
    """Paiement validé et scellé sur un type obligatoire (régularisation)."""

    now = timezone.now()
    payment = Payment(
        club=ctx.club,
        membership=membership,
        contribution_type=ctype,
        amount=Decimal(amount),
        currency=ctx.club.settings.currency,
        method=Payment.Method.CASH,
        paid_on=paid_on or club_today(ctx),
        source=Payment.Source.TREASURER_ENTRY,
        submitted_by=ctx.treasurer.user,
        submitted_at=now,
        validated_by=ctx.treasurer.user,
        validated_at=now,
    )
    payment.save()
    txn = services.open_payment_transaction(payment=payment, provider=Transaction.Provider.MANUAL)
    services.advance_transaction(transaction_obj=txn, status=Transaction.Status.SUCCEEDED)
    return payment


def make_expense(ctx, category=None, *, amount="25", by=None, **kwargs) -> Expense:
    return services.create_expense(
        club=ctx.club,
        created_by=(by or ctx.treasurer).user,
        category=category or make_category(ctx),
        amount=amount,
        beneficiary_name=kwargs.pop("beneficiary_name", "Station Total Gombe"),
        reason=kwargs.pop("reason", "Carburant du minibus"),
        expense_date=kwargs.pop("expense_date", club_today(ctx)),
        **kwargs,
    )


def release(ctx, expense, *, by=None, now=None) -> Expense:
    return services.release_expense(expense=expense, released_by=(by or ctx.vice_president).user, now=now)


def days_ago(days: int) -> datetime.datetime:
    return timezone.now() - datetime.timedelta(days=days)
