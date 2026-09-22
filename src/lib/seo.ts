/**
 * SEO utility for dynamically updating meta tags
 */

interface SEOData {
  title?: string;
  description?: string;
  image?: string;
  url?: string;
  type?: string;
}

const DEFAULT_TITLE = 'RepoLens - Code Visualization';
const DEFAULT_DESCRIPTION = 'Transform your code repositories into interactive knowledge graphs with AI-powered insights';
const DEFAULT_IMAGE = '/screenshot-desktop.png';
const BASE_URL = import.meta.env.VITE_APP_URL || 'https://repolens.app';

export function updateSEO(data: SEOData) {
  const title = data.title ? `${data.title} | RepoLens` : DEFAULT_TITLE;
  const description = data.description || DEFAULT_DESCRIPTION;
  const image = data.image || DEFAULT_IMAGE;
  const url = data.url || window.location.href;
  const type = data.type || 'website';

  // Update document title
  document.title = title;

  // Update or create meta tags
  const updateMetaTag = (name: string, content: string, isProperty = false) => {
    const attribute = isProperty ? 'property' : 'name';
    let meta = document.querySelector(`meta[${attribute}="${name}"]`) as HTMLMetaElement;
    
    if (!meta) {
      meta = document.createElement('meta');
      meta.setAttribute(attribute, name);
      document.head.appendChild(meta);
    }
    
    meta.setAttribute('content', content);
  };

  // Basic meta tags
  updateMetaTag('description', description);
  updateMetaTag('title', title);

  // Open Graph tags
  updateMetaTag('og:title', title, true);
  updateMetaTag('og:description', description, true);
  updateMetaTag('og:image', image, true);
  updateMetaTag('og:url', url, true);
  updateMetaTag('og:type', type, true);
  updateMetaTag('og:site_name', 'RepoLens', true);

  // Twitter Card tags
  updateMetaTag('twitter:card', 'summary_large_image');
  updateMetaTag('twitter:title', title);
  updateMetaTag('twitter:description', description);
  updateMetaTag('twitter:image', image);
}

export function resetSEO() {
  updateSEO({
    title: DEFAULT_TITLE,
    description: DEFAULT_DESCRIPTION,
    image: DEFAULT_IMAGE,
  });
}

