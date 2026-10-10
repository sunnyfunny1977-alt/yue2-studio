"""Prüfregeln für YuE2-Style und -Lyrics sowie Hilfsfunktionen."""
import re

from i18n import t

ALLOWED_TAGS = ["Intro", "Verse", "Pre-Chorus", "Chorus", "Bridge", "Interlude", "Outro"]
INSTRUMENTAL_TAGS = {"Intro", "Interlude", "Outro"}
# Kalibriert am offiziellen YuE2-Beispiel „tonight-awake“ (44 Zeilen ≈ 203 s):
# eine gesungene Zeile ≈ 2 Takte à 4 Schläge, instrumentale Sektion ≈ 8 s.
DEFAULT_BPM = 105
SECONDS_PER_EMPTY_SECTION = 8

_TAG_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}


def parse_sections(lyrics):
    """Liefert [(tag, [zeilen]), …]; Text vor dem ersten Tag bekommt das Tag None."""
    sections, tag, lines = [], None, []
    for raw in lyrics.replace("\r\n", "\n").split("\n"):
        m = _TAG_RE.match(raw)
        if m:
            if tag is not None or lines:
                sections.append((tag, lines))
            tag, lines = m.group(1).strip(), []
        elif raw.strip():
            lines.append(raw.strip())
    if tag is not None or lines:
        sections.append((tag, lines))
    return sections


def normalize_lyrics(lyrics):
    """Einheitliches Format: Tag-Zeile, Textzeilen, eine Leerzeile zwischen Sektionen."""
    blocks = []
    for tag, lines in parse_sections(lyrics):
        head = [f"[{tag}]"] if tag else []
        blocks.append("\n".join(head + lines))
    return "\n\n".join(blocks).strip()


def style_bpm(style):
    m = re.search(r"\b(\d{2,3})\s*BPM\b", style or "", re.I)
    bpm = int(m.group(1)) if m else DEFAULT_BPM
    return bpm if 40 <= bpm <= 220 else DEFAULT_BPM


def seconds_per_line(style=None):
    return 8 * 60 / style_bpm(style)


def estimate_seconds(lyrics, style=None):
    secs = 0.0
    for _, lines in parse_sections(lyrics):
        secs += len(lines) * seconds_per_line(style) if lines else SECONDS_PER_EMPTY_SECTION
    return int(round(secs))


def target_lines(target_seconds):
    """Ungefähre Zahl gesungener Zeilen für eine Ziel-Länge (mittleres Tempo)."""
    return max(8, int(round((target_seconds - 2 * SECONDS_PER_EMPTY_SECTION) / seconds_per_line())))


def structure_hint(target_seconds):
    """Grobe Strukturvorgabe für den Masterprompt passend zur Ziel-Länge."""
    if target_seconds <= 75:
        return "[Verse] [Chorus]"
    if target_seconds <= 135:
        return "[Intro] [Verse] [Chorus] [Verse] [Chorus]"
    if target_seconds <= 210:
        return "[Intro] [Verse] [Pre-Chorus] [Chorus] [Verse] [Pre-Chorus] [Chorus] [Bridge] [Chorus] [Outro]"
    if target_seconds <= 300:
        return ("[Intro] [Verse] [Pre-Chorus] [Chorus] [Verse] [Pre-Chorus] [Chorus] [Interlude] "
                "[Bridge] [Chorus] [Chorus] [Outro]")
    return ("[Intro] [Verse] [Pre-Chorus] [Chorus] [Verse] [Pre-Chorus] [Chorus] [Interlude] "
            "[Verse] [Bridge] [Chorus] [Chorus] [Outro]")


def lint(style, lyrics):
    """Gibt (fehler, hinweise) als Listen von Meldungen in der Oberflächensprache zurück."""
    errors, warnings = [], []
    style, lyrics = (style or "").strip(), (lyrics or "").strip()

    # --- Style ---
    if not style:
        errors.append(t("lint.style_empty"))
    else:
        if "\n" in style:
            errors.append(t("lint.style_multiline"))
        words = len(style.replace(",", " ").split())
        if words < 6:
            warnings.append(t("lint.style_short", n=words))
        if words > 45:
            warnings.append(t("lint.style_long", n=words))
        if not re.search(r"\b\d{2,3}\s*BPM\b", style, re.I):
            warnings.append(t("lint.no_bpm"))
        if not re.search(r"vocal|voice|singer|rap|choir|instrumental", style, re.I):
            warnings.append(t("lint.no_voice"))
        if "[" in style or "]" in style:
            errors.append(t("lint.style_tags"))

    # --- Lyrics ---
    if not lyrics:
        errors.append(t("lint.lyrics_empty"))
        return errors, warnings
    sections = parse_sections(lyrics)
    if sections and sections[0][0] is None:
        errors.append(t("lint.text_before_tag"))
    for i, (tag, lines) in enumerate(sections, 1):
        if tag is None:
            continue
        if tag not in ALLOWED_TAGS:
            if re.sub(r"\s*\d+$", "", tag) in ALLOWED_TAGS:
                errors.append(t("lint.numbered", i=i, tag=tag))
            else:
                errors.append(t("lint.unknown", i=i, tag=tag, allowed=", ".join(f"[{a}]" for a in ALLOWED_TAGS)))
        if not lines and tag not in INSTRUMENTAL_TAGS:
            errors.append(t("lint.empty_section", i=i, tag=tag))
        if lines and len(lines) < 2:
            warnings.append(t("lint.one_line", i=i, tag=tag))
        if len(lines) > 12:
            warnings.append(t("lint.many_lines", i=i, tag=tag, n=len(lines)))
        for line in lines:
            if re.search(r"[()\{\}]|\bx\s?\d\b|\*", line):
                errors.append(t("lint.direction", i=i, line=line))
            elif len(line) > 80:
                warnings.append(t("lint.long_line", i=i, n=len(line), line=line[:40]))
    if not any(lines for _, lines in sections):
        errors.append(t("lint.no_sung"))
    if not any(tag == "Chorus" for tag, _ in sections):
        warnings.append(t("lint.no_chorus"))
    return errors, warnings


def issues_text(style, lyrics):
    """Kompakte Problemliste für den Korrektur-Prompt."""
    errors, warnings = lint(style, lyrics)
    return "\n".join(f"- {m}" for m in errors + warnings) or "- none"


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", (name or "").strip())
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = "Song"
    if name.split(".")[0].upper() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:120]


def fmt_duration(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"
