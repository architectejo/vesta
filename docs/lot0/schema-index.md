# Index du schéma de données — Vesta (Lot 0)

À lire en premier, avant `schema-donnees.md` ou `schema-treasury.md`. Liste chaque entité, son app Django, ses relations principales et le fichier où trouver son détail (champs, types, contraintes). Deux fichiers de détail seulement :

- **`docs/lot0/schema-donnees.md`** — socle commun et tous les modules hors trésorerie.
- **`docs/lot0/schema-treasury.md`** — **seule référence** pour le domaine trésorerie (cotisations, paiements, grand livre chaîné, dépenses, assistance sociale). Rien n'est dupliqué ailleurs.

## Comptes et club (`apps/accounts`, `apps/clubs`)

| Entité | App | Relations principales | Détail |
| --- | --- | --- | --- |
| `User` | `accounts` | 1–n `Membership` (un compte, plusieurs clubs dans le temps) | `schema-donnees.md` §3.1 |
| `TermsVersion` | `accounts` | 1–n `TermsAcceptance` — versionnement des CGU (10.2 n° 27) | §3.6 |
| `TermsAcceptance` | `accounts` | FK `User`, FK `TermsVersion` | §3.6 |
| `Membership` | `clubs` | FK `User`, FK `Club` ; 1–n `MembershipRole` ; 0–1 `MembershipApplication`, `HealthRecord` ; 1–n `Injury`, `TransferOffer` | §3.2 |
| `MembershipRole` | `clubs` | FK `Membership` (rôles cumulables) | §3.3 |
| `MembershipApplication` | `clubs` | FK `Membership` ; FK `Payment` (frais d'adhésion → `schema-treasury.md`) ; parrain = FK `Membership` | §3.4, CDC 4.3 |
| `PresidencyTransfer` | `clubs` | FK `Club`, FK `Membership` (sortant/entrant) | §3.5 |
| `Club` | `clubs` | 1–1 `ClubSettings` ; 1–n `Membership`, `Licence`, `Season`, `ImportBatch` | §4.1 |
| `ClubSettings` | `clubs` | 1–1 `Club` — porte `currency`, `timezone`, `debt_tolerance_days`, `expense_justification_days`, `payment_link_url`, `assembly_quorum_percentage` | §4.2 (décision D4) |
| `Season` | `clubs` | FK `Club` (bornes de saison, remise à zéro des compteurs disciplinaires) | §4.3 |
| `Licence` | `clubs` | FK `Club` ; pas de formule (10.2 n° 20) — date de début/fin saisies par le Superuser ; évolution future par migration additive | §4.4, §4.5 |
| `ImportBatch` | `clubs` | FK `Club` ; référencée par `Due`/`Payment` (`schema-treasury.md`) | §4.7 |

## Sport (`apps/sport`)

| Entité | App | Relations principales | Détail |
| --- | --- | --- | --- |
| `Event` | `sport` | FK `Club` ; 0–1 `Session`, 0–1 `Match` ; 1–n `Attendance`, `Incident`, `Evaluation` | §5.1 |
| `Session` | `sport` | 1–1 `Event` (+ `club` dénormalisé) ; 1–n `TeamAssignment` | §5.2 |
| `Attendance` | `sport` | FK `Event`, FK `Membership` | §5.3 |
| `TeamAssignment` | `sport` | FK `Session`, FK `Membership` — éligibilité jamais stockée, recalculée à la volée | §5.4 |
| `Match` | `sport` | 1–1 `Event` (+ `club` dénormalisé) ; 1–n `MatchComposition` ; 0–1 `MatchSheet` | §5.5 |
| `MatchComposition` | `sport` | FK `Match`, FK `Membership` ; unique `(club, match, jersey_number)` | §5.6 |
| `MatchSheet` | `sport` | 1–1 `Match` (+ `club` dénormalisé) ; 1–n `MatchGoal` ; FK `Expense` facultative (équipements, `schema-treasury.md`) | §5.7 |
| `MatchGoal` | `sport` | FK `MatchSheet`, FK `Membership` (buteur/passeur) | §5.8 |
| `Incident` | `sport` | FK `Event`, FK `Membership` ; peut créer une `Suspension` | §5.9 |
| `Suspension` | `sport` | FK `Membership`, FK `Incident` — source du statut « Suspendu » (jamais stocké sur `Membership`) | §5.9 |
| `Evaluation` | `sport` | FK `Event`, FK `Membership`, FK `User` (évaluateur) | §5.10 |
| `TacticalPlan` | `sport` | FK `Club` ; 1–n `TacticalPlanPlacement`, `TacticalPlanAnnotation` | §5.11 |
| `TacticalPlanPlacement` / `TacticalPlanAnnotation` | `sport` | FK `TacticalPlan` | §5.11 |

## Médical (`apps/medical`) — confidentialité stricte, avec consentement du joueur au Président attaché à la fonction (10.2 n° 15, cf. `analyse.md` §4 Q1, décidé le 25/09/2026)

| Entité | App | Relations principales | Détail |
| --- | --- | --- | --- |
| `HealthRecord` | `medical` | 1–1 `Membership` ; consentement Président (`president_access_granted_at`/`_revoked_at`) | §6.1 |
| `Injury` | `medical` | FK `Membership`, FK `Event` (survenue) | §6.2 |
| `InjuryFollowUp` | `medical` | FK `Injury`, FK `User` (Médecin) | §6.3 |

## Logistique (`apps/logistics`)

| Entité | App | Relations principales | Détail |
| --- | --- | --- | --- |
| `Article` | `logistics` | FK `Club` ; 1–n `StockMovement` | §7.1 |
| `StockMovement` | `logistics` | FK `Article` ; FK `Expense`/`Match` facultatives | §7.2 |
| `Inventory` / `InventoryLine` | `logistics` | FK `Club` ; 1–n `InventoryLine` → FK `Article` | §7.3 |

## Mercato (`apps/mercato`)

| Entité | App | Relations principales | Détail |
| --- | --- | --- | --- |
| `TransferOffer` | `mercato` | FK `Membership` (visé), FK `Club` origine et destinataire — deux clubs | §8.1 |
| `MercatoThread` / `MercatoMessage` | `mercato` | FK deux `Club` ; `MercatoMessage.club` = club de l'expéditeur | §8.2 |

## Assemblées générales (`apps/assemblies`)

| Entité | App | Relations principales | Détail |
| --- | --- | --- | --- |
| `Assembly` | `assemblies` | FK `Club` ; 1–n `AgendaItem`, `AssemblyAttendance`, `Decision` ; 0–1 `Minutes` | §9.1 |
| `AgendaItem` | `assemblies` | FK `Assembly` | §9.2 |
| `AssemblyAttendance` | `assemblies` | FK `Assembly`, FK `Membership` — quorum via `ClubSettings.assembly_quorum_percentage` | §9.3 |
| `Decision` | `assemblies` | FK `Assembly`, FK `AgendaItem` | §9.4 |
| `Minutes` | `assemblies` | 1–1 `Assembly` — signé PIN Président (+ VP si en poste) | §9.5 |

## Communication (`apps/social`)

| Entité | App | Relations principales | Détail |
| --- | --- | --- | --- |
| `Post` | `social` | FK `Club` ; 1–n `PostImage`, `Comment`, `Like`, `PostReport` | §10.1 |
| `PostReport` | `social` | FK `Post`, FK `User` (`reported_by`) — notifie le Superuser (10.2 n° 23) | §10.4 |
| `PostImage` / `Comment` / `Like` | `social` | FK `Post` (+ `club` dénormalisé sur `PostImage`) | §10.1 |
| `Announcement` / `AnnouncementRead` | `social` | FK `Club` ; `AnnouncementRead` FK `Announcement`, FK `User` (+ `club` dénormalisé) | §10.2 |
| `ChatChannel` / `ChatMessage` | `social` | FK `Club` ; `ChatMessage` FK `ChatChannel` | §10.3 |

## Notifications, journal, support (`apps/notifications`, `apps/audit`, `apps/accounts`)

| Entité | App | Relations principales | Détail |
| --- | --- | --- | --- |
| `Notification` | `notifications` | FK `User` ; `club` **facultatif** (alertes de plateforme) | §11.1 |
| `NotificationPreference` | `notifications` | FK `User` | §11.2 |
| `AuditLog` | `audit` | `club` facultatif ; polymorphe vers toute entité (avant/après JSON) — couvre aussi les entrées trésorerie | §12 |
| `SupportSession` | `accounts` | FK `Club`, FK `User` (Superuser) — Ghost Mode | §13.1 |
| `PasswordResetRequest` | `accounts` | FK `User` | §13.2 |

## Trésorerie (`apps/treasury`) — voir uniquement `schema-treasury.md`

| Entité | Détail (fichier unique) |
| --- | --- |
| `ContributionType`, `ContributionTypeRate`, `ContributionAssignment`, `ContributionSuspension`, `Due` | `schema-treasury.md` §4 |
| `Payment`, `PaymentAllocation`, `PaymentReversal` | `schema-treasury.md` §5 |
| `CashSession` — session de caisse (Caisse Terrain Express, PIN vérifié une fois, valable jusqu'à minuit, 10.2 n° 22) | `schema-treasury.md` §5.4 |
| `Transaction`, `LedgerChainState`, `LedgerVerificationRun` | `schema-treasury.md` §6 |
| `ExpenseCategory`, `Expense`, `ExpenseAttachment`, `ExpenseDerogation` | `schema-treasury.md` §7 |
| `SocialAssistanceScale`, `SocialAssistanceRequest` | `schema-treasury.md` §8 |

Paramètres partagés lus par `finance-engine` : `club.settings.<champ>` (`ClubSettings`, ci-dessus), jamais `club.<champ>`.
