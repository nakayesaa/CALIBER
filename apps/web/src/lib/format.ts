export function formatDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...options,
  }).format(new Date(value));
}

export function formatDateTime(value: string): string {
  return formatDate(value, { hour: '2-digit', minute: '2-digit' });
}

export function formatSignal(value: number, digits = 1): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function humanize(value: string): string {
  return value.toLowerCase().replaceAll('_', ' ').replace(/^./, (character) => character.toUpperCase());
}
