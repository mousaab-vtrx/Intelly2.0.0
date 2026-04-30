import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchJson, fetchOptionalJson } from "../api/client";

export const reportKeys = {
  active: ["reports", "active"],
  dailyToday: ["reports", "daily", "today"],
  aiTools: (limit) => ["ai", "tools", "analysis", limit],
};

export function useActiveReport() {
  return useQuery({
    queryKey: reportKeys.active,
    queryFn: async () => {
      const payload = await fetchOptionalJson("/api/reports/active");
      return payload?.report ?? null;
    },
    staleTime: 30_000,
  });
}

export function useDailyTodayReport() {
  return useQuery({
    queryKey: reportKeys.dailyToday,
    queryFn: async () => {
      const payload = await fetchOptionalJson("/api/reports/daily/today");
      return payload?.report ?? null;
    },
    staleTime: 60_000,
  });
}

export function useAiToolAnalysis(limit = 120) {
  return useQuery({
    queryKey: reportKeys.aiTools(limit),
    queryFn: async () => {
      const payload = await fetchOptionalJson(`/api/ai/tools/analysis?limit=${limit}`);
      return payload?.analysis ?? null;
    },
    staleTime: 30_000,
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useGenerateReportMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ reportType, reason, regenerate = false }) => {
      const endpoint = regenerate ? "/api/reports/regenerate" : "/api/reports/generate";
      const payload = await fetchJson(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_type: reportType,
          reason,
        }),
      });
      return payload.report;
    },
    onSuccess: (report) => {
      if (report.report_type === "daily_full_report") {
        queryClient.setQueryData(reportKeys.dailyToday, report);
      } else {
        queryClient.setQueryData(reportKeys.active, report);
      }
      queryClient.invalidateQueries({ queryKey: reportKeys.active });
      queryClient.invalidateQueries({ queryKey: reportKeys.dailyToday });
    },
  });
}

export function useReportSelectionActionMutation() {
  return useMutation({
    mutationFn: async ({ reportId, action, selectedText }) => {
      const payload = await fetchJson("/api/reports/selection-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_id: reportId,
          action,
          selected_text: selectedText,
        }),
      });
      return payload;
    },
  });
}
