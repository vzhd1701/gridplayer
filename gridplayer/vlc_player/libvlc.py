from gridplayer.utils.libvlc_fixer import importing_embed_vlc

# Need to set env variables before importing vlc
with importing_embed_vlc():
    import vlc  # noqa: E402, F401, WPS433
