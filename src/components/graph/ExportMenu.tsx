import { Download, FileImage, FileType } from 'lucide-react';
import { Node, Edge } from '@xyflow/react';
import { toast } from 'sonner';
import { Button } from '../ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import { exportGraphAsPNG, exportGraphAsSVG, ExportOptions } from '../../lib/export';
import { trackEvent, Events } from '@/lib/analytics';

interface ExportMenuProps {
  containerRef: React.RefObject<HTMLElement>;
  nodes: Node[];
  edges: Edge[];
}

export function ExportMenu({ containerRef, nodes, edges }: ExportMenuProps) {
  const handleExportPNG = async (resolution: 1 | 2 | 4 = 2) => {
    if (!containerRef.current) {
      toast.error('Graph container not found');
      return;
    }

    if (!nodes.length) {
      toast.error('No graph to export');
      return;
    }

    const options: ExportOptions = {
      resolution,
      background: 'transparent',
    };

    await exportGraphAsPNG(nodes, edges, containerRef.current, options);

    trackEvent(Events.GRAPH_EXPORTED, {
      format: 'png',
      resolution,
      background: 'transparent',
      node_count: nodes.length,
    });
  };

  const handleExportSVG = async () => {
    if (!containerRef.current) {
      toast.error('Graph container not found');
      return;
    }

    if (!nodes.length) {
      toast.error('No graph to export');
      return;
    }

    const options: ExportOptions = {
      resolution: 1, // SVG is vector, resolution doesn't matter
      background: 'transparent',
    };

    await exportGraphAsSVG(nodes, edges, containerRef.current, options);

    trackEvent(Events.GRAPH_EXPORTED, {
      format: 'svg',
      background: 'transparent',
      node_count: nodes.length,
    });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          title="Export graph as image"
        >
          <Download className="h-4 w-4" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Export Format</DropdownMenuLabel>
        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={() => handleExportPNG(2)}>
          <FileImage className="h-4 w-4 mr-2" />
          <div className="flex flex-col flex-1">
            <span>PNG (High Quality)</span>
            <span className="text-xs text-muted-foreground">2x resolution</span>
          </div>
        </DropdownMenuItem>

        <DropdownMenuItem onClick={() => handleExportPNG(4)}>
          <FileImage className="h-4 w-4 mr-2" />
          <div className="flex flex-col flex-1">
            <span>PNG (Print Quality)</span>
            <span className="text-xs text-muted-foreground">4x resolution</span>
          </div>
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={handleExportSVG}>
          <FileType className="h-4 w-4 mr-2" />
          <div className="flex flex-col flex-1">
            <span>SVG (Vector)</span>
            <span className="text-xs text-muted-foreground">Scalable format</span>
          </div>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
