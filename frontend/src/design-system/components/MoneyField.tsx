import { TextField, type TextFieldProps } from "./TextField";

export interface MoneyFieldProps extends Omit<TextFieldProps, "type" | "rightSlot" | "inputMode"> {
  /** Devise du club, venant de l'API (jamais écrite en dur, CLAUDE.md §2.18). */
  currency: string;
}

/**
 * Champ de montant (docs/lot0/design-system.md §3.1 « MoneyField ») :
 * devise du club affichée en suffixe, clavier numérique, séparateur
 * décimal virgule ou point accepté ; la saisie est conservée telle quelle
 * (l'appelant l'envoie via `toApiAmount`).
 */
export function MoneyField({ currency, onChange, ...rest }: MoneyFieldProps) {
  return (
    <TextField
      {...rest}
      type="text"
      inputMode="decimal"
      onChange={onChange}
      rightSlot={<span className="text-sm text-text-muted">{currency}</span>}
    />
  );
}
