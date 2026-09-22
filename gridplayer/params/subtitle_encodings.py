"""The character sets a text subtitle file can be read as.

Transcribed from the table libsubsdec carries itself, in its order, so that
everything offered here is something the decoder will actually take.

Naming one of these is a fallback rather than an override: VLC reads the
file as UTF-8 wherever it is valid UTF-8, and only reaches for the named
set when it is not. A file that was already UTF-8 comes out the same either
way. None of this reaches ASS or SSA, which libass reads on its own.
"""

# what VLC does when nothing is named: UTF-8 where the file is UTF-8,
# Windows-1252 everywhere else
DEFAULT_ENCODING = ""

# VLC offers a "system" entry as well, which reads the file as the locale's
# own character set. It is left out on purpose: on a UTF-8 locale that is
# the one set already tried, so a file that is not UTF-8 converts to nothing
# and the subtitle is dropped without a word -- worse than showing it wrong,
# and nothing it would have served is out of reach of naming the set here.
SUBTITLE_ENCODINGS = {
    "UTF-8": "Universal (UTF-8)",
    "UTF-16": "Universal (UTF-16)",
    "UTF-16BE": "Universal (big endian UTF-16)",
    "UTF-16LE": "Universal (little endian UTF-16)",
    "GB18030": "Universal, Chinese (GB18030)",
    "ISO-8859-15": "Western European (Latin-9)",
    "Windows-1252": "Western European (Windows-1252)",
    "IBM850": "Western European (IBM 00850)",
    "ISO-8859-2": "Eastern European (Latin-2)",
    "Windows-1250": "Eastern European (Windows-1250)",
    "ISO-8859-3": "Esperanto (Latin-3)",
    "ISO-8859-10": "Nordic (Latin-6)",
    "Windows-1251": "Cyrillic (Windows-1251)",
    "KOI8-R": "Russian (KOI8-R)",
    "KOI8-U": "Ukrainian (KOI8-U)",
    "ISO-8859-6": "Arabic (ISO 8859-6)",
    "Windows-1256": "Arabic (Windows-1256)",
    "ISO-8859-7": "Greek (ISO 8859-7)",
    "Windows-1253": "Greek (Windows-1253)",
    "ISO-8859-8": "Hebrew (ISO 8859-8)",
    "Windows-1255": "Hebrew (Windows-1255)",
    "ISO-8859-9": "Turkish (ISO 8859-9)",
    "Windows-1254": "Turkish (Windows-1254)",
    "ISO-8859-11": "Thai (TIS 620-2533/ISO 8859-11)",
    "Windows-874": "Thai (Windows-874)",
    "ISO-8859-13": "Baltic (Latin-7)",
    "Windows-1257": "Baltic (Windows-1257)",
    "ISO-8859-14": "Celtic (Latin-8)",
    "ISO-8859-16": "South-Eastern European (Latin-10)",
    "ISO-2022-CN-EXT": "Simplified Chinese (ISO-2022-CN-EXT)",
    "EUC-CN": "Simplified Chinese Unix (EUC-CN)",
    "ISO-2022-JP-2": "Japanese (7-bits JIS/ISO-2022-JP-2)",
    "EUC-JP": "Japanese Unix (EUC-JP)",
    "Shift_JIS": "Japanese (Shift JIS)",
    "CP949": "Korean (EUC-KR/CP949)",
    "ISO-2022-KR": "Korean (ISO-2022-KR)",
    "Big5": "Traditional Chinese (Big5)",
    # VLC's own table pairs this label with ISO-2022-TW, which glibc's
    # iconv does not know -- asking for it on Linux converts nothing and
    # the raw bytes are drawn as though they were UTF-8. EUC-TW is the
    # name the label already promises, and every iconv has it.
    "EUC-TW": "Traditional Chinese Unix (EUC-TW)",
    "Big5-HKSCS": "Hong-Kong Supplementary (HKSCS)",
    "VISCII": "Vietnamese (VISCII)",
    "Windows-1258": "Vietnamese (Windows-1258)",
}
