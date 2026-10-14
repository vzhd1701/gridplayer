"""Stepping along a folder and along a list, and the List window."""


def scenario(d):
    d.open(d.media.clips[0], d.media.list_m3u)
    d.wait_until(
        lambda: len(d.cells) == 2 and all(c.is_playable for c in d.cells),
        "both play",
    )
    # both start on a.mp4; the list's is the one reading a list
    folder = next(c for c in d.cells if c.media_list is None)
    listed = next(c for c in d.cells if c.media_list is not None)

    d.act(folder, "Play Next File")
    d.wait_until(lambda: folder.video_params.uri.name == "b.mp4", "the folder's next")
    d.wait_until(lambda: folder.is_playable, "b.mp4 plays")
    d.act(folder, "Play Previous File")
    d.wait_until(lambda: folder.video_params.uri.name == "a.mp4", "and back")

    d.check("the list starts at 1/3", listed.navigation.list_place_txt == "1/3")
    d.check("titled from the list", listed.title == "Clip A", listed.title)
    d.act(listed, "Play Next File")
    d.wait_until(lambda: listed.navigation.list_place_txt == "2/3", "the list's next")
    d.wait_until(lambda: listed.title == "Clip B", "titled from the list")
    d.check("on b.mp4", listed.video_params.uri.name == "b.mp4")

    d.act(listed, "List")
    d.wait_until(
        lambda: [w for w in d.windows() if type(w).__name__ == "MediaListDialog"],
        "the List window is open",
    )
    window = d.windows()[-1]
    d.shot("list_window", window)
    window.close()
    d.pump()

    d.run(folder, "all", "next_video")
    d.wait_until(lambda: folder.video_params.uri.name == "b.mp4", "all stepped on")
    d.wait_until(lambda: listed.navigation.list_place_txt == "3/3", "the list too")

    d.note("end")
