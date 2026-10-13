"""YuE2 Studio – Gradio-Oberfläche (Deutsch / English)."""
import atexit
import os
import random
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

# Temporäre Dateien (Vorschau-Audio) landen in einem eigenen Ordner, der beim Beenden gelöscht wird.
TEMP_DIR = Path(tempfile.mkdtemp(prefix="yue2_app_"))
os.environ["GRADIO_TEMP_DIR"] = str(TEMP_DIR)
atexit.register(shutil.rmtree, TEMP_DIR, ignore_errors=True)

import gradio as gr  # noqa: E402
import soundfile as sf  # noqa: E402

import gpu_info  # noqa: E402
import i18n  # noqa: E402
import llm  # noqa: E402
import ui_theme as ui  # noqa: E402
from exporter import save_song  # noqa: E402
from i18n import t  # noqa: E402
from lyrics_tools import (estimate_seconds, fmt_duration, issues_text, lint, normalize_lyrics,  # noqa: E402
                          sanitize_filename, structure_hint, target_lines)
from settings import CONFIG, path, prompt  # noqa: E402
from yue_engine import ENGINE, SAMPLE_RATE, Cancelled  # noqa: E402

# Sprachneutrale Werte; die Anzeigenamen kommen aus i18n.
MODE_NEW, MODE_REMAKE = "new", "remake"
LYRIC_LANGS = ["auto", "German", "English", "Spanish", "French", "Italian", "Portuguese", "Dutch",
               "Japanese", "Chinese", "Korean"]
LYRICS_MODES = ["keep", "rewrite", "translate"]
COTS = ["full", "melody", "off"]


def mode_choices():
    return [(t("mode.new"), MODE_NEW), (t("mode.remake"), MODE_REMAKE)]


def lang_choices():
    return [(t(f"lang.{code}"), code) for code in LYRIC_LANGS]


def lmode_choices():
    return [(t(f"lm.{code}"), code) for code in LYRICS_MODES]


def cot_choices():
    return [(t(f"cot.{code}"), code) for code in COTS]


def lyric_language(code):
    return "" if code in (None, "", "auto") else code


# ---------------------------------------------------------------- Hilfen

def gpu_status():
    """(Text, ok) für den Status-Chip, z. B. „RX 7900 XTX · 24 GB · ROCm“."""
    gpu = gpu_info.current()
    if gpu.vendor == "none":
        return t("chip.gpu_none"), False
    return f"{gpu.short_name} · {gpu.vram_gib:.0f} GB · {gpu.runtime}", True


def model_choices():
    """(Modelle, Vorauswahl, ok, Statustext)."""
    try:
        models = llm.list_models()
    except llm.OllamaError:
        return [], None, False, t("chip.ollama_err")
    default = CONFIG["ollama_default_model"]
    value = default if default in models else (models[0] if models else None)
    return models, value, True, t("chip.ollama_ok", n=len(models))


def hero_html():
    _, _, ok, text = model_choices()
    gpu_text, gpu_ok = gpu_status()
    return ui.hero(ok, text, gpu_text, gpu_ok, gpu_info.current().low_vram)


def refresh_models():
    models, value, ok, text = model_choices()
    gpu_text, gpu_ok = gpu_status()
    return gr.update(choices=models, value=value), ui.hero(ok, text, gpu_text, gpu_ok, gpu_info.current().low_vram)


def require_model(model):
    if not model:
        raise gr.Error(t("err.no_model"))


def song_outputs(data, max_secs=None):
    """Gemeinsame Ausgabe aller Erstellen-/Korrigieren-Aktionen."""
    lyrics = normalize_lyrics(data["lyrics"])
    style = " ".join(data["style"].split())
    out = [data["title"], style, lyrics, data["language"], ui.lint_html(style, lyrics), data["title"]]
    out.append(gr.update(value=max_secs) if max_secs else gr.update())
    return out


# ---------------------------------------------------------------- Neuer Song

