#!/usr/bin/env python
# -*- coding: utf-8 -*-

# beta   - under development
# 1.0.0  - initial release, update UI, make watermark use blendmode
# 1.1.0  - performance boost, change blendmode back to normal due to poor performance
#        - upgrade UI, add sub progress bar
#        - fix bug when deleting multiple items
# 1.2.0  - Add opacity adjustments
# 1.2.1  - Fix browse button default directory
# 1.3.0  - Add PDF support
# 1.4.0  - Add feature: resize media
# 1.5.0  - Add feature: select overlay image

_title = 'Watermarkr'
_version = '1.5.0'
_des = ''
uiName = 'Watermarkr'

#Import python modules
import sys
import os
import logging
import getpass
import tempfile
import time
from functools import partial
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict
import subprocess

core = '%s/core' % os.environ.get('RFSCRIPT')
sys.path.append(core)

# import config
import rf_config as config
from rf_utils import log_utils
from rf_utils.ui import stylesheet

user = '%s-%s' % (config.Env.localuser, getpass.getuser()) or 'unknown'
logFile = log_utils.name(uiName, user)
logger = log_utils.init_logger(logFile)
logger.setLevel(logging.DEBUG)

# QT
os.environ['QT_PREFERRED_BINDING'] = os.pathsep.join(['PySide', 'PySide2'])
from Qt import QtCore
from Qt import QtWidgets
from Qt import QtGui

from rf_utils import file_utils
from rf_utils.widget.file_widget import Icon
from rf_utils.widget import display_widget
from rf_utils.pipeline import watermark
from rf_utils.pipeline import convert_lib

moduleDir = os.path.dirname(sys.modules[__name__].__file__).replace('\\', '/')
appName = os.path.splitext(os.path.basename(sys.modules[__name__].__file__))[0]

SUPPORT_FORMAT = ('.jpg', '.tif', '.tiff', '.png', '.pdf', '.mov', '.mp4')
NON_RESIZEABLE_FORMAT = ('.pdf')
WATERMARK_PATH = '{}/core/rf_template/default/watermark/watermark_2K_internal.png'.format(os.environ['RFSCRIPT'])
MIN_OPACITY = 0.05  # opacity slider min
MAX_OPACITY = 0.50  # opacity slider max
MIN_SIZE = 1  # resize slider min
MAX_SIZE =  16 # resize slider max
DEFAULT_SIZE = 8
SIZE_STEP = 512

DEFAULT_OPACITY = 0.12  # default opacity slider value
OPACITY_RANGE = (0.075, 0.15)  # range for auto opacity

class StampThread(QtCore.QThread):
    mediaStamped = QtCore.Signal(tuple)
    stampFinished = QtCore.Signal(tuple)
    progressStamped = QtCore.Signal(tuple)
    __stop = False

    def __init__(self, input_paths, text, output_paths, overlay_path, opacity, resize, callback_func=None, parent=None):
        super(StampThread, self).__init__(parent=parent)
        self.input_paths = input_paths
        self.text = text
        self.output_paths = output_paths
        self.overlay_path = overlay_path
        self.opacity = opacity
        self.resize = resize
        self.callback_func = callback_func
        self.results = []
        self._stop = False

    def stop(self):
        self._stop = True
        return 0

    def run(self):
        start_time = time.time()
        num_files = len(self.input_paths)
        temp_files = []
        for i, input_path in enumerate(self.input_paths):
            output_path = self.output_paths[i]
            if self.resize != None and os.path.splitext(input_path)[-1].lower() not in NON_RESIZEABLE_FORMAT:
                # do the resize
                resize_result = convert_lib.limit_media_size(input_path, limit_size=self.resize, output_path=None)
                if resize_result:
                    input_path = resize_result
                    temp_files.append(input_path)
                    print('Resized to temp: {}'.format(input_path))
            result = watermark.add_watermark_with_text(input_path=input_path, 
                                                overlay_path=self.overlay_path, 
                                                text=self.text, 
                                                output_path=output_path, 
                                                opacity=self.opacity,
                                                callback_func=self.callback_func)
            
            if self._stop:
                break

            self.results.append(result)
            self.mediaStamped.emit((i, result))
            progress = (i+1, num_files)
            self.progressStamped.emit(progress)

        if self._stop:
            self.input_paths = []
            self.output_paths = []
            self.text = None
            self._stop = False
        else:
            time_taken = time.time() - start_time
            self.stampFinished.emit((self.results, time_taken))
        if temp_files:
            for tf in temp_files:
                os.remove(tf)
            print('{} Temp files removed.'.format(len(temp_files)))
        return 0


