"""Optik der App: dunkles „Studio“-Theme, CSS und HTML-Bausteine."""
import html

import gradio as gr

from i18n import STRINGS, t
from lyrics_tools import estimate_seconds, fmt_duration, lint, parse_sections
from yue_engine import PHASES

VIOLET, CYAN = "#8b5cf6", "#22d3ee"
GRADIENT = "linear-gradient(135deg, #7c3aed 0%, #4f46e5 45%, #06b6d4 100%)"
GRADIENT_HOVER = "linear-gradient(135deg, #8b5cf6 0%, #6366f1 45%, #22d3ee 100%)"
BACKDROP = ("radial-gradient(1100px 620px at 8% -12%, rgba(124,58,237,.30), transparent 62%), "
            "radial-gradient(900px 560px at 100% 0%, rgba(6,182,212,.20), transparent 60%), "
            "radial-gradient(800px 600px at 50% 120%, rgba(79,70,229,.18), transparent 60%), #07070d")

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.violet,
    secondary_hue=gr.themes.colors.cyan,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "Consolas", "monospace"],
    radius_size=gr.themes.sizes.radius_lg,
).set(
    body_background_fill=BACKDROP, body_background_fill_dark=BACKDROP,
    body_text_color="#e8e7f5", body_text_color_dark="#e8e7f5",
    body_text_color_subdued="#9b99bd", body_text_color_subdued_dark="#9b99bd",
    background_fill_primary="#0d0d18", background_fill_primary_dark="#0d0d18",
    background_fill_secondary="#12121f", background_fill_secondary_dark="#12121f",
    border_color_primary="rgba(255,255,255,0.09)", border_color_primary_dark="rgba(255,255,255,0.09)",
    border_color_accent=VIOLET, border_color_accent_dark=VIOLET,
    color_accent=VIOLET, color_accent_soft="rgba(139,92,246,0.18)", color_accent_soft_dark="rgba(139,92,246,0.18)",
    block_background_fill="transparent", block_background_fill_dark="transparent",
    block_border_width="0px", block_shadow="none", block_shadow_dark="none", block_padding="6px 2px",
    block_label_background_fill="transparent", block_label_background_fill_dark="transparent",
    block_label_text_color="#a9a6d6", block_label_text_color_dark="#a9a6d6", block_label_border_width="0px",
    block_title_text_color="#a9a6d6", block_title_text_color_dark="#a9a6d6", block_title_text_weight="600",
    panel_background_fill="transparent", panel_background_fill_dark="transparent",
    panel_border_color="rgba(255,255,255,0.08)", panel_border_color_dark="rgba(255,255,255,0.08)",
    input_background_fill="rgba(6,6,14,0.72)", input_background_fill_dark="rgba(6,6,14,0.72)",
    input_background_fill_focus="rgba(10,10,22,0.9)", input_background_fill_focus_dark="rgba(10,10,22,0.9)",
    input_border_color="rgba(255,255,255,0.10)", input_border_color_dark="rgba(255,255,255,0.10)",
    input_border_color_focus=VIOLET, input_border_color_focus_dark=VIOLET,
    input_shadow_focus="0 0 0 3px rgba(139,92,246,0.25)", input_shadow_focus_dark="0 0 0 3px rgba(139,92,246,0.25)",
    button_primary_background_fill=GRADIENT, button_primary_background_fill_dark=GRADIENT,
    button_primary_background_fill_hover=GRADIENT_HOVER, button_primary_background_fill_hover_dark=GRADIENT_HOVER,
    button_primary_text_color="#ffffff", button_primary_text_color_dark="#ffffff",
    button_primary_border_color="transparent", button_primary_border_color_dark="transparent",
    button_primary_shadow="0 8px 30px -8px rgba(124,58,237,0.65)",
    button_primary_shadow_hover="0 10px 38px -6px rgba(34,211,238,0.55)",
    button_secondary_background_fill="rgba(255,255,255,0.05)", button_secondary_background_fill_dark="rgba(255,255,255,0.05)",
    button_secondary_background_fill_hover="rgba(255,255,255,0.10)",
    button_secondary_background_fill_hover_dark="rgba(255,255,255,0.10)",
    button_secondary_border_color="rgba(255,255,255,0.10)", button_secondary_border_color_dark="rgba(255,255,255,0.10)",
    button_secondary_text_color="#e8e7f5", button_secondary_text_color_dark="#e8e7f5",
    button_cancel_background_fill="rgba(244,63,94,0.12)", button_cancel_background_fill_dark="rgba(244,63,94,0.12)",
    button_cancel_background_fill_hover="rgba(244,63,94,0.22)",
    button_cancel_background_fill_hover_dark="rgba(244,63,94,0.22)",
    button_cancel_text_color="#fda4af", button_cancel_text_color_dark="#fda4af",
    button_cancel_border_color="rgba(244,63,94,0.35)", button_cancel_border_color_dark="rgba(244,63,94,0.35)",
    button_large_radius="14px",
    slider_color=VIOLET, slider_color_dark=VIOLET,
    checkbox_background_color_selected=VIOLET, checkbox_background_color_selected_dark=VIOLET,
    checkbox_border_color_selected=VIOLET, checkbox_border_color_selected_dark=VIOLET,
    layout_gap="14px",
)

