"""Vues des tests de performance (docs/ecrans/sport-statistiques-seance.md,
partie C8). Permission -> service -> réponse ; aucune règle métier ici.

Lecture : Coach, Assistant, Président, Vice-président et Directeur sportif
voient tout (``CanViewAllPerformance``) ; tout autre joueur ne voit que ses
propres résultats (jamais ceux des autres : 404 pour un autre joueur).
Écriture : Coach et Assistant (``CanManagePerformanceTests``).
"""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clubs.models import Membership
from apps.clubs.permissions import IsActiveClubMember
from apps.core.roles import has_any_role
from apps.core.tenant import get_active_club
from apps.sport import performance, services
from apps.sport.models import Event, PerformanceResult, PerformanceTest
from apps.sport.permissions import CanManagePerformanceTests, CanViewAllPerformance, PERFORMANCE_VIEW_ALL_ROLES
from apps.sport.views import _EVENT_NOT_FOUND, _GATE, _not_found, _sport_error

_TEST_NOT_FOUND = "Ce test n'existe pas dans ce club."
_RESULT_NOT_FOUND = "Ce résultat n'existe pas dans ce club."
_PLAYER_NOT_FOUND = "Ce joueur n'existe pas dans ce club."


class PerformanceTestInputSerializer(serializers.Serializer):
    """Forme des entrées ; toutes les règles (bornes, messages français) sont
    appliquées par ``apps.sport.performance``."""

    name = serializers.CharField(required=False, allow_blank=True)
    kind = serializers.CharField(required=False, allow_blank=True)
    distance_m = serializers.JSONField(required=False, allow_null=True)
    duration_s = serializers.JSONField(required=False, allow_null=True)
    attempts = serializers.JSONField(required=False, allow_null=True)
    time_limit_s = serializers.JSONField(required=False, allow_null=True)
    unit = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    decimals = serializers.JSONField(required=False, allow_null=True)
    higher_is_better = serializers.JSONField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)


class BulkItemSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField()
    attempt_no = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    time_ms = serializers.JSONField(required=False, allow_null=True)
    distance_m = serializers.JSONField(required=False, allow_null=True)
    count = serializers.JSONField(required=False, allow_null=True)
    value = serializers.JSONField(required=False, allow_null=True)
    outcome = serializers.CharField(required=False, allow_blank=True)
    client_uuid = serializers.UUIDField(required=False, allow_null=True)


class BulkResultsSerializer(serializers.Serializer):
    test_id = serializers.IntegerField()
    method = serializers.CharField()
    start_mode = serializers.CharField(required=False, allow_blank=True, default="")
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    items = BulkItemSerializer(many=True)


class ResultCorrectionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    outcome = serializers.CharField(required=False, allow_blank=True)
    time_ms = serializers.JSONField(required=False, allow_null=True)
    distance_m = serializers.JSONField(required=False, allow_null=True)
    count = serializers.JSONField(required=False, allow_null=True)
    value = serializers.JSONField(required=False, allow_null=True)


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


def _sees_all(request) -> bool:
    return bool(getattr(request.user, "is_superuser", False) or has_any_role(request.user, PERFORMANCE_VIEW_ALL_ROLES))


def _own_membership(request):
    if getattr(request.user, "is_superuser", False):
        return None
    return Membership.objects.filter(user=request.user, status=Membership.Status.ACTIVE).first()


def _get_test(pk):
    try:
        return PerformanceTest.objects.get(pk=pk), None
    except PerformanceTest.DoesNotExist:
        return None, _not_found(_TEST_NOT_FOUND)


def _test_from_query(request):
    raw = request.query_params.get("test")
    if not raw or not raw.isdigit():
        return None, Response({"detail": "Choisissez un test."}, status=status.HTTP_400_BAD_REQUEST)
    return _get_test(int(raw))


