import { useForm } from "react-hook-form";
import { useSettings, useUpdateSettings } from "../queries/useSettings";

interface SettingsForm {
  api_key?: string;
  default_model?: string;
}

export default function SettingsView() {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();
  const { register, handleSubmit, reset } = useForm<SettingsForm>();

  // Set form values when settings load
  if (settings && !isLoading) {
    reset({
      api_key: settings.api_key_enc ?? "",
      default_model: settings.default_model ?? "",
    });
  }

  const onSubmit = (data: SettingsForm) => {
    updateSettings.mutate({
      api_key: data.api_key || undefined,
      default_model: data.default_model || undefined,
    });
  };

  if (isLoading) return <p>Loading settings...</p>;

  return (
    <div style={{ maxWidth: 500 }}>
      <h1>Settings</h1>
      <form onSubmit={handleSubmit(onSubmit)}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "block", marginBottom: 4 }}>API Key (optional)</label>
          <input
            {...register("api_key")}
            type="password"
            placeholder="sk-..."
            style={{ width: "100%", padding: 8 }}
          />
          <p style={{ fontSize: "0.85em", color: "#666", margin: "4px 0" }}>
            Your key is stored encrypted. Falls back to OPENAI_API_KEY env var.
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
    </div>
  );
}