from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_ExceptionDialog(object):
    def setupUi(self, ExceptionDialog):
        ExceptionDialog.setObjectName("ExceptionDialog")
        ExceptionDialog.resize(518, 297)
        self.lay_main = QtWidgets.QVBoxLayout(ExceptionDialog)
        self.lay_main.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        self.lay_main.setObjectName("lay_main")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.errorIcon = QtWidgets.QLabel(ExceptionDialog)
        self.errorIcon.setObjectName("errorIcon")
        self.horizontalLayout.addWidget(self.errorIcon)
        self.errorLabel = QtWidgets.QLabel(ExceptionDialog)
        self.errorLabel.setTextFormat(QtCore.Qt.RichText)
        self.errorLabel.setOpenExternalLinks(True)
        self.errorLabel.setObjectName("errorLabel")
        self.horizontalLayout.addWidget(self.errorLabel)
        self.horizontalLayout.setStretch(1, 1)
        self.lay_main.addLayout(self.horizontalLayout)
        self.exceptionBox = QtWidgets.QTextBrowser(ExceptionDialog)
        self.exceptionBox.setMinimumSize(QtCore.QSize(500, 200))
        self.exceptionBox.setMaximumSize(QtCore.QSize(16777215, 200))
        self.exceptionBox.setObjectName("exceptionBox")
        self.lay_main.addWidget(self.exceptionBox)
        self.lay_buttons = QtWidgets.QHBoxLayout()
        self.lay_buttons.setObjectName("lay_buttons")
        self.copyButton = QtWidgets.QPushButton(ExceptionDialog)
        self.copyButton.setMinimumSize(QtCore.QSize(150, 0))
        self.copyButton.setObjectName("copyButton")
        self.lay_buttons.addWidget(self.copyButton)
        self.buttonBox = QtWidgets.QDialogButtonBox(ExceptionDialog)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Close)
        self.buttonBox.setObjectName("buttonBox")
        self.lay_buttons.addWidget(self.buttonBox)
        self.lay_main.addLayout(self.lay_buttons)

        self.retranslateUi(ExceptionDialog)
        self.buttonBox.rejected.connect(ExceptionDialog.reject)
        QtCore.QMetaObject.connectSlotsByName(ExceptionDialog)

    def retranslateUi(self, ExceptionDialog):
        _translate = QtCore.QCoreApplication.translate
        ExceptionDialog.setWindowTitle(
            _translate("ExceptionDialog", "Unhandled Exception")
        )
        self.errorLabel.setText(
            _translate(
                "ExceptionDialog",
                '<html><head/><body><p><span style=" font-weight:600;">Program terminated due to unhandled exception!</span></p><p>Please consider sending a bug report to the <a href="{APP_BUGTRACKER_URL}"><span style=" text-decoration: underline; color:#0000ff;">bug tracker</span></a>.</p></body></html>',
            )
        )
        self.copyButton.setText(_translate("ExceptionDialog", "Copy to Clipboard"))
