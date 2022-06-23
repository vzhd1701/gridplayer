# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/vzhd1701/gridplayer/compare/v0.2.2...HEAD
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
