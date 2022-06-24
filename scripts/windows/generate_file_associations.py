import argparse
from pathlib import Path

from gridplayer.params.extensions import SUPPORTED_AUDIO_EXT, SUPPORTED_VIDEO_EXT
from gridplayer.version import __app_name__

MULTISELECT_KEY = (
    (
        "Root: HKA;"
        r' Subkey: "Software\Classes\{APP_NAME}.{APP_EXT}\shell\open";'
        ' ValueType: string; ValueName: "MultiSelectModel";'
        r' ValueData: "Player"'
    ),
)

NEW_EXT_TEMPLATE = (
    (
        "Root: HKCR;"
        r' Subkey: "SystemFileAssociations\.{APP_EXT}";'
        ' ValueType: string; ValueName: "";'
        ' ValueData: ""; Flags: uninsdeletekey'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Classes\.{APP_EXT}";'
        ' ValueType: string; ValueName: "";'
        ' ValueData: ""; Flags: uninsdeletekey'
    ),
)

# https://jrsoftware.org/isfaq.php#assoc
EXT_TEMPLATE = (
    (
        "Root: HKCR;"
        r' Subkey: "SystemFileAssociations\.{APP_EXT}\shell\{APP_NAME}";'
        ' ValueType: string; ValueName: "";'
        ' ValueData: "Play with {APP_NAME}"; Flags: uninsdeletekey'
    ),
    (
        "Root: HKCR;"
        r' Subkey: "SystemFileAssociations\.{APP_EXT}\shell\{APP_NAME}";'
        ' ValueType: string; ValueName: "Icon";'
        r' ValueData: "{{app}}\{APP_NAME}.exe,0";'
    ),
    (
        "Root: HKCR;"
        r' Subkey: "SystemFileAssociations\.{APP_EXT}\shell\{APP_NAME}\command";'
        ' ValueType: string; ValueName: "";'
        r' ValueData: """{{app}}\{APP_NAME}.exe"" ""%1"""'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Classes\.{APP_EXT}\OpenWithProgids";'
        ' ValueType: string; ValueName: "{APP_NAME}.{APP_EXT}";'
        ' ValueData: ""; Flags: uninsdeletevalue'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Classes\{APP_NAME}.{APP_EXT}";'
        ' ValueType: string; ValueName: "";'
        ' ValueData: "{APP_EXT_DESC}"; Flags: uninsdeletekey'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Classes\{APP_NAME}.{APP_EXT}\DefaultIcon";'
        ' ValueType: string; ValueName: "";'
        r' ValueData: "{{app}}\lib\mime.ico"'  # change this in the future
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Classes\{APP_NAME}.{APP_EXT}\shell\open\command";'
        ' ValueType: string; ValueName: "";'
        r' ValueData: """{{app}}\{APP_NAME}.exe"" ""%1"""'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Classes\Applications\{APP_NAME}.exe\SupportedTypes";'
        ' ValueType: string; ValueName: ".{APP_EXT}";'
        ' ValueData: "";'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Clients\Media\{APP_NAME}\Capabilities\FileAssociations";'
        ' ValueType: string; ValueName: ".{APP_EXT}";'
        ' ValueData: "{APP_NAME}.{APP_EXT}";'
    ),
)

MEDIA_CLIENT = (
    (
        "Root: HKA;"
        r' Subkey: "Software\RegisteredApplications";'
        ' ValueType: string; ValueName: "{APP_NAME}";'
        r' ValueData: "Software\Clients\Media\{APP_NAME}"; Flags: uninsdeletevalue'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Classes\Applications\{APP_NAME}.exe";'
        ' ValueType: string; ValueName: "";'
        ' ValueData: ""; Flags: uninsdeletekey'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Clients\Media\{APP_NAME}";'
        ' ValueType: string; ValueName: "";'
        ' ValueData: "{APP_NAME}"; Flags: uninsdeletekey'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Clients\Media\{APP_NAME}\Capabilities";'
        ' ValueType: string; ValueName: "ApplicationDescription";'
        ' ValueData: "{APP_NAME} - Play videos side-by-side";'
    ),
    (
        "Root: HKA;"
        r' Subkey: "Software\Clients\Media\{APP_NAME}\Capabilities";'
        ' ValueType: string; ValueName: "ApplicationName";'
        ' ValueData: "{APP_NAME}";'
    ),
)


def generate_client_block():
    return "\n".join(MEDIA_CLIENT).format(APP_NAME=__app_name__)


def generate_ext_block(
    app_ext: str, type_name: str, is_multiselect: bool, is_new_ext: bool
):
    template = []

    if is_new_ext:
        template.extend(NEW_EXT_TEMPLATE)

    template.extend(EXT_TEMPLATE)

    if is_multiselect:
        template.extend(MULTISELECT_KEY)

    return "\n".join(template).format(
        APP_NAME=__app_name__,
        APP_EXT=app_ext,
        APP_EXT_DESC=f"{app_ext.upper()} {type_name} File ({__app_name__})",
    )


def iter_ext_blocks(extensions, type_name: str, is_multiselect: bool, is_new_ext: bool):
    yield from (
        generate_ext_block(ext, type_name, is_multiselect, is_new_ext)
        for ext in extensions
    )


def replace_in_file(file: Path, token: str, replacement: str):
    with file.open("r", encoding="utf-8") as f:
        content = f.read()

    if token not in content:
        raise ValueError(f"Token {token} not found in file {file}")

    content = content.replace(token, replacement)

    with file.open("w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate file association for Inno Setup",
    )
    parser.add_argument(
        "token",
        help="token in *.iss file that will be replaced with associations block",
    )
    parser.add_argument("iss_file", type=Path, help="*.iss file")

    args = parser.parse_args()

    blocks = [
        generate_client_block(),
        *iter_ext_blocks(
            SUPPORTED_AUDIO_EXT, "Audio", is_multiselect=True, is_new_ext=False
        ),
        *iter_ext_blocks(
            SUPPORTED_VIDEO_EXT, "Video", is_multiselect=True, is_new_ext=False
        ),
        generate_ext_block("gpls", "Playlist", is_multiselect=False, is_new_ext=True),
    ]

    blocks_txt = "\n".join(blocks)

    replace_in_file(args.iss_file, args.token, blocks_txt)
