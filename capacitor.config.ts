import type { CapacitorConfig } from '@capacitor/cli'

const url=process.env.CAPACITOR_SERVER_URL
if(!url) console.warn('CAPACITOR_SERVER_URL is not set; Android app will use bundled web assets.')

const config: CapacitorConfig = {
  appId: 'ru.elir.family',
  appName: 'Элир',
  webDir: 'public',
  server: url ? { url, cleartext: false } : undefined,
  android: { allowMixedContent: false }
}

export default config