def create_new(idea, language_code, target_secs, model):
    require_model(model)
    if not (idea or "").strip():
        raise gr.Error(t("err.no_idea"))
    lang = lyric_language(language_code)
    target_secs = int(target_secs)
    user = (f"Song idea: {idea.strip()}\n"
            f"Target language of the lyrics: {lang or 'the language the idea is written in'}\n"
            f"Target length: about {target_secs} seconds ({fmt_duration(target_secs)} min)\n"
            f"Suggested structure: {structure_hint(target_secs)}\n"
            f"Aim for about {target_lines(target_secs)} sung lines in total (≈ 2 bars per line).")
    try:
        data = llm.chat_json(model, prompt("master_new.md"), user)
    except llm.OllamaError as e:
        raise gr.Error(str(e))
    return song_outputs(data, max_secs=min(600, target_secs + 90))


# ---------------------------------------------------------------- Remake

def load_source_info(audio_file):
    """Liest beim Laden eines Songs Titel, Interpret, Album, Cover usw. aus den Tags (MP3, FLAC, M4A …)."""
    if not audio_file:
        return "", None
    from audio_utils import read_tags
    source = {"tags": read_tags(audio_file), "name": Path(audio_file).stem}
    return ui.track_card(source["tags"], source["name"]), source


def analyze_remake(audio_file):
    if not audio_file:
        raise gr.Error(t("err.no_upload"))
    from melody import transcribe_melody
    from lyrics_asr import transcribe

    llm.unload()  # VRAM für SheetSage2 und Whisper freimachen
    if not ENGINE.unload():
        raise gr.Error(t("err.busy"))
    keep = gr.update()
    yield keep, keep, ui.notice("info", t("remake.step1"),
                                      t("remake.step1_sub_cpu" if gpu_info.current().is_amd else "remake.step1_sub")), keep, keep
    try:
        abc, warnings = transcribe_melody(audio_file)
    except RuntimeError as e:
        yield keep, keep, ui.notice("err", t("remake.melody_failed"), ui.esc(e)), keep, keep
        raise gr.Error(str(e))
    note = f"<br>{t('remake.hints')}: {ui.esc('; '.join(warnings)[:300])}" if warnings else ""
    yield abc, keep, ui.notice("info", t("remake.step2"), t("remake.melody_done") + note), keep, keep
    try:
        text = transcribe(audio_file)
    except Exception as e:
        yield keep, keep, ui.notice("err", t("remake.asr_failed"), ui.esc(e)), keep, keep
        raise gr.Error(t("err.whisper", e=e))
    from audio_utils import load_mono
    duration = len(load_mono(audio_file, 8000)) / 8000
    yield (abc, text, ui.notice("ok", t("remake.done", dur=fmt_duration(duration)), t("remake.done_sub") + note),
           gr.update(value=min(600, int(duration) + 30)), duration)


def create_remake(transcript, lyrics_mode, target_lang_code, style_wish, abc, model, src_duration):
    require_model(model)
    if not (abc or "").strip():
        raise gr.Error(t("err.no_abc"))
    from melody import abc_header, abc_sections
    sections = abc_sections(abc)
    target = lyric_language(target_lang_code)
    if lyrics_mode == "translate" and not target:
        raise gr.Error(t("err.no_target_lang"))
    user = (f"Lyrics mode: {lyrics_mode}\n"
            + (f"Target language: {target}\n" if lyrics_mode == "translate" else "")
            + f"User wish for the new style / idea: {(style_wish or '').strip() or '(none)'}\n"
            f"Original song length: about {int(src_duration or 0)} seconds\n"
            f"Original score header (tempo, meter, key): {abc_header(abc) or 'unknown'}\n"
            f"Section order detected in the original melody: {' → '.join(sections) or 'unknown'}\n\n"
            f"Transcript of the original vocals:\n{(transcript or '').strip() or '(no vocals recognised)'}")
    try:
        data = llm.chat_json(model, prompt("master_remake.md"), user)
    except llm.OllamaError as e:
        raise gr.Error(str(e))
    return song_outputs(data)


