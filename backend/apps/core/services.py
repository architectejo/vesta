"""Regles metier partagees de l'app core.

Deux responsabilites :

1. :func:`resolve_active_membership` -- deduit le club actif de
   l'adhesion en cours de l'utilisateur authentifie (CLAUDE.md regle n9,
   CDC 6.3). Depuis la tache 1.3, branchee sur la requete HTTP reelle par
   ``apps.core.authentication.TenantJWTAuthentication`` (appelee a
   chaque requete authentifiee, avant l'execution de la vue).
2. :func:`log_action` -- interface stable du service d'audit (CLAUDE.md
   regle n6 ; CDC 5). Depuis la tache 1.6, ecrit reellement une entree
   dans ``apps.audit.models.AuditLog`` en deleguant a
   ``apps.audit.services.create_audit_log`` -- cette fonction reste le
   point d'entree unique utilise par les autres apps, pour n'avoir
   **aucun appel a modifier** au moment du branchement reel (c'etait deja
   la signature stable documentee par le stub de la tache 1.2).
"""

from __future__ import annotations

from typing import Any, Optional

from django.apps import apps

from apps.core.tenant import NoActiveClubError, get_active_club

__all__ = ["resolve_active_membership", "get_active_club_for_user", "log_action"]

# Sentinel distinct de ``None`` : ``None`` est une valeur legitime pour
# ``club`` (action de portee plateforme, schema-donnees.md §1.2, §12.1),
# alors que "parametre omis" doit deduire le club actif du contexte
# courant (CLAUDE.md regle n9). Un simple defaut ``club=None`` ne
# permettrait pas de distinguer les deux cas.
_CLUB_NOT_PROVIDED = object()

# Meme logique pour ``ip_address``/``user_agent`` : une chaine vide est une
# valeur legitime (aucun contexte HTTP, ex. commande de gestion), alors que
# "parametre omis" doit se remplir depuis le contexte de la requete HTTP
# courante (``apps.core.request_context``, tache 1.3 -- point ouvert laisse
# par la tache 1.6). Un simple defaut ``""`` ne permettrait pas de
# distinguer un appel qui fournit deliberement une chaine vide d'un appel
# qui n'y a simplement pas pense.
_IP_ADDRESS_NOT_PROVIDED = object()
_USER_AGENT_NOT_PROVIDED = object()

# Meme principe pour le Ghost Mode (tache 1.8, CDC 5.4) : `False`/`""`
# restent des valeurs legitimes explicites (un appelant qui sait qu'il
# n'agit pas en Ghost Mode), alors que "parametre omis" doit se remplir
# depuis le contexte de session de support courant
# (`apps.core.ghost_context`, positionne par
# `apps.core.authentication.TenantJWTAuthentication` pour la duree d'une
# requete Superuser presentant une session de support valide).
_ACTED_AS_GHOST_NOT_PROVIDED = object()
_SUPPORT_SESSION_ID_NOT_PROVIDED = object()