# Die App ist auf das dunkle Studio-Design ausgelegt – Dunkelmodus erzwingen.
FORCE_DARK_JS = """
() => {
  const url = new URL(window.location);
  if (url.searchParams.get('__theme') !== 'dark') {
    url.searchParams.set('__theme', 'dark');
    window.location.replace(url.href);
  }
}
"""

CSS = """
body { background-attachment: fixed !important; }
.gradio-container { max-width: 1480px !important; margin: 0 auto !important; padding: 26px 26px 48px !important;
  box-sizing: border-box !important; }
footer { display: none !important; }

/* ---------- Kopfbereich ---------- */
.hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  padding: 22px 26px; border-radius: 24px; position: relative; overflow: hidden;
  background: linear-gradient(120deg, rgba(124,58,237,.22), rgba(6,182,212,.10) 60%, rgba(255,255,255,.02));
  border: 1px solid rgba(255,255,255,.09); box-shadow: 0 20px 60px -30px rgba(124,58,237,.6); }
.hero::after { content: ""; position: absolute; inset: -40% -10% auto auto; width: 420px; height: 420px;
  background: radial-gradient(circle, rgba(34,211,238,.18), transparent 65%); pointer-events: none; }
.hero-left { display: flex; align-items: center; gap: 18px; z-index: 1; }
.logo { width: 58px; height: 58px; border-radius: 18px; background: """ + GRADIENT + """;
  display: flex; align-items: flex-end; justify-content: center; gap: 4px; padding: 13px 0;
  box-shadow: 0 10px 30px -8px rgba(124,58,237,.8); }
.logo i { display: block; width: 5px; border-radius: 3px; background: rgba(255,255,255,.95);
  animation: eq 1.1s ease-in-out infinite; }
.logo i:nth-child(1) { height: 40%; animation-delay: -.2s } .logo i:nth-child(2) { height: 90%; animation-delay: -.5s }
.logo i:nth-child(3) { height: 60%; animation-delay: -.8s } .logo i:nth-child(4) { height: 100%; animation-delay: -.3s }
.logo i:nth-child(5) { height: 50%; animation-delay: -.65s }
@keyframes eq { 0%,100% { transform: scaleY(.45) } 50% { transform: scaleY(1) } }
.logo i { transform-origin: bottom; }
.hero h1 { margin: 0 !important; font-size: 30px !important; font-weight: 800 !important; letter-spacing: -.02em;
  line-height: 1.1 !important; color: #fff !important; }
.hero h1 span { background: linear-gradient(90deg, #c4b5fd, #67e8f9); -webkit-background-clip: text;
  background-clip: text; color: transparent; }
.hero p { margin: 6px 0 0 !important; color: #b9b7da !important; font-size: 14.5px !important; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; z-index: 1; }
.chip { display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px; border-radius: 999px; font-size: 12.5px;
  font-weight: 600; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.10); color: #dcdaf2;
  white-space: nowrap; }
.chip .dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }
.chip.ok .dot { background: #34d399; box-shadow: 0 0 10px #34d399; }
.chip.warn .dot { background: #fbbf24; box-shadow: 0 0 10px #fbbf24; }
.chip.err .dot { background: #fb7185; box-shadow: 0 0 10px #fb7185; }
.chip.accent { background: rgba(139,92,246,.16); border-color: rgba(139,92,246,.35); color: #ddd6fe; }

/* ---------- Karten & Schritte ---------- */
/* Kein backdrop-filter auf Karten: er macht die Karte zum Bezugsrahmen für position:fixed und
   verschiebt dadurch Gradios Dropdown-Listen nach unten. Stattdessen ein deckenderer Hintergrund. */
.card { background: linear-gradient(180deg, rgba(20,20,36,.86), rgba(14,14,26,.86)) !important;
  border: 1px solid rgba(255,255,255,.08) !important;
  border-radius: 22px !important; padding: 20px 22px 22px !important;
  box-shadow: 0 24px 60px -36px rgba(0,0,0,.9); }
.card .form, .card .gr-form { background: transparent !important; border: none !important; box-shadow: none !important;
  gap: 12px !important; }
.card .block { background: transparent !important; }
.card .block:has(> .label-wrap) { overflow: visible !important; }
.step { display: flex; align-items: center; gap: 14px; margin-bottom: 4px; }
.step-num { font-family: var(--font-mono); font-size: 13px; font-weight: 700; color: #fff; width: 38px; height: 38px;
  border-radius: 12px; display: flex; align-items: center; justify-content: center; background: """ + GRADIENT + """;
  box-shadow: 0 6px 20px -6px rgba(124,58,237,.8); flex-shrink: 0; }
.step-title { font-size: 18px; font-weight: 750; color: #fff; letter-spacing: -.01em; }
.step-sub { font-size: 13px; color: #9b99bd; margin-top: 1px; }
.card [data-testid="block-info"] { font-size: 11.5px !important; font-weight: 650 !important;
  letter-spacing: .07em; text-transform: uppercase; color: #a9a6d6 !important; }
.card textarea, .card input[type=text], .card input[type=number] { font-size: 14.5px !important; }
#lyrics-box textarea { font-family: var(--font-mono) !important; font-size: 13.5px !important; line-height: 1.7 !important; }
#style-box textarea { font-size: 14px !important; line-height: 1.55 !important; }
#idea-box textarea { font-size: 16px !important; line-height: 1.6 !important; }

/* ---------- Segment-Schalter (Modus, Format) ---------- */
.seg .wrap { display: grid !important; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 6px !important;
  background: rgba(0,0,0,.35); padding: 6px; border-radius: 16px; border: 1px solid rgba(255,255,255,.08); }
.seg label { justify-content: center !important; border-radius: 12px !important; padding: 11px 14px !important;
  background: transparent !important; border: 1px solid transparent !important; box-shadow: none !important;
  font-weight: 650 !important; color: #b9b7da !important; cursor: pointer; transition: all .18s ease; }
.seg label:hover { background: rgba(255,255,255,.05) !important; color: #fff !important; }
.seg label.selected { background: """ + GRADIENT + """ !important; color: #fff !important;
  box-shadow: 0 8px 24px -10px rgba(124,58,237,.9) !important; }
.seg input[type=radio] { display: none !important; }
#mode-switch label { font-size: 15px !important; padding: 14px !important; }

/* ---------- Buttons ---------- */
#gen-btn { min-height: 60px; font-size: 17px !important; font-weight: 750 !important; letter-spacing: .01em;
  background-size: 200% 200% !important; animation: shine 6s ease infinite; }
@keyframes shine { 0%,100% { background-position: 0% 50% } 50% { background-position: 100% 50% } }
.create-btn { min-height: 52px; font-size: 15.5px !important; font-weight: 700 !important; }
.ghost-btn { font-weight: 600 !important; }
/* Lange Ollama-Modellnamen nicht mehrfach umbrechen: Liste und Einträge breiter als das Feld */
#model-dd ul.options { min-width: 380px !important; }
#model-dd ul.options li { width: auto !important; }
.icon-btn { min-width: 46px !important; max-width: 46px !important; font-size: 18px !important; }

/* ---------- Fortschritt ---------- */
.prog { padding: 16px 18px; border-radius: 18px; background: rgba(0,0,0,.30); border: 1px solid rgba(255,255,255,.08); }
.prog-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
.prog-stage { font-weight: 700; color: #fff; font-size: 15px; }
.prog-pct { font-family: var(--font-mono); font-weight: 700; color: #c4b5fd; font-size: 15px; }
.prog-bar { height: 10px; border-radius: 999px; background: rgba(255,255,255,.07); overflow: hidden; }
.prog-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #7c3aed, #6366f1, #22d3ee, #7c3aed);
  background-size: 300% 100%; animation: flow 2.2s linear infinite; transition: width .8s ease;
  box-shadow: 0 0 18px rgba(139,92,246,.7); }
@keyframes flow { from { background-position: 0% 0 } to { background-position: 300% 0 } }
.prog-steps { display: flex; gap: 6px; margin: 14px 0 12px; flex-wrap: wrap; }
.ps { flex: 1; text-align: center; font-size: 11.5px; font-weight: 650; padding: 6px 4px; border-radius: 10px;
  color: #77759a; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.05); min-width: 62px; }
.ps.done { color: #a7f3d0; background: rgba(52,211,153,.10); border-color: rgba(52,211,153,.25); }
.ps.active { color: #fff; background: rgba(139,92,246,.22); border-color: rgba(139,92,246,.55);
  animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(139,92,246,.0) } 50% { box-shadow: 0 0 0 4px rgba(139,92,246,.18) } }
.prog.idle { display: flex; gap: 14px; align-items: center; color: #9b99bd; font-size: 14px; }
.prog.idle .big { font-size: 26px; }

/* ---------- Ergebnis & Hinweise ---------- */
.result { padding: 18px; border-radius: 18px; border: 1px solid rgba(52,211,153,.28);
  background: linear-gradient(135deg, rgba(52,211,153,.10), rgba(34,211,238,.06)); }
.result-head { display: flex; gap: 14px; align-items: center; margin-bottom: 12px; }
.result-icon { width: 46px; height: 46px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
  font-size: 22px; background: """ + GRADIENT + """; color: #fff; flex-shrink: 0; }
.result-title { font-size: 18px; font-weight: 750; color: #fff; }
.result-sub { font-size: 13px; color: #a7f3d0; }
.notice { padding: 13px 16px; border-radius: 14px; font-size: 14px; line-height: 1.5; border: 1px solid; }
.notice b { display: block; margin-bottom: 2px; }
.notice.ok { background: rgba(52,211,153,.09); border-color: rgba(52,211,153,.28); color: #bbf7d0; }
.notice.info { background: rgba(139,92,246,.10); border-color: rgba(139,92,246,.30); color: #ddd6fe; }
.notice.warn { background: rgba(251,191,36,.09); border-color: rgba(251,191,36,.30); color: #fde68a; }
.notice.err { background: rgba(244,63,94,.10); border-color: rgba(244,63,94,.32); color: #fecdd3; }
.notice code { font-family: var(--font-mono); font-size: 12.5px; background: rgba(0,0,0,.3); padding: 2px 6px;
  border-radius: 6px; word-break: break-all; }
.lint { display: flex; flex-direction: column; gap: 8px; }
.lint-row { display: flex; gap: 8px; flex-wrap: wrap; }
.lint-item { display: flex; gap: 10px; align-items: flex-start; font-size: 13.5px; padding: 9px 12px; border-radius: 12px; }
.lint-item.err { background: rgba(244,63,94,.10); color: #fecdd3; border: 1px solid rgba(244,63,94,.25); }
.lint-item.warn { background: rgba(251,191,36,.08); color: #fde68a; border: 1px solid rgba(251,191,36,.22); }
.lint-item.ok { background: rgba(52,211,153,.08); color: #bbf7d0; border: 1px solid rgba(52,211,153,.22); }
.block.html-slot, .block.html-slot > .html-container { padding: 0 !important; }
.html-slot .pending, .html-slot.pending, .prose.pending { opacity: 1 !important; }

/* ---------- Diverses ---------- */
.card .label-wrap { font-weight: 650; }
.card audio, .card .waveform-container { border-radius: 14px; }
.card ::part(scroll) { scrollbar-width: none !important; }  /* WaveSurfer (Shadow-DOM) ohne Scrollleiste */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: rgba(139,92,246,.35); border-radius: 10px; }
::-webkit-scrollbar-track { background: transparent; }
/* ---------- Sprachumschalter & Startdialog ---------- */
.hero-chips { margin-top: 12px; }
#top-row { position: relative; }
#lang-switch { position: absolute !important; top: 18px; right: 22px; z-index: 20; width: auto !important;
  min-width: 0 !important; flex: none !important; }
#lang-switch .wrap { padding: 4px !important; gap: 4px !important; border-radius: 12px !important; }
#lang-switch label { padding: 7px 14px !important; font-size: 13px !important; border-radius: 9px !important; }
#lang-modal { position: fixed !important; inset: 0; z-index: 1000; background: rgba(4,4,10,.74);
  backdrop-filter: blur(10px); justify-content: center; align-items: center; padding: 20px; margin: 0 !important; }
#lang-modal .modal-card { width: 100%; max-width: 500px; flex-grow: 0 !important; text-align: center;
  background: rgba(16,16,30,.96) !important; border: 1px solid rgba(255,255,255,.10) !important; border-radius: 26px !important;
  padding: 30px 28px 28px !important; box-shadow: 0 30px 90px -20px rgba(124,58,237,.55); }
.modal-head .logo { margin: 0 auto 16px; }
.modal-head h2 { margin: 0 !important; font-size: 24px !important; font-weight: 800 !important; color: #fff !important; }
.modal-head p { margin: 6px 0 10px !important; color: #b9b7da !important; }
.modal-head .modal-en { margin-top: 14px !important; font-size: 19px !important; color: #c4b5fd !important; }
.lang-btn { min-height: 62px; font-size: 17px !important; font-weight: 700 !important; }
@media (max-width: 900px) { #lang-switch { position: static !important; margin: 8px 0 0 auto; } }
@media (max-width: 900px) { .gradio-container { padding: 14px !important; } .hero h1 { font-size: 24px !important; } }
"""

