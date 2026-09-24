from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_SettingsDialog:
    def setupUi(self, SettingsDialog):
        SettingsDialog.setObjectName("SettingsDialog")
        SettingsDialog.setSizeGripEnabled(True)
        SettingsDialog.setModal(True)
        self.lay_main = QtWidgets.QVBoxLayout(SettingsDialog)
        self.lay_main.setSizeConstraint(QtWidgets.QLayout.SetDefaultConstraint)
        self.lay_main.setObjectName("lay_main")
        self.lay_main_2 = QtWidgets.QHBoxLayout()
        self.lay_main_2.setSpacing(12)
        self.lay_main_2.setObjectName("lay_main_2")
        self.section_index = QtWidgets.QListWidget(SettingsDialog)
        self.section_index.setMinimumSize(QtCore.QSize(200, 350))
        self.section_index.setMaximumSize(QtCore.QSize(200, 16777215))
        self.section_index.setObjectName("section_index")
        item = QtWidgets.QListWidgetItem()
        font = QtGui.QFont()
        font.setBold(True)
        item.setFont(font)
        item.setFlags(QtCore.Qt.NoItemFlags)
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        font = QtGui.QFont()
        font.setBold(True)
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
        item.setFont(font)
        item.setFlags(QtCore.Qt.NoItemFlags)
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        font = QtGui.QFont()
        font.setBold(True)
        item.setFont(font)
        item.setFlags(QtCore.Qt.NoItemFlags)
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        item = QtWidgets.QListWidgetItem()
        self.section_index.addItem(item)
        self.lay_main_2.addWidget(self.section_index)
        self.section_page = CurrentPageStackedWidget(SettingsDialog)
        self.section_page.setMinimumSize(QtCore.QSize(500, 0))
        self.section_page.setObjectName("section_page")
        self.page_general_player = QtWidgets.QWidget()
        self.page_general_player.setObjectName("page_general_player")
        self.lay_section_player = QtWidgets.QVBoxLayout(self.page_general_player)
        self.lay_section_player.setContentsMargins(0, 0, 0, 0)
        self.lay_section_player.setObjectName("lay_section_player")
        self.formLayout_color_scheme = QtWidgets.QFormLayout()
        self.formLayout_color_scheme.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_color_scheme.setObjectName("formLayout_color_scheme")
        self.playerColorSchemeLabel = QtWidgets.QLabel(self.page_general_player)
        self.playerColorSchemeLabel.setObjectName("playerColorSchemeLabel")
        self.formLayout_color_scheme.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.playerColorSchemeLabel
        )
        self.playerColorScheme = QtWidgets.QComboBox(self.page_general_player)
        self.playerColorScheme.setObjectName("playerColorScheme")
        self.formLayout_color_scheme.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.playerColorScheme
        )
        self.lay_section_player.addLayout(self.formLayout_color_scheme)
        self.playerOneInstance = QtWidgets.QCheckBox(self.page_general_player)
        self.playerOneInstance.setObjectName("playerOneInstance")
        self.lay_section_player.addWidget(self.playerOneInstance)
        self.playerStayOnTop = QtWidgets.QCheckBox(self.page_general_player)
        self.playerStayOnTop.setObjectName("playerStayOnTop")
        self.lay_section_player.addWidget(self.playerStayOnTop)
        self.playerStartMaximized = QtWidgets.QCheckBox(self.page_general_player)
        self.playerStartMaximized.setObjectName("playerStartMaximized")
        self.lay_section_player.addWidget(self.playerStartMaximized)
        self.playerStartFullscreen = QtWidgets.QCheckBox(self.page_general_player)
        self.playerStartFullscreen.setObjectName("playerStartFullscreen")
        self.lay_section_player.addWidget(self.playerStartFullscreen)
        self.playerInhibitScreensaver = QtWidgets.QCheckBox(self.page_general_player)
        self.playerInhibitScreensaver.setObjectName("playerInhibitScreensaver")
        self.lay_section_player.addWidget(self.playerInhibitScreensaver)
        self.formLayout_10 = QtWidgets.QFormLayout()
        self.formLayout_10.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_10.setObjectName("formLayout_10")
        self.playerRecentList = QtWidgets.QCheckBox(self.page_general_player)
        self.playerRecentList.setObjectName("playerRecentList")
        self.formLayout_10.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.playerRecentList
        )
        self.horizontalLayout_6 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.playerRecentListSize = QtWidgets.QSpinBox(self.page_general_player)
        self.playerRecentListSize.setObjectName("playerRecentListSize")
        self.horizontalLayout_6.addWidget(self.playerRecentListSize)
        self.label_16 = QtWidgets.QLabel(self.page_general_player)
        self.label_16.setObjectName("label_16")
        self.horizontalLayout_6.addWidget(self.label_16)
        self.formLayout_10.setLayout(
            0, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_6
        )
        self.lay_section_player.addLayout(self.formLayout_10)
        self.section_timeouts = QtWidgets.QLabel(self.page_general_player)
        font = QtGui.QFont()
        font.setBold(True)
        self.section_timeouts.setFont(font)
        self.section_timeouts.setObjectName("section_timeouts")
        self.lay_section_player.addWidget(self.section_timeouts)
        self.formLayout_3 = QtWidgets.QFormLayout()
        self.formLayout_3.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_3.setObjectName("formLayout_3")
        self.timeoutMouseHideFlag = QtWidgets.QCheckBox(self.page_general_player)
        self.timeoutMouseHideFlag.setObjectName("timeoutMouseHideFlag")
        self.formLayout_3.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.timeoutMouseHideFlag
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
            1, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout
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
        self.section_screenshots = QtWidgets.QLabel(self.page_general_player)
        font = QtGui.QFont()
        font.setBold(True)
        self.section_screenshots.setFont(font)
        self.section_screenshots.setObjectName("section_screenshots")
        self.lay_section_player.addWidget(self.section_screenshots)
        self.formLayout_screenshots = QtWidgets.QFormLayout()
        self.formLayout_screenshots.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_screenshots.setObjectName("formLayout_screenshots")
        self.screenshotsDirLabel = QtWidgets.QLabel(self.page_general_player)
        self.screenshotsDirLabel.setObjectName("screenshotsDirLabel")
        self.formLayout_screenshots.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.screenshotsDirLabel
        )
        self.lay_screenshots_dir = QtWidgets.QHBoxLayout()
        self.lay_screenshots_dir.setObjectName("lay_screenshots_dir")
        self.screenshotsDir = QtWidgets.QLineEdit(self.page_general_player)
        self.screenshotsDir.setMinimumSize(QtCore.QSize(260, 0))
        self.screenshotsDir.setObjectName("screenshotsDir")
        self.lay_screenshots_dir.addWidget(self.screenshotsDir)
        self.screenshotsDirBrowse = QtWidgets.QPushButton(self.page_general_player)
        self.screenshotsDirBrowse.setObjectName("screenshotsDirBrowse")
        self.lay_screenshots_dir.addWidget(self.screenshotsDirBrowse)
        self.formLayout_screenshots.setLayout(
            0, QtWidgets.QFormLayout.FieldRole, self.lay_screenshots_dir
        )
        self.screenshotsFilenameTemplateLabel = QtWidgets.QLabel(
            self.page_general_player
        )
        self.screenshotsFilenameTemplateLabel.setObjectName(
            "screenshotsFilenameTemplateLabel"
        )
        self.formLayout_screenshots.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.screenshotsFilenameTemplateLabel
        )
        self.lay_screenshots_template = QtWidgets.QHBoxLayout()
        self.lay_screenshots_template.setObjectName("lay_screenshots_template")
        self.screenshotsFilenameTemplate = QtWidgets.QLineEdit(self.page_general_player)
        self.screenshotsFilenameTemplate.setMinimumSize(QtCore.QSize(260, 0))
        self.screenshotsFilenameTemplate.setObjectName("screenshotsFilenameTemplate")
        self.lay_screenshots_template.addWidget(self.screenshotsFilenameTemplate)
        self.screenshotsFilenameTemplateHelpButton = QtWidgets.QPushButton(
            self.page_general_player
        )
        self.screenshotsFilenameTemplateHelpButton.setMaximumSize(QtCore.QSize(24, 24))
        self.screenshotsFilenameTemplateHelpButton.setText("?")
        self.screenshotsFilenameTemplateHelpButton.setObjectName(
            "screenshotsFilenameTemplateHelpButton"
        )
        self.lay_screenshots_template.addWidget(
            self.screenshotsFilenameTemplateHelpButton
        )
        self.formLayout_screenshots.setLayout(
            1, QtWidgets.QFormLayout.FieldRole, self.lay_screenshots_template
        )
        self.screenshotsFormatLabel = QtWidgets.QLabel(self.page_general_player)
        self.screenshotsFormatLabel.setObjectName("screenshotsFormatLabel")
        self.formLayout_screenshots.setWidget(
            2, QtWidgets.QFormLayout.LabelRole, self.screenshotsFormatLabel
        )
        self.lay_screenshots_format = QtWidgets.QHBoxLayout()
        self.lay_screenshots_format.setObjectName("lay_screenshots_format")
        self.screenshotsFormat = QtWidgets.QComboBox(self.page_general_player)
        self.screenshotsFormat.setObjectName("screenshotsFormat")
        self.lay_screenshots_format.addWidget(self.screenshotsFormat)
        self.screenshotsJPGQualityLabel = QtWidgets.QLabel(self.page_general_player)
        self.screenshotsJPGQualityLabel.setObjectName("screenshotsJPGQualityLabel")
        self.lay_screenshots_format.addWidget(self.screenshotsJPGQualityLabel)
        self.screenshotsJPGQuality = QtWidgets.QSpinBox(self.page_general_player)
        self.screenshotsJPGQuality.setObjectName("screenshotsJPGQuality")
        self.lay_screenshots_format.addWidget(self.screenshotsJPGQuality)
        self.formLayout_screenshots.setLayout(
            2, QtWidgets.QFormLayout.FieldRole, self.lay_screenshots_format
        )
        self.lay_section_player.addLayout(self.formLayout_screenshots)
        spacerItem = QtWidgets.QSpacerItem(
            20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_section_player.addItem(spacerItem)
        self.section_page.addWidget(self.page_general_player)
        self.page_subtitle_style = PageScrollArea()
        self.page_subtitle_style.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.page_subtitle_style.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        self.page_subtitle_style.setWidgetResizable(True)
        self.page_subtitle_style.setObjectName("page_subtitle_style")
        self.page_subtitle_style_contents = QtWidgets.QWidget()
        self.page_subtitle_style_contents.setObjectName("page_subtitle_style_contents")
        self.page_subtitle_style.setWidget(self.page_subtitle_style_contents)
        self.section_page.addWidget(self.page_subtitle_style)
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
        self.page_general_shortcuts = QtWidgets.QWidget()
        self.page_general_shortcuts.setObjectName("page_general_shortcuts")
        self.lay_page_general_shortcuts = QtWidgets.QVBoxLayout(
            self.page_general_shortcuts
        )
        self.lay_page_general_shortcuts.setContentsMargins(0, 0, 0, 0)
        self.lay_page_general_shortcuts.setObjectName("lay_page_general_shortcuts")
        self.keymapEditor = KeymapEditor(self.page_general_shortcuts)
        self.keymapEditor.setObjectName("keymapEditor")
        self.lay_page_general_shortcuts.addWidget(self.keymapEditor)
        self.section_page.addWidget(self.page_general_shortcuts)
        self.page_streaming_resolution = QtWidgets.QWidget()
        self.page_streaming_resolution.setObjectName("page_streaming_resolution")
        self.lay_page_streaming_resolution = QtWidgets.QVBoxLayout(
            self.page_streaming_resolution
        )
        self.lay_page_streaming_resolution.setContentsMargins(0, 0, 0, 0)
        self.lay_page_streaming_resolution.setObjectName(
            "lay_page_streaming_resolution"
        )
        self.streamingHLSVIAStreamlink = QtWidgets.QCheckBox(
            self.page_streaming_resolution
        )
        self.streamingHLSVIAStreamlink.setObjectName("streamingHLSVIAStreamlink")
        self.lay_page_streaming_resolution.addWidget(self.streamingHLSVIAStreamlink)
        self.formLayout_7 = QtWidgets.QFormLayout()
        self.formLayout_7.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_7.setObjectName("formLayout_7")
        self.label_8 = QtWidgets.QLabel(self.page_streaming_resolution)
        self.label_8.setObjectName("label_8")
        self.formLayout_7.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_8)
        self.streamingResolverPriority = QtWidgets.QComboBox(
            self.page_streaming_resolution
        )
        self.streamingResolverPriority.setObjectName("streamingResolverPriority")
        self.formLayout_7.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.streamingResolverPriority
        )
        self.lay_page_streaming_resolution.addLayout(self.formLayout_7)
        self.label_ytdlp = QtWidgets.QLabel(self.page_streaming_resolution)
        font = QtGui.QFont()
        font.setBold(True)
        self.label_ytdlp.setFont(font)
        self.label_ytdlp.setText("yt-dlp")
        self.label_ytdlp.setObjectName("label_ytdlp")
        self.lay_page_streaming_resolution.addWidget(self.label_ytdlp)
        self.formLayout_ytdlp = QtWidgets.QFormLayout()
        self.formLayout_ytdlp.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_ytdlp.setObjectName("formLayout_ytdlp")
        self.label_js_runtime = QtWidgets.QLabel(self.page_streaming_resolution)
        self.label_js_runtime.setObjectName("label_js_runtime")
        self.formLayout_ytdlp.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.label_js_runtime
        )
        self.streamingJSRuntimePath = QtWidgets.QLineEdit(
            self.page_streaming_resolution
        )
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.streamingJSRuntimePath.sizePolicy().hasHeightForWidth()
        )
        self.streamingJSRuntimePath.setSizePolicy(sizePolicy)
        self.streamingJSRuntimePath.setMinimumSize(QtCore.QSize(260, 0))
        self.streamingJSRuntimePath.setObjectName("streamingJSRuntimePath")
        self.formLayout_ytdlp.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.streamingJSRuntimePath
        )
        self.lay_ytdlp_test = QtWidgets.QHBoxLayout()
        self.lay_ytdlp_test.setObjectName("lay_ytdlp_test")
        self.streamingTestButton = QtWidgets.QPushButton(self.page_streaming_resolution)
        self.streamingTestButton.setObjectName("streamingTestButton")
        self.lay_ytdlp_test.addWidget(self.streamingTestButton)
        spacerItem1 = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )
        self.lay_ytdlp_test.addItem(spacerItem1)
        self.formLayout_ytdlp.setLayout(
            1, QtWidgets.QFormLayout.SpanningRole, self.lay_ytdlp_test
        )
        self.lay_page_streaming_resolution.addLayout(self.formLayout_ytdlp)
        self.label_10 = QtWidgets.QLabel(self.page_streaming_resolution)
        font = QtGui.QFont()
        font.setBold(True)
        self.label_10.setFont(font)
        self.label_10.setObjectName("label_10")
        self.lay_page_streaming_resolution.addWidget(self.label_10)
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.streamingResolverPriorityPatterns = ResolverPatternsList(
            self.page_streaming_resolution
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
        self.label_11 = QtWidgets.QLabel(self.page_streaming_resolution)
        font = QtGui.QFont()
        font.setBold(True)
        self.label_11.setFont(font)
        self.label_11.setObjectName("label_11")
        self.formLayout_8.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_11)
        self.streamingWildcardHelpButton = QtWidgets.QPushButton(
            self.page_streaming_resolution
        )
        self.streamingWildcardHelpButton.setMaximumSize(QtCore.QSize(24, 24))
        self.streamingWildcardHelpButton.setText("?")
        self.streamingWildcardHelpButton.setObjectName("streamingWildcardHelpButton")
        self.formLayout_8.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.streamingWildcardHelpButton
        )
        self.verticalLayout.addLayout(self.formLayout_8)
        self.streamingWildcardHelp = QtWidgets.QLabel(self.page_streaming_resolution)
        self.streamingWildcardHelp.setObjectName("streamingWildcardHelp")
        self.verticalLayout.addWidget(self.streamingWildcardHelp)
        self.verticalLayout.setStretch(0, 1)
        self.lay_page_streaming_resolution.addLayout(self.verticalLayout)
        self.section_page.addWidget(self.page_streaming_resolution)
        self.page_streaming_cookies = QtWidgets.QWidget()
        self.page_streaming_cookies.setObjectName("page_streaming_cookies")
        self.lay_page_streaming_cookies = QtWidgets.QVBoxLayout(
            self.page_streaming_cookies
        )
        self.lay_page_streaming_cookies.setContentsMargins(0, 0, 0, 0)
        self.lay_page_streaming_cookies.setObjectName("lay_page_streaming_cookies")
        self.cookiesEnabled = QtWidgets.QCheckBox(self.page_streaming_cookies)
        self.cookiesEnabled.setObjectName("cookiesEnabled")
        self.lay_page_streaming_cookies.addWidget(self.cookiesEnabled)
        self.cookiesList = CookieStoreList(self.page_streaming_cookies)
        self.cookiesList.setObjectName("cookiesList")
        self.lay_page_streaming_cookies.addWidget(self.cookiesList)
        self.cookiesAllowUpdate = QtWidgets.QCheckBox(self.page_streaming_cookies)
        self.cookiesAllowUpdate.setObjectName("cookiesAllowUpdate")
        self.lay_page_streaming_cookies.addWidget(self.cookiesAllowUpdate)
        self.cookiesWarning = QtWidgets.QLabel(self.page_streaming_cookies)
        self.cookiesWarning.setWordWrap(True)
        self.cookiesWarning.setObjectName("cookiesWarning")
        self.lay_page_streaming_cookies.addWidget(self.cookiesWarning)
        self.lay_cookies_footer = QtWidgets.QHBoxLayout()
        self.lay_cookies_footer.setObjectName("lay_cookies_footer")
        self.label_cookies_howto = QtWidgets.QLabel(self.page_streaming_cookies)
        font = QtGui.QFont()
        font.setBold(True)
        self.label_cookies_howto.setFont(font)
        self.label_cookies_howto.setObjectName("label_cookies_howto")
        self.lay_cookies_footer.addWidget(self.label_cookies_howto)
        self.cookiesHowToButton = QtWidgets.QPushButton(self.page_streaming_cookies)
        self.cookiesHowToButton.setMaximumSize(QtCore.QSize(24, 24))
        self.cookiesHowToButton.setText("?")
        self.cookiesHowToButton.setObjectName("cookiesHowToButton")
        self.lay_cookies_footer.addWidget(self.cookiesHowToButton)
        spacerItem2 = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )
        self.lay_cookies_footer.addItem(spacerItem2)
        self.lay_page_streaming_cookies.addLayout(self.lay_cookies_footer)
        self.section_page.addWidget(self.page_streaming_cookies)
        self.page_streaming_network = QtWidgets.QWidget()
        self.page_streaming_network.setObjectName("page_streaming_network")
        self.lay_page_streaming_network = QtWidgets.QVBoxLayout(
            self.page_streaming_network
        )
        self.lay_page_streaming_network.setContentsMargins(0, 0, 0, 0)
        self.lay_page_streaming_network.setObjectName("lay_page_streaming_network")
        self.lay_network_form = QtWidgets.QFormLayout()
        self.lay_network_form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.AllNonFixedFieldsGrow
        )
        self.lay_network_form.setObjectName("lay_network_form")
        self.label_network_proxy_mode = QtWidgets.QLabel(self.page_streaming_network)
        self.label_network_proxy_mode.setObjectName("label_network_proxy_mode")
        self.lay_network_form.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.label_network_proxy_mode
        )
        self.networkProxyMode = QtWidgets.QComboBox(self.page_streaming_network)
        self.networkProxyMode.setObjectName("networkProxyMode")
        self.lay_network_form.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.networkProxyMode
        )
        self.label_network_proxy_url = QtWidgets.QLabel(self.page_streaming_network)
        self.label_network_proxy_url.setObjectName("label_network_proxy_url")
        self.lay_network_form.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.label_network_proxy_url
        )
        self.networkProxyUrl = QtWidgets.QLineEdit(self.page_streaming_network)
        self.networkProxyUrl.setPlaceholderText("http://host:port, socks5h://host:port")
        self.networkProxyUrl.setObjectName("networkProxyUrl")
        self.lay_network_form.setWidget(
            1, QtWidgets.QFormLayout.FieldRole, self.networkProxyUrl
        )
        self.label_network_timeout = QtWidgets.QLabel(self.page_streaming_network)
        self.label_network_timeout.setObjectName("label_network_timeout")
        self.lay_network_form.setWidget(
            2, QtWidgets.QFormLayout.LabelRole, self.label_network_timeout
        )
        self.networkTimeout = QtWidgets.QSpinBox(self.page_streaming_network)
        self.networkTimeout.setObjectName("networkTimeout")
        self.lay_network_form.setWidget(
            2, QtWidgets.QFormLayout.FieldRole, self.networkTimeout
        )
        self.label_network_user_agent = QtWidgets.QLabel(self.page_streaming_network)
        self.label_network_user_agent.setObjectName("label_network_user_agent")
        self.lay_network_form.setWidget(
            3, QtWidgets.QFormLayout.LabelRole, self.label_network_user_agent
        )
        self.networkUserAgent = QtWidgets.QLineEdit(self.page_streaming_network)
        self.networkUserAgent.setObjectName("networkUserAgent")
        self.lay_network_form.setWidget(
            3, QtWidgets.QFormLayout.FieldRole, self.networkUserAgent
        )
        self.lay_page_streaming_network.addLayout(self.lay_network_form)
        self.networkForceIPv4 = QtWidgets.QCheckBox(self.page_streaming_network)
        self.networkForceIPv4.setObjectName("networkForceIPv4")
        self.lay_page_streaming_network.addWidget(self.networkForceIPv4)
        self.networkVerifyTLS = QtWidgets.QCheckBox(self.page_streaming_network)
        self.networkVerifyTLS.setObjectName("networkVerifyTLS")
        self.lay_page_streaming_network.addWidget(self.networkVerifyTLS)
        self.networkRelayNote = QtWidgets.QLabel(self.page_streaming_network)
        self.networkRelayNote.setWordWrap(True)
        self.networkRelayNote.setObjectName("networkRelayNote")
        self.lay_page_streaming_network.addWidget(self.networkRelayNote)
        self.lay_network_footer = QtWidgets.QHBoxLayout()
        self.lay_network_footer.setObjectName("lay_network_footer")
        self.networkTestButton = QtWidgets.QPushButton(self.page_streaming_network)
        self.networkTestButton.setObjectName("networkTestButton")
        self.lay_network_footer.addWidget(self.networkTestButton)
        spacerItem3 = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )
        self.lay_network_footer.addItem(spacerItem3)
        self.lay_page_streaming_network.addLayout(self.lay_network_footer)
        spacerItem4 = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_page_streaming_network.addItem(spacerItem4)
        self.section_page.addWidget(self.page_streaming_network)
        self.page_defaults_playlist = PageScrollArea()
        self.page_defaults_playlist.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.page_defaults_playlist.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        self.page_defaults_playlist.setWidgetResizable(True)
        self.page_defaults_playlist.setObjectName("page_defaults_playlist")
        self.page_defaults_playlist_contents = QtWidgets.QWidget()
        self.page_defaults_playlist_contents.setObjectName(
            "page_defaults_playlist_contents"
        )
        self.page_defaults_playlist.setWidget(self.page_defaults_playlist_contents)
        self.section_page.addWidget(self.page_defaults_playlist)
        self.page_defaults_video = PageScrollArea()
        self.page_defaults_video.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.page_defaults_video.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        self.page_defaults_video.setWidgetResizable(True)
        self.page_defaults_video.setObjectName("page_defaults_video")
        self.page_defaults_video_contents = QtWidgets.QWidget()
        self.page_defaults_video_contents.setObjectName("page_defaults_video_contents")
        self.page_defaults_video.setWidget(self.page_defaults_video_contents)
        self.section_page.addWidget(self.page_defaults_video)
        self.page_advanced_decoder = QtWidgets.QWidget()
        self.page_advanced_decoder.setObjectName("page_advanced_decoder")
        self.lay_page_advanced_decoder = QtWidgets.QVBoxLayout(
            self.page_advanced_decoder
        )
        self.lay_page_advanced_decoder.setContentsMargins(0, 0, 0, 0)
        self.lay_page_advanced_decoder.setObjectName("lay_page_advanced_decoder")
        self.playerVideoDriverBox = QtWidgets.QGroupBox(self.page_advanced_decoder)
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
        self.lay_page_advanced_decoder.addWidget(self.playerVideoDriverBox)
        self.label_9 = QtWidgets.QLabel(self.page_advanced_decoder)
        font = QtGui.QFont()
        font.setBold(True)
        self.label_9.setFont(font)
        self.label_9.setOpenExternalLinks(True)
        self.label_9.setObjectName("label_9")
        self.lay_page_advanced_decoder.addWidget(self.label_9)
        self.miscVLCOptions = QtWidgets.QLineEdit(self.page_advanced_decoder)
        self.miscVLCOptions.setObjectName("miscVLCOptions")
        self.lay_page_advanced_decoder.addWidget(self.miscVLCOptions)
        self.section_experimental = QtWidgets.QLabel(self.page_advanced_decoder)
        font = QtGui.QFont()
        font.setBold(True)
        self.section_experimental.setFont(font)
        self.section_experimental.setObjectName("section_experimental")
        self.lay_page_advanced_decoder.addWidget(self.section_experimental)
        self.miscOpaqueHWOverlay = QtWidgets.QCheckBox(self.page_advanced_decoder)
        self.miscOpaqueHWOverlay.setObjectName("miscOpaqueHWOverlay")
        self.lay_page_advanced_decoder.addWidget(self.miscOpaqueHWOverlay)
        self.miscFakeOverlayInvisibility = QtWidgets.QCheckBox(
            self.page_advanced_decoder
        )
        self.miscFakeOverlayInvisibility.setObjectName("miscFakeOverlayInvisibility")
        self.lay_page_advanced_decoder.addWidget(self.miscFakeOverlayInvisibility)
        self.miscForceNativeDragEvents = QtWidgets.QCheckBox(self.page_advanced_decoder)
        self.miscForceNativeDragEvents.setObjectName("miscForceNativeDragEvents")
        self.lay_page_advanced_decoder.addWidget(self.miscForceNativeDragEvents)
        self.lay_miscHWCropBorder = QtWidgets.QFormLayout()
        self.lay_miscHWCropBorder.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.lay_miscHWCropBorder.setObjectName("lay_miscHWCropBorder")
        self.miscHWCropBorderLabel = QtWidgets.QLabel(self.page_advanced_decoder)
        self.miscHWCropBorderLabel.setObjectName("miscHWCropBorderLabel")
        self.lay_miscHWCropBorder.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.miscHWCropBorderLabel
        )
        self.miscHWCropBorder = QtWidgets.QComboBox(self.page_advanced_decoder)
        self.miscHWCropBorder.setObjectName("miscHWCropBorder")
        self.lay_miscHWCropBorder.setWidget(
            0, QtWidgets.QFormLayout.FieldRole, self.miscHWCropBorder
        )
        self.lay_page_advanced_decoder.addLayout(self.lay_miscHWCropBorder)
        spacerItem5 = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_page_advanced_decoder.addItem(spacerItem5)
        self.section_page.addWidget(self.page_advanced_decoder)
        self.page_advanced_logging = QtWidgets.QWidget()
        self.page_advanced_logging.setObjectName("page_advanced_logging")
        self.lay_page_advanced_logging = QtWidgets.QVBoxLayout(
            self.page_advanced_logging
        )
        self.lay_page_advanced_logging.setContentsMargins(0, 0, 0, 0)
        self.lay_page_advanced_logging.setObjectName("lay_page_advanced_logging")
        self.logLimit = QtWidgets.QCheckBox(self.page_advanced_logging)
        self.logLimit.setObjectName("logLimit")
        self.lay_page_advanced_logging.addWidget(self.logLimit)
        self.formLayout_6 = QtWidgets.QFormLayout()
        self.formLayout_6.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_6.setObjectName("formLayout_6")
        self.logLimitSizeLabel = QtWidgets.QLabel(self.page_advanced_logging)
        self.logLimitSizeLabel.setObjectName("logLimitSizeLabel")
        self.formLayout_6.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.logLimitSizeLabel
        )
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.logLimitSize = QtWidgets.QSpinBox(self.page_advanced_logging)
        self.logLimitSize.setObjectName("logLimitSize")
        self.horizontalLayout_3.addWidget(self.logLimitSize)
        self.label_5 = QtWidgets.QLabel(self.page_advanced_logging)
        self.label_5.setObjectName("label_5")
        self.horizontalLayout_3.addWidget(self.label_5)
        self.formLayout_6.setLayout(
            0, QtWidgets.QFormLayout.FieldRole, self.horizontalLayout_3
        )
        self.logLimitBackupsLabel = QtWidgets.QLabel(self.page_advanced_logging)
        self.logLimitBackupsLabel.setObjectName("logLimitBackupsLabel")
        self.formLayout_6.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.logLimitBackupsLabel
        )
        self.logLimitBackups = QtWidgets.QSpinBox(self.page_advanced_logging)
        self.logLimitBackups.setObjectName("logLimitBackups")
        self.formLayout_6.setWidget(
            1, QtWidgets.QFormLayout.FieldRole, self.logLimitBackups
        )
        self.lay_page_advanced_logging.addLayout(self.formLayout_6)
        self.label_6 = QtWidgets.QLabel(self.page_advanced_logging)
        font = QtGui.QFont()
        font.setBold(True)
        self.label_6.setFont(font)
        self.label_6.setObjectName("label_6")
        self.lay_page_advanced_logging.addWidget(self.label_6)
        self.formLayout_5 = QtWidgets.QFormLayout()
        self.formLayout_5.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldsStayAtSizeHint
        )
        self.formLayout_5.setObjectName("formLayout_5")
        self.logLevelLabel = QtWidgets.QLabel(self.page_advanced_logging)
        self.logLevelLabel.setObjectName("logLevelLabel")
        self.formLayout_5.setWidget(
            0, QtWidgets.QFormLayout.LabelRole, self.logLevelLabel
        )
        self.logLevel = QtWidgets.QComboBox(self.page_advanced_logging)
        self.logLevel.setObjectName("logLevel")
        self.formLayout_5.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.logLevel)
        self.logLevelVLCLabel = QtWidgets.QLabel(self.page_advanced_logging)
        self.logLevelVLCLabel.setObjectName("logLevelVLCLabel")
        self.formLayout_5.setWidget(
            1, QtWidgets.QFormLayout.LabelRole, self.logLevelVLCLabel
        )
        self.logLevelVLC = QtWidgets.QComboBox(self.page_advanced_logging)
        self.logLevelVLC.setObjectName("logLevelVLC")
        self.formLayout_5.setWidget(
            1, QtWidgets.QFormLayout.FieldRole, self.logLevelVLC
        )
        self.lay_page_advanced_logging.addLayout(self.formLayout_5)
        spacerItem6 = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.lay_page_advanced_logging.addItem(spacerItem6)
        self.section_page.addWidget(self.page_advanced_logging)
        self.lay_main_2.addWidget(self.section_page)
        self.lay_main.addLayout(self.lay_main_2)
        self.lay_buttons = QtWidgets.QHBoxLayout()
        self.lay_buttons.setSpacing(0)
        self.lay_buttons.setObjectName("lay_buttons")
        self.dataDirOpen = QtWidgets.QPushButton(SettingsDialog)
        self.dataDirOpen.setMinimumSize(QtCore.QSize(130, 0))
        self.dataDirOpen.setObjectName("dataDirOpen")
        self.lay_buttons.addWidget(self.dataDirOpen)
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
        self.section_page.setCurrentIndex(4)
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
        item.setText(_translate("SettingsDialog", "Subtitle Style"))
        item = self.section_index.item(3)
        item.setText(_translate("SettingsDialog", "Shortcuts"))
        item = self.section_index.item(4)
        item.setText(_translate("SettingsDialog", "Language"))
        item = self.section_index.item(5)
        item.setText(_translate("SettingsDialog", "Defaults"))
        item = self.section_index.item(6)
        item.setText(_translate("SettingsDialog", "Playlist"))
        item = self.section_index.item(7)
        item.setText(_translate("SettingsDialog", "Video"))
        item = self.section_index.item(8)
        item.setText(_translate("SettingsDialog", "Streaming"))
        item = self.section_index.item(9)
        item.setText(_translate("SettingsDialog", "Link Resolution"))
        item = self.section_index.item(10)
        item.setText(_translate("SettingsDialog", "Cookies"))
        item = self.section_index.item(11)
        item.setText(_translate("SettingsDialog", "Network"))
        item = self.section_index.item(12)
        item.setText(_translate("SettingsDialog", "Advanced"))
        item = self.section_index.item(13)
        item.setText(_translate("SettingsDialog", "Video Decoder"))
        item = self.section_index.item(14)
        item.setText(_translate("SettingsDialog", "Logging"))
        self.section_index.setSortingEnabled(__sortingEnabled)
        self.playerColorSchemeLabel.setText(
            _translate("SettingsDialog", "Color scheme")
        )
        self.playerOneInstance.setText(
            _translate("SettingsDialog", "Allow only one instance")
        )
        self.playerStayOnTop.setText(_translate("SettingsDialog", "Stay on top"))
        self.playerStartMaximized.setText(
            _translate("SettingsDialog", "Start with maximized window")
        )
        self.playerStartFullscreen.setText(
            _translate("SettingsDialog", "Start in fullscreen mode")
        )
        self.playerInhibitScreensaver.setText(
            _translate("SettingsDialog", "Disable screensaver while playing")
        )
        self.playerRecentList.setText(
            _translate("SettingsDialog", "Enable recent list, maximum size")
        )
        self.label_16.setText(_translate("SettingsDialog", "(items)"))
        self.section_timeouts.setText(_translate("SettingsDialog", "Timeouts"))
        self.timeoutMouseHideFlag.setText(
            _translate("SettingsDialog", "Hide mouse after timeout")
        )
        self.label_2.setText(_translate("SettingsDialog", "(sec)"))
        self.timeoutVideoInitLabel.setText(
            _translate("SettingsDialog", "Video initialization timeout")
        )
        self.label_7.setText(_translate("SettingsDialog", "(sec)"))
        self.section_screenshots.setText(_translate("SettingsDialog", "Screenshots"))
        self.screenshotsDirLabel.setText(_translate("SettingsDialog", "Folder"))
        self.screenshotsDir.setPlaceholderText(
            _translate("SettingsDialog", "In the data folder")
        )
        self.screenshotsDirBrowse.setText(_translate("SettingsDialog", "Browse..."))
        self.screenshotsFilenameTemplateLabel.setText(
            _translate("SettingsDialog", "File name format")
        )
        self.screenshotsFormatLabel.setText(_translate("SettingsDialog", "Format"))
        self.screenshotsJPGQualityLabel.setText(_translate("SettingsDialog", "Quality"))
        self.label_4.setText(
            _translate(
                "SettingsDialog",
                '<p>If you have a handful of free time and a desire to support this project, please <a href="https://crowdin.com/project/gridplayer">help with the translation</a>. No coding skills or special software is required!</p><p><a href="https://github.com/vzhd1701/gridplayer#translations">Full list of translators</a></p>',
            )
        )
        self.streamingHLSVIAStreamlink.setText(
            _translate("SettingsDialog", "Use Streamlink for HLS streams when possible")
        )
        self.label_8.setText(_translate("SettingsDialog", "Priority URL resolver"))
        self.label_js_runtime.setText(
            _translate("SettingsDialog", "JavaScript runtime")
        )
        self.streamingJSRuntimePath.setPlaceholderText(
            _translate("SettingsDialog", "Auto")
        )
        self.streamingJSRuntimePath.setToolTip(
            _translate(
                "SettingsDialog",
                "Folder holding deno, node, qjs or bun. Leave empty to search the usual places.",
            )
        )
        self.streamingTestButton.setToolTip(
            _translate(
                "SettingsDialog",
                "Resolve a YouTube link step by step and report which step gives way",
            )
        )
        self.streamingTestButton.setText(
            _translate("SettingsDialog", "Test a YouTube link")
        )
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
        self.cookiesEnabled.setToolTip(
            _translate(
                "SettingsDialog",
                "Send the stored cookies when resolving and streaming links",
            )
        )
        self.cookiesEnabled.setText(_translate("SettingsDialog", "Use stored cookies"))
        self.cookiesAllowUpdate.setToolTip(
            _translate(
                "SettingsDialog",
                "Sites hand out fresh cookies as you use them. Keeping those makes a stored login last longer, at the cost of rewriting the cookies file as you watch.",
            )
        )
        self.cookiesAllowUpdate.setText(
            _translate("SettingsDialog", "Let yt-dlp refresh stored cookies")
        )
        self.cookiesWarning.setText(
            _translate(
                "SettingsDialog",
                "Cookies are login credentials. Anyone with access to this computer can read them.",
            )
        )
        self.label_cookies_howto.setText(
            _translate("SettingsDialog", "How to export cookies")
        )
        self.label_network_proxy_mode.setText(_translate("SettingsDialog", "Proxy"))
        self.networkProxyMode.setToolTip(
            _translate(
                "SettingsDialog",
                "System follows the machine's own proxy settings. None connects directly, ignoring them.",
            )
        )
        self.label_network_proxy_url.setText(
            _translate("SettingsDialog", "Proxy address")
        )
        self.label_network_timeout.setText(
            _translate("SettingsDialog", "Request timeout")
        )
        self.networkTimeout.setToolTip(
            _translate(
                "SettingsDialog",
                "How long to wait on a request before giving up on it. This applies while a link is being resolved, not while it is playing.",
            )
        )
        self.networkTimeout.setSpecialValueText(_translate("SettingsDialog", "Auto"))
        self.networkTimeout.setSuffix(_translate("SettingsDialog", " sec"))
        self.label_network_user_agent.setText(
            _translate("SettingsDialog", "User agent")
        )
        self.networkUserAgent.setToolTip(
            _translate(
                "SettingsDialog",
                "How the player identifies itself to sites. Leave empty for the default.",
            )
        )
        self.networkUserAgent.setPlaceholderText(_translate("SettingsDialog", "Auto"))
        self.networkForceIPv4.setToolTip(
            _translate(
                "SettingsDialog",
                "Skip IPv6 and connect over IPv4 only. Fixes a connection that stalls on IPv6 that is offered but does not work, and sites that turn away your IPv6 address.",
            )
        )
        self.networkForceIPv4.setText(_translate("SettingsDialog", "Force IPv4"))
        self.networkVerifyTLS.setToolTip(
            _translate(
                "SettingsDialog",
                "Turn this off only for a proxy that signs traffic with its own certificate",
            )
        )
        self.networkVerifyTLS.setText(
            _translate("SettingsDialog", "Verify TLS certificates")
        )
        self.networkRelayNote.setText(
            _translate(
                "SettingsDialog",
                "These settings apply to http and https links. Other links, such as rtsp and rtmp, are opened by the player itself, and only the user agent applies to them.",
            )
        )
        self.networkTestButton.setToolTip(
            _translate(
                "SettingsDialog",
                "Try these settings against a real address and report which step fails",
            )
        )
        self.networkTestButton.setText(_translate("SettingsDialog", "Test network"))
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
        self.section_experimental.setText(_translate("SettingsDialog", "Experimental"))
        self.miscOpaqueHWOverlay.setText(
            _translate("SettingsDialog", "Opaque overlay (fix black screen)")
        )
        self.miscFakeOverlayInvisibility.setText(
            _translate(
                "SettingsDialog",
                "Fake overlay invisibility (fix overlay on top of other windows)",
            )
        )
        self.miscForceNativeDragEvents.setText(
            _translate("SettingsDialog", "Force native drag-n-drop for in-window drag")
        )
        self.miscHWCropBorderLabel.setText(
            _translate("SettingsDialog", "HW video border fix")
        )
        self.miscHWCropBorder.setToolTip(
            _translate(
                "SettingsDialog",
                "Hidden margin that keeps hardware video edge artifacts out of view. Auto uses the platform default.",
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
        self.dataDirOpen.setText(_translate("SettingsDialog", "Open data folder"))
        self.dataDirOpen.setToolTip(
            _translate(
                "SettingsDialog",
                "Where the log file, the settings and the stored cookies are kept, and where a JavaScript runtime can be put for GridPlayer to find.",
            )
        )


from gridplayer.widgets.cookie_store_list import CookieStoreList
from gridplayer.widgets.keymap_tree_view import KeymapEditor
from gridplayer.widgets.language_list import LanguageList
from gridplayer.widgets.resolver_patterns_list import ResolverPatternsList
from gridplayer.widgets.settings_current_page_stack import CurrentPageStackedWidget
from gridplayer.widgets.settings_page_scroll_area import PageScrollArea
