import { createContext, useContext, type ReactNode } from 'react';

export type SessionState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | {
      status: 'authenticated';
      user: { id: string; displayName: string };
      permissions: readonly string[];
    };

const SessionContext = createContext<SessionState>({ status: 'anonymous' });

export function SessionProvider({
  value,
  children,
}: {
  value: SessionState;
  children: ReactNode;
}) {
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  return useContext(SessionContext);
}
