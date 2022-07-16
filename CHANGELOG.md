# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.2] - 2022-07-16

### Fixed

- Prevent timeout when loading HLS streams directly ([f5b8164](https://github.com/vzhd1701/gridplayer/commit/f5b8164111aa11bfb9188cde059694e71ed10a05))
- Improve overlay workarounds for Linux ([70963b5](https://github.com/vzhd1701/gridplayer/commit/70963b5ee71bd08d7b5bb9284e5629de0af3262b))

## [0.4.1] - 2022-07-15

### Fixed

- Add fix setting for overlay appearing on top of other windows with some window managers (Linux) ([748e79d](https://github.com/vzhd1701/gridplayer/commit/748e79dfef9b2c4adddb353b0444ae14a41b7786))
- Fix transparency mask for opaque overlay (Linux) ([542a6fb](https://github.com/vzhd1701/gridplayer/commit/542a6fbc6fca9d57afcd8cbc03acfbd6f73f9999))

## [0.4.0] - 2022-07-14

### Added

- New setting to control URL resolver priority ([fc72744](https://github.com/vzhd1701/gridplayer/commit/fc7274428c1af496be30ab84dc2fc673691d7e40), [47150b6](https://github.com/vzhd1701/gridplayer/commit/47150b6b87114028c9aece370c2d03994e0db30a))
- New setting to show overlay border for active video ([60d513d](https://github.com/vzhd1701/gridplayer/commit/60d513dff01192152547281b2bbb20ec72c92259))
- New setting to control video init timeout ([7346792](https://github.com/vzhd1701/gridplayer/commit/7346792a97287098a0a4bfa6e64ebbda83d320c4))
- New setting to limit log file size ([71c4fdc](https://github.com/vzhd1701/gridplayer/commit/71c4fdc991e95538161ba9b41f3195a08bbc15e9))
- New setting to set custom VLC options ([8ee6424](https://github.com/vzhd1701/gridplayer/commit/8ee6424efc7774d9bc6d80e15e89043d72b005fe))
- New option to set auto reload timer for live videos ([305e890](https://github.com/vzhd1701/gridplayer/commit/305e89044f84eb1d3af91eabaeb74f2f77adf846))
- Added paste button to add urls dialog ([0ebcfa4](https://github.com/vzhd1701/gridplayer/commit/0ebcfa4d72c6f0292e294bcf165c58b965b14176))

### Changed

- Overhauled settings dialog ([6fc329e](https://github.com/vzhd1701/gridplayer/commit/6fc329ef1154de6959ba5974979b662e6d02bf45), [704dd98](https://github.com/vzhd1701/gridplayer/commit/704dd98cf4a686237a842153ea0f3f88a1859f5a), [3d82901](https://github.com/vzhd1701/gridplayer/commit/3d829016add15f1c3e35dd4078bc14f8e0a4ad03))
- Visual style is now same for every OS ([d24832a](https://github.com/vzhd1701/gridplayer/commit/d24832a4c1b9dd0436685241c088ef44dceec455), [54a4772](https://github.com/vzhd1701/gridplayer/commit/54a4772c0a3be48c3bb3b3da7e89c457b7860ccc))

### Fixed

- Improved streaming URLs playback ([021e61a](https://github.com/vzhd1701/gridplayer/commit/021e61a6a0fe23b3fe3b70d272d83e9d48165ae2), [8c33a6f](https://github.com/vzhd1701/gridplayer/commit/8c33a6f339ca5ad9e2406c20848cd13084e809c2))
- Improved video init timeouts ([7492565](https://github.com/vzhd1701/gridplayer/commit/749256584b57519d80bd5705f855d587e06d4e8d), [c174be5](https://github.com/vzhd1701/gridplayer/commit/c174be5b933fafa363a7358b99a8f25467272be5))
- Improved video init speed ([8408551](https://github.com/vzhd1701/gridplayer/commit/84085514e96659cf57b267bea3f2bfa5b429b12a))
- Avoid crash on bulk seek (seconds) ([ef72d6a](https://github.com/vzhd1701/gridplayer/commit/ef72d6a5a487eeabdc9c0a625f434d748f5087b5)), closes [#59](https://github.com/vzhd1701/gridplayer/issues/59)
- Set video aspect & scale on video load ([d80bec3](https://github.com/vzhd1701/gridplayer/commit/d80bec3703aebc00b039647926f0baeb72527ce3))
- Prevent overlay from showing above other windows (Linux) ([98caea7](https://github.com/vzhd1701/gridplayer/commit/98caea76126ecdfd9704ae72639a8d895e369f84))
- Show black screen instead of error if pause snapshot fail (livestreams) ([9ba942d](https://github.com/vzhd1701/gridplayer/commit/9ba942d81c110f9f27a12f1f5621f00f72ae5556))
- Avoid exception on malformed VLC log message ([5f0c23d](https://github.com/vzhd1701/gridplayer/commit/5f0c23dbe9eb9c197d1b089fda732c72508cb9b6))
- Added missing header title for file dialogs ([c950928](https://github.com/vzhd1701/gridplayer/commit/c95092868846b3388eec7efb28f71f52d3d913cf))

## [0.3.0] - 2022-06-24

### Added

- Support for streaming URLs, which allows playing any URL that is supported by [streamlink](https://github.com/streamlink/streamlink) or [yt-dlp](https://github.com/yt-dlp/yt-dlp), plus mms, mmsh, rtp, rtsp and udp protocols ([9425343](https://github.com/vzhd1701/gridplayer/commit/9425343450bc282aecbc1456cbc03c81d3e7d80e))
- Support for audio files ([8507bcb](https://github.com/vzhd1701/gridplayer/commit/8507bcb69ed4a1e708036f6ab896d92e770acc60))
- Playlist state snapshots, which allow keeping multiple grid & video presets ([2b19e97](https://github.com/vzhd1701/gridplayer/commit/2b19e97bc9bfe0e22b507ec87d36a8b05f7ec9a0))
- New command to sync other videos according to active video position or timecode ([90a0449](https://github.com/vzhd1701/gridplayer/commit/90a04498ef84d55ec373c5f827a4d86f8278a03e))
- New command that allows jumping to video time percent ([9e2a377](https://github.com/vzhd1701/gridplayer/commit/9e2a3777ccab1ab3636ea1fcad0bd61f8a5ace51))
- New command that allows jumping to video timecode ([59cc6cc](https://github.com/vzhd1701/gridplayer/commit/59cc6cc8cfb9cf12aafefcbcb14226fd865746b5))
- New command to shuffle video blocks ([2d040da](https://github.com/vzhd1701/gridplayer/commit/2d040da20c0fa35b72dfa34a8908211f2a402e87))
- New command to reload videos (useful in case of network errors) ([8861b73](https://github.com/vzhd1701/gridplayer/commit/8861b73e806c21db3318a9730a00f116696c6734))
- Option to seek sync using timecode ([37b3e34](https://github.com/vzhd1701/gridplayer/commit/37b3e34b9792e5a5ea5f36942bd6e51512d2270e))
- Option to cancel when closing unsaved playlist ([4254a7a](https://github.com/vzhd1701/gridplayer/commit/4254a7a272292bcefae9510b5f642a6128bc0f59))
- Playlist settings to disable pausing videos with left mouse click & seeking using mouse wheel ([b3b9bde](https://github.com/vzhd1701/gridplayer/commit/b3b9bde5de3df485c211384a4b5318a0ded8d994))
- Info label that displays video loading status ([4c14188](https://github.com/vzhd1701/gridplayer/commit/4c141886fa3535b91bd546cce1418a73878bfdec))
- Animation while video is loading ([d874bea](https://github.com/vzhd1701/gridplayer/commit/d874bea367a2130dcbd20b7952a5ddb628201a13))
- Animation for status change on play/pause button, will appear mostly when pausing/unpausing live streams ([432f933](https://github.com/vzhd1701/gridplayer/commit/432f93392336c8d6ed0effc66e7a09718e583bf0))
- Installer file associations and context menu option (Windows)

### Changed

- Videos opened via file explorer or command line will be added to the current playlist ([857d959](https://github.com/vzhd1701/gridplayer/commit/857d959727abf9e41578618030481c6fd0f662a3))
- All single video commands & options are now in sync with bulk commands ([26150bd](https://github.com/vzhd1701/gridplayer/commit/26150bd3d680beb1c3f8d345afed1887b71dadd0), [3ea89b5](https://github.com/vzhd1701/gridplayer/commit/3ea89b5fb1bd1560d4a4db600a686bed2f99212b), [56f7465](https://github.com/vzhd1701/gridplayer/commit/56f7465d6a770d45a3399fde8316ee2a30876135))
- Single video command hotkeys are all mirrored with Shift+ equivalents for bulk commands
- Improved context menu visual style ([9d3e489](https://github.com/vzhd1701/gridplayer/commit/9d3e48967c65c37a63f7d25e2afe3c05eac10832), [e764ce2](https://github.com/vzhd1701/gridplayer/commit/e764ce2ea18c2700150c1a429e95d85e1f58f578))
- Improved settings window visual style (MacOS) ([aaf9d6b](https://github.com/vzhd1701/gridplayer/commit/aaf9d6b3fcfdf2ab4928eefb26007261b8046c15))
- Improved video startup speed ([8311e7c](https://github.com/vzhd1701/gridplayer/commit/8311e7ce352039db9b81efd2553e662d16d81d64))
- Imporved application shutdown speed ([18f48a5](https://github.com/vzhd1701/gridplayer/commit/18f48a5a7d8d53f13170347abad46d5bebc005a1), [6454fa2](https://github.com/vzhd1701/gridplayer/commit/6454fa290eea0e0ecaaee7983758d78d1c58d9c0))
- Optimized some context menu icons ([4f9a908](https://github.com/vzhd1701/gridplayer/commit/4f9a9085f5c0646eaf6847fd72421de5fd30f0d0))

### Fixed

- Fix drag-n-drop between different player instances ([38c8235](https://github.com/vzhd1701/gridplayer/commit/38c82353f966c8abb32aa98be62a0d1714a2af1d)), closes [#49](https://github.com/vzhd1701/gridplayer/issues/49)
- Fix crash on bad setting ([8ce0d4b](https://github.com/vzhd1701/gridplayer/commit/8ce0d4b5c539079cc6dbc7ee8ea76ecbb7098108))
- Fix minor stability & performance issues

## [0.2.2] - 2022-04-09

### Added

- Hungarian translation ([5cd6892](https://github.com/vzhd1701/gridplayer/commit/5cd68929ce72954738005f044a77b956298c71cc))
- New option to control warning about unsaved playlist changes ([380ad92](https://github.com/vzhd1701/gridplayer/commit/380ad9219254edc588d939eadd2a6f1d041ab0a0))

### Fixed

- Fix crash on some setups ([2334439](https://github.com/vzhd1701/gridplayer/commit/233443916c5727a8f287bf18e8ca47dcd8a2f6bf)), closes [#40](https://github.com/vzhd1701/gridplayer/issues/40)
- Unpause videos when window is restored ([8c82293](https://github.com/vzhd1701/gridplayer/commit/8c82293c8e3b77dc65f4124cfd8e85979046f1a9))

## [0.2.1] - 2022-02-03

### Added

- Ability to switch focus using keyboard ([f441f88](https://github.com/vzhd1701/gridplayer/commit/f441f88569db3548c0bd5f1825f4622b6de8ace0))

### Fixed

- Fix handling files with uppercase extension ([74e8648](https://github.com/vzhd1701/gridplayer/commit/74e8648b68ecc8ad2b20846570d7ac49897211f5))
- Prevent error when opening second instance without arguments ([3c33209](https://github.com/vzhd1701/gridplayer/commit/3c33209dd427a0de8cb55cb05075341ea3c81759)), closes [#23](https://github.com/vzhd1701/gridplayer/issues/23)

## [0.2.0] - 2021-12-29

### Added

- Internationalization support ([2c436e6](https://github.com/vzhd1701/gridplayer/commit/2c436e60c66101405204520c164f0a9f460d110e))
- New option to disable overlay timeout ([4d0782a](https://github.com/vzhd1701/gridplayer/commit/4d0782aa1ee46c20068bc9022ac2cee6e8c9a966))
- New option to loop through videos in directory ([cd78f48](https://github.com/vzhd1701/gridplayer/commit/cd78f48ff0466226951a5e4449e66f4cbad84d8e))
- New option to rename videos and set custom color ([a2cba33](https://github.com/vzhd1701/gridplayer/commit/a2cba335c7cc45995b4d5f204cff1b1b5d8b36f7))
- Russian translation ([e1d81c3](https://github.com/vzhd1701/gridplayer/commit/e1d81c33bdd29fcd3b045dc01f0deef707f738ce))

### Fixed

- Fix name for about dialog ([c9bbda5](https://github.com/vzhd1701/gridplayer/commit/c9bbda5ca2088352c67444c4442953e8c411d4a9))

## [0.1.6] - 2021-12-01

### Fixed

- Fix UI scaling with high DPI ([ddbf005](https://github.com/vzhd1701/gridplayer/commit/ddbf005447971b631e8fc5aebceb982a2ee5fd3c))

## [0.1.5] - 2021-11-22

### Added

- New option to synchronize seek ([b85c554](https://github.com/vzhd1701/gridplayer/commit/b85c554b6086e127e71df390bf59ef9c62225a1d))
- Ability to seek while dragging cursor ([a3a7024](https://github.com/vzhd1701/gridplayer/commit/a3a7024834a9a152e178099cd53183ec485bd854))

### Fixed

- Added missing library to avoid startup error (windows) ([0193ee8](https://github.com/vzhd1701/gridplayer/commit/0193ee870102dbf909b2bd6dc9127d5a260c9c15))

## [0.1.4] - 2021-11-15

### Fixed

- Fix error when opening some formats (ts, wmv) ([4c8b19c](https://github.com/vzhd1701/gridplayer/commit/4c8b19cba10050fb775a8c82b69099894905560a))

## [0.1.3] - 2021-11-09

### Added

- Missing jump seek actions ([caac5f5](https://github.com/vzhd1701/gridplayer/commit/caac5f5f6d924ecf6de530d90827ed4e641afb46))
- Fit grid modes ([c19b22d](https://github.com/vzhd1701/gridplayer/commit/c19b22d725ed0137e5cdcb6bd3aa187392f9584a))
- Grid size adjustment ([1dd4d61](https://github.com/vzhd1701/gridplayer/commit/1dd4d6116880c0ae12b14dbfa0d8a198493e125f))

### Fixed

- Fix hardware decoding in MacOS ([899ca3b](https://github.com/vzhd1701/gridplayer/commit/899ca3b97aafa93a72dd3c8c5fa7c7b696e3ebdf))

## [0.1.2] - 2021-11-01

### Fixed

- Fix random loop context menu icon ([347bbde](https://github.com/vzhd1701/gridplayer/commit/347bbde7e47dc4dbe7915f17f9a591a87c86f754))
- Prevent cursor from hiding while dragging ([b08f360](https://github.com/vzhd1701/gridplayer/commit/b08f3607f6d186ed7b9c8f1b5eab69f82862ee48))
- Prevent double click on overlay buttons ([b8d59f8](https://github.com/vzhd1701/gridplayer/commit/b8d59f8a59a1f94b20038d504ae8815bb797f314))
- Show source video overlay when dragging ([c33e7e0](https://github.com/vzhd1701/gridplayer/commit/c33e7e0305f448f1ea57d96aed0537227fbe1f8e))
- Fix adding files from context menu
- Prevent window from going background on drag-n-drop

## [0.1.1] - 2021-10-19

### Added

- Dark mode compatibility ([cd778e2](https://github.com/vzhd1701/gridplayer/commit/cd778e2b3841cfb0d2c28a74ee8134f43009c072))
- Better message if VLC is not installed ([9b23823](https://github.com/vzhd1701/gridplayer/commit/9b23823864a102715d48d6fb149cbf2469ff6673))

### Fixed

- Added special setting to fix KDE black screen bug ([0997d3c](https://github.com/vzhd1701/gridplayer/commit/0997d3c377219b085c3088825a8a2d4ff34b6384))
- Prevent accidental playlist overwrite if placeholder is not available ([f686e6e](https://github.com/vzhd1701/gridplayer/commit/f686e6e05031764f262ce74e20ec43e6589387be))

## [0.1.0] - (2021-10-13)

### Added

- Initial release

[Unreleased]: https://github.com/vzhd1701/gridplayer/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/vzhd1701/gridplayer/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/vzhd1701/gridplayer/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/vzhd1701/gridplayer/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/vzhd1701/gridplayer/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/vzhd1701/gridplayer/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/vzhd1701/gridplayer/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/vzhd1701/gridplayer/compare/v0.1.6...v0.2.0
[0.1.6]: https://github.com/vzhd1701/gridplayer/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/vzhd1701/gridplayer/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/vzhd1701/gridplayer/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/vzhd1701/gridplayer/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/vzhd1701/gridplayer/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/vzhd1701/gridplayer/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/vzhd1701/gridplayer/releases/tag/v0.0.1
