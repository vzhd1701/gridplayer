"""Settings edits, resets, cancellation and inheritance through the real menus."""

SETTINGS = {
    "player/media_keys_background": False,
    "video_defaults/scale": 1.05,
    "video_defaults/stream_quality": "540p",
    "subtitles/font": "GridPlayer Missing Test Font",
    "network/proxy_url": "http://old:8080",
    "network/force_ipv4": True,
}


def scenario(d):
    from pathlib import Path

    from gridplayer.params.static import ProxyMode
    from gridplayer.playlist_settings import PlaylistSettings
    from gridplayer.settings import Settings
    from gridplayer.widgets.settings_page_scroll_area import PageScrollArea

    store = Settings()
    session = PlaylistSettings()
    scale = "video_defaults/scale"
    url = "network/proxy_url"
    d.check(
        "the app settings are isolated in the run output",
        Path(store.filename).resolve().is_relative_to(d.out.resolve()),
        store.filename,
    )
    d.open(d.media.clips[0])
    block = d.wait_for_cell("a.mp4")
    d.act(block, "Play / Pause")

    def edit_network(dialog):
        dialog.show_page("network")
        form = dialog.form_of(url)
        mode = dialog.widget("network/proxy_mode")
        mode.setCurrentIndex(mode.findData(ProxyMode.CUSTOM))
        form._reset_btns[url].click()
        dialog.widget(url).setText("http://new:8080")
        mode.setCurrentIndex(mode.findData(ProxyMode.SYSTEM))
        d.check("the proxy address is disabled", not dialog.widget(url).isEnabled())

    def cancel_global(dialog):
        edit_network(dialog)
        dialog.reject()

    d.through_modal(lambda: d.act(block, "Settings"), "global_cancel", cancel_global)
    d.check("Cancel preserves the proxy address", store.get(url) == SETTINGS[url])

    def save_global(dialog):
        edit_network(dialog)
        d.shot("network_edited", dialog)
        dialog.accept()

    d.through_modal(lambda: d.act(block, "Settings"), "global_save", save_global)
    d.check(
        "the superseded reset does not save a disabled edit",
        store.get(url) == SETTINGS[url],
    )
    for key in (scale, "video_defaults/stream_quality", "subtitles/font"):
        d.check(
            f"untouched {key} keeps its original value", store.get(key) == SETTINGS[key]
        )

    def press_reset(box):
        from PyQt5.QtWidgets import QMessageBox

        reset = next(
            button
            for button in box.buttons()
            if box.buttonRole(button) == QMessageBox.DestructiveRole
        )
        reset.click()

    def reset_network(dialog):
        dialog.show_page("network")
        d.through_modal(dialog.resetPage.click, "reset_confirm", press_reset)
        d.check(
            "the reset page is no longer marked modified",
            dialog.resetPage.isHidden(),
        )
        d.shot("network_reset", dialog)
        dialog.accept()

    d.through_modal(lambda: d.act(block, "Settings"), "global_reset", reset_network)
    for key in (url, "network/force_ipv4"):
        d.check(f"reset removes {key} from storage", not store.settings.contains(key))

    def reopened_global(dialog):
        dialog.show_page("network")
        d.check("the reset address reopens empty", dialog.value(url) == "")
        d.check(
            "the reset checkbox reopens off", not dialog.value("network/force_ipv4")
        )
        dialog.reject()

    d.through_modal(
        lambda: d.act(block, "Settings"), "global_reopened", reopened_global
    )

    def video_form(dialog):
        dialog.show_page("video")
        d.app.processEvents()
        scroll = dialog.pages["video"].findChild(PageScrollArea)
        scroll.ensureWidgetVisible(dialog._video_form.widget(scale))
        d.app.processEvents()
        return dialog._video_form

    def accept_for_new_videos_only(dialog):
        """OK, and the videos already here left as they are."""

        def only_new(box):
            (button,) = [b for b in box.buttons() if b.text() == "Only new"]
            button.click()

        d.through_modal(dialog.accept, "only_new", only_new)

    def cancel_playlist(dialog):
        video_form(dialog).widget(scale).setValue(2.0)
        dialog.reject()

    d.through_modal(
        lambda: d.act(block, "Edit Playlist Settings"),
        "playlist_cancel",
        cancel_playlist,
    )
    d.check("playlist Cancel keeps zoom inherited", not session.is_overridden(scale))

    def untouched_playlist(dialog):
        form = video_form(dialog)
        d.check(
            "the inherited zoom has no override mark",
            not form.is_modified(scale),
        )
        d.shot("zoom_inherited", dialog)
        dialog.accept()

    d.through_modal(
        lambda: d.act(block, "Edit Playlist Settings"),
        "playlist_untouched",
        untouched_playlist,
    )
    d.check(
        "accepting rounded zoom does not create an override",
        not session.is_overridden(scale),
    )
    d.check("inherited zoom retains its exact value", session.get(scale) == 1.05)

    def edit_playlist(dialog):
        video_form(dialog).widget(scale).setValue(2.0)
        d.shot("zoom_override", dialog)
        accept_for_new_videos_only(dialog)

    d.through_modal(
        lambda: d.act(block, "Edit Playlist Settings"),
        "playlist_override",
        edit_playlist,
    )
    d.check(
        "an edit creates a zoom override",
        session.is_overridden(scale) and session.get(scale) == 2.0,
    )
    d.open(d.media.clips[1])
    overridden = d.wait_for_cell("b.mp4")
    d.check("a new video uses the playlist zoom", overridden.video_params.scale == 2.0)
    d.act(overridden, "Play / Pause")

    def reset_playlist(dialog):
        form = video_form(dialog)
        d.check(
            "the override is shown on reopening",
            form.value(scale) == 2.0 and form.is_modified(scale),
        )
        form._reset_btns[scale].click()
        d.check("reset clears the override mark", not form.is_modified(scale))
        d.shot("zoom_reset", dialog)
        accept_for_new_videos_only(dialog)

    d.through_modal(
        lambda: d.act(block, "Edit Playlist Settings"),
        "playlist_reset",
        reset_playlist,
    )
    d.check(
        "playlist reset removes the zoom override", not session.is_overridden(scale)
    )
    d.check("reset restores the exact global zoom", session.get(scale) == 1.05)
    d.open(d.media.clips[2])
    inherited = d.wait_for_cell("c.mp4")
    d.check(
        "a new video inherits zoom after reset", inherited.video_params.scale == 1.05
    )
    d.note("settings applied")
