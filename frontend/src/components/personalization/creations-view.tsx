import {
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  Lightbulb,
  Sparkles,
  Target,
} from "lucide-react";
import { useCallback, useState } from "react";
import type {
  SkillCreation,
  SkillSourceInfo,
  WorkflowPattern,
} from "../../types";
import { BulletText } from "../bullet-text";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { Tooltip } from "../tooltip";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import { ConfidenceBar, SectionHeader } from "./skill-shared";
import { StepRefList } from "./skill-patterns-view";
import { SkillPreviewDialog } from "./skill-preview-dialog";

export function CreationSection({
  skills,
  workflowPatterns,
  fetchWithToken,
  agentSources,
}: {
  skills: SkillCreation[];
  workflowPatterns: WorkflowPattern[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  return (
    <section>
      <SectionHeader
        icon={<Sparkles className="w-5 h-5" />}
        title="Custom Skills"
        tooltip="Generated skills from your patterns"
        accentColor="text-accent-emerald"
      />
      <div className="space-y-3">
        {skills.map((skill) => (
          <CreatedSkillCard
            key={skill.element_name}
            skill={skill}
            workflowPatterns={workflowPatterns}
            fetchWithToken={fetchWithToken}
            agentSources={agentSources}
          />
        ))}
      </div>
    </section>
  );
}

function CreatedSkillCard({
  skill,
  workflowPatterns,
  fetchWithToken,
  agentSources,
}: {
  skill: SkillCreation;
  workflowPatterns: WorkflowPattern[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [showPreview, setShowPreview] = useState(false);
  const [installed, setInstalled] = useState(false);
  const [editedContent, setEditedContent] = useState(skill.skill_md_content);
  const [rationaleExpanded, setRationaleExpanded] = useState(false);
  const [patternsExpanded, setPatternsExpanded] = useState(false);

  const matchedPatterns = workflowPatterns.filter((p) =>
    skill.addressed_patterns?.includes(p.title),
  );

  const handleInstall = useCallback(
    async (content: string, targets: string[]) => {
      try {
        const res = await fetchWithToken("/api/skills/install", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: skill.element_name, content }),
        });
        if (!res.ok) return;

        if (targets.length > 0) {
          await fetchWithToken(`/api/skills/sync/${skill.element_name}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ targets }),
          });
        }
        setInstalled(true);
      } catch {
        /* ignore */
      }
      setShowPreview(false);
    },
    [fetchWithToken, skill.element_name],
  );

  return (
    <div className="border border-default rounded-xl bg-control/20 overflow-hidden">
      {/* Header: Name + Confidence + Action */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-base font-bold text-primary">{skill.element_name}</span>
            {skill.confidence > 0 && <ConfidenceBar confidence={skill.confidence} />}
          </div>
          <div className="flex items-center gap-2">
            {installed ? (
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-accent-emerald bg-accent-emerald-subtle rounded-lg border border-accent-emerald">
                <Check className="w-3.5 h-3.5" /> Installed
              </span>
            ) : (
              <Tooltip text="Preview and install skill">
                <button
                  onClick={() => guardAction(() => setShowPreview(true))}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg transition"
                >
                  <Eye className="w-3.5 h-3.5" />
                  Preview &amp; Install
                </button>
              </Tooltip>
            )}
          </div>
        </div>
        <p className="text-sm text-secondary leading-relaxed mt-1.5">
          <span className="font-semibold text-secondary">Skill Description: </span>
          {skill.description}
        </p>
      </div>

      {/* Why this helps */}
      <div className="px-5 py-3 border-t border-default/20">
        <button
          onClick={() => setRationaleExpanded(!rationaleExpanded)}
          className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
        >
          {rationaleExpanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-emerald" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-emerald" />}
          <Lightbulb className="w-3.5 h-3.5 text-accent-emerald" />
          <span className="text-sm font-semibold text-accent-emerald uppercase tracking-wide">Why this helps</span>
        </button>
        {rationaleExpanded && (
          <BulletText text={skill.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
        )}
      </div>

      {/* Toggleable What this covers */}
      {matchedPatterns.length > 0 && (
        <div className="px-5 py-3 border-t border-default/20">
          <button
            onClick={() => setPatternsExpanded(!patternsExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {patternsExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-emerald" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-emerald" />}
            <Target className="w-3.5 h-3.5 text-accent-emerald" />
            <span className="text-sm font-semibold text-accent-emerald uppercase tracking-wide">What this covers</span>
            <span className="text-dimmed">({matchedPatterns.length})</span>
          </button>
          {patternsExpanded && (
            <div className="mt-2.5 space-y-3">
              {matchedPatterns.map((p, i) => (
                <div key={i} className="border-l-2 border-accent-emerald-border pl-3 space-y-1.5">
                  <h6 className="text-sm font-semibold text-primary">{p.title}</h6>
                  <BulletText text={p.description} className="text-sm text-secondary leading-relaxed" />
                  <StepRefList refs={p.example_refs} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {showPreview && (
        <SkillPreviewDialog
          skillName={skill.element_name}
          content={editedContent}
          onContentChange={setEditedContent}
          onInstall={handleInstall}
          onCancel={() => setShowPreview(false)}
          agentSources={agentSources}
        />
      )}
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}