WAVEFORM = gr.WaveformOptions(waveform_color="#4b4a6e", waveform_progress_color=VIOLET,
                              show_recording_waveform=True, trim_region_color="rgba(34,211,238,0.25)",
                              sample_rate=48000)


def esc(text):
    return html.escape(str(text if text is not None else ""))


def chip(text, kind=""):
    dot = '<span class="dot"></span>' if kind in {"ok", "warn", "err"} else ""
    return f'<span class="chip {kind}">{dot}{esc(text)}</span>'


def hero(ollama_ok, ollama_text, gpu_text, gpu_ok=True):
    return f"""
<div class="hero">
  <div class="hero-left">
    <div class="logo"><i></i><i></i><i></i><i></i><i></i></div>
    <div><h1>YuE2 <span>Studio</span></h1>
      <p>{t("hero.sub")}</p>
      <div class="chips hero-chips">
        {chip(ollama_text, "ok" if ollama_ok else "err")}
        {chip(gpu_text, "ok" if gpu_ok else "warn")}
        {chip(t("chip.yue"), "accent")}
      </div></div>
  </div>
</div>"""


def step(num, title_key, sub_key=""):
    sub = t(sub_key) if sub_key else ""
    return (f'<div class="step"><div class="step-num">{num:02d}</div><div>'
            f'<div class="step-title">{esc(t(title_key))}</div><div class="step-sub">{esc(sub)}</div></div></div>')


