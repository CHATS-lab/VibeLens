// Cross-subsystem agent metadata. Every frontend consumer that needs an
// agent's label, color, icon, or normalized slug imports from here.
export {
  getAgentMeta,
  SOURCE_COLORS,
  SOURCE_LABELS,
  SOURCE_DESCRIPTIONS,
} from "./meta";
export { normalizeSourceType } from "./normalize";
export { AgentIcon } from "./agent-icon";
