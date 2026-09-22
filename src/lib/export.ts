import { Node, Edge } from '@xyflow/react';
import { toast } from 'sonner';
import { toPng, toSvg } from 'html-to-image';

export interface ExportOptions {
  filename?: string;
  resolution?: 1 | 2 | 4; // 1x, 2x, 4x for retina
  background?: 'transparent' | 'white' | 'theme';
  format?: 'png' | 'svg';
}

/**
 * Wait for multiple animation frames to ensure rendering is complete
 */
function waitForFrames(frameCount: number = 3): Promise<void> {
  return new Promise((resolve) => {
    let count = 0;
    const wait = () => {
      count++;
      if (count >= frameCount) {
        resolve();
      } else {
        requestAnimationFrame(wait);
      }
    };
    requestAnimationFrame(wait);
  });
}

/**
 * Export the graph as PNG or SVG using html-to-image library
 * This is the officially recommended approach for React Flow export
 */
export async function exportGraphAsPNG(
  nodes: Node[],
  edges: Edge[],
  containerElement: HTMLElement,
  options: ExportOptions = {}
): Promise<void> {
  const {
    filename = `repolens-graph-${new Date().toISOString().split('T')[0]}.png`,
    resolution = 2,
    background = 'transparent',
    format = 'png',
  } = options;

  try {
    toast.info('Preparing export...');

    // Verify we have nodes to export
    if (!nodes.length) {
      toast.error('No graph to export');
      return;
    }

    // Find the React Flow viewport element - this is what we want to capture
    const viewportElement = containerElement.querySelector('.react-flow__viewport') as HTMLElement;
    if (!viewportElement) {
      toast.error('React Flow viewport not found');
      return;
    }

    // Hide UI elements temporarily
    const elementsToHide: Array<{ element: HTMLElement; originalDisplay: string }> = [];
    const uiSelectors = [
      '.react-flow__controls',
      '.react-flow__minimap',
      '.react-flow__attribution',
      '.react-flow__panel',
    ];

    uiSelectors.forEach((selector) => {
      const elements = containerElement.querySelectorAll<HTMLElement>(selector);
      elements.forEach((el) => {
        if (el.style.display !== 'none') {
          elementsToHide.push({
            element: el,
            originalDisplay: el.style.display,
          });
          el.style.display = 'none';
        }
      });
    });

    // Wait for 3 animation frames to ensure layout has stabilized
    await waitForFrames(3);

    // Determine background color for html-to-image
    // Note: html-to-image uses undefined for transparent, not 'transparent' string
    let backgroundColor: string | undefined;
    if (background === 'transparent') {
      backgroundColor = undefined; // undefined means transparent in html-to-image
    } else if (background === 'white') {
      backgroundColor = '#ffffff';
    } else {
      // Get theme background color
      const bgColor = getComputedStyle(document.documentElement).getPropertyValue('--background');
      const trimmedBgColor = bgColor?.trim();
      backgroundColor = trimmedBgColor ? `hsl(${trimmedBgColor})` : '#ffffff';
    }

    // Capture the viewport using html-to-image
    let dataUrl: string;

    if (format === 'svg') {
      dataUrl = await toSvg(viewportElement, {
        backgroundColor,
        pixelRatio: resolution,
        cacheBust: true,
        skipFonts: true, // Skip font embedding - fonts are already loaded globally
      });
    } else {
      dataUrl = await toPng(viewportElement, {
        backgroundColor,
        pixelRatio: resolution,
        cacheBust: true,
        skipFonts: true, // Skip font embedding - fonts are already loaded globally
      });
    }

    // Restore hidden elements
    elementsToHide.forEach(({ element, originalDisplay }) => {
      element.style.display = originalDisplay;
    });

    // Download the image
    const link = document.createElement('a');
    link.download = filename;
    link.href = dataUrl;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    toast.success('Graph exported successfully!');
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    toast.error(`Failed to export graph: ${errorMessage}`);

    // Ensure UI elements are restored on error
    const uiSelectors = [
      '.react-flow__controls',
      '.react-flow__minimap',
      '.react-flow__attribution',
      '.react-flow__panel',
    ];

    uiSelectors.forEach((selector) => {
      const elements = containerElement.querySelectorAll<HTMLElement>(selector);
      elements.forEach((el) => {
        el.style.display = '';
      });
    });

    console.error('Export error:', error);
  }
}

/**
 * Export graph as SVG
 */
export async function exportGraphAsSVG(
  nodes: Node[],
  edges: Edge[],
  containerElement: HTMLElement,
  options: Omit<ExportOptions, 'format'> = {}
): Promise<void> {
  const svgFilename = options.filename?.replace('.png', '.svg') ||
    `repolens-graph-${new Date().toISOString().split('T')[0]}.svg`;

  return exportGraphAsPNG(nodes, edges, containerElement, {
    ...options,
    filename: svgFilename,
    format: 'svg',
  });
}

/**
 * Get resolution label for display
 */
export function getResolutionLabel(resolution: 1 | 2 | 4): string {
  switch (resolution) {
    case 1:
      return 'Standard (1x)';
    case 2:
      return 'High Quality (2x)';
    case 4:
      return 'Print Quality (4x)';
  }
}

/**
 * Get background label for display
 */
export function getBackgroundLabel(background: 'transparent' | 'white' | 'theme'): string {
  switch (background) {
    case 'transparent':
      return 'Transparent';
    case 'white':
      return 'White';
    case 'theme':
      return 'Theme Color';
  }
}
