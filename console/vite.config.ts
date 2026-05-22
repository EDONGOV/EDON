import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  if (command === 'build' && process.env.EDON_CLIENT_BUILD === 'true' && env.VITE_CONSOLE_DEV_MODE === 'true') {
    throw new Error('Refusing client build: VITE_CONSOLE_DEV_MODE must be false for client releases.')
  }

  return {
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
  }
})
