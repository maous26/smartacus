'use client';

/**
 * Client-side Providers
 * =====================
 *
 * Wraps the app with client-side context providers.
 */

import { ToastProvider } from './Toast';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      {children}
    </ToastProvider>
  );
}
