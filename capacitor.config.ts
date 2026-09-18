import type { CapacitorConfig } from '@capacitor/cli'

const url=process.env.CAPACITOR_SERVER_URL || 'http://62.84.122.57'

const config: CapacitorConfig = {
  appId: 'ru.elir.personal',
  appName: 'Элир',
  webDir: 'public',
  server: { url, cleartext: true },
  android: { allowMixedContent: true }
}

export default config
