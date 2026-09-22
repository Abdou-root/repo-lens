import { useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Search, Book, Zap, MessageSquare, Map, Keyboard, FileQuestion, ExternalLink, X } from 'lucide-react';

interface HelpCenterProps {
  open: boolean;
  onClose: () => void;
}

interface HelpArticle {
  id: string;
  title: string;
  content: string;
  category: string;
  keywords: string[];
}

const helpArticles: HelpArticle[] = [
  {
    id: 'getting-started',
    title: 'Getting Started with RepoLens',
    category: 'Getting Started',
    keywords: ['intro', 'basics', 'start', 'tutorial'],
    content: `
**Welcome to RepoLens!**

RepoLens transforms your code repositories into interactive knowledge graphs. Here's how to get started:

1. **Add a Repository**: Paste a GitHub URL in the Dashboard
2. **Wait for Analysis**: RepoLens will clone and analyze your code
3. **Explore the Graph**: Navigate through files, classes, and functions
4. **Use AI Chat**: Ask questions about your codebase

The graph shows:
- **Files** (gray nodes): Source code files
- **Classes** (blue nodes): Class definitions
- **Functions** (green nodes): Function/method definitions
- **Folders** (yellow nodes): Directory grouping

Click any node to see details, code, and connections.
    `,
  },
  {
    id: 'graph-navigation',
    title: 'Navigating the Graph',
    category: 'Graph Navigation',
    keywords: ['zoom', 'pan', 'navigate', 'move', 'controls'],
    content: `
**Graph Controls:**

**Mouse/Trackpad:**
- **Click & Drag**: Pan around the graph
- **Scroll**: Zoom in/out
- **Click Node**: Select and view details
- **Click Background**: Deselect

**Touch (Mobile):**
- **Drag**: Pan around
- **Pinch**: Zoom in/out
- **Tap Node**: Select
- **Long Press**: Show context menu

**View Controls:**
- **Folder View**: Organize by directory structure
- **Flat View**: See all nodes without grouping
- **Layout Direction**: Switch between horizontal/vertical
- **Collapse/Expand**: Hide or show folder contents

**Tips:**
- Use the minimap (bottom-right) for quick navigation
- The search bar highlights matching nodes
- Click "Insights" to discover interesting patterns
    `,
  },
  {
    id: 'search',
    title: 'Searching Your Code',
    category: 'Search',
    keywords: ['find', 'search', 'filter', 'locate'],
    content: `
**Search Features:**

**Text Search:**
Type in the search bar to find nodes by name. The graph will:
- Highlight all matching nodes
- Auto-expand folders containing matches
- Show match count

**Command Palette (⌘K):**
- Quick access to any node
- Filter by type (files, classes, functions)
- Recent items
- Common actions

**Search Tips:**
- Search is case-insensitive
- Matches partial names
- Use filters to narrow results
- Click a match to jump to it
    `,
  },
  {
    id: 'ai-chat',
    title: 'Using AI Chat',
    category: 'AI Features',
    keywords: ['ai', 'chat', 'questions', 'assistant', 'llm'],
    content: `
**AI-Powered Code Understanding:**

The AI Chat can answer questions about your codebase using context from the graph.

**Example Questions:**
- "Where is user authentication handled?"
- "What does the parseConfig function do?"
- "How are API routes structured?"
- "Find all database queries"
- "Explain the dependency between X and Y"

**Chat Features:**
- **Context-Aware**: References selected nodes
- **Code Snippets**: Shows relevant code
- **Navigation**: Click code references to jump to nodes
- **History**: Conversations saved per repository

**Tips:**
- Select a node before asking for specific details
- Be specific in your questions
- Use the chat to explore complex relationships
    `,
  },
  {
    id: 'insights',
    title: 'Understanding Insights',
    category: 'AI Features',
    keywords: ['insights', 'complexity', 'hotspots', 'analysis', 'architecture'],
    content: `
**Automated Code Insights:**

RepoLens automatically detects interesting patterns in your code:

**Entry Points:**
- Files with no incoming dependencies
- Often main files, CLI tools, or top-level modules
- Good starting points for understanding the codebase

**Complexity Hotspots:**
- Files with high code complexity
- Large files (>500 lines)
- Many connections or responsibilities
- May benefit from refactoring

**Architecture Hubs:**
- Files with many incoming/outgoing connections
- Central to the architecture
- Changes may have wide impact
- Critical for understanding the system

**Isolated Modules:**
- Files with few connections
- Self-contained functionality
- Easier to understand and modify independently

Click any insight to jump to that node in the graph.
    `,
  },
  {
    id: 'keyboard-shortcuts',
    title: 'Keyboard Shortcuts',
    category: 'Shortcuts',
    keywords: ['keyboard', 'shortcuts', 'hotkeys', 'keys'],
    content: `
**Keyboard Shortcuts:**

**Global:**
- **⌘K** / **Ctrl+K**: Open command palette
- **?**: Open help center (this sidebar)
- **Esc**: Close open panels/modals

**Navigation:**
- **Tab**: Navigate through nodes
- **Enter**: Select focused node
- **Escape**: Deselect current node

**Graph Controls:**
- **+**: Zoom in
- **-**: Zoom out
- **0**: Reset zoom
- **F**: Fit view to all nodes

**Chat:**
- **⌘/** / **Ctrl+/**: Toggle AI chat
- **⌘Enter**: Send message

**Search:**
- **⌘F** / **Ctrl+F**: Focus search
- **Escape**: Clear search
    `,
  },
  {
    id: 'export',
    title: 'Exporting Graphs',
    category: 'Features',
    keywords: ['export', 'download', 'save', 'png', 'image'],
    content: `
**Export as PNG:**

Click the "Export PNG" button in the toolbar to save your graph visualization.

**Export Options:**
- **Resolution**: Standard (1x), High Quality (2x), or Print Quality (4x)
- **Background**: Transparent, White, or Theme Color
- **Include UI**: Show or hide controls, minimap, and legend

**Use Cases:**
- Documentation
- Presentations
- Code reviews
- Architecture discussions
- Onboarding materials

**Tips:**
- Use 2x resolution for most needs
- Print quality (4x) is great for large prints
- Transparent background works best for slides
- Hide UI elements for cleaner exports
    `,
  },
  {
    id: 'troubleshooting',
    title: 'Troubleshooting',
    category: 'Help',
    keywords: ['help', 'problem', 'error', 'issue', 'bug', 'fix'],
    content: `
**Common Issues:**

**Graph not loading:**
- Check your internet connection
- Refresh the page
- Verify the repository was analyzed successfully
- Check browser console for errors

**Search not working:**
- Try clearing the search and typing again
- Ensure you're searching in the correct repository
- Check if the node exists in the graph

**AI Chat not responding:**
- Check your internet connection
- Verify you have credits remaining
- Try rephrasing your question
- Make sure a repository is selected

**Performance issues:**
- Large graphs (>1000 nodes) may be slower
- Try using folder view to group nodes
- Filter by type to reduce visible nodes
- Close other browser tabs

**Repository analysis stuck:**
- Refresh the page to check status
- Very large repositories may take 10-30 minutes
- Check the progress bar for current step
- Contact support if stuck for >1 hour

**Still need help?**
Report issues on [GitHub](https://github.com/yourusername/repolens/issues) or contact support.
    `,
  },
];

