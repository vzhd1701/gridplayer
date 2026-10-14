from PyQt5.QtWidgets import QStackedLayout


class QStackedLayoutFloating(QStackedLayout):
    """overridden setGeometry for children is not honored due to type casting inside Qt,
    need to override setGeometry in Layout to make floating windows resize with parent

    https://code.qt.io/cgit/qt/qtbase.git/tree/src/widgets/kernel/qstackedlayout.cpp#n474
    """

    def setGeometry(self, rect):
        if self.stackingMode() == QStackedLayout.StackOne:
            widget = self.currentWidget()
            if widget:
                widget.setGeometry(rect)
        if self.stackingMode() == QStackedLayout.StackAll:
            for i in range(self.count()):
                widget = self.itemAt(i).widget()
                if widget:
                    widget.setGeometry(rect)