def resolve_active_membership(user, club=None):
    """Determine l'adhesion (``Membership``) en cours d'un utilisateur.

    CLAUDE.md regle n9 : « Le club actif se deduit de l'adhesion en
    cours, jamais d'un ``tenant_id`` fige dans le JWT. » Cette fonction
    est le point d'entree unique de cette regle : elle ne fait jamais
    confiance a une valeur transmise telle quelle par le client, elle la
    verifie systematiquement contre les adhesions reelles de
    l'utilisateur en base.

    Parametres :
    - ``user`` : l'utilisateur authentifie (``accounts.User``).
    - ``club`` : optionnel. Si fourni (par exemple resolu depuis le slug
      ``/c/<slug>`` de l'URL, CDC 7.3), restreint la recherche a ce club
      et **verifie** qu'une adhesion active y existe reellement -- le
      ``club`` n'est jamais accepte sans cette verification. Si omis,
      la fonction tente de deduire le club actif a partir des seules
      adhesions actives de l'utilisateur.

    Cas particulier documente (voir docs/lot0/schema-donnees.md, note
    Q4 de l'analyse) : un utilisateur peut, rarement, avoir une adhesion
    active simultanee dans plusieurs clubs. Dans ce cas, sans ``club``
    explicite, le club actif est ambigu : cette fonction leve
    delibierement :class:`NoActiveClubError` plutot que d'en choisir un
    arbitrairement -- **point ouvert transmis a la tache 1.3**, qui devra
    decider du mecanisme de selection explicite (ex. slug d'URL, dernier
    club utilise stocke cote client et revalide ici a chaque requete).

    Leve :class:`NoActiveClubError` si l'utilisateur n'est pas
    authentifie, si c'est un Superuser (qui n'a jamais de fiche joueur,
    CLAUDE.md regle n1), ou si aucune adhesion active ne correspond.
    """

    if user is None or not getattr(user, "is_authenticated", False):
        raise NoActiveClubError(
            "Utilisateur non authentifié : aucun club actif ne peut être déterminé."
        )

    if getattr(user, "is_superuser", False):
        raise NoActiveClubError(
            "Un Superuser n'a pas de fiche joueur et n'appartient à aucun club : "
            "aucun club actif ne peut être déterminé."
        )

    # Import tardif pour eviter tout import circulaire au chargement des
    # apps (apps.clubs importe apps.core.models.TenantModel).
    Membership = apps.get_model("clubs", "Membership")

    # `all_objects` (non filtre par club actif) est l'usage legitime ici :
    # c'est precisement ce qui determine le club actif, avant qu'un
    # contexte tenant-aware n'existe (voir apps.core.models.TenantModel).
    queryset = Membership.all_objects.filter(
        user=user, status=Membership.Status.ACTIVE
    )

    if club is not None:
        membership = queryset.filter(club=club).first()
        if membership is None:
            raise NoActiveClubError(
                "Aucune adhésion active de cet utilisateur pour le club demandé : "
                "accès refusé."
            )
        return membership

    memberships = list(queryset[:2])
    if not memberships:
        raise NoActiveClubError(
            "Aucune adhesion active pour cet utilisateur : aucun club actif."
        )
    if len(memberships) > 1:
        raise NoActiveClubError(
            "Plusieurs adhesions actives simultanees pour cet utilisateur : le "
            "club actif est ambigu sans le preciser explicitement (voir docstring "
            "de resolve_active_membership -- point ouvert pour la tache 1.3)."
        )
    return memberships[0]


def get_active_club_for_user(user, club=None):
    """Raccourci : renvoie directement le ``Club`` actif d'un utilisateur.

    Equivalent a ``resolve_active_membership(user, club).club``.
    """

    return resolve_active_membership(user, club=club).club


