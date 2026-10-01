import { EmptyState } from "../../design-system";

/**
 * Pages « Journal d'activité » et « Paramètres » (superuser-espace.md
 * §3.4, §3.5) : aucun endpoint de lecture n'existe côté API
 * (`backend/apps/audit/urls.py` est vide malgré un modèle `AuditLog`
 * fonctionnel ; aucun endpoint de paramètres plateforme n'existe non
 * plus). Plutôt que de construire ces écrans contre une API inventée,
 * cette page l'indique explicitement — trou backend signalé au compte
 * rendu, à combler par `backend-dev`.
 */
export function UnavailablePage({ title }: { title: string }) {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-text">{title}</h1>
      </header>
      <EmptyState
        variant="error"
        message="Cette section n'est pas encore disponible."
        description="Aucun point d'accès de l'API ne la sert encore (voir compte rendu de la tâche)."
      />
    </div>
  );
}
