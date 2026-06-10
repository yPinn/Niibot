import DOMPurify from 'dompurify'

const SAFE_ANSI_CSS = new Set([
  'color',
  'background-color',
  'font-weight',
  'font-style',
  'text-decoration',
  'text-decoration-line',
  'text-decoration-color',
])

DOMPurify.addHook('afterSanitizeAttributes', node => {
  if (!(node instanceof HTMLElement) || !node.style.length) return
  for (let i = node.style.length - 1; i >= 0; i--) {
    const prop = node.style[i]
    if (!SAFE_ANSI_CSS.has(prop)) node.style.removeProperty(prop)
  }
})

const ANSI_HTML_CONFIG = {
  ALLOWED_TAGS: ['span'],
  ALLOWED_ATTR: ['style'],
}

export function sanitizeAnsiHtml(html: string): string {
  return DOMPurify.sanitize(html, ANSI_HTML_CONFIG) as string
}
