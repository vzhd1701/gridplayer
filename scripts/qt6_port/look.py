"""Screenshots of what Qt draws, to compare PyQt5 with PyQt6 (docs/plans/QT6_PLAN.md,
stages 0.4 and 3.3). The same scenario runs on both:

    uv run python -m tests.real_app.run scripts/qt6_port/look.py --out DIR

and with QT_SCALE_FACTOR=1.5 for 150%. It leaves one PNG per window, page and menu:
the player with four paused cells, the context menu and each of its submenus, every
page of Settings and of the Playlist window, and the dialogs the menus open.
"""

try:
    from PyQt6.QtCore import QPoint
except ImportError:
    from PyQt5.QtCore import QPoint

# what a dialog opened from a cell's menu is called in the shots
DIALOGS = {
    "About": "about",
    "Rename": "rename",
    "Set Position": "set_position",
    "Set Crop": "set_crop",
    "Audio Delay: %v": "audio_delay",
    "Subtitle Delay: %v": "subtitle_delay",
    "Grid Size: %v": "grid_size",
    "Add - URL(s)": "add_urls",
    "Bookmarks in Playlist": "bookmarks",
    "Lists in Playlist": "lists",
}


def scenario(d):
    d.open(*d.media.clips, d.media.feature)
    for clip in d.media.clips:
        d.wait_for_cell(clip.name)
    block = d.wait_for_cell("feature.mkv")

    d.act(block, "Pause [ALL]")
    d.wait_until(lambda: all(b.video_params.is_paused for b in d.cells), "all paused")
    d.pump(1)
    d.shot("player")

    _menus(d, block)
    _paged(d, block, "Settings", "settings")
    _paged(d, block, "Edit Playlist Settings", "playlist")

    for action, name in DIALOGS.items():
        d.through_modal(lambda action=action: d.act(block, action), f"dialog_{name}")


def _menus(d, block):
    # offscreen has no clipboard: its mimeData() is None, which Add - Clipboard's
    # check doesn't expect (a harness limit, not the app's)
    d.ctx.actions["Add - Clipboard"].enable_if = lambda: False

    d.ctx.active_block = block
    menu = d.player._managers_inst["menu"].make_menu()
    menu.popup(d.player.mapToGlobal(QPoint(40, 40)))
    d.pump(0.5)
    d.shot("menu", menu)

    for action in menu.actions():
        submenu = action.menu()
        if submenu is None or not action.isEnabled():
            continue
        menu.setActiveAction(action)
        submenu.popup(menu.mapToGlobal(menu.actionGeometry(action).topRight()))
        d.pump(0.3)
        name = action.text().replace("&", "").replace("/", "-").strip().lower()
        d.shot(f"menu_{'_'.join(name.split())}", submenu)
        submenu.hide()

    menu.hide()
    menu.deleteLater()
    d.pump(0.2)


def _paged(d, block, action, prefix):
    def each_page(dialog):
        for page_id in list(dialog.pages):
            dialog.show_page(page_id)
            d.pump(0.3)
            d.shot(f"{prefix}_{page_id}", dialog)

    d.through_modal(lambda: d.act(block, action), f"{prefix}_first", each_page)
