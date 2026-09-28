/**
 * Kokoro TTS panel: pick the language and the voice without editing config.yaml.
 *
 * Lives in the plugin package as `desktop/plugin.js`, so it installs and uninstalls with
 * the Python half. Talks to the plugin's own backend at /api/plugins/kokoro/.
 */
import {
  host, PALETTE_AREA, ROUTES_AREA, Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  SIDEBAR_NAV_AREA, usePluginI18n
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'kokoro'
const ROUTE = '/kokoro'

function Picker({ value, options, onChange }) {
  return jsxs(Select, {
    value,
    onValueChange: onChange,
    children: [
      jsx(SelectTrigger, { className: 'w-52', children: jsx(SelectValue, {}) }),
      jsx(SelectContent, { children: options.map(option => jsx(SelectItem, { value: option, children: option })) })
    ]
  })
}

function Row({ label, hint, children }) {
  return jsxs('div', {
    className: 'flex items-center justify-between gap-6',
    children: [
      jsxs('div', {
        children: [
          jsx('div', { className: 'text-sm', children: label }),
          hint ? jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: hint }) : null
        ]
      }),
      children
    ]
  })
}

function Panel({ ctx }) {
  const t = usePluginI18n(ID)
  const [state, setState] = useState(null)
  const [error, setError] = useState('')

  const message = reason => String((reason && reason.message) || reason)

  useEffect(() => {
    ctx.rest('/state').then(setState).catch(reason => setError(message(reason)))
  }, [])

  const save = patch => {
    setError('')
    ctx
      .rest('/settings', { method: 'POST', body: patch })
      .then(next => {
        setState(next)
        host.notify({ kind: 'info', message: t('saved') })
      })
      .catch(reason => setError(message(reason)))
  }

  if (error) {
    return jsx('div', { className: 'p-4 text-sm text-(--ui-text-secondary)', children: error })
  }
  if (!state) {
    return jsx('div', { className: 'p-4 text-sm text-(--ui-text-tertiary)', children: t('loading') })
  }

  const voices = state.voices[state.language] || []

  return jsxs('div', {
    className: 'flex h-full flex-col gap-6 p-4',
    children: [
      jsx('div', { className: 'text-sm font-medium', children: t('title') }),
      jsx(Row, {
        label: t('language'),
        hint: t('languageHint'),
        children: jsx(Picker, {
          value: state.language,
          options: state.languages,
          // Switching language also picks that language's first voice: keeping the old id would
          // leave a voice from another language selected.
          onChange: language => save({ language, voice: (state.voices[language] || [''])[0] })
        })
      }),
      jsx(Row, {
        label: t('voice'),
        hint: t('voiceHint'),
        children: jsx(Picker, {
          value: state.voice || voices[0] || '',
          options: voices,
          onChange: voice => save({ voice })
        })
      }),
      jsx('div', {
        className: 'text-xs text-(--ui-text-tertiary)',
        children: t('engine', state.python || t('hermesInterpreter'), state.idle_seconds)
      })
    ]
  })
}

export default {
  id: ID,
  name: 'Kokoro TTS',
  register(ctx) {
    ctx.i18n.register({
      en: {
        title: 'Kokoro TTS (local, CPU)',
        language: 'Language',
        languageHint: 'Voices come from the model itself',
        voice: 'Voice',
        voiceHint: 'Empty means the first voice of the language',
        engine: (python, idle) => `interpreter: ${python} · unloads after ${idle}s idle`,
        hermesInterpreter: 'the Hermes interpreter',
        saved: 'Kokoro TTS updated',
        loading: 'Loading voices…',
        palette: 'Kokoro TTS: language & voice'
      },
      'pt-BR': {
        title: 'Kokoro TTS (local, CPU)',
        language: 'Idioma',
        languageHint: 'As vozes vêm do próprio modelo',
        voice: 'Voz',
        voiceHint: 'Vazio usa a primeira voz do idioma',
        engine: (python, idle) => `interpretador: ${python} · descarrega após ${idle}s ocioso`,
        hermesInterpreter: 'o interpretador do Hermes',
        saved: 'Kokoro TTS atualizado',
        loading: 'Carregando vozes…',
        palette: 'Kokoro TTS: idioma e voz'
      }
    })

    ctx.register({
      id: 'page',
      area: ROUTES_AREA,
      data: { path: ROUTE },
      render: () => jsx(Panel, { ctx })
    })

    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      order: 60,
      data: { path: ROUTE, label: 'Kokoro TTS', codicon: 'mic' }
    })

    ctx.register({
      id: 'open',
      area: PALETTE_AREA,
      data: {
        id: 'kokoro.open',
        label: ctx.i18n.t('palette'),
        keywords: ['kokoro', 'tts', 'voice', 'language'],
        run: () => host.navigate(ROUTE)
      }
    })
  }
}