class Watermarkr(QtWidgets.QMainWindow):
    subprogress = QtCore.Signal(tuple)

    def __init__(self, parent=None):
        # setup Window
        super(Watermarkr, self).__init__(parent)

        # app vars
        self.thread = None

        # ui vars
        self.w = 550
        self.h = 645
        self.app_icon = '{}/icons/app_icon.png'.format(moduleDir)
        self.logo_icon = '{}/icons/riff_logo.png'.format(moduleDir)
        self.refresh_icon = '{}/icons/clear_icon.png'.format(moduleDir)
        self.delete_icon = '{}/icons/delete_icon.png'.format(moduleDir)
        self.stamp_icon = '{}/icons/stamp_icon.png'.format(moduleDir)

        # init functions
        self.setupUi()
        self.init_signals()
        self.set_default()
        
    def setupUi(self):
        self.setObjectName(uiName)
        self.setWindowTitle('{} {} {}'.format(_title, _version, _des))
        self.setWindowIcon(QtGui.QIcon(self.app_icon))
        self.setLocale(QtCore.QLocale(QtCore.QLocale.English, QtCore.QLocale.UnitedStates))

        self.centralwidget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.centralwidget)
        self.resize(self.w, self.h)

        # main layout
        self.main_layout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.main_layout.setSpacing(5)

        # header layout
        self.header_layout = QtWidgets.QHBoxLayout()
        self.main_layout.addLayout(self.header_layout)

        # logo
        self.logo = QtWidgets.QLabel()
        self.logo.setPixmap(QtGui.QPixmap(self.logo_icon).scaled(64, 64, QtCore.Qt.KeepAspectRatio))
        self.header_layout.addWidget(self.logo)

        # reciever layout
        self.reciever_layout = QtWidgets.QFormLayout()
        self.reciever_layout.setLabelAlignment(QtCore.Qt.AlignRight)
        self.reciever_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.reciever_layout.setContentsMargins(9, 9, 9, 0)
        self.reciever_layout.setSpacing(9)
        self.header_layout.addLayout(self.reciever_layout)
        
        # reciever lineEdit
        self.reciever_lineEdit = QtWidgets.QLineEdit()
        self.reciever_lineEdit.setPlaceholderText('< Who will recieve files? >')
        self.reciever_lineEdit.setMinimumWidth(120)
        self.reciever_layout.addRow('Name', self.reciever_lineEdit)
        # task lineEdit
        self.task_lineEdit = QtWidgets.QLineEdit()
        self.task_lineEdit.setPlaceholderText('< What do they do? >')
        self.task_lineEdit.setMinimumWidth(120)
        self.reciever_layout.addRow('Task', self.task_lineEdit)

        # clear button
        self.header_button_layout = QtWidgets.QVBoxLayout()
        self.header_layout.addLayout(self.header_button_layout)

        spacerItem1 = QtWidgets.QSpacerItem(20, 30, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        self.header_button_layout.addItem(spacerItem1)

        # clear button
        self.button_layout = QtWidgets.QHBoxLayout()
        self.button_layout.setSpacing(5)
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.header_button_layout.addLayout(self.button_layout)

        self.delete_button = QtWidgets.QPushButton()
        self.delete_button.setIcon(QtGui.QIcon(self.delete_icon))
        self.delete_button.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.button_layout.addWidget(self.delete_button)

        # refresh button
        self.refresh_button = QtWidgets.QPushButton()
        self.refresh_button.setIcon(QtGui.QIcon(self.refresh_icon))
        self.refresh_button.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.button_layout.addWidget(self.refresh_button)

        # drop layout
        self.drop_layout = QtWidgets.QHBoxLayout()
        self.main_layout.addLayout(self.drop_layout)
        # drop widget
        self.drop_widget = display_widget.DropUrlTree()
        self.drop_widget.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.drop_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.drop_widget.setColumnCount(2)
        header = self.drop_widget.headerItem()
        header.setText(0, 'File Name')
        header.setText(1, 'Size')
        self.drop_widget.setColumnWidth(0, 330)
        self.drop_widget.setColumnWidth(1, 75)
        self.drop_layout.addWidget(self.drop_widget)

        # browse layout
        self.browse_layout = QtWidgets.QHBoxLayout()
        self.browse_layout.setSpacing(9)
        self.main_layout.addLayout(self.browse_layout)

        self.dest_label = QtWidgets.QLabel('Output')
        self.browse_layout.addWidget(self.dest_label)

        self.dest_lineEdit = QtWidgets.QLineEdit()
        self.dest_lineEdit.setPlaceholderText('< Files will go to your desktop >')
        self.browse_layout.addWidget(self.dest_lineEdit)

        self.browse_button = QtWidgets.QPushButton('...')
        self.browse_button.setMinimumSize(QtCore.QSize(25, 25))
        self.browse_button.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.browse_layout.addWidget(self.browse_button)

        # watermark path
        self.watermark_layout = QtWidgets.QHBoxLayout()
        self.watermark_layout.setSpacing(9)
        self.main_layout.addLayout(self.watermark_layout)

        self.wm_label = QtWidgets.QLabel('Overlay')
        self.watermark_layout.addWidget(self.wm_label)

        self.watermark_lineEdit = QtWidgets.QLineEdit()
        self.watermark_lineEdit.setReadOnly(True)
        self.watermark_layout.addWidget(self.watermark_lineEdit)

        self.browse_watermark_button = QtWidgets.QPushButton('...')
        self.browse_watermark_button.setMinimumSize(QtCore.QSize(25, 25))
        self.browse_watermark_button.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.watermark_layout.addWidget(self.browse_watermark_button)

        # stamp layout
        self.stamp_layout = QtWidgets.QHBoxLayout()
        self.stamp_layout.setSpacing(9)
        self.main_layout.addLayout(self.stamp_layout)

        # bottom layout
        self.bottom_layout = QtWidgets.QVBoxLayout()
        self.bottom_layout.setSpacing(3)
        self.button_layout.setContentsMargins(9, 9, 9, 3)
        self.stamp_layout.addLayout(self.bottom_layout)

        # opacity
        self.slider_layout = QtWidgets.QFormLayout()
        self.bottom_layout.addLayout(self.slider_layout)
        
        self.opacity_layout = QtWidgets.QHBoxLayout()
        self.opacity_layout.setSpacing(5)

        # linedit
        self.opacity_lineEdit = QtWidgets.QLineEdit()
        self.opacity_lineEdit.setMaximumWidth(40)
        self.opacity_lineEdit.setMaximumHeight(20)
        self.opacity_lineEdit.setReadOnly(True)
        self.opacity_layout.addWidget(self.opacity_lineEdit)

        # opacity slider
        self.opacity_slider = QtWidgets.QSlider()
        self.opacity_slider.setMaximumHeight(18)
        self.opacity_slider.setOrientation(QtCore.Qt.Horizontal)
        self.opacity_layout.addWidget(self.opacity_slider)

        # adaptive checkbox
        self.adaptive_checkbox = QtWidgets.QCheckBox('Auto')
        self.opacity_layout.addWidget(self.adaptive_checkbox)

        self.opacity_layout.setStretch(0, 0)
        self.opacity_layout.setStretch(1, 5)

        self.slider_layout.addRow('Opacity: ', self.opacity_layout)

        # resize
        self.size_layout = QtWidgets.QHBoxLayout()
        self.size_layout.setSpacing(5)

        # linedit
        self.resize_lineEdit = QtWidgets.QLineEdit()
        self.resize_lineEdit.setMaximumWidth(40)
        self.resize_lineEdit.setMaximumHeight(20)
        self.resize_lineEdit.setReadOnly(True)
        self.size_layout.addWidget(self.resize_lineEdit)

        # opacity slider
        self.resize_slider = QtWidgets.QSlider()
        self.resize_slider.setMaximumHeight(18)
        self.resize_slider.setOrientation(QtCore.Qt.Horizontal)
        self.resize_slider.setTickInterval(1)
        self.resize_slider.setSingleStep(1) # arrow-key step-size
        self.resize_slider.setPageStep(1) # mouse-wheel/page-key step-size
        self.resize_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.size_layout.addWidget(self.resize_slider)

        # adaptive checkbox
        self.resize_checkbox = QtWidgets.QCheckBox('On')
        self.resize_checkbox.setMinimumWidth(44)
        self.resize_checkbox.setChecked(True)
        self.size_layout.addWidget(self.resize_checkbox)

        self.size_layout.setStretch(0, 0)
        self.size_layout.setStretch(1, 5)

        self.slider_layout.addRow('Resize: ', self.size_layout)

        # progress bars
        self.mainProgressBar = QtWidgets.QProgressBar()
        self.mainProgressBar.setTextVisible(True)
        self.mainProgressBar.setMaximumHeight(20)
        self.mainProgressBar.setMinimum(0)
        self.mainProgressBar.setMaximum(100)
        self.mainProgressBar.setValue(0)
        self.bottom_layout.addWidget(self.mainProgressBar)

        self.subProgressBar = QtWidgets.QProgressBar()
        self.subProgressBar.setTextVisible(True)
        self.subProgressBar.setMaximumHeight(15)
        self.subProgressBar.setMinimum(0)
        self.subProgressBar.setMaximum(100)
        self.subProgressBar.setValue(0)
        self.bottom_layout.addWidget(self.subProgressBar)

        # stamp button
        self.stamp_button = QtWidgets.QPushButton('Stamp')
        self.stamp_button.setStyleSheet('QPushButton { color: white; font-size: 14px; border: 3px solid rgb(9, 105, 181); border-radius: 42px; }')
        self.stamp_button.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.stamp_button.setFixedSize(QtCore.QSize(84, 84))
        self.stamp_button.setIcon(QtGui.QIcon(self.stamp_icon))
        self.stamp_layout.addWidget(self.stamp_button)

        self.stamp_layout.setStretch(0, 9)
        self.stamp_layout.setStretch(1, 3)

        # status line
        self.statusBar = QtWidgets.QStatusBar()
        status_font = QtGui.QFont()
        status_font.setItalic(True)
        self.statusBar.setFont(status_font)
        self.statusBar.setStyleSheet('color: rgb(150, 150, 150)')
        self.main_layout.addWidget(self.statusBar)

    def set_default(self):
        # watermark path
        self.watermark_lineEdit.setText(WATERMARK_PATH)
        # opacity slider
        opacity_min = int(MIN_OPACITY*100)
        opacity_max = int(MAX_OPACITY*100)
        self.opacity_slider.setMinimum(opacity_min)
        self.opacity_slider.setMaximum(opacity_max)
        self.opacity_slider.setValue(int(DEFAULT_OPACITY*100))
        self.adaptive_checkbox.setChecked(True)
        # resize slider
        self.resize_slider.setMinimum(MIN_SIZE)
        self.resize_slider.setMaximum(MAX_SIZE)
        self.resize_slider.setValue(DEFAULT_SIZE)
        self.resize_checkbox.setChecked(False)

        self.drop_widget.setFocus()
        self.statusBar.showMessage('Ready.')

    def init_signals(self):
        self.drop_widget.multipleDropped.connect(self.file_dropped)
        self.browse_watermark_button.clicked.connect(self.browse_watermark)
        self.browse_button.clicked.connect(self.browse_directory)
        self.dest_lineEdit.editingFinished.connect(self.dest_edit)
        self.delete_button.clicked.connect(self.del_item)
        self.refresh_button.clicked.connect(self.clear_item)
        self.stamp_button.clicked.connect(self.stamp)
        self.adaptive_checkbox.toggled.connect(self.adaptive_toggled)
        self.opacity_slider.valueChanged.connect(self.opacity_slider_changed)
        self.resize_slider.valueChanged.connect(self.resize_slider_changed)
        self.resize_checkbox.toggled.connect(self.resize_toggled)

        # actions
        self.del_action = QtWidgets.QAction(self.drop_widget)
        self.del_action.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete))
        self.drop_widget.addAction(self.del_action)
        self.del_action.triggered.connect(self.del_item)

        # self.esc_action = QtWidgets.QAction(self.drop_widget)
        # self.esc_action.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape))
        # self.addAction(self.esc_action)
        # self.esc_action.triggered.connect(self.stop_process)

    def opacity_slider_changed(self, value):
        self.opacity_lineEdit.setText('{}%'.format(value))

    def adaptive_toggled(self, checked):
        self.opacity_lineEdit.setEnabled(not checked)
        self.opacity_slider.setEnabled(not checked)

    def resize_slider_changed(self, value):
        self.resize_lineEdit.setText(str(value*SIZE_STEP))

    def resize_toggled(self, checked):
        self.resize_lineEdit.setEnabled(checked)
        self.resize_slider.setEnabled(checked)

    # def stop_process(self):
    #     if not self.thread and self.thread.isRunning():
    #         return
    #     self.thread.stop()
    #     # self.thread.exit()
    #     self.thread.wait()
    #     self.thread = None

    #     self.statusBar.showMessage('Process stopped by user')
    #     self.mainProgressBar.setValue(0)
    #     self.subProgressBar.setValue(0)
    #     QtWidgets.QApplication.restoreOverrideCursor()
    #     self.enable_ui(value=True)

    def dest_edit(self):
        path = self.dest_lineEdit.text().replace('\\', '/')
        if not os.path.isdir(path):
            self.dest_lineEdit.clear()
        else:
            self.dest_lineEdit.setText(path)

    def del_item(self):
        sels = self.drop_widget.selectedItems()
        if sels:
            index = 0
            for sel in sels:
                index = self.drop_widget.indexOfTopLevelItem(sel)
                self.drop_widget.takeTopLevelItem(index)

            # try to select the next one
            try:
                self.drop_widget.setCurrentItem(self.drop_widget.topLevelItem(index))
            except Exception:
                pass

    def clear_item(self):
        self.drop_widget.clear()

    def file_dropped(self, paths):
        existing_paths = self.get_current_paths()
        i = 0
        unsupported_files = []
        duplicated_files = []
        for path in paths:
            logger.info('Dropped: {}'.format(path))
            fn, ext = os.path.splitext(path)
            if ext.lower() not in SUPPORT_FORMAT:
                unsupported_files.append(path)
            elif path in existing_paths:
                duplicated_files.append(path)
            else:
                baseName = os.path.basename(path)
                item = QtWidgets.QTreeWidgetItem(self.drop_widget)
                # filename
                item.setText(0, baseName)
                # file size
                item.setText(1,  file_utils.get_readable_filesize(path))
                # icon
                iconWidget = QtGui.QIcon()
                iconPath = Icon.extMap.get(ext.lower(), Icon.extMap['unknown'])
                iconWidget.addPixmap(QtGui.QPixmap(iconPath), QtGui.QIcon.Normal, QtGui.QIcon.Off)
                item.setIcon(0, iconWidget)
                # data
                item.setData(QtCore.Qt.UserRole, 0, path)
                # tooltip
                item.setToolTip(0, path)
                i += 1
        if unsupported_files or duplicated_files:
            err_msg = 'Not all dropped files are valid, '
            if unsupported_files:
                err_msg += '\n\n'
                err_msg += '- Unsupported Format\n    '
                err_msg += '\n    '.join([os.path.basename(p) for p in unsupported_files])
            if duplicated_files:
                err_msg += '\n\n'
                err_msg += '- Duplicated Files\n    '
                err_msg += '\n    '.join([os.path.basename(p) for p in duplicated_files])

            qmsgBox = QtWidgets.QMessageBox(self)
            qmsgBox.setText(err_msg)
            qmsgBox.setWindowTitle('Drop Error')
            qmsgBox.addButton('  OK  ', QtWidgets.QMessageBox.AcceptRole)
            qmsgBox.setIcon(QtWidgets.QMessageBox.Critical)
            qmsgBox.exec_()

    def get_current_paths(self):
        rootItem = self.drop_widget.invisibleRootItem()
        paths = []
        for i in range(rootItem.childCount()):
            item = rootItem.child(i)
            path = item.data(QtCore.Qt.UserRole, 0)
            paths.append(path)
        return paths

    def browse_directory(self):
        dirpath = QtWidgets.QFileDialog.getExistingDirectory(parent=self, 
                                                            caption='Browse Output Directory',
                                                            dir=os.path.expanduser('~'))
        if dirpath:
            self.dest_lineEdit.setText(dirpath.replace('\\', '/'))

    def browse_watermark(self):
        dirpath = QtWidgets.QFileDialog.getOpenFileName(parent=self, 
                                                        caption='Browse Overlay Image',
                                                        dir=os.path.dirname(WATERMARK_PATH))[0]
        if dirpath:
            self.watermark_lineEdit.setText(dirpath.replace('\\', '/'))

    def check_user_inputs(self):
        name = self.reciever_lineEdit.text()
        task = self.task_lineEdit.text()
        paths = self.get_current_paths()
        overlay_path = self.watermark_lineEdit.text()  # overlay path 
        if not name or not task or not paths:
            err_msg = 'Invalid inputs,\n'
            if not name or not file_utils.is_ascii(text=name):
                err_msg += '- Please fill the name of reciever in English\n'
            if not task or not file_utils.is_ascii(text=task):
                err_msg += '- Please fill task name in English\n'
            if not paths:
                err_msg += '- No files to stamp watermark'
            if not overlay_path or not os.path.exists(overlay_path):
                err_msg += '- Overlay image doesn\'t exist'

            qmsgBox = QtWidgets.QMessageBox(self)
            qmsgBox.setText(err_msg)
            qmsgBox.setWindowTitle('Inputs Error')
            qmsgBox.addButton('  OK  ', QtWidgets.QMessageBox.AcceptRole)
            qmsgBox.setIcon(QtWidgets.QMessageBox.Critical)
            qmsgBox.exec_()
            raise Exception('Invalid user inputs')

        # output dir
        output_dir = self.dest_lineEdit.text()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.expanduser("~/Desktop")

        return name, task, paths, output_dir, overlay_path

    def thread_stamp(self, input_paths, text, output_paths, overlay_path, opacity, resize): 
        self.thread = StampThread(input_paths=input_paths, 
                                text=text, 
                                output_paths=output_paths,
                                overlay_path=overlay_path,
                                opacity=opacity,
                                resize=resize,
                                callback_func=self.emit_subprogress, 
                                parent=self)

        # call update progress to update UI
        self.subProgressBar.setValue(0)
        self.update_main_progress((0, len(input_paths)))

        self.thread.progressStamped.connect(self.update_main_progress)
        self.thread.mediaStamped.connect(self.reset_progress_ui)
        self.thread.stampFinished.connect(self.stamp_finished)
        self.subprogress.connect(self.update_sub_progress)
        self.thread.start()

    def update_main_progress(self, results, *args, **kwargs):
        current, total = results
        # update statubar text
        status_text = 'Working on file: ({}/{})...'.format(current+1, total)
        self.statusBar.showMessage(status_text)
        # select the item in the list
        self.drop_widget.setCurrentItem(self.drop_widget.topLevelItem(current))
        # update progressbar
        self.mainProgressBar.setValue((current/float(total))*100)

    def emit_subprogress(self, callback_result, *args, **kwargs):
        self.subprogress.emit(callback_result)

    def update_sub_progress(self, callback_result, *args, **kwargs):
        current, total = callback_result
        percent = (float(current)/float(total)) * 100.0
        self.subProgressBar.setValue(int(percent))

    def reset_progress_ui(self, *args):
        self.mainProgressBar.setValue(0)
        self.subProgressBar.setValue(0)

    def stamp_finished(self, results, *args, **kwargs):
        paths, time_taken = results
        self.statusBar.showMessage('Finished in {} sec'.format(time_taken))
        self.reset_progress_ui()
        QtWidgets.QApplication.restoreOverrideCursor()

        qmsgBox = QtWidgets.QMessageBox(self)
        qmsgBox.setText('Stamp finished, please check your result.')
        qmsgBox.setWindowTitle('Success')
        qmsgBox.addButton('  OK  ', QtWidgets.QMessageBox.AcceptRole)
        qmsgBox.setIcon(QtWidgets.QMessageBox.Information)
        qmsgBox.exec_()

        self.enable_ui(value=True)

    def stamp(self):
        # check for user input first
        name, task, input_paths, output_dir, overlay_path = self.check_user_inputs()
        if self.adaptive_checkbox.isChecked():
            opacity = OPACITY_RANGE
        else:
            opacity = self.opacity_slider.value() * 0.01

        resize = None
        if self.resize_checkbox.isChecked():
            resize = int(self.resize_lineEdit.text())

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.enable_ui(value=False)
        self.statusBar.showMessage('Preparing to process...')

        rootItem = self.drop_widget.invisibleRootItem()
        # prepare text
        overlay_text = 'For {} - {} - {}'.format(name, task, datetime.strftime(datetime.today(), '%y/%m/%d'))
        folder_name = '{}_{}'.format(name, datetime.strftime(datetime.today(), '%y%m%d'))
        output_name_dir = '{}/{}'.format(output_dir, folder_name)
        if not os.path.exists(output_name_dir):
            os.makedirs(output_name_dir)

        # prepare output paths
        output_paths = []
        for i, path in enumerate(input_paths):
            baseName = os.path.basename(path)
            output_path = '{}/{}'.format(output_name_dir, baseName)
            output_paths.append(output_path)
        
        self.thread_stamp(input_paths=input_paths, 
                        text=overlay_text, 
                        output_paths=output_paths, 
                        overlay_path=overlay_path, 
                        opacity=opacity, 
                        resize=resize)
    
    def enable_ui(self, value):
        self.reciever_lineEdit.setEnabled(value)
        self.task_lineEdit.setEnabled(value)
        self.drop_widget.setEnabled(value)
        self.dest_lineEdit.setEnabled(value)
        self.browse_button.setEnabled(value)  
        self.delete_button.setEnabled(value)
        self.refresh_button.setEnabled(value)
        self.stamp_button.setEnabled(value) 
   
def show():
    app = QtWidgets.QApplication(sys.argv)
    myApp = Watermarkr()
    myApp.show()
    stylesheet.set_default(app)
    # draw_widget background
    myApp.drop_widget.setStyleSheet('background-image:url("{}/icons/bg.png");'.format(moduleDir))

    sys.exit(app.exec_())

if __name__ == '__main__':
    show()
