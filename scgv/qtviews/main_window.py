import sys
import traceback

import os

from PyQt5.QtWidgets import QMainWindow, QAction, \
    QStatusBar, QFileDialog

from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot, \
    QThreadPool

from scgv.models.model import DataModel

from scgv.models.featuremat_model import FeaturematModel

from scgv.qtviews.heatmap import BaseHeatmapWidget, HeatmapWindow
from scgv.qtviews.guide import GuideWindow
from scgv.qtviews.canvas import Canvas


class WorkerSignals(QObject):

    finished = pyqtSignal()
    progress = pyqtSignal(int)

    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    status = pyqtSignal(object)


class Worker(QRunnable):

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''
        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(
                *self.args, **self.kwargs,
                status=self.signals.status,
                progress=self.signals.progress,
            )
        except Exception:
            # Emit error
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            # Return the result of the processing
            self.signals.result.emit(result)
        finally:
            # Done
            self.signals.finished.emit()


def icons_folder():
    modulename = os.path.abspath(__file__)
    dirname = os.path.dirname(modulename)
    iconsdir = os.path.join(dirname, 'icons')
    return iconsdir


class OpenButtons(object):

    def __init__(self, window):
        self.window = window

        self.window.toolbar.addSeparator()
        icons = icons_folder()

        self.open_dir_action = QAction(
            QIcon(os.path.join(icons, "folder.png")),
            "Open Directory", self.window)
        self.open_dir_action.setStatusTip("Open Directory button")
        self.open_dir_action.triggered.connect(self.on_open_directory_click)
        self.window.toolbar.addAction(self.open_dir_action)

        self.open_archive_action = QAction(
            QIcon(os.path.join(icons, "archive.png")),
            "Open Archive", self.window)
        self.open_archive_action.setStatusTip("Open Archive button")
        self.open_archive_action.triggered.connect(self.on_open_archive_click)
        self.window.toolbar.addAction(self.open_archive_action)

        self.threadpool = QThreadPool()

    def on_open_directory_click(self, s):
        dirname = QFileDialog.getExistingDirectory(
            self.window, "Open Directory")
        if dirname is None or dirname == "":
            print("open directory canceled...")
            return
        self.load_model(dirname)

    def on_open_archive_click(self, s):
        filter = "Zip File (*.zip)"
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "Open Zip File",
            ".", filter)
        if filename is None or filename == "":
            print("open archive canceled...")
            return
        self.load_model(filename)

    def load_model(self, filename):

        self.open_archive_action.setEnabled(False)
        self.open_dir_action.setEnabled(False)

        worker = Worker(self._build_model, filename)
        worker.signals.result.connect(self.window.set_model)
        worker.signals.error.connect(self._load_error)
        worker.signals.finished.connect(self._load_complete)
        self.threadpool.start(worker)

    def _load_complete(self):
        self.window.update()

    def _load_error(self, *args, **kwargs):
        self.open_archive_action.setEnabled(True)
        self.open_dir_action.setEnabled(True)

    def _build_model(self, filename, *args, **kwargs):
        try:
            model = DataModel(filename)
            model.make()
            return model
        except Exception:
            self._load_error()
            return None


class ActionButtons(object):

    def __init__(self, window):
        self.window = window
        self.model = None

        self.window.toolbar.addSeparator()
        # icons = icons_folder()

        self.feature_view_action = QAction(
            # QIcon(os.path.join(icons, "format-justify-fill.png")),
            "Feature View", self.window
        )
        self.feature_view_action.setStatusTip("Open Feature View")
        self.feature_view_action.triggered.connect(
            self.on_feature_view_action)
        self.window.toolbar.addAction(self.feature_view_action)

        self.configure_tracks_action = QAction(
            "Configure Tracks", self.window
        )
        self.configure_tracks_action.setStatusTip("Configure Tracks")
        self.configure_tracks_action.triggered.connect(
            self.on_configure_tracks_action_action)
        self.window.toolbar.addAction(self.configure_tracks_action)

    def on_configure_tracks_action_action(self, *args, **kwargs):
        if self.model is None:
            return
        if self.model.data.guide_df is None:
            return

        dialog = GuideWindow(
            self.window, self.model)
        dialog.signals.selected_tracks_change.connect(
            self.on_selected_tracks_change)

        dialog.show()

    def on_selected_tracks_change(
            self, selected_tracks, *args, **kwargs):
        print('on_selected_tracks_change:', selected_tracks, args, kwargs)
        if selected_tracks == self.model.selected_tracks:
            return
        self.model.selected_tracks = selected_tracks
        self.model.update_selected_tracks()
        self.window.update()

    def on_feature_view_action(self, *args, **kwargs):
        if self.model is None:
            return
        if self.model.data.features_df is None:
            return

        self.feature_view_action.setEnabled(False)

        features_model = FeaturematModel(self.model)
        features_model.make()

        dialog = HeatmapWindow(
            self.window, features_model, new_canvas=Canvas)
        dialog.signals.closing.connect(self.on_feature_view_closing)

        dialog.show()

    def on_feature_view_closing(self):
        self.feature_view_action.setEnabled(True)

    def set_model(self, model):
        self.model = model


class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.setWindowTitle("SCGV Main")

        self._main = BaseHeatmapWidget(self)
        self.setCentralWidget(self._main)

        self.toolbar = self._main.toolbar
        self.addToolBar(self._main.toolbar)

        self.setStatusBar(QStatusBar(self))
        self.open_buttons = OpenButtons(self)
        self.action_buttons = ActionButtons(self)

    def set_model(self, model):
        if model is None:
            return
        self._main.set_model(model)
        self.action_buttons.set_model(model)

    def update(self):
        self._main.update()
        super(MainWindow, self).update()
