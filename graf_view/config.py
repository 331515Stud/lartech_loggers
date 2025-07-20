from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
import numpy as np
import matplotlib as mpl

def create_dark_palette():
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    return palette

DARK_PALETTE = create_dark_palette()

def configure_matplotlib():
    mpl.rcParams.update({
        'axes.facecolor': 'black',
        'figure.facecolor': 'black',
        'axes.edgecolor': 'white',
        'axes.labelcolor': 'white',
        'text.color': 'white',
        'xtick.color': 'white',
        'ytick.color': 'white',
        'grid.color': '#444444',
        'lines.antialiased': True,
        'path.simplify': True,
        'path.simplify_threshold': 0.1
    })

configure_matplotlib()

NUM_CHANNELS = 6
DEFAULT_X = np.linspace(0, 10, 1000)
INITIAL_X_RANGE = (np.min(DEFAULT_X), np.max(DEFAULT_X))
MAX_THREADS = 4