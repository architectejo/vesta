import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { Footer } from "./design-system";
import { AppLayout } from "./layouts/AppLayout";
import { AccueilPage } from "./routes/accueil/AccueilPage";
import { AdminLayout } from "./routes/admin/AdminLayout";
import { ClubsLicencesPage } from "./routes/admin/ClubsLicencesPage";
import { DashboardPage } from "./routes/admin/DashboardPage";
import { UnavailablePage } from "./routes/admin/UnavailablePage";
import { JournalPage } from "./routes/admin/JournalPage";
import { UsersPage } from "./routes/admin/UsersPage";
import { AssembleesPage } from "./routes/club/assemblees/AssembleesPage";
import { ArchivesPage } from "./routes/club/archives/ArchivesPage";
import { ChatPage } from "./routes/club/chat/ChatPage";
import { BoardDashboardPage } from "./routes/club/tableau-de-bord/BoardDashboardPage";
import { ComiteBureauPage } from "./routes/club/ComiteBureauPage";
import { PlayerCardsPage } from "./routes/club/cartes/PlayerCardsPage";
import { CommuniquesPage } from "./routes/club/communiques/CommuniquesPage";
import { ConnexionPage } from "./routes/connexion/ConnexionPage";
import { FilPage } from "./routes/fil/FilPage";
import { DesignSystemDemoPage } from "./routes/dev/DesignSystemDemo";
import { MaterielPage } from "./routes/logistics/MaterielPage";
import { MedicalPage } from "./routes/medical/MedicalPage";
import { MercatoPage } from "./routes/mercato/MercatoPage";
import { ProfilPage } from "./routes/profil/ProfilPage";
import { MatchPage } from "./routes/sport/MatchPage";
import { SeancePage } from "./routes/sport/SeancePage";
import { TableauNoirPage } from "./routes/sport/TableauNoirPage";
import { PlansRedirect } from "./routes/sport/PlansRedirect";
import { VestiairePage } from "./routes/sport/VestiairePage";
import { EntrainementsPage } from "./routes/sport/EntrainementsPage";
import { AssistanceSocialePage } from "./routes/treasury/AssistanceSocialePage";
import { DepensesPage } from "./routes/treasury/DepensesPage";
import { GrilleCotisationsPage } from "./routes/treasury/GrilleCotisationsPage";
import { TresoreriePage } from "./routes/treasury/TresoreriePage";

function NotFoundPlaceholder() {
  return (
    <div className="mx-auto max-w-xl p-6 text-center">
      <p className="text-sm text-text-muted">Cet élément n'existe plus.</p>
      <Footer />
    </div>
  );
}

/**
 * Racine des routes (tâche 1.9). `/dev/design-system` est une route de
 * développement interne (CLAUDE.md, tâche 1.0), protégée par
 * `ProtectedRoute requireSuperuser` (06/10/2026) pour ne jamais être
 * accessible publiquement en production.
 */
export function App() {
  return (
    <Routes>
      <Route path="/connexion" element={<ConnexionPage />} />
      <Route path="/c/:slug" element={<ConnexionPage />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout>
              <AccueilPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/tableau-de-bord"
        element={
          <ProtectedRoute>
            <AppLayout>
              <BoardDashboardPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/profil"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ProfilPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/club/joueurs"
        element={
          <ProtectedRoute>
            <AppLayout>
              <PlayerCardsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/club/comite"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ComiteBureauPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/club/assemblees"
        element={
          <ProtectedRoute>
            <AppLayout>
              <AssembleesPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/fil"
        element={
          <ProtectedRoute>
            <AppLayout>
              <FilPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/club/communiques"
        element={
          <ProtectedRoute>
            <AppLayout>
              <CommuniquesPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/club/archives"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ArchivesPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/club/chat"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ChatPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/materiel"
        element={
          <ProtectedRoute>
            <AppLayout>
              <MaterielPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/mercato"
        element={
          <ProtectedRoute>
            <AppLayout>
              <MercatoPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/medical"
        element={
          <ProtectedRoute>
            <AppLayout>
              <MedicalPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/tresorerie"
        element={
          <ProtectedRoute>
            <AppLayout>
              <TresoreriePage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/tresorerie/grille"
        element={
          <ProtectedRoute>
            <AppLayout>
              <GrilleCotisationsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/tresorerie/depenses"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DepensesPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/tresorerie/assistance"
        element={
          <ProtectedRoute>
            <AppLayout>
              <AssistanceSocialePage />
            </AppLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/vestiaire"
        element={
          <ProtectedRoute>
            <AppLayout>
              <VestiairePage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/entrainements"
        element={
          <ProtectedRoute>
            <AppLayout>
              <EntrainementsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/seances/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <SeancePage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/matchs/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <MatchPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route path="/plans" element={<PlansRedirect />} />
      <Route
        path="/plans/:id/tableau"
        element={
          <ProtectedRoute>
            <AppLayout>
              <TableauNoirPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin"
        element={
          <ProtectedRoute requireSuperuser>
            <AdminLayout>
              <DashboardPage />
            </AdminLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/clubs"
        element={
          <ProtectedRoute requireSuperuser>
            <AdminLayout>
              <ClubsLicencesPage />
            </AdminLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/utilisateurs"
        element={
          <ProtectedRoute requireSuperuser>
            <AdminLayout>
              <UsersPage />
            </AdminLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/journal"
        element={
          <ProtectedRoute requireSuperuser>
            <AdminLayout>
              <JournalPage />
            </AdminLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/parametres"
        element={
          <ProtectedRoute requireSuperuser>
            <AdminLayout>
              <UnavailablePage title="Paramètres" />
            </AdminLayout>
          </ProtectedRoute>
        }
      />

      <Route
        path="/dev/design-system"
        element={
          <ProtectedRoute requireSuperuser>
            <DesignSystemDemoPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<NotFoundPlaceholder />} />
    </Routes>
  );
}

export default App;