def modal_html():
    """Startdialog – bewusst zweisprachig, da noch keine Sprache gewählt ist."""
    de_title, en_title = STRINGS["modal.title"]
    de_sub, en_sub = STRINGS["modal.sub"]
    return f"""
<div class="modal-head">
  <div class="logo"><i></i><i></i><i></i><i></i><i></i></div>
  <h2>{esc(de_title)}</h2>
  <p>{esc(de_sub)}</p>
  <h2 class="modal-en">{esc(en_title)}</h2>
  <p>{esc(en_sub)}</p>
</div>"""


def notice(kind, title, body=""):
    body_html = f"<span>{body}</span>" if body else ""
    return f'<div class="notice {kind}"><b>{esc(title)}</b>{body_html}</div>'


def idle_html():
    return f'<div class="prog idle"><span class="big">🎛️</span><span>{t("idle")}</span></div>'


def progress_html(p):
    keys = [k for k, *_ in PHASES]
    current = keys.index(p.key) if p.key in keys else (len(keys) if p.key == "done" else 0)
    steps = []
    for i, key in enumerate(keys):
        cls = "done" if i < current else "active" if i == current else ""
        steps.append(f'<span class="ps {cls}">{"✓ " if cls == "done" else ""}{esc(t("phase." + key))}</span>')
    meta = []
    if p.abc_tokens:
        meta.append(chip(t("prog.score", n=p.abc_tokens)))
    if p.semantic_tokens:
        meta.append(chip(t("prog.music", s=f"{p.semantic_tokens / 25:.0f}")))
    meta.append(chip(f"⏱ {fmt_duration(p.elapsed)}"))
    pct = max(2.0, p.percent)
    return f"""
<div class="prog">
  <div class="prog-head"><span class="prog-stage">{esc(t("stage." + p.stage))} …</span><span class="prog-pct">{p.percent:.0f} %</span></div>
  <div class="prog-bar"><div class="prog-fill" style="width:{pct:.1f}%"></div></div>
  <div class="prog-steps">{''.join(steps)}</div>
  <div class="chips">{''.join(meta)}</div>
</div>"""


