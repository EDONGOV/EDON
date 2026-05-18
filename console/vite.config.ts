import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          minSize: 20_000,
          groups: [
            { name: 'react-vendor', test: /node_modules[\\/](react|react-dom)[\\/]/ },
            { name: 'motion-vendor', test: /node_modules[\\/](framer-motion|motion-dom|motion-utils|tslib)[\\/]/ },
            { name: 'icon-vendor', test: /node_modules[\\/]lucide-react[\\/]/ },
          ],
        },
      },
    },
  },
})