# ---------------------------------------------------------------- Korrektur

def check(style, lyrics):
    return ui.lint_html(style, lyrics) or ui.notice("warn", t("check.empty_t"), t("check.empty_b"))


def correct(title, style, lyrics, request, model):
    require_model(model)
    if not (style or lyrics):
        raise gr.Error(t("err.nothing_to_correct"))
    user = (f"Correction request from the user: {(request or '').strip() or '(none – only fix rule violations)'}\n\n"
            f"Automatic check warnings:\n{issues_text(style, lyrics)}\n\n"
            f"Current title: {title}\n\nCurrent style:\n{style}\n\nCurrent lyrics:\n{lyrics}")
    try:
        data = llm.chat_json(model, prompt("master_correct.md"), user, temperature=0.4)
    except llm.OllamaError as e:
        raise gr.Error(str(e))
    return song_outputs(data)


def normalize(style, lyrics):
    lyrics = normalize_lyrics(lyrics or "")
    return lyrics, ui.lint_html(style, lyrics)


# ---------------------------------------------------------------- Generierung

def generate(mode, title, style, lyrics, language, cot, seed, random_seed, cfg, max_secs, abc,
             model, idea, style_wish, transcript, lyrics_mode, source_file, source_meta):
    errors, _ = lint(style, lyrics)
    if errors:
        raise gr.Error(t("err.fix_first") + "\n" + "\n".join(errors[:5]))
    if mode == MODE_REMAKE:
        if not (abc or "").strip():
            raise gr.Error(t("err.remake_no_abc"))
        cot, use_abc = "melody", abc
    else:
        use_abc = None
    seed = random.randrange(0, 2**31) if random_seed else int(seed or 0)
    cfg_scale = None if cfg is None or abs(float(cfg) - 1.0) < 1e-9 else float(cfg)

    llm.unload()  # Ollama-Modell aus dem VRAM werfen – YuE2 braucht ~22 GB
    box = {}

    def work():
        try:
            box["result"] = ENGINE.generate(style, lyrics, cot=cot, seed=seed, abc=use_abc,
                                            cfg_scale=cfg_scale, max_seconds=int(max_secs),
                                            expected_seconds=estimate_seconds(lyrics, style))
        except BaseException as e:  # an den UI-Thread weiterreichen
            box["error"] = e

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while worker.is_alive():
        yield gr.update(), ui.progress_html(ENGINE.progress), gr.update(), seed
        worker.join(timeout=1.0)

    if "error" in box:
        e = box["error"]
        if isinstance(e, Cancelled):
            yield None, ui.notice("warn", t("gen.cancelled")), None, seed
            return
        yield gr.update(), ui.notice("err", t("gen.failed"), ui.esc(e)), gr.update(), seed
        raise gr.Error(f"{t('gen.failed')}: {e}")

    audio, meta = box["result"]
    preview = TEMP_DIR / f"preview_{int(time.time())}.flac"
    sf.write(preview, audio, SAMPLE_RATE, subtype="PCM_16")
    info = {
        **meta, "title": title, "language": language, "style": style, "lyrics": lyrics,
        "mode": mode, "created": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "llm_model": model,
        "idea": idea if mode == MODE_NEW else style_wish,
    }
    if mode == MODE_REMAKE:
        tags = {k: v for k, v in ((source_meta or {}).get("tags") or {}).items() if k != "cover"}
        info.update(source_file=Path(source_file).name if source_file else "", transcript=transcript,
                    lyrics_mode=lyrics_mode, abc=abc, source_tags=tags)
    result = {"audio": audio, "info": info, "meta": meta, "seed": seed, "title": title}
    yield str(preview), ui.result_html(title, meta, seed), result, seed


def cancel():
    ENGINE.cancel()
    return ui.notice("warn", t("cancel.t"), t("cancel.b"))


def unload_all():
    llm.unload()
    if not ENGINE.unload():
        return ui.notice("warn", t("unload.busy_t"), t("unload.busy_b"))
    return ui.notice("ok", t("unload.ok_t"), t("unload.ok_b"))


