from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_SettingsDialog(object):
    def setupUi(self, SettingsDialog):
        SettingsDialog.setObjectName("SettingsDialog")
        SettingsDialog.resize(732, 451)
        SettingsDialog.setSizeGripEnabled(True)
        SettingsDialog.setModal(True)
        self.lay_main = QtWidgets.QVBoxLayout(SettingsDialog)
        self.lay_main.setSizeConstraint(QtWidgets.QLayout.SetMinimumSize)
        self.lay_main.setObjectName("lay_main")
        self.lay_main_2 = QtWidgets.QHBoxLayout()
        self.lay_main_2.setSpacing(12)
        self.lay_main_2.setObjectName("lay_main_2")
        self.section_index = QtWidgets.QListWidget(SettingsDialog)
        self.section_index.setMinimumSize(QtCore.QSize(200, 400))
        self.section_index.setMaximumSize(QtCore.QSize(200, 16777215))
        self.section_index.setObjectName("section_index")
        item = QtWidgets.QListWidgetItem()
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        item.setFont(font)
        item.setFlags(QtCore.Qt.NoItemFlags)
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        item.setFont(font)
        item.setFlags(QtCore.Qt.NoItemFlags)
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        item.setFont(font)
        item.setFlags(QtCore.Qt.NoItemFlags)
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        self.lay_main_2.addWidget(self.section_index)
        self.section_page = QtWidgets.QStackedWidget(SettingsDialog)
        self.section_page.setMinimumSize(QtCore.QSize(500, 0))
        self.section_page.setObjectName("section_page")
        self.page_general_player = QtWidgets.QWidget()
        self.page_general_player.setObjectName("page_general_player")
        self.lay_section_player = QtWidgets.QVBoxLayout(self.page_general_player)
        self.lay_section_player.setContentsMargins(0, 0, 0, 0)
        self.lay_section_player.setObjectName("lay_section_player")
        self.playerPauseBackgroundVideos = QtWidgets.QCheckBox(self.page_general_player)
        self.playerPauseBackgroundVideos.setObjectName("playerPauseBackgroundVideos")
        self.lay_section_player.addWidget(self.playerPauseBackgroundVideos)
        self.playerPauseWhenMinimized = QtWidgets.QCheckBox(self.page_general_player)
        self.playerPauseWhenMinimized.setObjectName("playerPauseWhenMinimized")
        self.lay_section_player.addWidget(self.playerPauseWhenMinimized)
        self.playerInhibitScreensaver = QtWidgets.QCheckBox(self.page_general_player)
        self.playerInhibitScreensaver.setObjectName("playerInhibitScreensaver")
        self.lay_section_player.addWidget(self.playerInhibitScreensaver)
        self.playerOneInstance = QtWidgets.QCheckBox(self.page_general_player)
        self.playerOneInstance.setObjectName("playerOneInstance")
        self.lay_section_player.addWidget(self.playerOneInstance)
        self.playerShowOverlayBorder = QtWidgets.QCheckBox(self.page_general_player)
        self.playerShowOverlayBorder.setObjectName("playerShowOverlayBorder")
        self.lay_section_player.addWidget(self.playerShowOverlayBorder)
        self.section_timeouts = QtWidgets.QLabel(self.page_general_player)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.section_timeouts.setFont(font)
        self.section_timeouts.setObjectName("section_timeouts")
        self.lay_section_player.addWidget(self.section_timeouts)
        self.formLayout_3 = QtWidgets.QFormLayout()
        self.formLayout_3.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_3.setObjectName("formLayout_3")
        self.timeoutOverlayFlag = QtWidgets.QCheckBox(self.page_general_player)
        self.timeoutOverlayFlag.setObjectName("timeoutOverlayFlag")
        self.formLayout_3.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.timeoutOverlayFlag
        )
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.timeoutOverlay = QtWidgets.QSpinBox(self.page_general_player)
        self.timeoutOverlay.setObjectName("timeoutOverlay")
        self.horizontalLayout_2.addWidget(self.timeoutOverlay)
        self.label_3 = QtWidgets.QLabel(self.page_general_player)
        self.label_3.setObjectName("label_3")
        self.horizontalLayout_2.addWidget(self.label_3)
        self.formLayout_3.setLayout(
            1, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_2
        )
        self.timeoutMouseHideFlag = QtWidgets.QCheckBox(self.page_general_player)
        self.timeoutMouseHideFlag.setObjectName("timeoutMouseHideFlag")
        self.formLayout_3.setWidget(
            2, QtWidgets.QFormLayout.LabelRole, self.timeoutMouseHideFlag
        )
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.timeoutMouseHide = QtWidgets.QSpinBox(self.page_general_player)
        self.timeoutMouseHide.setObjectName("timeoutMouseHide")
        self.horizontalLayout.addWidget(self.timeoutMouseHide)
        self.label_2 = QtWidgets.QLabel(self.page_general_player)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout.addWidget(self.label_2)
        self.formLayout_3.setLayout(
            2, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout
        )
        self.timeoutVideoInitLabel = QtWidgets.QLabel(self.page_general_player)
        self.timeoutVideoInitLabel.setObjectName("timeoutVideoInitLabel")
        self.formLayout_3.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.timeoutVideoInitLabel
        )
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.timeoutVideoInit = QtWidgets.QSpinBox(self.page_general_player)
        self.timeoutVideoInit.setObjectName("timeoutVideoInit")
        self.horizontalLayout_4.addWidget(self.timeoutVideoInit)
        self.label_7 = QtWidgets.QLabel(self.page_general_player)
        self.label_7.setObjectName("label_7")
        self.horizontalLayout_4.addWidget(self.label_7)
        self.formLayout_3.setLayout(
            0, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_4
        )
        self.lay_section_player.addLayout(self.formLayout_3)
        spacerItem = QtWidgets.QSpacerItem(
            20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_section_player.addItem(spacerItem)
        self.section_page.addWidget(self.page_general_player)
        self.page_general_language = QtWidgets.QWidget()
        self.page_general_language.setObjectName("page_general_language")
        self.lay_page_general_language = QtWidgets.QVBoxLayout(
            self.page_general_language
        )
        self.lay_page_general_language.setContentsMargins(0, 0, 0, 0)
        self.lay_page_general_language.setObjectName("lay_page_general_language")
        self.listLanguages = LanguageList(self.page_general_language)
        self.listLanguages.setObjectName("listLanguages")
        self.lay_page_general_language.addWidget(self.listLanguages)
        self.label_4 = QtWidgets.QLabel(self.page_general_language)
        self.label_4.setWordWrap(True)
        self.label_4.setOpenExternalLinks(True)
        self.label_4.setObjectName("label_4")
        self.lay_page_general_language.addWidget(self.label_4)
        self.section_page.addWidget(self.page_general_language)
        self.page_misc_streaming = QtWidgets.QWidget()
        self.page_misc_streaming.setObjectName("page_misc_streaming")
        self.lay_page_general_streams = QtWidgets.QVBoxLayout(self.page_misc_streaming)
        self.lay_page_general_streams.setContentsMargins(0, 0, 0, 0)
        self.lay_page_general_streams.setObjectName("lay_page_general_streams")
        self.streamingHLSVIAStreamlink = QtWidgets.QCheckBox(self.page_misc_streaming)
        self.streamingHLSVIAStreamlink.setObjectName("streamingHLSVIAStreamlink")
        self.lay_page_general_streams.addWidget(self.streamingHLSVIAStreamlink)
        self.formLayout_7 = QtWidgets.QFormLayout()
        self.formLayout_7.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_7.setObjectName("formLayout_7")
        self.label_8 = QtWidgets.QLabel(self.page_misc_streaming)
        self.label_8.setObjectName("label_8")
        self.formLayout_7.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_8)
        self.streamingResolverPriority = QtWidgets.QComboBox(self.page_misc_streaming)
        self.streamingResolverPriority.setObjectName("streamingResolverPriority")
        self.formLayout_7.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.streamingResolverPriority
        )
        self.lay_page_general_streams.addLayout(self.formLayout_7)
        self.label_10 = QtWidgets.QLabel(self.page_misc_streaming)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_10.setFont(font)
        self.label_10.setObjectName("label_10")
        self.lay_page_general_streams.addWidget(self.label_10)
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.streamingResolverPriorityPatterns = ResolverPatternsList(
            self.page_misc_streaming
        )
        self.streamingResolverPriorityPatterns.setObjectName(
            "streamingResolverPriorityPatterns"
        )
        self.verticalLayout.addWidget(self.streamingResolverPriorityPatterns)
        self.formLayout_8 = QtWidgets.QFormLayout()
        self.formLayout_8.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_8.setObjectName("formLayout_8")
        self.label_11 = QtWidgets.QLabel(self.page_misc_streaming)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_11.setFont(font)
        self.label_11.setObjectName("label_11")
        self.formLayout_8.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_11)
        self.streamingWildcardHelpButton = QtWidgets.QPushButton(
            self.page_misc_streaming
        )
        self.streamingWildcardHelpButton.setMaximumSize(QtCore.QSize(24, 24))
        self.streamingWildcardHelpButton.setText("?")
        self.streamingWildcardHelpButton.setObjectName("streamingWildcardHelpButton")
        self.formLayout_8.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.streamingWildcardHelpButton
        )
        self.verticalLayout.addLayout(self.formLayout_8)
        self.streamingWildcardHelp = QtWidgets.QLabel(self.page_misc_streaming)
        self.streamingWildcardHelp.setObjectName("streamingWildcardHelp")
        self.verticalLayout.addWidget(self.streamingWildcardHelp)
        self.verticalLayout.setStretch(0, 1)
        self.lay_page_general_streams.addLayout(self.verticalLayout)
        self.section_page.addWidget(self.page_misc_streaming)
        self.page_defaults_playlist = QtWidgets.QWidget()
        self.page_defaults_playlist.setObjectName("page_defaults_playlist")
        self.lay_page_defaults_playlist = QtWidgets.QVBoxLayout(
            self.page_defaults_playlist
        )
        self.lay_page_defaults_playlist.setContentsMargins(0, 0, 0, 0)
        self.lay_page_defaults_playlist.setObjectName("lay_page_defaults_playlist")
        self.playlistSaveWindow = QtWidgets.QCheckBox(self.page_defaults_playlist)
        self.playlistSaveWindow.setObjectName("playlistSaveWindow")
        self.lay_page_defaults_playlist.addWidget(self.playlistSaveWindow)
        self.playlistSavePosition = QtWidgets.QCheckBox(self.page_defaults_playlist)
        self.playlistSavePosition.setObjectName("playlistSavePosition")
        self.lay_page_defaults_playlist.addWidget(self.playlistSavePosition)
        self.playlistSaveState = QtWidgets.QCheckBox(self.page_defaults_playlist)
        self.playlistSaveState.setObjectName("playlistSaveState")
        self.lay_page_defaults_playlist.addWidget(self.playlistSaveState)
        self.playlistTrackChanges = QtWidgets.QCheckBox(self.page_defaults_playlist)
        self.playlistTrackChanges.setObjectName("playlistTrackChanges")
        self.lay_page_defaults_playlist.addWidget(self.playlistTrackChanges)
        self.playlistDisableClickPause = QtWidgets.QCheckBox(
            self.page_defaults_playlist
        )
        self.playlistDisableClickPause.setObjectName("playlistDisableClickPause")
        self.lay_page_defaults_playlist.addWidget(self.playlistDisableClickPause)
        self.playlistDisableWheelSeek = QtWidgets.QCheckBox(self.page_defaults_playlist)
        self.playlistDisableWheelSeek.setObjectName("playlistDisableWheelSeek")
        self.lay_page_defaults_playlist.addWidget(self.playlistDisableWheelSeek)
        self.formLayout_2 = QtWidgets.QFormLayout()
        self.formLayout_2.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_2.setObjectName("formLayout_2")
        self.playlistSeekSyncModeLabel = QtWidgets.QLabel(self.page_defaults_playlist)
        self.playlistSeekSyncModeLabel.setObjectName("playlistSeekSyncModeLabel")
        self.formLayout_2.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.playlistSeekSyncModeLabel
        )
        self.playlistSeekSyncMode = QtWidgets.QComboBox(self.page_defaults_playlist)
        self.playlistSeekSyncMode.setObjectName("playlistSeekSyncMode")
        self.formLayout_2.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.playlistSeekSyncMode
        )
        self.lay_page_defaults_playlist.addLayout(self.formLayout_2)
        self.label = QtWidgets.QLabel(self.page_defaults_playlist)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label.setFont(font)
        self.label.setObjectName("label")
        self.lay_page_defaults_playlist.addWidget(self.label)
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        self.formLayout.setObjectName("formLayout")
        self.gridModeLabel = QtWidgets.QLabel(self.page_defaults_playlist)
        self.gridModeLabel.setObjectName("gridModeLabel")
        self.formLayout.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.gridModeLabel
        )
        self.gridMode = QtWidgets.QComboBox(self.page_defaults_playlist)
        self.gridMode.setObjectName("gridMode")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.gridMode)
        self.gridSizeLabel = QtWidgets.QLabel(self.page_defaults_playlist)
        self.gridSizeLabel.setObjectName("gridSizeLabel")
        self.formLayout.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.gridSizeLabel
        )
        self.gridSize = QtWidgets.QSpinBox(self.page_defaults_playlist)
        self.gridSize.setObjectName("gridSize")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.gridSize)
        self.lay_page_defaults_playlist.addLayout(self.formLayout)
        self.gridFit = QtWidgets.QCheckBox(self.page_defaults_playlist)
        self.gridFit.setObjectName("gridFit")
        self.lay_page_defaults_playlist.addWidget(self.gridFit)
        self.gridShuffleOnLoad = QtWidgets.QCheckBox(self.page_defaults_playlist)
        self.gridShuffleOnLoad.setObjectName("gridShuffleOnLoad")
        self.lay_page_defaults_playlist.addWidget(self.gridShuffleOnLoad)
        spacerItem1 = QtWidgets.QSpacerItem(
            20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_page_defaults_playlist.addItem(spacerItem1)
        self.section_page.addWidget(self.page_defaults_playlist)
        self.page_defaults_video = QtWidgets.QWidget()
        self.page_defaults_video.setObjectName("page_defaults_video")
        self.lay_page_defaults_video = QtWidgets.QVBoxLayout(self.page_defaults_video)
        self.lay_page_defaults_video.setContentsMargins(0, 0, 0, 0)
        self.lay_page_defaults_video.setObjectName("lay_page_defaults_video")
        self.formLayout_4 = QtWidgets.QFormLayout()
        self.formLayout_4.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_4.setObjectName("formLayout_4")
        self.videoAspectLabel = QtWidgets.QLabel(self.page_defaults_video)
        self.videoAspectLabel.setObjectName("videoAspectLabel")
        self.formLayout_4.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.videoAspectLabel
        )
        self.videoAspect = QtWidgets.QComboBox(self.page_defaults_video)
        self.videoAspect.setObjectName("videoAspect")
        self.formLayout_4.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.videoAspect
        )
        self.repeatModeLabel = QtWidgets.QLabel(self.page_defaults_video)
        self.repeatModeLabel.setObjectName("repeatModeLabel")
        self.formLayout_4.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.repeatModeLabel
        )
        self.repeatMode = QtWidgets.QComboBox(self.page_defaults_video)
        self.repeatMode.setObjectName("repeatMode")
        self.formLayout_4.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.repeatMode)
        self.lay_page_defaults_video.addLayout(self.formLayout_4)
        self.videoRandomLoop = QtWidgets.QCheckBox(self.page_defaults_video)
        self.videoRandomLoop.setObjectName("videoRandomLoop")
        self.lay_page_defaults_video.addWidget(self.videoRandomLoop)
        self.videoPaused = QtWidgets.QCheckBox(self.page_defaults_video)
        self.videoPaused.setObjectName("videoPaused")
        self.lay_page_defaults_video.addWidget(self.videoPaused)
        self.videoMuted = QtWidgets.QCheckBox(self.page_defaults_video)
        self.videoMuted.setObjectName("videoMuted")
        self.lay_page_defaults_video.addWidget(self.videoMuted)
        self.label_12 = QtWidgets.QLabel(self.page_defaults_video)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_12.setFont(font)
        self.label_12.setObjectName("label_12")
        self.lay_page_defaults_video.addWidget(self.label_12)
        self.formLayout_9 = QtWidgets.QFormLayout()
        self.formLayout_9.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_9.setObjectName("formLayout_9")
        self.streamQualityLabel = QtWidgets.QLabel(self.page_defaults_video)
        self.streamQualityLabel.setObjectName("streamQualityLabel")
        self.formLayout_9.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.streamQualityLabel
        )
        self.streamQuality = QtWidgets.QComboBox(self.page_defaults_video)
        self.streamQuality.setObjectName("streamQuality")
        self.formLayout_9.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.streamQuality
        )
        self.label_13 = QtWidgets.QLabel(self.page_defaults_video)
        self.label_13.setObjectName("label_13")
        self.formLayout_9.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.label_13)
        self.horizontalLayout_5 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.streamAutoReloadTimer = QtWidgets.QSpinBox(self.page_defaults_video)
        self.streamAutoReloadTimer.setObjectName("streamAutoReloadTimer")
        self.horizontalLayout_5.addWidget(self.streamAutoReloadTimer)
        self.label_14 = QtWidgets.QLabel(self.page_defaults_video)
        self.label_14.setObjectName("label_14")
        self.horizontalLayout_5.addWidget(self.label_14)
        self.formLayout_9.setLayout(
            1, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_5
        )
        self.lay_page_defaults_video.addLayout(self.formLayout_9)
        spacerItem2 = QtWidgets.QSpacerItem(
            20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_page_defaults_video.addItem(spacerItem2)
        self.section_page.addWidget(self.page_defaults_video)
        self.page_misc_advanced = QtWidgets.QWidget()
        self.page_misc_advanced.setObjectName("page_misc_advanced")
        self.lay_page_misc_advanced = QtWidgets.QVBoxLayout(self.page_misc_advanced)
        self.lay_page_misc_advanced.setContentsMargins(0, 0, 0, 0)
        self.lay_page_misc_advanced.setObjectName("lay_page_misc_advanced")
        self.playerVideoDriverBox = QtWidgets.QGroupBox(self.page_misc_advanced)
        self.playerVideoDriverBox.setMaximumSize(QtCore.QSize(250, 16777215))
        self.playerVideoDriverBox.setObjectName("playerVideoDriverBox")
        self.lay_playerVideoDriverBox = QtWidgets.QVBoxLayout(self.playerVideoDriverBox)
        self.lay_playerVideoDriverBox.setObjectName("lay_playerVideoDriverBox")
        self.playerVideoDriver = QtWidgets.QComboBox(self.playerVideoDriverBox)
        self.playerVideoDriver.setObjectName("playerVideoDriver")
        self.lay_playerVideoDriverBox.addWidget(self.playerVideoDriver)
        self.lay_playerVideoDriverPlayers = QtWidgets.QHBoxLayout()
        self.lay_playerVideoDriverPlayers.setObjectName("lay_playerVideoDriverPlayers")
        self.playerVideoDriverPlayersLabel = QtWidgets.QLabel(self.playerVideoDriverBox)
        self.playerVideoDriverPlayersLabel.setObjectName(
            "playerVideoDriverPlayersLabel"
        )
        self.lay_playerVideoDriverPlayers.addWidget(self.playerVideoDriverPlayersLabel)
        self.playerVideoDriverPlayers = QtWidgets.QSpinBox(self.playerVideoDriverBox)
        self.playerVideoDriverPlayers.setObjectName("playerVideoDriverPlayers")
        self.lay_playerVideoDriverPlayers.addWidget(self.playerVideoDriverPlayers)
        self.lay_playerVideoDriverPlayers.setStretch(0, 1)
        self.lay_playerVideoDriverBox.addLayout(self.lay_playerVideoDriverPlayers)
        self.lay_page_misc_advanced.addWidget(self.playerVideoDriverBox)
        self.label_9 = QtWidgets.QLabel(self.page_misc_advanced)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_9.setFont(font)
        self.label_9.setObjectName("label_9")
        self.lay_page_misc_advanced.addWidget(self.label_9)
        self.miscVLCOptions = QtWidgets.QLineEdit(self.page_misc_advanced)
        self.miscVLCOptions.setObjectName("miscVLCOptions")
        self.lay_page_misc_advanced.addWidget(self.miscVLCOptions)
        self.section_misc = QtWidgets.QLabel(self.page_misc_advanced)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.section_misc.setFont(font)
        self.section_misc.setObjectName("section_misc")
        self.lay_page_misc_advanced.addWidget(self.section_misc)
        self.miscOpaqueHWOverlay = QtWidgets.QCheckBox(self.page_misc_advanced)
        self.miscOpaqueHWOverlay.setObjectName("miscOpaqueHWOverlay")
        self.lay_page_misc_advanced.addWidget(self.miscOpaqueHWOverlay)
        self.miscFakeOverlayInvisibility = QtWidgets.QCheckBox(self.page_misc_advanced)
        self.miscFakeOverlayInvisibility.setObjectName("miscFakeOverlayInvisibility")
        self.lay_page_misc_advanced.addWidget(self.miscFakeOverlayInvisibility)
        spacerItem3 = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_page_misc_advanced.addItem(spacerItem3)
        self.section_page.addWidget(self.page_misc_advanced)
        self.page_misc_logging = QtWidgets.QWidget()
        self.page_misc_logging.setObjectName("page_misc_logging")
        self.lay_page_misc_logging = QtWidgets.QVBoxLayout(self.page_misc_logging)
        self.lay_page_misc_logging.setContentsMargins(0, 0, 0, 0)
        self.lay_page_misc_logging.setObjectName("lay_page_misc_logging")
        self.logLimit = QtWidgets.QCheckBox(self.page_misc_logging)
        self.logLimit.setObjectName("logLimit")
        self.lay_page_misc_logging.addWidget(self.logLimit)
        self.formLayout_6 = QtWidgets.QFormLayout()
        self.formLayout_6.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_6.setObjectName("formLayout_6")
        self.logLimitSizeLabel = QtWidgets.QLabel(self.page_misc_logging)
        self.logLimitSizeLabel.setObjectName("logLimitSizeLabel")
        self.formLayout_6.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.logLimitSizeLabel
        )
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.logLimitSize = QtWidgets.QSpinBox(self.page_misc_logging)
        self.logLimitSize.setObjectName("logLimitSize")
        self.horizontalLayout_3.addWidget(self.logLimitSize)
        self.label_5 = QtWidgets.QLabel(self.page_misc_logging)
        self.label_5.setObjectName("label_5")
        self.horizontalLayout_3.addWidget(self.label_5)
        self.formLayout_6.setLayout(
            0, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_3
        )
        self.logLimitBackupsLabel = QtWidgets.QLabel(self.page_misc_logging)
        self.logLimitBackupsLabel.setObjectName("logLimitBackupsLabel")
        self.formLayout_6.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.logLimitBackupsLabel
        )
        self.logLimitBackups = QtWidgets.QSpinBox(self.page_misc_logging)
        self.logLimitBackups.setObjectName("logLimitBackups")
        self.formLayout_6.setWidget(
            1, QtWidgets.QFormLayout.FieldRole, self.logLimitBackups
        )
        self.lay_page_misc_logging.addLayout(self.formLayout_6)
        self.label_6 = QtWidgets.QLabel(self.page_misc_logging)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_6.setFont(font)
        self.label_6.setObjectName("label_6")
        self.lay_page_misc_logging.addWidget(self.label_6)
        self.formLayout_5 = QtWidgets.QFormLayout()
        self.formLayout_5.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_5.setObjectName("formLayout_5")
        self.logLevelLabel = QtWidgets.QLabel(self.page_misc_logging)
        self.logLevelLabel.setObjectName("logLevelLabel")
        self.formLayout_5.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.logLevelLabel
        )
        self.logLevel = QtWidgets.QComboBox(self.page_misc_logging)
        self.logLevel.setObjectName("logLevel")
        self.formLayout_5.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.logLevel)
        self.logLevelVLCLabel = QtWidgets.QLabel(self.page_misc_logging)
        self.logLevelVLCLabel.setObjectName("logLevelVLCLabel")
        self.formLayout_5.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.logLevelVLCLabel
        )
        self.logLevelVLC = QtWidgets.QComboBox(self.page_misc_logging)
        self.logLevelVLC.setObjectName("logLevelVLC")
        self.formLayout_5.setWidget(
            1, QtWidgets.QFormLayout.FieldRole, self.logLevelVLC
        )
        self.lay_page_misc_logging.addLayout(self.formLayout_5)
        spacerItem4 = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_page_misc_logging.addItem(spacerItem4)
        self.section_page.addWidget(self.page_misc_logging)
        self.lay_main_2.addWidget(self.section_page)
        self.lay_main.addLayout(self.lay_main_2)
        self.lay_buttons = QtWidgets.QHBoxLayout()
        self.lay_buttons.setSpacing(0)
        self.lay_buttons.setObjectName("lay_buttons")
        self.logFileOpen = QtWidgets.QPushButton(SettingsDialog)
        self.logFileOpen.setMinimumSize(QtCore.QSize(130, 0))
        self.logFileOpen.setObjectName("logFileOpen")
        self.lay_buttons.addWidget(self.logFileOpen)
        self.buttonBox = QtWidgets.QDialogButtonBox(SettingsDialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(
            QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Ok
        )
        self.buttonBox.setObjectName("buttonBox")
        self.lay_buttons.addWidget(self.buttonBox)
        self.lay_main.addLayout(self.lay_buttons)
        self.lay_main.setStretch(0, 1)

        self.retranslateUi(SettingsDialog)
        self.section_page.setCurrentIndex(0)
        self.buttonBox.accepted.connect(SettingsDialog.accept)  # type: ignore
        self.buttonBox.rejected.connect(SettingsDialog.reject)  # type: ignore
        QtCore.QMetaObject.connectSlotsByName(SettingsDialog)

    def retranslateUi(self, SettingsDialog):
        _translate = QtCore.QCoreApplication.translate
        SettingsDialog.setWindowTitle(_translate("SettingsDialog", "Settings"))
        __sortingEnabled = self.section_index.isSortingEnabled()
        self.section_index.setSortingEnabled(False)
        item = self.section_index.item(0)
        item.setText(_translate("SettingsDialog", "General"))
        item = self.section_index.item(1)
        item.setText(_translate("SettingsDialog", "Player"))
        item = self.section_index.item(2)
        item.setText(_translate("SettingsDialog", "Language"))
        item = self.section_index.item(3)
        item.setText(_translate("SettingsDialog", "Defaults"))
        item = self.section_index.item(4)
        item.setText(_translate("SettingsDialog", "Playlist"))
        item = self.section_index.item(5)
        item.setText(_translate("SettingsDialog", "Video"))
        item = self.section_index.item(6)
        item.setText(_translate("SettingsDialog", "Miscellaneous"))
        item = self.section_index.item(7)
        item.setText(_translate("SettingsDialog", "Streaming"))
        item = self.section_index.item(8)
        item.setText(_translate("SettingsDialog", "Logging"))
        item = self.section_index.item(9)
        item.setText(_translate("SettingsDialog", "Advanced"))
        self.section_index.setSortingEnabled(__sortingEnabled)
        self.playerPauseBackgroundVideos.setText(
            _translate("SettingsDialog", "Pause background videos on single mode")
        )
        self.playerPauseWhenMinimized.setText(
            _translate("SettingsDialog", "Pause videos when minimized")
        )
        self.playerInhibitScreensaver.setText(
            _translate("SettingsDialog", "Disable screensaver while playing")
        )
        self.playerOneInstance.setText(
            _translate("SettingsDialog", "Allow only one instance")
        )
        self.playerShowOverlayBorder.setText(
            _translate("SettingsDialog", "Show overlay border for active video")
        )
        self.section_timeouts.setText(_translate("SettingsDialog", "Timeouts"))
        self.timeoutOverlayFlag.setText(
            _translate("SettingsDialog", "Hide overlay after timeout")
        )
        self.label_3.setText(_translate("SettingsDialog", "(sec)"))
        self.timeoutMouseHideFlag.setText(
            _translate("SettingsDialog", "Hide mouse after timeout")
        )
        self.label_2.setText(_translate("SettingsDialog", "(sec)"))
        self.timeoutVideoInitLabel.setText(
            _translate("SettingsDialog", "Video initialization timeout")
        )
        self.label_7.setText(_translate("SettingsDialog", "(sec)"))
        self.label_4.setText(
            _translate(
                "SettingsDialog",
                '<p>If you have a handful of free time and a desire to support this project, please <a href="https://crowdin.com/project/gridplayer">help with the translation</a>. No coding skills or special software is required!</p>',
            )
        )
        self.streamingHLSVIAStreamlink.setText(
            _translate("SettingsDialog", "Use Streamlink for HLS streams when possible")
        )
        self.label_8.setText(_translate("SettingsDialog", "Priority URL resolver"))
        self.label_10.setText(
            _translate("SettingsDialog", "Resolver priority patterns")
        )
        self.label_11.setText(_translate("SettingsDialog", "Wildcard syntax"))
        self.streamingWildcardHelp.setText(
            _translate(
                "SettingsDialog",
                "<p><b>The asterisk</b> * matches zero or more characters.<br>\n"
                "<b>The question mark</b> ? matches exactly one character.</p>\n"
                "<p><i>For Host Wildcard only:</i><br>\n"
                "*.example.com will match both example.com and www.example.com<br>\n"
                "**.example.com will match subdomains <b>only</b></p>",
            )
        )
        self.playlistSaveWindow.setText(
            _translate("SettingsDialog", "Save window position and size")
        )
        self.playlistSavePosition.setText(
            _translate("SettingsDialog", "Save videos playback position")
        )
        self.playlistSaveState.setText(
            _translate("SettingsDialog", "Save videos playing / paused status")
        )
        self.playlistTrackChanges.setText(
            _translate("SettingsDialog", "Warn about unsaved changes")
        )
        self.playlistDisableClickPause.setText(
            _translate("SettingsDialog", "Disable pause with left mouse click")
        )
        self.playlistDisableWheelSeek.setText(
            _translate("SettingsDialog", "Disable seek with mouse wheel")
        )
        self.playlistSeekSyncModeLabel.setText(
            _translate("SettingsDialog", "Seek sync mode")
        )
        self.label.setText(_translate("SettingsDialog", "Grid"))
        self.gridModeLabel.setText(_translate("SettingsDialog", "Grid mode"))
        self.gridSizeLabel.setText(_translate("SettingsDialog", "Grid size"))
        self.gridFit.setText(_translate("SettingsDialog", "Fit grid cells"))
        self.gridShuffleOnLoad.setText(_translate("SettingsDialog", "Shuffle on load"))
        self.videoAspectLabel.setText(_translate("SettingsDialog", "Aspect mode"))
        self.repeatModeLabel.setText(_translate("SettingsDialog", "Repeat mode"))
        self.videoRandomLoop.setText(
            _translate("SettingsDialog", "Start at random position")
        )
        self.videoPaused.setText(_translate("SettingsDialog", "Paused"))
        self.videoMuted.setText(_translate("SettingsDialog", "Muted"))
        self.label_12.setText(_translate("SettingsDialog", "Streaming Videos"))
        self.streamQualityLabel.setText(_translate("SettingsDialog", "Stream quality"))
        self.label_13.setText(_translate("SettingsDialog", "Auto reload time"))
        self.label_14.setText(_translate("SettingsDialog", "(min)"))
        self.playerVideoDriverBox.setTitle(
            _translate("SettingsDialog", "Video Decoder")
        )
        self.playerVideoDriverPlayersLabel.setText(
            _translate("SettingsDialog", "Videos per process")
        )
        self.label_9.setText(
            _translate(
                "SettingsDialog",
                'VLC Options [<a href="https://wiki.videolan.org/VLC_command-line_help/">reference</a>]',
            )
        )
        self.section_misc.setText(_translate("SettingsDialog", "Experimental"))
        self.miscOpaqueHWOverlay.setText(
            _translate("SettingsDialog", "Opaque overlay (fix black screen)")
        )
        self.miscFakeOverlayInvisibility.setText(
            _translate(
                "SettingsDialog",
                "Fake overlay invisibility (fix overlay on top of other windows)",
            )
        )
        self.logLimit.setText(_translate("SettingsDialog", "Limit log file size"))
        self.logLimitSizeLabel.setText(_translate("SettingsDialog", "Log file size"))
        self.label_5.setText(_translate("SettingsDialog", "MB"))
        self.logLimitBackupsLabel.setText(
            _translate("SettingsDialog", "Log files to keep")
        )
        self.label_6.setText(_translate("SettingsDialog", "Logging levels"))
        self.logLevelLabel.setText(_translate("SettingsDialog", "Log level"))
        self.logLevelVLCLabel.setText(_translate("SettingsDialog", "Log level (VLC)"))
        self.logFileOpen.setText(_translate("SettingsDialog", "Open log file"))


from gridplayer.widgets.language_list import LanguageList
from gridplayer.widgets.resolver_patterns_list import ResolverPatternsList