export function HelpCenter({ open, onClose }: HelpCenterProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedCategories, setExpandedCategories] = useState<string[]>(['Getting Started']);

  // Filter articles by search query
  const filteredArticles = searchQuery
    ? helpArticles.filter(
        (article) =>
          article.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          article.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
          article.keywords.some((kw) => kw.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : helpArticles;

  // Group articles by category
  const categorizedArticles = filteredArticles.reduce((acc, article) => {
    if (!acc[article.category]) {
      acc[article.category] = [];
    }
    acc[article.category].push(article);
    return acc;
  }, {} as Record<string, HelpArticle[]>);

  const categoryIcons: Record<string, any> = {
    'Getting Started': Book,
    'Graph Navigation': Map,
    'Search': Search,
    'AI Features': MessageSquare,
    'Shortcuts': Keyboard,
    'Features': Zap,
    'Help': FileQuestion,
  };

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto">
        <SheetHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div>
              <SheetTitle className="text-2xl">Help Center</SheetTitle>
              <SheetDescription>
                Find answers, learn features, and get the most out of RepoLens
              </SheetDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="h-8 w-8 p-0"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </SheetHeader>

        {/* Search */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search help articles..."
            className="pl-9"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Articles */}
        {Object.keys(categorizedArticles).length > 0 ? (
          <Accordion
            type="multiple"
            value={searchQuery ? Object.keys(categorizedArticles) : expandedCategories}
            onValueChange={setExpandedCategories}
            className="space-y-2"
          >
            {Object.entries(categorizedArticles).map(([category, articles]) => {
              const Icon = categoryIcons[category] || FileQuestion;

              return (
                <AccordionItem key={category} value={category} className="border rounded-lg px-4">
                  <AccordionTrigger className="hover:no-underline">
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 text-primary" />
                      <span className="font-semibold">{category}</span>
                      <span className="text-xs text-muted-foreground ml-1">
                        ({articles.length})
                      </span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-4 pt-2">
                      {articles.map((article) => (
                        <div key={article.id} className="space-y-2">
                          <h4 className="font-medium text-sm">{article.title}</h4>
                          <div className="prose prose-sm dark:prose-invert max-w-none">
                            {article.content.split('\n').map((line, idx) => {
                              if (line.startsWith('**') && line.endsWith('**')) {
                                return (
                                  <p key={idx} className="font-semibold mt-3 mb-1">
                                    {line.replace(/\*\*/g, '')}
                                  </p>
                                );
                              }
                              if (line.startsWith('- **')) {
                                const parts = line.match(/- \*\*(.*?)\*\*: (.*)/);
                                if (parts) {
                                  return (
                                    <p key={idx} className="ml-4 text-sm">
                                      <strong>{parts[1]}:</strong> {parts[2]}
                                    </p>
                                  );
                                }
                              }
                              if (line.startsWith('- ')) {
                                return (
                                  <p key={idx} className="ml-4 text-sm">
                                    • {line.substring(2)}
                                  </p>
                                );
                              }
                              if (line.match(/^\d+\./)) {
                                return (
                                  <p key={idx} className="ml-4 text-sm">
                                    {line}
                                  </p>
                                );
                              }
                              if (line.trim() === '') {
                                return <div key={idx} className="h-2" />;
                              }
                              if (line.includes('[GitHub]')) {
                                return (
                                  <p key={idx} className="text-sm">
                                    {line.split('[GitHub]')[0]}
                                    <a
                                      href="#"
                                      className="text-primary hover:underline inline-flex items-center gap-1"
                                      target="_blank"
                                      rel="noopener noreferrer"
                                    >
                                      GitHub
                                      <ExternalLink className="h-3 w-3" />
                                    </a>
                                    {line.split('(https://github.com/yourusername/repolens/issues)')[1]}
                                  </p>
                                );
                              }
                              return (
                                <p key={idx} className="text-sm text-muted-foreground">
                                  {line}
                                </p>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              );
            })}
          </Accordion>
        ) : (
          <div className="text-center py-12">
            <FileQuestion className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-sm text-muted-foreground">
              No articles found matching "{searchQuery}"
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => setSearchQuery('')}
            >
              Clear Search
            </Button>
          </div>
        )}

        {/* Footer */}
        <div className="mt-8 pt-6 border-t">
          <div className="bg-muted/50 p-4 rounded-lg">
            <p className="text-sm font-medium mb-2">Still need help?</p>
            <p className="text-xs text-muted-foreground mb-3">
              Can't find what you're looking for? We're here to help.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1" asChild>
                <a href="https://github.com/yourusername/repolens/issues" target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-3 w-3 mr-2" />
                  Report Issue
                </a>
              </Button>
              <Button variant="outline" size="sm" className="flex-1" asChild>
                <a href="mailto:support@repolens.com">
                  Contact Support
                </a>
              </Button>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
