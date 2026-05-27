import DOMPurify from 'dompurify'

const ANSI_HTML_CONFIG = {
  ALLOWED_TAGS: ['span'],
  ALLOWED_ATTR: ['style'],
}

export function sanitizeAnsiHtml(html: string): string {
  return DOMPurify.sanitize(html, ANSI_HTML_CONFIG) as string
}
