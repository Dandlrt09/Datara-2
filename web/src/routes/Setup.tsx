import GuidedFlow from "./settings/GuidedFlow";
import { useProviderSetup } from "./settings/useProviderSetup";

/**
 * The standalone guided route: variant C's second screen. In the other variants
 * AppShell sends `/app/setup` back to Ajustes, so this component is only
 * mounted when the two-screen arrangement is the one being tried.
 */
export default function Setup() {
  const setup = useProviderSetup();
  if (setup.isLoading) return <p>Cargando...</p>;
  return <GuidedFlow setup={setup} layout="page" />;
}
