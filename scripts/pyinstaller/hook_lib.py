import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(sys.executable), "lib")

sys.path.append(_LIB_DIR)
sys._MEIPASS = _LIB_DIR
