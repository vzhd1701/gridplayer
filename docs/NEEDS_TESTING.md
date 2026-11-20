# Needs testing

Built, and checked as far as our machines and CI reach, but not yet tried on the hardware below. Each entry says what
has been checked, what hasn't, and what to look at. With such a machine: use the app by hand, and run
`just test-real-app` if you can. Once tried, write down what was seen where it was measured and take the entry out.

## Windows on arm64

From `docs/archive/QT6_PLAN.md` 7.8 (2026-11-19).

- **Checked:** GitHub's `windows-11-arm` runner builds the installer and the portable zip and plays a clip on each
  driver (`--self-check`), and runs the unit tests and the real-app scenarios on VLC and MPV (on trial, passing since
  2026-11-20).
- **Not tried:** a real arm64 PC, by hand, on its own screen.
- **Look at:**
  - OpenGL comes from the GPU's driver (Qualcomm's has it) or from Microsoft's OpenCL and OpenGL Compatibility Pack.
    Without either, MPV's Shared output can't draw; Copy and Direct don't need it.
  - Hardware decoding on VLC and MPV, on a Qualcomm GPU.
  - Many VLC videos at once: VLC's arm64 build imports `WaitOnAddress` from Windows itself, so `libvlc_waits.py`
    leaves it be. Watch the CPU (`docs/findings/VLC_WAITS.md`).

## Linux on arm64

From `docs/archive/QT6_PLAN.md` 7.3 (2026-11-19).

- **Checked:** the AppImage is built on GitHub's `ubuntu-24.04-arm` runner and plays a clip there on each driver,
  under Xvfb. From source on that runner: the unit tests and the real-app scenarios on VLC and MPV (on trial).
- **Not tried:** an arm desktop with a real screen and GPU (a Raspberry Pi 5, a Snapdragon laptop on Linux, Asahi on
  a Mac), on X11 or Wayland.
- **Look at:** OpenGL through the board's Mesa driver, MPV's outputs, and what hardware decoding VLC and MPV pick
  there.

## Linux desktops

From `docs/archive/QT6_PLAN.md` 4.2 (2026-11-19).

- **Checked:** Wayland at 1.5 on sway (Qt 6 draws at 1.5, sharp); GNOME 46 on the Ubuntu VM, X11 and Wayland.
- **Not tried:**
  - GNOME's own fractional scaling (experimental there), at 125% and 150%.
  - On X11, MPV Shared's picture as the window is made bigger, on a real GPU. On the VM's Mesa 25.2.8 the cells
    jump down and back; on Mesa 26.2 and in the Flatpak they don't.
- **Look at:** text and lines sharp, the layout the same as at 100%; the cells staying put during a resize.

## Linux on NVIDIA or AMD GPUs

From `docs/archive/MPV_PLAN.md` 10.4 and 10.12 (2026-11-11).

- **Checked:** Linux on `test_gpu` (Intel, VAAPI, X11 and Wayland). Windows on NVIDIA (RTX 3060) and on an AMD
  iGPU.
- **Not tried:**
  - Linux on NVIDIA or AMD: Hardware MPV's decoding, its Copy, Shared and Direct outputs, VLC Hardware.
  - A switch from MPV to VLC Hardware while playing, on NVIDIA on Linux.
  - HEVC and 10-bit through VAAPI, which needs a newer Intel than `test_gpu`.
- **Look at:** which decoder MPV takes (the log says), and the bench's mix against `docs/findings/MPV_PERFORMANCE.md`.

## Macs

From `docs/archive/MPV_PLAN.md` 11.4 (2026-11-15).

- **Checked:** every real-app scenario on Hardware MPV, Software MPV and VLC, with Copy and Shared output, on
  `test_macos_real`: a hackintosh with an Intel HD 4600 (VideoToolbox decodes H.264 only), macOS 15 and one 1080p
  screen. CI builds the `.app` for Intel and Apple Silicon and plays a clip with each.
- **Not tried:**
  - Apple Silicon by hand: its arm64 libmpv, OpenGL on Metal, VideoToolbox for HEVC, VP9 and AV1.
  - A Retina screen, or a 4K one scaled: frames at the screen's pixels, cells, zoom and screenshots.
  - Two GPUs: which one Qt's context draws on.
  - Sleep and wake, a screen unplugged, the window moved between screens of different scales.
- **Look at:** Auto in "Decode on the CPU" reads no video memory on macOS, so it never moves a video to the CPU
  there. Metal can say how much a GPU has, if that turns out to be needed.
