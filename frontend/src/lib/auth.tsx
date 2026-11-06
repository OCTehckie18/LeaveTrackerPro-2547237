import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";
import { api } from "./api";
import type { Me } from "./types";

export function useMeQuery() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<Me>("/auth/me"),
    retry: false,
    staleTime: 20_000,
    refetchInterval: 60_000, // keeps the "needs your action" badges fresh (in-app notifications)
  });
}

const MeContext = createContext<Me | null>(null);
export const MeProvider = MeContext.Provider;

/** The signed-in user. Only call inside routes wrapped by <RequireAuth>. */
export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe used outside <RequireAuth>");
  return me;
}
