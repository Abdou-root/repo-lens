/**
 * Shared utility functions for graph visualization components.
 *
 * These utilities are used across GraphExplorer, NodeDrawer, CustomNodes, etc.
 * to maintain consistency and reduce duplication.
 */

/**
 * Extract folder path from a file path.
 * @example getFolderPath("src/components/Header.tsx") // "src/components"
 * @example getFolderPath("index.ts") // "."
 */
export function getFolderPath(filePath: string): string {
  if (!filePath || typeof filePath !== 'string') {
    return '.';
  }

  // Handle both Unix and Windows paths
  const separator = filePath.includes('\\') ? '\\' : '/';
  const parts = filePath.split(separator).filter(Boolean);

  if (parts.length <= 1) return '.'; // Root level
  return parts.slice(0, -1).join('/'); // Always use Unix separator for consistency
}

/**
 * Detect programming language from file extension.
 * Used for syntax highlighting in code previews.
 */
export function getLanguageFromPath(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || '';
  const langMap: Record<string, string> = {
    'py': 'python',
    'ts': 'typescript',
    'tsx': 'tsx',
    'js': 'javascript',
    'jsx': 'jsx',
    'rs': 'rust',
    'go': 'go',
    'java': 'java',
    'rb': 'ruby',
    'php': 'php',
    'cs': 'csharp',
    'cpp': 'cpp',
    'c': 'c',
    'h': 'c',
    'hpp': 'cpp',
    'swift': 'swift',
    'kt': 'kotlin',
    'scala': 'scala',
    'sql': 'sql',
    'sh': 'bash',
    'bash': 'bash',
    'zsh': 'bash',
    'json': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'toml': 'toml',
    'md': 'markdown',
    'css': 'css',
    'scss': 'scss',
    'html': 'html',
    'xml': 'xml',
  };
  return langMap[ext] || 'text';
}

/**
 * Get file extension from filename.
 */
export function getFileExtension(filename: string): string {
  return filename.split('.').pop()?.toLowerCase() || '';
}

/**
 * Check if a file is a code file based on extension.
 */
export function isCodeFile(filename: string): boolean {
  const codeExtensions = new Set([
    'ts', 'tsx', 'js', 'jsx', 'py', 'rs', 'go', 'java', 'rb', 'php',
    'cs', 'cpp', 'c', 'h', 'hpp', 'swift', 'kt', 'scala',
  ]);
  return codeExtensions.has(getFileExtension(filename));
}

/**
 * Build folder hierarchy from a list of folder paths.
 * Returns a map of folder path -> parent folder path
 */
export function buildFolderHierarchy(folderPaths: Set<string>): Map<string, string | null> {
  const hierarchy = new Map<string, string | null>();

  // Sort by depth (shorter paths first) to ensure parents are processed first
  const sortedPaths = Array.from(folderPaths).sort((a, b) => {
    const depthA = a === '.' ? 0 : a.split('/').length;
    const depthB = b === '.' ? 0 : b.split('/').length;
    return depthA - depthB;
  });

  for (const path of sortedPaths) {
    if (path === '.') {
      hierarchy.set(path, null);
    } else {
      const parentPath = getFolderPath(path + '/dummy'); // Add dummy to get parent
      hierarchy.set(path, folderPaths.has(parentPath) ? parentPath : null);
    }
  }

  return hierarchy;
}
