import react from '@vitejs/plugin-react-swc'
import path from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: false,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: [
        // config.ts excluded: API_ENDPOINTS contains 15+ URL-builder arrow fns that
        // are never called in tests. assertTrustedOAuthUrl and apiFetch ARE tested
        // in config.test.ts but coverage tracking is not meaningful here.
        'src/lib/apiCache.ts',
        'src/lib/sort.ts',
        'src/lib/groupByCategory.ts',
        'src/hooks/useSortState.ts',
        'src/hooks/useDocumentTitle.ts',
        'src/hooks/usePolling.ts',
        'src/components/ProtectedRoute.tsx',
        'src/api/user.ts',
        'src/contexts/AuthContext.tsx',
        'src/pages/dashboard/events/renderTemplate.ts',
        'src/lib/plus-program.ts',
      ],
      thresholds: { lines: 80, functions: 80, branches: 80 },
    },
  },
})
