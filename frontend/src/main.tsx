import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ToastProvider } from "./components/Toast";
import { ApiError } from "./lib/api";
import "@fontsource-variable/inter";
import "./index.css";

// A 401 from a data call while we believed we were signed in means the session ended: re-check who
// we are and let RequireAuth redirect to the login page.
// Never react to the "who am I" query itself (its 401 just means "not signed in"), and only act
// when that query last succeeded; otherwise this handler re-triggers itself in an endless loop.
const onAuthLost = (error: unknown) => {
  if (
    error instanceof ApiError &&
    error.code === "UNAUTHENTICATED" &&
    queryClient.getQueryState(["me"])?.status === "success"
  ) {
    queryClient.invalidateQueries({ queryKey: ["me"] });
  }
};

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError: onAuthLost }),
  mutationCache: new MutationCache({ onError: onAuthLost }),
  defaultOptions: {
    queries: {
      // Retry only "server is waking up / network" failures, with a growing delay (free-tier cold start).
      retry: (count, error) =>
        error instanceof ApiError && (error.status === 0 || error.status >= 502) && count < 4,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      refetchOnWindowFocus: true,
      staleTime: 10_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
