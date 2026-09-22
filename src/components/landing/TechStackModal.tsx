import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ArrowRight, Database, Server, Brain, Code } from 'lucide-react';

interface TechStackModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TechStackModal({ open, onOpenChange }: TechStackModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Technical Architecture</DialogTitle>
          <DialogDescription>
            How RepoLens transforms code into knowledge graphs
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Architecture Flow */}
          <div className="flex flex-wrap items-center justify-center gap-3 p-6 rounded-lg bg-muted/30 border border-border">
            <ArchNode icon={Code} label="GitHub Repo" />
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
            <ArchNode icon={Server} label="FastAPI" />
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
            <ArchNode icon={Database} label="Neo4j" />
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
            <ArchNode icon={Brain} label="RAG + LLM" />
          </div>

          {/* Technology Details */}
          <div className="grid gap-4">
            <TechDetail
              title="FastAPI Backend"
              description="High-performance Python API that clones repositories, parses ASTs, and extracts relationships. Handles concurrent parsing with async workers."
            />
            <TechDetail
              title="Neo4j Graph Database"
              description="Native graph storage for nodes (files, classes, functions) and edges (imports, calls, inheritance). Enables efficient traversal queries."
            />
            <TechDetail
              title="RAG Architecture"
              description="Retrieval-Augmented Generation combines code context with LLM capabilities. Embeddings stored in vector DB for semantic code search."
            />
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-4 pt-4 border-t border-border">
            <Stat value="<500ms" label="Parse time per file" />
            <Stat value="10k+" label="Nodes supported" />
            <Stat value="98%" label="Accuracy on relationships" />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ArchNode({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1 p-3 rounded-lg bg-card border border-border">
      <Icon className="h-6 w-6 text-primary" />
      <span className="text-xs font-medium">{label}</span>
    </div>
  );
}

function TechDetail({ title, description }: { title: string; description: string }) {
  return (
    <div className="p-4 rounded-lg bg-card border border-border">
      <h4 className="font-semibold mb-1">{title}</h4>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="text-center">
      <p className="text-2xl font-bold font-mono">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
