/** « 0 canal », « 1 canal », « 2 canaux ». */
export function formatChannelCount(count: number): string {
  return `${count} ${count > 1 ? "canaux" : "canal"}`;
}
