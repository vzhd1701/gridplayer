# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Replace video on drag-n-drop while holding modifier key (default: shift) ([b8affe3](https://github.com/vzhd1701/gridplayer/commit/b8affe37f2bb0feef9e196c079db0901010125d3))
- Add visual drag-n-drop indicators with option to drop before/after ([98b674f](https://github.com/vzhd1701/gridplayer/commit/98b674fadb866688086232a652b9a468d097d4ad))
- Add option to start with maximized window ([74282df](https://github.com/vzhd1701/gridplayer/commit/74282df433867e45c7da95d10875979770933024))
- Add option to start in fullscreen mode ([02cb6fd](https://github.com/vzhd1701/gridplayer/commit/02cb6fd04272f8356a0223b031737f4addc21c62))
- Add option to manually select app color scheme ([6a59985](https://github.com/vzhd1701/gridplayer/commit/6a59985855ae5471a3a6d1d75a89829003764bfd))
- Add option to disable overlay ([2c7163f](https://github.com/vzhd1701/gridplayer/commit/2c7163f34231bb1180e57d296d00f7b7f6121030))
- Add shortcuts editor ([fa22fa7](https://github.com/vzhd1701/gridplayer/commit/fa22fa7d8767f580f701c7a5f0677b704330c5a7))
- Add "save playlist as" option ([7cb07dd](https://github.com/vzhd1701/gridplayer/commit/7cb07dd7a275d5d82996aacd5ad2dcc6c8be7647))
- Show playlist name in the window title ([237ea43](https://github.com/vzhd1701/gridplayer/commit/237ea43e5a6d97ae171a9e258a31f7b58c6f8bd1))

### Fixed

- Wait for vlc process cleanup on linux to avoid crashes ([04821b1](https://github.com/vzhd1701/gridplayer/commit/04821b1aff7cc761492f2f5ae4c2d74591d63e11))
- Prevent switching to single mode without active video (double click on empty space) ([526210f](https://github.com/vzhd1701/gridplayer/commit/526210f21f2ab8c46e5a250a0ccd114341d6bcba))
- Improve drag n drop on KDE ([a7b2def](https://github.com/vzhd1701/gridplayer/commit/a7b2def2448a9ad3ac6821c23bbb4ed120f0b72b))
- Reset playlist setting to defaults after closing playlist ([fd728f3](https://github.com/vzhd1701/gridplayer/commit/fd728f3f64c2cef240549458c51bdec30801ad62))
- Use setWindowFilePath to update playlist name in window title ([703b6ea](https://github.com/vzhd1701/gridplayer/commit/703b6eab58d71f528c9a4e9e7d1d37dc59e74743))
- Set proper parent to each submenu to avoid crashes on mac ([8ecffe9](https://github.com/vzhd1701/gridplayer/commit/8ecffe93a4d7b1f999e82d963cd99e335d0bc90b))
- Ensure that video is seekable if loaded in paused state ([71615d9](https://github.com/vzhd1701/gridplayer/commit/71615d993d9bb7e71a432ef45fa558be234a9315))
- Improve vlc frame offset detection to avoid glitches with KWin on linux ([03e812b](https://github.com/vzhd1701/gridplayer/commit/03e812b8bc5ac398917cebab1888cad657391470))
- Make loading animation and video status icon transparent ([a52bd47](https://github.com/vzhd1701/gridplayer/commit/a52bd4781677ef8d2fe517990a0e65360fc03989))
- Set overlay opacity on child widgets to avoid clipping glitches on linux ([7d2d5b3](https://github.com/vzhd1701/gridplayer/commit/7d2d5b341c54867082182e71f737f6f8efaf3ace))
- Unset QT_XCB_GL_INTEGRATION on linux to avoid forked process crash ([839bf83](https://github.com/vzhd1701/gridplayer/commit/839bf83394d8d402c36e85b678072b3a5c9e26da))
- Adjust video on vout to ensure correct aspect on video load in Mac and Linux ([878b817](https://github.com/vzhd1701/gridplayer/commit/878b817009bd4b47494996726e39bd2c6b765019))
- Avoid crash on spam reload ([737fe79](https://github.com/vzhd1701/gridplayer/commit/737fe79619d6f929ede35205a89338a2e8385b12))
- Add compositor detection on linux to avoid black overlay ([e22e91c](https://github.com/vzhd1701/gridplayer/commit/e22e91cc8dd9fc2562483317d2368097c93dfe65))
- Add newly saved playlist into recent list ([1682959](https://github.com/vzhd1701/gridplayer/commit/16829599d0b864e1659036ba49b62f95cdf2ca6d))
- Improve system color theme sync on linux and windows ([e41cc36](https://github.com/vzhd1701/gridplayer/commit/e41cc361967d7f9cb405718d51bb68ba3801d5a3)), ([ab062b3](https://github.com/vzhd1701/gridplayer/commit/ab062b340ddd00352262b6402aa621472359faf4))
- Unify app style and colors ([61d90b0](https://github.com/vzhd1701/gridplayer/commit/61d90b04df15e31d67ed4bb9b2de9269a420e375))
- Improve language selection section in settings ([65bc49d](https://github.com/vzhd1701/gridplayer/commit/65bc49da7c32edc48552bd67976ac089877ca33b))
- Avoid crash for menu with custom style ([afac43f](https://github.com/vzhd1701/gridplayer/commit/afac43f9b9d92777588115647ea3e67b9652e013))
- Avoid memory leaks on menus ([bbde797](https://github.com/vzhd1701/gridplayer/commit/bbde7977ede3694d68ec629f68fe9da494f692b4))
- Handle invalid track metadata and duplicate closes ([#319](https://github.com/vzhd1701/gridplayer/issues/319)) ([b0ade83](https://github.com/vzhd1701/gridplayer/commit/b0ade837afaecb86b77fe4ced0f4c0a4935568bf))
- Improve missing libvlc handling ([fd4539f](https://github.com/vzhd1701/gridplayer/commit/fd4539f80742fa0bf70c850cf3a41c39e4bc843c))
- Check if action is enabled on invoke to keep hotkeys always active ([5a18d0c](https://github.com/vzhd1701/gridplayer/commit/5a18d0c48a99bd82fa19fffcdeb12e789a696339))
- Force xcb on linux becuase libVLC doesnt work with wayland ([f5f77c2](https://github.com/vzhd1701/gridplayer/commit/f5f77c27d69167f2b204603414d2d4cba1c9dfc9))

## [0.5.5] - 2026-07-24

### Added

- Native Apple Silicon (arm64) macOS build support, with arch-aware build scripts and a `BUILD_MACOS_ARCH` override for Intel (`x86_64`) builds ([de4a54a](https://github.com/vzhd1701/gridplayer/commit/de4a54a))
- Czech, Norwegian, Swedish, Taiwanese, Vietnamese translations ([fd35bf2](https://github.com/vzhd1701/gridplayer/commit/fd35bf2cac5e8f9a222635ad4c09bf043ad71bdf)), ([c52c5de](https://github.com/vzhd1701/gridplayer/commit/c52c5de8ca055f2b22bb108b4ef048a2861f86be)), ([0867eea](https://github.com/vzhd1701/gridplayer/commit/0867eea48a2cbbdb154fb9ca5fe1f1c79fd58767))

### Fixed

- Update translations ([c52c5de](https://github.com/vzhd1701/gridplayer/commit/c52c5de8ca055f2b22bb108b4ef048a2861f86be))
- Update streamlink and yt-dlp ([8e172e5](https://github.com/vzhd1701/gridplayer/commit/8e172e5))
- Avoid checkbox shrinking in language select dialog ([d510a80](https://github.com/vzhd1701/gridplayer/commit/d510a809ce76a3d3eff312c4ac01b3b3a7ec4566))
- Force load app icon to avoid default icon on Windows 11 ([51d0d92](https://github.com/vzhd1701/gridplayer/commit/51d0d92cfe75efdc8a15d16874dd246fee658c57))
- Restore URI parsing for playlists ([b02b31b](https://github.com/vzhd1701/gridplayer/commit/b02b31bd3be7e0fbaa278dee1d9740835f005635)), closes [#294](https://github.com/vzhd1701/gridplayer/issues/294) [#311](https://github.com/vzhd1701/gridplayer/issues/311)
- Show error when picking missing local video from recent list ([de03e3b](https://github.com/vzhd1701/gridplayer/commit/de03e3b12969e625acdc35609cbea1c33583de54))
- Improve file validation when importing from clipboard ([7ca8208](https://github.com/vzhd1701/gridplayer/commit/7ca820875c772e4d3c839c00369d635f8f4cac98)), closes [#296](https://github.com/vzhd1701/gridplayer/issues/296)
- Safeguard playback position updates ([52c706d](https://github.com/vzhd1701/gridplayer/commit/52c706d3c106dc8ae2b50a36ba09a90a581c23c4)), closes [#309](https://github.com/vzhd1701/gridplayer/issues/309)

## [0.5.4] - 2025-11-24

### Added

- Allow rtmp protocol ([#165](https://github.com/vzhd1701/gridplayer/issues/165)) ([939dd5a](https://github.com/vzhd1701/gridplayer/commit/939dd5a5235e8a852aa1b0e51b00538923a5bbbe))

### Fixed

- Update streamlink, yt-dlp and minimum python version ([#271](https://github.com/vzhd1701/gridplayer/issues/271)) ([763745c](https://github.com/vzhd1701/gridplayer/commit/763745c987beb0e333e3521a362f0f00bf1af6d9))

## [0.5.3] - 2023-10-17

### Added

- Option to crop video ([8b1fba3](https://github.com/vzhd1701/gridplayer/commit/8b1fba3658fc9af7cac3c6604342a71165a6e455))

### Fixed

- Update yt-dlp and Streamlink ([c5790f2](https://github.com/vzhd1701/gridplayer/commit/c5790f231173b965369d8afc1a205e884323e2cd))
- Update translations ([48ff112](https://github.com/vzhd1701/gridplayer/commit/48ff1125236f1c0ac76620fb4c32c1bc97d8f235))
- Prevent video distortion when rotation is enabled ([d0dc5be](https://github.com/vzhd1701/gridplayer/commit/d0dc5bee1ea7c54cabc9985a4f3e3b7ccda0868f))
- Add h265 and hevc to video extensions ([6cbc01f](https://github.com/vzhd1701/gridplayer/commit/6cbc01ffdfd3ded6acd7cfebcf942c1f0031a0bd))
- Allow opening any files ([c775315](https://github.com/vzhd1701/gridplayer/commit/c775315df5bcb3ed4e635cd8465a9272a1020a1d)), closes [#170](https://github.com/vzhd1701/gridplayer/issues/170)
- Increase maximum zoom scale to 10 (max for VLC) ([3a346fb](https://github.com/vzhd1701/gridplayer/commit/3a346fbc51f727816293d4cc6b6ddafccad808af))

## [0.5.2] - 2023-08-23

### Fixed

- Update yt-dlp and Streamlink ([442f71f](https://github.com/vzhd1701/gridplayer/commit/442f71fe3dcf6254b9bfb7a750752dcaff7733fd))
- Show stream bitrate and codec name if parsed by yt-dlp ([75f84cd](https://github.com/vzhd1701/gridplayer/commit/75f84cd6149690d804cb265262e3e5b4f35716a3))
- Retry if HLS video time is not initialized ([66c6e48](https://github.com/vzhd1701/gridplayer/commit/66c6e48940a793e7647efb3fbf2cb95294b68b15))
- Fix compatibility with new Streamlink API ([90c3adc](https://github.com/vzhd1701/gridplayer/commit/90c3adc1cfd083f7ad78237db1946828669fcef6))
- Fix m3u8 format generated by HLS proxy ([b12e370](https://github.com/vzhd1701/gridplayer/commit/b12e37026ff7558da8e1a8a6dbd8d2d5265eeb3d))
- Fix relay proxy chunked encoding ([57e5aef](https://github.com/vzhd1701/gridplayer/commit/57e5aef3efa2aaa13cca79d6a246e0daa0e2f639))

## [0.5.1] - 2023-06-05

### Added

- Option to transform video (rotate, mirror, transpose) ([236b989](https://github.com/vzhd1701/gridplayer/commit/236b9895b9fc9b5ba7b9ccda503271466a108103))

### Fixed

- Update translations ([042e3b7](https://github.com/vzhd1701/gridplayer/commit/042e3b7b8716ffd1a0c6b851c089af49700a38fc))
- Prevent video freeze on MacOS ([fe37336](https://github.com/vzhd1701/gridplayer/commit/fe3733606e78e30c1245e7126cda842cc847d94f))
- Access URL directly if yt-dlp reports a direct link ([6aa0a13](https://github.com/vzhd1701/gridplayer/commit/6aa0a1397db68311cf3295e53ddc83d4a996b4d6))
- Add support for relative paths ([884b687](https://github.com/vzhd1701/gridplayer/commit/884b687d4b0a85bcef6eb63bae6865c4e24d7dd8))
- Filter video streams only if preferred quality is configured ([f9a98bf](https://github.com/vzhd1701/gridplayer/commit/f9a98bf9f712a2d80a12c6d03c5aef84127002dc))

## [0.5.0] - 2023-05-18

### Added

- Arabic translation ([7cf8b06](https://github.com/vzhd1701/gridplayer/commit/7cf8b06a240c576c30d5cc4bb2f7f29f5fa1ef02))
- Chinese Simplified translation ([681c403](https://github.com/vzhd1701/gridplayer/commit/681c403235eaad95d3b5c43b6a141f171caabb80))
- Dutch translation ([d27d47a](https://github.com/vzhd1701/gridplayer/commit/d27d47a45aaabfa1c79183609cae775406923b67))
- French translation ([aa5d48a](https://github.com/vzhd1701/gridplayer/commit/aa5d48af693af359d1673ad86b4293b9d79de387))
- German translation ([11f9136](https://github.com/vzhd1701/gridplayer/commit/11f913651c97a4451aa1b1cc6500102483f116eb))
- Italian translation ([b16b0b3](https://github.com/vzhd1701/gridplayer/commit/b16b0b34f28d1669cc3b47806c5a8fbd64ed739e))
- Japanese translation ([79876de](https://github.com/vzhd1701/gridplayer/commit/79876defe67bd3d7c4cf8114c41cfd4218293b59))
- Korean translation ([61423ea](https://github.com/vzhd1701/gridplayer/commit/61423ea46584352bf9216e049712979ba7afaa60))
- Polish translation ([06d2fc3](https://github.com/vzhd1701/gridplayer/commit/06d2fc353ba0b70043da10875394ef89d79dda21))
- Portuguese, Brazilian translation ([b16d352](https://github.com/vzhd1701/gridplayer/commit/b16d3525f937c4fca5a515d8eb1b4a18af117f3e))
- Spanish translation ([3b76290](https://github.com/vzhd1701/gridplayer/commit/3b762903401be985d8e6ef7c7d07638687002918))
- Option to paste files/links from clipboard ([f300c22](https://github.com/vzhd1701/gridplayer/commit/f300c228f0f992537c5faeeac164137f7376d702))
- Option to select audio mode (stereo, mono, etc) ([ef9be61](https://github.com/vzhd1701/gridplayer/commit/ef9be61c0eed96820334c7677c3509d4fe6bad0b))
- Option to select audio only stream when available ([b77e409](https://github.com/vzhd1701/gridplayer/commit/b77e4093244da2d8a2124292ae8d3f9504fb1e3b))
- Option to select audio/video track ([009917f](https://github.com/vzhd1701/gridplayer/commit/009917f4fe3e00b453f68dc926cdac317383a13c))
- Stay on top setting ([1227bab](https://github.com/vzhd1701/gridplayer/commit/1227bab6369adf8e9a83069d508bee6ae7000cb7))
- Recent list support for videos/playlists ([48acba1](https://github.com/vzhd1701/gridplayer/commit/48acba1db0ac5fb73eee528106682b5756daf9f3))
- Single mode switch in context menu ([faf8d5f](https://github.com/vzhd1701/gridplayer/commit/faf8d5f22e5741ce9fd97c222ec786c91ab3a1d0))
- Volume controls in context menu ([f749821](https://github.com/vzhd1701/gridplayer/commit/f7498218b5a64bdfe4ad64bf60d78fce8ca2b7bc))

### Fixed

- Update yt-dlp and Streamlink ([635aaf5](https://github.com/vzhd1701/gridplayer/commit/635aaf5a26e43a061c08108cd42dbe14bf756e02))
- Terminate child processes on app exit (Windows) ([5045337](https://github.com/vzhd1701/gridplayer/commit/50453373d425df0f5b903af7f11a8b4100827c6e))
- Reorganize context menu ([3070fd5](https://github.com/vzhd1701/gridplayer/commit/3070fd53b9e16cf5ec0e70b92aad9b08b2934c8c))
- Avoid moving overlay during paintEvent to prevent app crash ([10b141b](https://github.com/vzhd1701/gridplayer/commit/10b141b0f75277eaa53b35c637fc3af2e3465772))
- Avoid rare exception on app close ([1968173](https://github.com/vzhd1701/gridplayer/commit/19681731e50544a84be46721a3f431a25cb76dc9))
- Avoid wide text cramming on main screen ([f4b63be](https://github.com/vzhd1701/gridplayer/commit/f4b63befc8488c1fd1845cceb257f3f0e068b5a9))
- Disable video controls if no video track ([c439ce2](https://github.com/vzhd1701/gridplayer/commit/c439ce2529b4b4282a0ed25aa95ccd5fdcbf1f82))
- Crash on missing VLC ([d76b089](https://github.com/vzhd1701/gridplayer/commit/d76b08944003322d7abe70181f8e5d090a4488d9)), closes [#112](https://github.com/vzhd1701/gridplayer/issues/112)
- Crash when loop start/end unset in playlist ([c2b7b34](https://github.com/vzhd1701/gridplayer/commit/c2b7b340dcfcd52ac34a3d2d10b8f77b19c18663))
- Crash when opening a playlist ([d1bb3ae](https://github.com/vzhd1701/gridplayer/commit/d1bb3ae95056710bc5a327bb544171e1e80c5533))
- Icon glitches ([cab0eed](https://github.com/vzhd1701/gridplayer/commit/cab0eed6b3ed9fa488538b3207b3127dcce0ec6f))
- Hide FPS from track description if it's empty ([ca3dd61](https://github.com/vzhd1701/gridplayer/commit/ca3dd6150c9618e9f42abe4566b125dd7ac1af32))
- Hide volume button if no audio tracks ([f4ce4cd](https://github.com/vzhd1701/gridplayer/commit/f4ce4cd20d885f318d4cc5fcdcbfc3e711654823))
- Kill process silently on KeyboardInterrupt ([92ccfd7](https://github.com/vzhd1701/gridplayer/commit/92ccfd712ecbbb714d9193f2624841945dcb4ad6))
- Loop videos via VLC playlist to avoid abrupt video stop ([7247d57](https://github.com/vzhd1701/gridplayer/commit/7247d5738b43b26bf3ebd4960d8d47d2d6bbc284))
- Make context menu scrollable if it exceeds screen size ([fa0f741](https://github.com/vzhd1701/gridplayer/commit/fa0f7414bf208ca75c33a9f4c631646b0cbc5b64))
- Prevent missing overlay in SW mode ([28378f7](https://github.com/vzhd1701/gridplayer/commit/28378f7f668436e4b05cf5d453e8bc3dd5abf0d4))
- Update icon for [ALL] ([c80c759](https://github.com/vzhd1701/gridplayer/commit/c80c759bc60052b408c30d2ebff661f208a4ec63))
- Use different font color for disabled context menu entries ([1ca5863](https://github.com/vzhd1701/gridplayer/commit/1ca58638604af1b7bb904bc4ba08506a03023699))

## [0.4.3] - 2022-07-18

### Fixed

- Update yt-dlp to 2022.07.18 ([b206753](https://github.com/vzhd1701/gridplayer/commit/b206753))
- Prevent video double initialization ([0e7824d](https://github.com/vzhd1701/gridplayer/commit/0e7824d))
- Add missing VLC plugins (Windows) ([c9ff21e](https://github.com/vzhd1701/gridplayer/commit/c9ff21e))

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

[Unreleased]: https://github.com/vzhd1701/gridplayer/compare/v0.5.5...HEAD
[0.5.5]: https://github.com/vzhd1701/gridplayer/compare/v0.5.4...v0.5.5
[0.5.4]: https://github.com/vzhd1701/gridplayer/compare/v0.5.3...v0.5.4
[0.5.3]: https://github.com/vzhd1701/gridplayer/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/vzhd1701/gridplayer/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/vzhd1701/gridplayer/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/vzhd1701/gridplayer/compare/v0.4.3...v0.5.0
[0.4.3]: https://github.com/vzhd1701/gridplayer/compare/v0.4.2...v0.4.3
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
