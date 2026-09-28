# hermes-kokoro-tts

Kokoro-82M as a TTS provider for [Hermes Agent](https://hermes-agent.nousresearch.com). 54 voices
in 9 languages, CPU only, offline, no API key, and the model stays loaded between replies.

- 54 voices, spread like this: en-us 20, en-gb 8, zh 8, ja 5, hi 4, es 3, pt-br 3, it 2, fr 1
- language and voice dropdowns, in the Kokoro TTS panel and in the plugin's settings
- a small daemon holds the model in RAM and unloads it after `idle_seconds` of no use
- ~350 MB of disk for the model, downloaded from Hugging Face on first use

## Install

```bash
hermes plugins install elfo-97/hermes-kokoro-tts
```

[Listen to the samples first →](https://hermes-kokoro-voices.vercel.app)

Answer yes when it asks `Enable now?`, then grab a voice id from the [samples](#voices) (`pf_dora`
is pt-BR female; the id is language + gender) and set it. The keys are in
[Configuration](#configuration), and the settings form under Settings → Plugins → kokoro, the
Kokoro TTS panel and `hermes plugins` all write to the same values.

## Voices

Every voice has a player at [hermes-kokoro-voices.vercel.app](https://hermes-kokoro-voices.vercel.app).

The id reads as language, gender, name: `pf_dora` is pt-BR female, `am_onyx` is en-US male. Each
voice is its own anchor, so `https://hermes-kokoro-voices.vercel.app/#pf_dora` links straight at one.
Hit copy on the page and paste the command it hands you. The same clips ship as MP3 in
[`samples/`](samples).

## Configuration

| key | default | meaning |
|---|---|---|
| `language` | `en-us` | language of the default voice |
| `voice` | empty | an explicit voice id, overrides `language` |
| `python` | the Hermes interpreter | interpreter that has `kokoro` and `soundfile` |
| `port` | `51235` | local port for the daemon |
| `idle_seconds` | `300` | the daemon exits after this much idle time |

Kokoro runs in its own Python, so it needs `kokoro`, `soundfile` and `numpy` there (`pip install
kokoro soundfile`). Leave `python` empty and it uses the interpreter Hermes runs on; point it at a
virtualenv instead if that one has them.

Japanese and Chinese need their language packs in that Python too:

```bash
pip install "misaki[zh]"                                          # Chinese: jieba, pypinyin, cn2an, ordered-set
pip install pyopenjtalk-plus fugashi unidic-lite jaconv mojimoji  # Japanese
```

`pyopenjtalk-plus` ships `pyopenjtalk` prebuilt. Upstream `pyopenjtalk` has no wheel and builds from
source (CMake + MSVC on Windows), so `pip install "misaki[ja]"` fails there on its own.

Every key is settable the same way, `hermes config set plugins.entries.kokoro.settings.<key> <value>`,
and `plugin.yaml` declares them in `config_schema`, so the settings form, the Kokoro TTS panel and
`hermes plugins` (press Enter on the kokoro row) all edit the same values. The provider also shows up
under `hermes tools` → Text-to-Speech.

## Performance

Measured on an i3-10100 (4 cores / 8 threads), CPU only, `pf_dora`:

| metric | measured |
|---|---|
| audio generated | 28 s of speech in 10.5 s (~2.7x realtime) |
| CPU | ~4 threads busy while speaking |
| RAM | ~1.3 GB resident with the model loaded, 0% CPU when idle |
| first call after startup | ~12 s (spawns the daemon, loads the model) |
| call while warm | ~2 s |

The plugin never touches the GPU and makes no network calls after the model download.

## Credits

[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad, Apache-2.0. This plugin is only
the Hermes adapter around it.

## License

MIT. See [LICENSE](LICENSE).
