from gridplayer.utils.libvlc_fixer import importing_embed_vlc

# Need to set env variables before importing vlc
with importing_embed_vlc():
    from gridplayer.vlc_player import vlc  # noqa: F401
