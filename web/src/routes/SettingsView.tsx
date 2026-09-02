import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useSettings, useUpdateSettings } from "../queries/useSettings";
import { QueryError } from "../components/ErrorCard";

interface SettingsForm {
  api_key?: string;
  default_model?: string;
}

export default function SettingsView() {
  const { data: settings, isLoading, error, refetch } = useSettings();
  const updateSettings = useUpdateSettings();
  const { register, handleSubmit, reset } = useForm<SettingsForm>();

  // Sync form defaults once settings load. reset() MUST run inside an
  // effect: calling it during render updates form state while rendering,
  // which re-renders the form forever (blank screen).
  useEffect(() => {
    if (settings) {
      reset({
        api_key: "",
        default_model: settings.default_model ?? "",
      });
    }
  }, [settings, reset]);

  const onSubmit = (data: SettingsForm) => {
    updateSettings.mutate({
      api_key: data.api_key?.trim() || undefined,
      default_model: data.default_model?.trim() || undefined,
    });
  };

  if (isLoading) return <p>Loading settings...</p>;

  return (
    <div style={{ maxWidth: 500 }}>
      <h1>Settings</h1>
      <QueryError error={error as Error | null} onRetry={refetch}>
        <form onSubmit={handleSubmit(onSubmit)}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", marginBottom: 4 }}>
              OpenAI API Key{" "}
              {settings?.has_api_key && (
                <span style={{ color: "green", fontSize: "0.85em" }}>
                  (saved — leave blank to keep)
                </span>
              )}
            </label>
            <input
              {...register("api_key")}
              type="password"
              placeholder="sk-..."
              style={{ width: "100%", padding: 8 }}
            />
            <p style={{ fontSize: "0.85em", color: "#666", margin: "4px 0" }}>
              Stored server-side and never sent back to the browser. Falls back
              to the OPENAI_API_KEY env var when empty.
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", marginBottom: 4 }}>Default Model</label>
            <input
              {...register("default_model")}
              placeholder="gpt-4o-2024-08-06"
              style={{ width: "100%", padding: 8 }}
            />
          </div>
          {updateSettings.isSuccess && (
            <p style={{ color: "green" }}>Settings saved</p>
          )}
          {updateSettings.isError && (
            <p style={{ color: "red" }}>Failed to save settings</p>
          )}
          <button type="submit" disabled={updateSettings.isPending} style={{ padding: "8px 16px" }}>
            {updateSettings.isPending ? "Saving..." : "Save"}
          </button>
        </form>
      </QueryError>
    </div>
  );
}