def _run_input(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


class PerformanceTemplatesView(APIView):
    """``GET /sport/performance-test-templates/`` : modèles proposés (liste de
    référence servie depuis le code, rien n'est créé)."""

    permission_classes = _GATE + [CanManagePerformanceTests]

    def get(self, request):
        return Response({"results": performance.list_templates(), "health_help": performance.HEALTH_HELP})


class PerformanceTestListCreateView(APIView):
    """``GET|POST /sport/performance-tests/``."""

    def get_permissions(self):
        permission = CanManagePerformanceTests if self.request.method == "POST" else CanViewAllPerformance
        return [p() for p in _GATE + [permission]]

    def get(self, request):
        archived = request.query_params.get("archived")
        include = "only" if archived == "only" else archived in ("1", "true")
        return Response({"results": performance.get_tests_overview(club=get_active_club(), include_archived=include)})

    def post(self, request):
        data = _run_input(PerformanceTestInputSerializer, request)
        try:
            test = performance.create_performance_test(club=get_active_club(), actor=request.user, data=data)
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(performance.describe_test(test), status=status.HTTP_201_CREATED)


class PerformanceTestDetailView(APIView):
    """``GET|PATCH /sport/performance-tests/{id}/``."""

    def get_permissions(self):
        permission = CanManagePerformanceTests if self.request.method == "PATCH" else CanViewAllPerformance
        return [p() for p in _GATE + [permission]]

    def get(self, request, pk):
        test, error = _get_test(pk)
        if error is not None:
            return error
        return Response(performance.describe_test(test))

    def patch(self, request, pk):
        test, error = _get_test(pk)
        if error is not None:
            return error
        data = _run_input(PerformanceTestInputSerializer, request)
        try:
            test = performance.update_performance_test(test=test, actor=request.user, data=data)
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(performance.describe_test(test))


class PerformanceTestArchiveView(APIView):
    permission_classes = _GATE + [CanManagePerformanceTests]

    def post(self, request, pk):
        test, error = _get_test(pk)
        if error is not None:
            return error
        try:
            test = performance.archive_performance_test(test=test, actor=request.user)
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(performance.describe_test(test))


class PerformanceLeaderboardView(APIView):
    """``GET /sport/performance-tests/{id}/leaderboard/?period=last|season``."""

    permission_classes = _GATE + [CanViewAllPerformance]

    def get(self, request, pk):
        test, error = _get_test(pk)
        if error is not None:
            return error
        try:
            data = performance.get_leaderboard(
                club=get_active_club(), test=test, period=request.query_params.get("period") or "last",
                request=request,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        return Response(data)


class EventPerformanceResultsView(APIView):
    """``GET /sport/events/{id}/performance-results/?test=`` : le staff voit le
    classement de la séance, tout autre joueur sa propre ligne seulement."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, pk):
        try:
            event = Event.objects.get(pk=pk)
        except Event.DoesNotExist:
            return _not_found(_EVENT_NOT_FOUND)
        test, error = _test_from_query(request)
        if error is not None:
            return error
        return Response(
            performance.get_event_results(
                event=event, test=test, viewer=request.user, viewer_membership=_own_membership(request),
                sees_all=_sees_all(request), request=request,
            )
        )


class EventPerformanceResultsBulkView(APIView):
    """``POST /sport/events/{id}/performance-results/bulk/`` : enregistre des
    mesures (Coach, Assistant), idempotent par ``client_uuid``."""

    permission_classes = _GATE + [CanManagePerformanceTests]

    def post(self, request, pk):
        try:
            event = Event.objects.select_related("club").get(pk=pk)
        except Event.DoesNotExist:
            return _not_found(_EVENT_NOT_FOUND)
        data = _run_input(BulkResultsSerializer, request)
        test, error = _get_test(data["test_id"])
        if error is not None:
            return error
        try:
            outcome = performance.record_results(
                event=event, test=test, method=data["method"], start_mode=data.get("start_mode", ""),
                client_uuid=data.get("client_uuid"), items=[dict(item) for item in data["items"]],
                actor=request.user,
            )
        except services.SportError as exc:
            return _sport_error(exc)
        payload = {
            "run_id": outcome["run_id"],
            "counts": outcome["counts"],
            "results": [
                {
                    "membership_id": item["membership_id"],
                    "outcome": item["outcome"],
                    "message": item["message"],
                    "warning": item["warning"],
                    "result": (
                        {
                            "id": item["result"].pk,
                            "attempt_no": item["result"].attempt_no,
                            **performance.serialize_result_value(test, item["result"]),
                        }
                        if item["result"] is not None
                        else None
                    ),
                }
                for item in outcome["results"]
            ],
        }
        return Response(payload, status=status.HTTP_201_CREATED if outcome["counts"]["created"] else status.HTTP_200_OK)


def _result_for(request, pk, *, manage: bool):
    """Résultat visible par le lecteur : tout pour le staff, le sien sinon
    (404, jamais 403, pour ne pas révéler l'existence d'un résultat)."""

    queryset = PerformanceResult.objects.select_related("run__event", "run__test", "run__recorded_by", "membership__user")
    try:
        result = queryset.get(pk=pk)
    except PerformanceResult.DoesNotExist:
        return None, _not_found(_RESULT_NOT_FOUND)
    if not manage and not _sees_all(request):
        own = _own_membership(request)
        if own is None or result.membership_id != own.pk:
            return None, _not_found(_RESULT_NOT_FOUND)
    return result, None


class PerformanceResultDetailView(APIView):
    """``GET|PATCH /sport/performance-results/{id}/``."""

    def get_permissions(self):
        permission = CanManagePerformanceTests if self.request.method == "PATCH" else IsActiveClubMember
        return [p() for p in _GATE + [permission]]

    def get(self, request, pk):
        result, error = _result_for(request, pk, manage=False)
        if error is not None:
            return error
        return Response(performance.get_result_detail(result=result, viewer=request.user, request=request))

    def patch(self, request, pk):
        result, error = _result_for(request, pk, manage=True)
        if error is not None:
            return error
        data = _run_input(ResultCorrectionSerializer, request)
        reason = data.pop("reason", "")
        try:
            result = performance.correct_result(result=result, actor=request.user, reason=reason, data=data)
        except services.SportError as exc:
            return _sport_error(exc)
        result = PerformanceResult.objects.select_related("run__event", "run__test", "run__recorded_by", "membership__user").get(pk=result.pk)
        return Response(performance.get_result_detail(result=result, viewer=request.user, request=request))


class PerformanceResultVoidView(APIView):
    """``POST /sport/performance-results/{id}/void/`` : retire un résultat (motif obligatoire)."""

    permission_classes = _GATE + [CanManagePerformanceTests]

    def post(self, request, pk):
        result, error = _result_for(request, pk, manage=True)
        if error is not None:
            return error
        data = _run_input(VoidSerializer, request)
        try:
            result = performance.void_result(result=result, actor=request.user, reason=data["reason"])
        except services.SportError as exc:
            return _sport_error(exc)
        result = PerformanceResult.objects.select_related("run__event", "run__test", "run__recorded_by", "membership__user").get(pk=result.pk)
        return Response(performance.get_result_detail(result=result, viewer=request.user, request=request))


def _player_performance_response(request, membership):
    raw = request.query_params.get("test")
    if raw:
        if not raw.isdigit():
            return Response({"detail": "Choisissez un test."}, status=status.HTTP_400_BAD_REQUEST)
        test, error = _get_test(int(raw))
        if error is not None:
            return error
        return Response(performance.get_player_evolution(membership=membership, test=test, request=request))
    return Response(performance.get_player_overview(membership=membership, request=request))


class PlayerPerformanceView(APIView):
    """``GET /sport/players/{membership_id}/performance/?test=`` : le staff
    (lecture) ou le joueur lui-même ; 404 pour tout autre joueur."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request, membership_id):
        try:
            membership = Membership.objects.select_related("user").get(pk=membership_id)
        except Membership.DoesNotExist:
            return _not_found(_PLAYER_NOT_FOUND)
        if not _sees_all(request):
            own = _own_membership(request)
            if own is None or own.pk != membership.pk:
                return _not_found(_PLAYER_NOT_FOUND)
        return _player_performance_response(request, membership)


class MyPerformanceView(APIView):
    """``GET /sport/performance/me/?test=`` : « Mes tests » et « Mon évolution »."""

    permission_classes = _GATE + [IsActiveClubMember]

    def get(self, request):
        membership = _own_membership(request)
        if membership is None:
            return _not_found("Aucune fiche joueur n'est associée à ce compte dans ce club.")
        return _player_performance_response(request, membership)
