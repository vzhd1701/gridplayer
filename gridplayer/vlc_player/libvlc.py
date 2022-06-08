from gridplayer.utils.libvlc import pre_import_embed_vlc

# Need to set env variables before importing vlc
pre_import_embed_vlc()
import vlc  # noqa: E402, F401
