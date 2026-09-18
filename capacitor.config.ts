import type { CapacitorConfig } from '@capacitor/cli'

const url=process.env.CAPACITOR_SERVER_URL || 'https://elir.62.84.122.57.nip.io'

const config: CapacitorConfig = {
  appId: 'ru.elir.personal',
  appName: 'Элир',
  webDir: 'public',
  server: { url, cleartext: false },
  android: { allowMixedContent: false }
}

export default config