def result_html(title, meta, seed):
    chips = [chip(f"⏱ {fmt_duration(meta['duration'])} min"), chip(f"🎲 Seed {seed}"),
             chip(t("result.render", s=f"{meta['gen_seconds']:.0f}")), chip(f"🧠 cot = {meta['cot']}")]
    truncated = [t("trunc." + k) for k, v in meta["truncated"].items() if v]
    warn = ""
    if truncated:
        warn = ('<div style="margin-top:12px">'
                + notice("warn", t("result.trunc_t"), esc(t("result.trunc_b", parts=", ".join(truncated)))) + "</div>")
    return f"""
<div class="result">
  <div class="result-head"><div class="result-icon">♪</div>
    <div><div class="result-title">{esc(title or t('result.untitled'))}</div>
    <div class="result-sub">{t("result.sub")}</div></div></div>
  <div class="chips">{''.join(chips)}</div>{warn}
</div>"""


def lint_html(style, lyrics):
    if not (style or lyrics):
        return ""
    errors, warnings = lint(style, lyrics)
    sections = parse_sections(lyrics or "")
    lines = sum(len(l) for _, l in sections)
    duration = fmt_duration(estimate_seconds(lyrics or "", style))
    head = (f'<div class="lint-row">{chip(t("lint.duration", d=duration), "accent")}'
            f'{chip(t("lint.sections", n=len(sections)))}{chip(t("lint.lines", n=lines))}</div>')
    items = [f'<div class="lint-item err">❌ <span>{esc(e)}</span></div>' for e in errors]
    items += [f'<div class="lint-item warn">⚠️ <span>{esc(w)}</span></div>' for w in warnings]
    if not items:
        items = [f'<div class="lint-item ok">✅ <span>{esc(t("lint.ok"))}</span></div>']
    return f'<div class="lint">{head}{"".join(items)}</div>'


def head_html(lang):
    """Gradio übersetzt seine eigenen Texte (z. B. „Audio hier ablegen“) anhand von navigator.language.
    Vor dem Start der App auf die gewählte Sprache setzen (zuletzt gewählte Sprache aus localStorage)."""
    return f"""<script>
(function () {{
  try {{
    var l = localStorage.getItem('yue2_lang') || '{lang}';
    Object.defineProperty(navigator, 'language', {{ get: function () {{ return l; }} }});
    Object.defineProperty(navigator, 'languages', {{ get: function () {{ return [l]; }} }});
  }} catch (e) {{}}
}})();
</script>"""
