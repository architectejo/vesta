import { EmptyState } from "../../design-system";

/**
 * Page de repli pour une section sans point d'accès API. Le journal
 * d'activité Superuser dispose désormais de son écran (`JournalPage`) ; cette
 * page ne sert plus qu'aux sections sans endpoint (ex. « Paramètres » de la
 * plateforme, superuser-espace.md §3.5). Plutôt que de construire un écran
 * contre une API inventée, elle l'indique explicitement.
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
