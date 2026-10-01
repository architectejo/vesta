import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BACKEND_DIR = path.resolve(__dirname, "../../../backend");
const PYTHON_BIN = path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe");

/**
 * Exécute une commande `manage.py shell -c "<script>"` en lecture seule
 * (ou en écriture explicitement journalisée par le service appelé), pour
 * les vérifications que le produit ne propose pas encore de consulter
 * autrement (CDC 9.3, étape 10 : « contrôle du journal » — voir le compte
 * rendu de la tâche 5.2, aucune vue de consultation du journal n'existe
 * encore côté API ni interface). N'écrit jamais directement dans les
 * modèles : appelle toujours les services réels.
 */
export function runShell(script: string): string {
  const result = spawnSync(PYTHON_BIN, ["manage.py", "shell", "-c", script], {
    cwd: BACKEND_DIR,
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    throw new Error(`manage.py shell a échoué (code ${result.status}) :\n${result.stdout}\n${result.stderr}`);
  }
  return result.stdout;
}
