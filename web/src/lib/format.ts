/**
 * Utilitaires de formatage - cohérents entre serveur et client
 * Évite les erreurs d'hydratation React
 */

/**
 * Formate un nombre avec séparateur de milliers (format US)
 * Utilise un format fixe pour éviter les différences serveur/client
 * Arrondit automatiquement à l'entier le plus proche par défaut
 */
export function formatNumber(num: number, decimals: number = 0): string {
  // Vérification de sécurité pour les valeurs invalides
  if (!Number.isFinite(num)) {
    return '0';
  }

  // Arrondir d'abord pour éviter les problèmes de précision flottante
  const rounded = Math.round(num * Math.pow(10, decimals)) / Math.pow(10, decimals);

  // Séparer partie entière et décimale
  const parts = rounded.toFixed(decimals).split('.');
  const integerPart = parts[0];
  const decimalPart = parts[1];

  // Ajouter les séparateurs de milliers à la partie entière uniquement
  const formattedInteger = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',');

  // Retourner avec ou sans décimales
  if (decimalPart !== undefined && decimals > 0) {
    return `${formattedInteger}.${decimalPart}`;
  }
  return formattedInteger;
}

/**
 * Formate un montant en dollars
 */
export function formatCurrency(amount: number, decimals: number = 0): string {
  return `$${formatNumber(amount, decimals)}`;
}

/**
 * Formate une date de manière cohérente
 */
export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const day = date.getDate().toString().padStart(2, '0');
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const year = date.getFullYear();
  return `${day}/${month}/${year}`;
}

/**
 * Formate une date avec heure
 */
export function formatDateTime(dateString: string): string {
  const date = new Date(dateString);
  const day = date.getDate().toString().padStart(2, '0');
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const year = date.getFullYear();
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  return `${day}/${month}/${year} ${hours}:${minutes}`;
}

/**
 * Formate un prix
 */
export function formatPrice(price: number): string {
  return `$${price.toFixed(2)}`;
}

/**
 * Formate un pourcentage
 */
export function formatPercent(value: number, decimals: number = 0): string {
  return `${(value * 100).toFixed(decimals)}%`;
}