def log_action(
    *,
    actor,
    club=_CLUB_NOT_PROVIDED,
    action_type: str,
    obj,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    ip_address: str = _IP_ADDRESS_NOT_PROVIDED,
    user_agent: str = _USER_AGENT_NOT_PROVIDED,
    device: str = "",
    acted_as_ghost: bool = _ACTED_AS_GHOST_NOT_PROVIDED,
    support_session_id: str = _SUPPORT_SESSION_ID_NOT_PROVIDED,
):
    """Ecrit une entree dans le journal d'activite (CLAUDE.md regle n6 ; CDC 5).

    Point d'entree stable utilise par toutes les apps (signature posee
    des la tache 1.2). Delegue a
    ``apps.audit.services.create_audit_log``, qui applique les
    garde-fous non negociables : acteur reel obligatoire (y compris en
    Ghost Mode, CDC 5.4), append-only (CDC 5.3), aucun contenu medical
    copie pour une action ``medical.*`` (CLAUDE.md regle n11, CDC 5.2).

    Parametres :
    - ``actor`` : l'utilisateur (``User``) a l'origine de l'action --
      l'identite reelle, meme en Ghost Mode (jamais "Systeme Vesta", qui
      n'est qu'un affichage cote club, pas une valeur stockee).
    - ``club`` : le club concerne. Si **omis**, deduit du club actif du
      contexte courant (``apps.core.tenant.get_active_club``, CLAUDE.md
      regle n9). Passer explicitement ``club=None`` pour une action de
      portee plateforme (licence, compte, CGU...) sans deduction.
    - ``action_type`` : identifiant hierarchique et stable de l'action
      (ex. ``"role.appointed"``, CDC 5.2).
    - ``obj`` : l'objet cree/modifie/supprime ; ``object_type``/
      ``object_id`` en sont deduits (``obj.__class__.__name__``, ``obj.pk``).
    - ``before`` / ``after`` : etat avant/apres, JSON-serialisable.
      **Jamais de contenu medical** (rejete par le service pour toute
      action ``medical.*``), ni de mot de passe (hache ou non).
    - ``ip_address`` / ``user_agent`` : contexte de la requete (CDC 5.1).
      Si **omis**, deduits du contexte de la requete HTTP courante
      (``apps.core.request_context.get_request_meta``, positionne par
      ``apps.core.middleware.RequestContextMiddleware`` -- resout le
      point ouvert laisse par la tache 1.6). Restent vides hors de toute
      requete HTTP (signaux sur les modeles de la tache 1.2, commandes de
      gestion). Passer explicitement une chaine (y compris vide) pour ne
      jamais deduire du contexte courant.
    - ``device`` : reste vide tant qu'aucune app ne le renseigne (aucune
      deduction automatique, contrairement a ``ip_address``/``user_agent``).
    - ``acted_as_ghost`` / ``support_session_id`` : Ghost Mode (tache 1.8 ;
      CDC 5.4). Si **omis**, deduits du contexte de session de support
      courant (``apps.core.ghost_context.get_ghost_context``, positionne
      par ``apps.core.authentication.TenantJWTAuthentication`` pour la
      duree d'une requete Superuser presentant une session de support
      valide) : ``acted_as_ghost=True``/``support_session_id=<id>`` si un
      tel contexte existe, ``False``/``""`` sinon. Passer explicitement
      ces deux parametres pour ne jamais deduire du contexte courant (ex.
      un appelant qui sait deja, sans contexte de requete HTTP, qu'une
      action donnee est ou n'est pas faite en Ghost Mode).

    Renvoie l'entree ``AuditLog`` creee.
    """

    from apps.audit.services import create_audit_log
    from apps.core.ghost_context import get_ghost_context
    from apps.core.request_context import get_request_meta

    resolved_club = get_active_club() if club is _CLUB_NOT_PROVIDED else club

    if ip_address is _IP_ADDRESS_NOT_PROVIDED or user_agent is _USER_AGENT_NOT_PROVIDED:
        request_meta = get_request_meta()
        resolved_ip_address = (
            request_meta.ip_address if ip_address is _IP_ADDRESS_NOT_PROVIDED else ip_address
        )
        resolved_user_agent = (
            request_meta.user_agent if user_agent is _USER_AGENT_NOT_PROVIDED else user_agent
        )
    else:
        resolved_ip_address = ip_address
        resolved_user_agent = user_agent

    if acted_as_ghost is _ACTED_AS_GHOST_NOT_PROVIDED or support_session_id is _SUPPORT_SESSION_ID_NOT_PROVIDED:
        ghost_context = get_ghost_context()
        resolved_acted_as_ghost = (
            ghost_context is not None if acted_as_ghost is _ACTED_AS_GHOST_NOT_PROVIDED else acted_as_ghost
        )
        resolved_support_session_id = (
            (ghost_context.support_session_id if ghost_context is not None else "")
            if support_session_id is _SUPPORT_SESSION_ID_NOT_PROVIDED
            else support_session_id
        )
    else:
        resolved_acted_as_ghost = acted_as_ghost
        resolved_support_session_id = support_session_id

    if obj is None:
        raise ValueError(
            "log_action() exige un objet concerne (`obj`) : impossible de "
            "resoudre `object_type`/`object_id` sans lui (CDC 5.1)."
        )

    return create_audit_log(
        actor=actor,
        club=resolved_club,
        action_type=action_type,
        object_type=obj.__class__.__name__,
        object_id=obj.pk,
        before=before,
        after=after,
        ip_address=resolved_ip_address,
        user_agent=resolved_user_agent,
        device=device,
        acted_as_ghost=resolved_acted_as_ghost,
        support_session_id=resolved_support_session_id,
    )
