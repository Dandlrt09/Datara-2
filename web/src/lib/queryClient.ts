import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: 0, refetchOnWindowFocus: false },
      mutations: { retry: 0 },
    },
  });
}