/**
 * Point d'entrée unique des icônes (docs/lot0/design-system-icones-animations.md
 * §1.1, §3.4). Toute icône de l'application passe par ce fichier : jamais
 * d'import direct de `lucide-react` ailleurs, jamais de SVG fait main pour
 * une icône (seules exceptions : `PitchMarkings`/`AnnotationsLayer` du
 * `PitchBoard` et `PlayerSilhouette` de `PlayerTradingCard`, qui sont des
 * graphismes, pas des icônes).
 *
 * Noms métier -> icône Lucide retenue (table §3.4). Imports nommés
 * uniquement : pas de `import * as icons`, pas de chargement par nom calculé.
 */
import {
  Archive,
  ArchiveX,
  ArrowDown,
  ArrowLeft,
  ArrowLeftRight,
  ArrowUp,
  Bell,
  Camera,
  CalendarDays,
  Check,
  CircleAlert,
  CircleCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Download,
  Ellipsis,
  Eraser,
  ExternalLink,
  Eye,
  EyeOff,
  FileImage,
  FileText,
  Gavel,
  Globe,
  Grid3x3,
  HandHeart,
  House,
  LayoutDashboard,
  Image,
  Inbox,
  Info,
  Landmark,
  Lock,
  LoaderCircle,
  LogOut,
  Megaphone,
  Menu,
  Minus,
  MessagesSquare,
  MousePointer2,
  MoveUpRight,
  Newspaper,
  Package,
  Paperclip,
  Palette,
  Pencil,
  Pin,
  Plus,
  Receipt,
  Redo2,
  Search,
  Shield,
  Shirt,
  SlidersHorizontal,
  Square,
  Stethoscope,
  Trash2,
  TriangleAlert,
  Trophy,
  Type,
  Undo2,
  Upload,
  UserRound,
  Users,
  Wallet,
  WifiOff,
  X,
} from "lucide-react";

// Navigation, fermeture, actions génériques (§3.4).
export const IconBack = ArrowLeft;
export const IconClose = X;
export const IconRemove = X;
export const IconMenu = Menu;
export const IconMore = Ellipsis;
export const IconUndo = Undo2;
export const IconRedo = Redo2;
export const IconEdit = Pencil;
export const IconDelete = Trash2;
export const IconAdd = Plus;
export const IconDecrease = Minus;
export const IconSearch = Search;
export const IconFilter = SlidersHorizontal;
export const IconChevronLeft = ChevronLeft;
export const IconChevronRight = ChevronRight;
export const IconChevronDown = ChevronDown;
export const IconSortAsc = ArrowUp;
export const IconSortDesc = ArrowDown;
export const IconMoveUp = ArrowUp;
export const IconMoveDown = ArrowDown;
export const IconCheck = Check;
export const IconLock = Lock;
export const IconPin = Pin;
export const IconNotifications = Bell;
export const IconDownload = Download;
export const IconUpload = Upload;
export const IconCamera = Camera;
export const IconAttachment = Paperclip;
export const IconImage = Image;
// Archive des documents (docs/ecrans/club-archives.md §9).
export const IconDocumentPdf = FileText;
export const IconDocumentImage = FileImage;
export const IconWithdraw = ArchiveX;
export const IconOpenExternal = ExternalLink;
export const IconError = CircleAlert;
export const IconWarning = TriangleAlert;
export const IconInfo = Info;
export const IconSuccess = CircleCheck;
export const IconEmpty = Inbox;
export const IconLoading = LoaderCircle;
export const IconOffline = WifiOff;
export const IconPublic = Globe;
export const IconPrivate = Users;
export const IconShow = Eye;
export const IconHide = EyeOff;
export const IconLogout = LogOut;
export const IconTheme = Palette;

// Barre d'outils du tableau noir (§3.4).
export const IconToolSelect = MousePointer2;
export const IconToolArrow = MoveUpRight;
export const IconToolZone = Square;
export const IconToolText = Type;
export const IconToolEraser = Eraser;

// Navigation de la barre latérale (§3.4, « Navigation »).
export const IconNavHome = House;
export const IconNavBoardDashboard = LayoutDashboard;
export const IconNavLocker = Shirt;
export const IconNavFeed = Newspaper;
export const IconNavProfile = UserRound;
export const IconNavBoard = Users;
export const IconNavAssembly = Landmark;
export const IconNavAnnouncements = Megaphone;
export const IconNavArchives = Archive;
export const IconNavChat = MessagesSquare;
export const IconNavCoach = ClipboardList;
export const IconNavSessions = CalendarDays;
export const IconNavMatches = Trophy;
export const IconNavDiscipline = Gavel;
export const IconNavTreasuryDashboard = Wallet;
export const IconNavContributionsGrid = Grid3x3;
export const IconNavExpenses = Receipt;
export const IconNavSocialAssistance = HandHeart;
export const IconNavMedical = Stethoscope;
export const IconNavMaterial = Package;
export const IconNavMercato = ArrowLeftRight;
export const IconNavSuperuser = Shield;
