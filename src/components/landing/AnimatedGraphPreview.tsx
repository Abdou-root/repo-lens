import { useEffect, useState } from 'react';

interface Node {
  id: string;
  label: string;
  type: 'file' | 'function' | 'class';
  x: number;
  y: number;
  delay: number;
}

interface Edge {
  from: string;
  to: string;
  delay: number;
}

const nodes: Node[] = [
  { id: 'app', label: 'app.py', type: 'file', x: 200, y: 80, delay: 0 },
  { id: 'routes', label: 'routes.py', type: 'file', x: 80, y: 180, delay: 200 },
  { id: 'models', label: 'models.py', type: 'file', x: 320, y: 180, delay: 400 },
  { id: 'auth', label: 'AuthHandler', type: 'class', x: 50, y: 300, delay: 600 },
  { id: 'db', label: 'Database', type: 'class', x: 350, y: 300, delay: 800 },
  { id: 'handler', label: 'handle_request', type: 'function', x: 200, y: 280, delay: 1000 },
];

const edges: Edge[] = [
  { from: 'app', to: 'routes', delay: 1200 },
  { from: 'app', to: 'models', delay: 1400 },
  { from: 'routes', to: 'auth', delay: 1600 },
  { from: 'routes', to: 'handler', delay: 1800 },
  { from: 'models', to: 'db', delay: 2000 },
  { from: 'handler', to: 'db', delay: 2200 },
];

const nodeColors = {
  file: { bg: 'hsl(var(--primary))', border: 'hsl(var(--primary))', text: 'hsl(var(--primary-foreground))' },
  function: { bg: 'hsl(var(--chart-2))', border: 'hsl(var(--chart-2))', text: 'white' },
  class: { bg: 'hsl(var(--chart-1))', border: 'hsl(var(--chart-1))', text: 'white' },
};

export function AnimatedGraphPreview() {
  const [visibleNodes, setVisibleNodes] = useState<Set<string>>(new Set());
  const [visibleEdges, setVisibleEdges] = useState<Set<string>>(new Set());
  const [animationKey, setAnimationKey] = useState(0);

  useEffect(() => {
    // Reset animation
    setVisibleNodes(new Set());
    setVisibleEdges(new Set());

    // Animate nodes appearing
    nodes.forEach((node) => {
      setTimeout(() => {
        setVisibleNodes((prev) => new Set([...prev, node.id]));
      }, node.delay);
    });

    // Animate edges appearing
    edges.forEach((edge) => {
      setTimeout(() => {
        setVisibleEdges((prev) => new Set([...prev, `${edge.from}-${edge.to}`]));
      }, edge.delay);
    });

    // Restart animation after all elements are visible
    const restartTimeout = setTimeout(() => {
      setAnimationKey((prev) => prev + 1);
    }, 5000);

    return () => clearTimeout(restartTimeout);
  }, [animationKey]);

  const getNodePosition = (id: string) => {
    const node = nodes.find((n) => n.id === id);
    return node ? { x: node.x, y: node.y } : { x: 0, y: 0 };
  };

  return (
    <div className="w-full aspect-video bg-background/50 rounded-lg overflow-hidden relative">
      <svg
        viewBox="0 0 400 380"
        className="w-full h-full"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Grid pattern background */}
        <defs>
          <pattern
            id="grid"
            width="20"
            height="20"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 20 0 L 0 0 0 20"
              fill="none"
              stroke="hsl(var(--border))"
              strokeWidth="0.5"
              opacity="0.3"
            />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />

        {/* Edges */}
        {edges.map((edge) => {
          const from = getNodePosition(edge.from);
          const to = getNodePosition(edge.to);
          const isVisible = visibleEdges.has(`${edge.from}-${edge.to}`);

          return (
            <g key={`${edge.from}-${edge.to}`}>
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="hsl(var(--muted-foreground))"
                strokeWidth="2"
                opacity={isVisible ? 0.4 : 0}
                className="transition-opacity duration-500"
              />
              {/* Animated dot along the edge */}
              {isVisible && (
                <circle r="3" fill="hsl(var(--primary))">
                  <animateMotion
                    dur="2s"
                    repeatCount="indefinite"
                    path={`M${from.x},${from.y} L${to.x},${to.y}`}
                  />
                </circle>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map((node) => {
          const isVisible = visibleNodes.has(node.id);
          const colors = nodeColors[node.type];

          return (
            <g
              key={node.id}
              transform={`translate(${node.x}, ${node.y})`}
              opacity={isVisible ? 1 : 0}
              className="transition-all duration-500"
              style={{
                transform: `translate(${node.x}px, ${node.y}px) scale(${isVisible ? 1 : 0.5})`,
              }}
            >
              {/* Node background with pulse effect */}
              <circle
                r="30"
                fill={colors.bg}
                opacity="0.1"
                className={isVisible ? 'animate-ping' : ''}
                style={{ animationDuration: '3s' }}
              />
              {/* Main node circle */}
              <circle
                r="24"
                fill={colors.bg}
                stroke={colors.border}
                strokeWidth="2"
                className="drop-shadow-lg"
              />
              {/* Node label */}
              <text
                textAnchor="middle"
                dy="0.35em"
                fontSize="8"
                fontFamily="monospace"
                fill={colors.text}
                fontWeight="500"
              >
                {node.label.length > 12
                  ? node.label.slice(0, 10) + '...'
                  : node.label}
              </text>
              {/* Type indicator */}
              <text
                textAnchor="middle"
                dy="2.5em"
                fontSize="6"
                fill="hsl(var(--muted-foreground))"
              >
                {node.type}
              </text>
            </g>
          );
        })}

        {/* Legend */}
        <g transform="translate(10, 340)">
          <circle cx="10" cy="0" r="6" fill={nodeColors.file.bg} />
          <text x="22" y="4" fontSize="8" fill="hsl(var(--muted-foreground))">
            File
          </text>

          <circle cx="60" cy="0" r="6" fill={nodeColors.function.bg} />
          <text x="72" y="4" fontSize="8" fill="hsl(var(--muted-foreground))">
            Function
          </text>

          <circle cx="130" cy="0" r="6" fill={nodeColors.class.bg} />
          <text x="142" y="4" fontSize="8" fill="hsl(var(--muted-foreground))">
            Class
          </text>
        </g>
      </svg>

      {/* Overlay text */}
      <div className="absolute bottom-4 right-4 text-xs text-muted-foreground bg-background/80 px-2 py-1 rounded">
        Live visualization preview
      </div>
    </div>
  );
}