# ---------------------------------------------------------------- Speichern

def save(result, name, fmt, out_dir, overwrite):
    if not result:
        raise gr.Error(t("err.no_song"))
    name = sanitize_filename(name or result["info"].get("title"))
    info = {**result["info"], "title": name}
    try:
        audio_file, text_file = save_song(result["audio"], SAMPLE_RATE, name, fmt,
                                          out_dir or path("output_dir"), info, overwrite=overwrite)
    except (FileExistsError, RuntimeError, OSError) as e:
        return ui.notice("err", t("save.failed"), ui.esc(e))
    return ui.notice("ok", t("save.ok", name=name),
                     f"<code>{ui.esc(audio_file)}</code><br><code>{ui.esc(text_file)}</code>")


# ---------------------------------------------------------------- UI

def build_ui():
    models, model_value, _, _ = model_choices()
    registry = []  # (Komponente, {Eigenschaft: i18n-Schlüssel oder Funktion}) – wird beim Sprachwechsel neu befüllt

    def tr(component, **spec):
        registry.append((component, spec))
        return component

    with gr.Blocks(title="YuE2 Studio", theme=ui.THEME, css=ui.CSS, js=ui.FORCE_DARK_JS,
                   head=ui.head_html(i18n.get_lang())) as demo:
        # --- Startdialog: Sprache wählen (nur beim allerersten Start)
        # Unsichtbar gebaut; on_load blendet ihn nur ein, solange noch keine Sprache gewählt wurde (kein Aufblitzen).
        with gr.Column(visible=False, elem_id="lang-modal") as modal:
            with gr.Column(elem_classes="modal-card"):
                gr.HTML(ui.modal_html(), elem_classes="html-slot")
                with gr.Row():
                    pick_de = gr.Button("Deutsch", variant="primary", elem_classes="lang-btn")
                    pick_en = gr.Button("English", variant="primary", elem_classes="lang-btn")

        # --- Kopfbereich mit Sprachumschalter oben rechts
        with gr.Row(elem_id="top-row"):
            hero = gr.HTML(hero_html(), elem_classes="html-slot")
            lang_switch = gr.Radio([("DE", "de"), ("EN", "en")], value=i18n.get_lang(), show_label=False,
                                   container=False, elem_id="lang-switch", elem_classes="seg", scale=0, min_width=110)
        language_state = gr.State("")
        src_duration = gr.State(0)
        result_state = gr.State(None)
        source_info = gr.State(None)  # Tags des geladenen Original-Songs (Remake)

        with gr.Row(equal_height=False):
            # ================= Linke Spalte: Komposition =================
            with gr.Column(scale=7, min_width=460):
                with gr.Column(elem_classes="card"):
                    tr(gr.HTML(ui.step(1, "step1.title", "step1.sub")),
                       value=lambda: ui.step(1, "step1.title", "step1.sub"))
                    with gr.Row():
                        mode = tr(gr.Radio(mode_choices(), value=MODE_NEW, show_label=False, container=False,
                                           elem_id="mode-switch", elem_classes="seg", scale=5), choices=mode_choices)
                        with gr.Column(scale=3, min_width=220):
                            with gr.Row():
                                model_dd = tr(gr.Dropdown(models, value=model_value, label=t("model.label"),
                                                          scale=5, min_width=160, elem_id="model-dd"),
                                              label="model.label")
                                refresh_btn = gr.Button("↻", scale=0, min_width=46, elem_classes="icon-btn")

                    # --- Neuer Song
                    with gr.Column(visible=True) as new_group:
                        idea = tr(gr.Textbox(label=t("idea.label"), lines=4, elem_id="idea-box",
                                             placeholder=t("idea.ph")), label="idea.label", placeholder="idea.ph")
                        with gr.Row():
                            language = tr(gr.Dropdown(lang_choices(), value="auto", label=t("language.label")),
                                          choices=lang_choices, label="language.label")
                            target_secs = tr(gr.Slider(60, 480, value=180, step=15, label=t("target.label")),
                                             label="target.label")
                        create_new_btn = tr(gr.Button(t("create.btn"), variant="primary", elem_classes="create-btn"),
                                            value="create.btn")

                    # --- Remake
                    with gr.Column(visible=False) as remake_group:
                        source = tr(gr.Audio(label=t("source.label"), type="filepath", sources=["upload"],
                                             waveform_options=ui.WAVEFORM), label="source.label")
                        track_box = gr.HTML(elem_classes="html-slot")
                        analyze_btn = tr(gr.Button(t("analyze.btn"), variant="secondary", elem_classes="ghost-btn"),
                                         value="analyze.btn")
                        remake_status = gr.HTML(elem_classes="html-slot")
                        transcript = tr(gr.Textbox(label=t("transcript.label"), lines=7), label="transcript.label")
                        with gr.Accordion(t("abc.acc"), open=False) as abc_acc:
                            abc = gr.Textbox(lines=12, show_label=False)
                        tr(abc_acc, label="abc.acc")
                        lyrics_mode = tr(gr.Radio(lmode_choices(), value="keep", label=t("lmode.label"),
                                                  elem_classes="seg"), choices=lmode_choices, label="lmode.label")
                        with gr.Row():
                            style_wish = tr(gr.Textbox(label=t("wish.label"), lines=2, scale=3,
                                                       placeholder=t("wish.ph")), label="wish.label", placeholder="wish.ph")
                            remake_lang = tr(gr.Dropdown(lang_choices(), value="auto", scale=1, min_width=150,
                                                         label=t("rlang.label")), choices=lang_choices, label="rlang.label")
                        create_remake_btn = tr(gr.Button(t("create.btn"), variant="primary", elem_classes="create-btn"),
                                               value="create.btn")

                with gr.Column(elem_classes="card"):
                    tr(gr.HTML(ui.step(2, "step2.title", "step2.sub")),
                       value=lambda: ui.step(2, "step2.title", "step2.sub"))
                    title = tr(gr.Textbox(label=t("title.label"), placeholder=t("title.ph")),
                               label="title.label", placeholder="title.ph")
                    style = tr(gr.Textbox(label=t("style.label"), lines=2, elem_id="style-box", placeholder=t("style.ph")),
                               label="style.label", placeholder="style.ph")
                    lyrics = tr(gr.Textbox(label=t("lyrics.label"), lines=20, elem_id="lyrics-box",
                                           placeholder="[Verse]\n…\n\n[Chorus]\n…"), label="lyrics.label")
                    lint_box = gr.HTML(elem_classes="html-slot")
                    with gr.Row():
                        check_btn = tr(gr.Button(t("check.btn"), elem_classes="ghost-btn"), value="check.btn")
                        normalize_btn = tr(gr.Button(t("normalize.btn"), elem_classes="ghost-btn"), value="normalize.btn")
                    with gr.Row(equal_height=True):
                        correction = tr(gr.Textbox(label=t("correction.label"), scale=4, placeholder=t("correction.ph")),
                                        label="correction.label", placeholder="correction.ph")
                        correct_btn = tr(gr.Button(t("correct.btn"), scale=1, min_width=170, variant="secondary"),
                                         value="correct.btn")

            # ================= Rechte Spalte: Studio =================
            with gr.Column(scale=5, min_width=380):
                with gr.Column(elem_classes="card"):
                    tr(gr.HTML(ui.step(3, "step3.title", "step3.sub")),
                       value=lambda: ui.step(3, "step3.title", "step3.sub"))
                    gen_btn = tr(gr.Button(t("gen.btn"), variant="primary", size="lg", elem_id="gen-btn"),
                                 value="gen.btn")
                    with gr.Row():
                        cancel_btn = tr(gr.Button(t("cancel.btn"), variant="stop", size="sm"), value="cancel.btn")
                        unload_btn = tr(gr.Button(t("unload.btn"), size="sm", elem_classes="ghost-btn"),
                                        value="unload.btn")
                    gen_status = gr.HTML(ui.idle_html(), elem_classes="html-slot")
                    player = tr(gr.Audio(label=t("player.label"), type="filepath", interactive=False,
                                         waveform_options=ui.WAVEFORM), label="player.label")
                    with gr.Accordion(t("adv.acc"), open=False) as adv_acc:
                        cot = tr(gr.Dropdown(cot_choices(), value="full", label=t("cot.label")),
                                 choices=cot_choices, label="cot.label")
                        max_secs = tr(gr.Slider(30, 600, value=180 if gpu_info.current().low_vram else 300, step=10,
                                                label=t("max.label")), label="max.label")
                        with gr.Row():
                            seed = tr(gr.Number(value=831001, precision=0, label=t("seed.label"), min_width=120),
                                      label="seed.label")
                            cfg = tr(gr.Number(value=1.0, label=t("cfg.label"), minimum=0, maximum=20, min_width=120),
                                     label="cfg.label")
                        random_seed = tr(gr.Checkbox(value=True, label=t("random.label")), label="random.label")
                    tr(adv_acc, label="adv.acc")

                with gr.Column(elem_classes="card"):
                    tr(gr.HTML(ui.step(4, "step4.title", "step4.sub")),
                       value=lambda: ui.step(4, "step4.title", "step4.sub"))
                    save_name = tr(gr.Textbox(label=t("savename.label"), placeholder=t("savename.ph")),
                                   label="savename.label", placeholder="savename.ph")
                    save_fmt = tr(gr.Radio(["MP3", "FLAC"], value="MP3", label=t("fmt.label"), elem_classes="seg"),
                                  label="fmt.label")
                    save_dir = tr(gr.Textbox(value=str(path("output_dir")), label=t("savedir.label")),
                                  label="savedir.label")
                    overwrite = tr(gr.Checkbox(value=False, label=t("overwrite.label")), label="overwrite.label")
                    save_btn = tr(gr.Button(t("save.btn"), variant="primary", elem_classes="create-btn"),
                                  value="save.btn")
                    save_box = gr.HTML(elem_classes="html-slot")

        # --- Sprache anwenden: alle registrierten Texte plus dynamische Inhalte neu erzeugen
        translated = [component for component, _ in registry]
        dynamic = [hero, lint_box, gen_status, remake_status, save_box, track_box]

        def texts(style_text, lyrics_text, result, source):
            updates = []
            for _, spec in registry:
                updates.append(gr.update(**{prop: (src() if callable(src) else t(src)) for prop, src in spec.items()}))
            status = ui.result_html(result["title"], result["meta"], result["seed"]) if result else ui.idle_html()
            track = ui.track_card(source["tags"], source["name"]) if source else ""
            return updates + [hero_html(), ui.lint_html(style_text, lyrics_text), status, "", "", track]

        def switch_language(lang, *inputs):
            i18n.set_lang(lang)
            return texts(*inputs)

        def pick_language(lang, *inputs):
            i18n.set_lang(lang)  # speichert die Wahl – der Dialog erscheint nicht wieder
            return [gr.update(visible=False), gr.update(value=lang)] + texts(*inputs)

        def on_load(*inputs):
            # Neu laden der Seite: aktuelle Sprache anwenden und Dialog nur beim ersten Start zeigen.
            return [gr.update(visible=i18n.is_first_start()), gr.update(value=i18n.get_lang())] + texts(*inputs)

        text_inputs = [style, lyrics, result_state, source_info]
        demo.load(on_load, inputs=text_inputs, outputs=[modal, lang_switch] + translated + dynamic,
                  show_progress="hidden")
        # .input statt .change: reagiert nur auf Klicks des Nutzers, nicht auf das programmatische Setzen beim Laden.
        lang_switch.input(switch_language, inputs=[lang_switch] + text_inputs, outputs=translated + dynamic,
                          show_progress="hidden")
        # Gradios eigene Texte (z. B. Upload-Hinweis) folgen der Sprache beim nächsten Laden (siehe ui.head_html).
        # Ohne laufende Arbeit (keine Eingaben, kein Song) kurz neu laden, damit auch Gradios Texte sofort wechseln.
        remember = """(l) => {
          try { localStorage.setItem('yue2_lang', l); } catch (e) {}
          const typed = ['#idea-box', '#style-box', '#lyrics-box'].some(
            (id) => (document.querySelector(id + ' textarea') || {}).value?.trim());
          // Geladener Original-Song (.track), generierter Song (.result) oder laufende Generierung zählen als Arbeit.
          const busy = typed || document.querySelector('.track, .result, .prog:not(.idle)');
          if (!busy) setTimeout(() => window.location.reload(), 700);
        }"""
        lang_switch.input(None, inputs=lang_switch, js=remember)
        picked = [modal, lang_switch] + translated + dynamic
        for button, code in ((pick_de, "de"), (pick_en, "en")):
            button.click(lambda *inputs, code=code: pick_language(code, *inputs), inputs=text_inputs,
                         outputs=picked, show_progress="hidden")
            button.click(None, js=f"() => {{ try {{ localStorage.setItem('yue2_lang', '{code}'); }} catch (e) {{}} }}")

        # --- Events
        refresh_btn.click(refresh_models, outputs=[model_dd, hero])
        mode.change(lambda m: (gr.update(visible=m == MODE_NEW), gr.update(visible=m == MODE_REMAKE)),
                    inputs=mode, outputs=[new_group, remake_group])
        song_out = [title, style, lyrics, language_state, lint_box, save_name, max_secs]
        create_new_btn.click(create_new, inputs=[idea, language, target_secs, model_dd], outputs=song_out)
        source.change(load_source_info, inputs=source, outputs=[track_box, source_info], show_progress="hidden")
        analyze_btn.click(analyze_remake, inputs=source,
                          outputs=[abc, transcript, remake_status, max_secs, src_duration], show_progress="hidden")
        create_remake_btn.click(create_remake,
                                inputs=[transcript, lyrics_mode, remake_lang, style_wish, abc, model_dd, src_duration],
                                outputs=song_out)
        check_btn.click(check, inputs=[style, lyrics], outputs=lint_box)
        normalize_btn.click(normalize, inputs=[style, lyrics], outputs=[lyrics, lint_box])
        correct_btn.click(correct, inputs=[title, style, lyrics, correction, model_dd], outputs=song_out)
        title.change(lambda value: value, inputs=title, outputs=save_name)
        gen_event = gen_btn.click(generate,
                                  inputs=[mode, title, style, lyrics, language_state, cot, seed, random_seed, cfg,
                                          max_secs, abc, model_dd, idea, style_wish, transcript, lyrics_mode, source,
                                          source_info],
                                  outputs=[player, gen_status, result_state, seed], show_progress="hidden")
        # ENGINE.cancel() stoppt YuE2 im Hintergrund-Thread, cancels= beendet den UI-Generator.
        cancel_btn.click(cancel, outputs=gen_status, cancels=[gen_event], queue=False)
        unload_btn.click(unload_all, outputs=gen_status)
        save_btn.click(save, inputs=[result_state, save_name, save_fmt, save_dir, overwrite], outputs=save_box)
    return demo


if __name__ == "__main__":
    # Ein (minimales) I18n-Objekt lässt Gradio seine eigenen Texte nach dem Laden mit navigator.language
    # neu initialisieren – das head-Skript hat sie zu diesem Zeitpunkt bereits auf die gewählte Sprache gesetzt.
    gradio_i18n = gr.I18n(de={"app.name": "YuE2 Studio"}, en={"app.name": "YuE2 Studio"})
    build_ui().queue().launch(server_name="127.0.0.1", server_port=CONFIG["server_port"],
                              inbrowser=True, allowed_paths=[str(TEMP_DIR)], i18n=gradio_i18n)
