import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

_application = None


def application():
    global _application
    if _application is None:
        _application = QApplication.instance() or QApplication([])
        _application.setStyle('Fusion')
        if os.name == 'nt':
            for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisym.ttf', 'msyh.ttc', 'msyhbd.ttc'):
                QFontDatabase.addApplicationFont(os.path.join(os.environ['WINDIR'], 'Fonts', font))
    return _application


def flush():
    application().processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def until(condition, timeout=3):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        flush()
        time.sleep(.01)
    flush()
    return condition()
