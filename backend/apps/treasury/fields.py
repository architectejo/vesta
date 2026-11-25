"""Champs de sérialiseur partagés de la trésorerie."""

from __future__ import annotations

from rest_framework import serializers

from apps.treasury import services


class MoneyField(serializers.Field):
    """Montant saisi par l'utilisateur (décision client du 15/11/2026).

    Délègue ENTIÈREMENT à ``services.to_money`` (une seule source de
    vérité) : virgule ou point décimal acceptés (« 10,50 », « 10.50 »),
    entier accepté ; plus de 2 décimales, notation scientifique,
    séparateur de milliers et booléen refusés avec le message en français
    du service, jamais arrondis en silence.

    Valeur validée : ``Decimal`` à 2 décimales. Représentation : chaîne au
    point décimal (« 10.50 »), inchangée pour l'interface.
    """

    default_error_messages = {"invalid": services._AMOUNT_INVALID_MESSAGE}

    def to_internal_value(self, data):
        # Nombre JSON (``12.5``) : déjà accepté par l'ancien ``DecimalField``
        # (test_expenses_review_api). Il est ramené à son écriture exacte
        # (``repr`` : la plus courte qui redonne le même nombre, « 12.5 »)
        # puis soumis aux règles de saisie texte de ``to_money`` : « 12.555 »,
        # « nan », « inf » ou « 1e+22 » restent refusés. Aucun calcul en
        # flottant. Les booléens (sous-classe d'``int``) restent refusés.
        if isinstance(data, float):
            data = repr(data)
        try:
            return services.to_money(data)
        except services.InvalidAmountError as exc:
            raise serializers.ValidationError(str(exc), code="invalid") from None

    def to_representation(self, value):
        return services._money_str(value)
