from PyQt5 import QtGui, QtCore, uic
from PyQt5.QtWidgets import (QTableWidgetItem, QGridLayout, QGroupBox, QLineEdit,
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QComboBox, QScrollArea)
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from ecog.utils import bands as default_bands
from ecog.signal_processing.preprocess_data import preprocess_data
from .FS_colorLUT import get_lut
from threading import Event, Thread
import numpy as np
from scipy import signal
import os
import time

path = os.path.dirname(__file__)

# Creates custom interval type -------------------------------------------------
Ui_CustomInterval, _ = uic.loadUiType(os.path.join(path,"intervals_gui.ui"))
class CustomIntervalDialog(QtGui.QDialog, Ui_CustomInterval):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

    def getResults(self):
        if self.exec_() == QtGui.QDialog.Accepted:
            # get all values
            text = str(self.lineEdit.text())
            color = str(self.comboBox.currentText())
            return text, color
        else:
            return '', ''


# Warning of no High gamma data in the NWB file ------------ -------------------
class NoHighGammaDialog(QtGui.QDialog):
    def __init__(self):
        super().__init__()
        self.text = QLabel("There is no high gamma data in the current NWB file.\n"+
                           "To calculate high gamma power traces, got to:\n"+
                           "Tools -> Analysis -> Spectral Analysis")
        self.okButton = QtGui.QPushButton("OK")
        self.okButton.clicked.connect(self.onAccepted)
        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(self.text)
        vbox.addWidget(self.okButton)
        self.setLayout(vbox)
        self.setWindowTitle('No high gama data')
        self.exec_()

    def onAccepted(self):
        self.accept()


# Warning of no High gamma data in the NWB file --------------------------------
class NoPreprocessedDialog(QtGui.QDialog):
    def __init__(self):
        super().__init__()
        self.text = QLabel("There is no preprocessed data in the current NWB file.\n"+
                           "To generate preprocessed voltage traces, got to:\n"+
                           "Tools -> Analysis -> Spectral Analysis")
        self.okButton = QtGui.QPushButton("OK")
        self.okButton.clicked.connect(self.onAccepted)
        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(self.text)
        vbox.addWidget(self.okButton)
        self.setLayout(vbox)
        self.setWindowTitle('No preprocessed data')
        self.exec_()

    def onAccepted(self):
        self.accept()


# Warning of no Trials data in the NWB file ------------------------------------
class NoTrialsDialog(QtGui.QDialog):
    def __init__(self):
        super().__init__()
        self.text = QLabel("There is no trials data in the current NWB file.\n"+
                           "Trial times are needed to generate ERP.")
        self.okButton = QtGui.QPushButton("OK")
        self.okButton.clicked.connect(self.onAccepted)
        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(self.text)
        vbox.addWidget(self.okButton)
        self.setLayout(vbox)
        self.setWindowTitle('No trial data')
        self.exec_()

    def onAccepted(self):
        self.accept()

# Calculates High gamma from data in the NWB file ------------------------------
class CalcHighGammaDialog(QtGui.QDialog):
    def __init__(self, parent):
        super().__init__()
        self.fpath = parent.model.pathName
        self.fname = parent.model.fileName
        self.value = -1

        self.okButton = QtGui.QPushButton("OK")
        self.okButton.setEnabled(True)
        self.okButton.clicked.connect(self.ok)
        self.cancelButton = QtGui.QPushButton("Cancel")
        self.cancelButton.clicked.connect(self.cancel)
        try:
            hg = parent.model.nwb.modules['ecephys'].data_interfaces['high_gamma'].data
            self.text = QLabel("High gamma data already exists in the current NWB file.")
            self.okButton.setEnabled(False)
        except:
            self.text = QLabel("Calculate high gamma power?\n"+
                                "The results will be saved in the current NWB file.")
        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.okButton)
        hbox.addWidget(self.cancelButton)
        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(self.text)
        vbox.addLayout(hbox)
        self.setLayout(vbox)
        self.setWindowTitle('Calculate high gama power')
        self.exec_()

    def ok(self):
        self.text.setText('Processing spectral decomposition. Please wait...')
        self.okButton.setEnabled(False)
        self.cancelButton.setEnabled(False)
        subj, aux = self.fname.split('_')
        block = [ aux.split('.')[0][1:] ]
        self.thread = ChildProgram(path=self.fpath, subject=subj,
                                   blocks=block, filter='high_gamma',
                                   bands_vals=None)
        self.thread.finished.connect(self.out_close)
        self.thread.start()

    def out_close(self):
        self.value = 1
        self.accept()

    def cancel(self):
        self.value = -1
        self.accept()


# Exit confirmation ------------------------------------------------------------
Ui_Exit, _ = uic.loadUiType(os.path.join(path,"exit_gui.ui"))
class ExitDialog(QtGui.QDialog, Ui_Exit):
    def __init__(self, parent):
        super().__init__()
        self.setupUi(self)

        self.pushButton_1.setEnabled(False)
        self.pushButton_1.clicked.connect(self.save)
        self.pushButton_2.clicked.connect(self.cancel)
        self.pushButton_3.clicked.connect(self.exit)

        if parent.model.unsaved_changes_annotation or parent.model.unsaved_changes_interval:
            text = "There are unsaved changes in this session.\n"+ \
                   "Do you want to save them before exit?"
            self.label.setText(text)
            self.pushButton_1.setEnabled(True)

        self.setWindowTitle('Exit ecogVIS')
        self.exec_()

    def save(self):
        self.value = 1
        self.accept()

    def cancel(self):
        self.value = 0
        self.accept()

    def exit(self):
        self.value = -1
        self.accept()


# Selects channels from specific brain regions to be plotted -------------------
class SelectChannelsDialog(QtGui.QDialog):
    def __init__(self, stringlist, checked):
        super().__init__()

        self.model = QtGui.QStandardItemModel()
        for i, string in enumerate(stringlist):
            item = QtGui.QStandardItem(string)
            item.setCheckable(True)
            check = (QtCore.Qt.Checked if checked[i] else QtCore.Qt.Unchecked)
            item.setCheckState(check)
            self.model.appendRow(item)

        self.listView = QtGui.QListView()
        self.listView.setModel(self.model)

        self.okButton = QtGui.QPushButton("OK")
        self.selectButton = QtGui.QPushButton("Select All")
        self.unselectButton = QtGui.QPushButton("Unselect All")

        hbox = QtGui.QHBoxLayout()
        hbox.addStretch(1)
        hbox.addWidget(self.okButton)
        hbox.addWidget(self.selectButton)
        hbox.addWidget(self.unselectButton)

        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(self.listView)
        #vbox.addStretch(1)
        vbox.addLayout(hbox)

        self.setLayout(vbox)
        #self.setLayout(layout)
        self.setWindowTitle('Select Regions:')

        self.okButton.clicked.connect(self.onAccepted)
        self.selectButton.clicked.connect(self.select_all)
        self.unselectButton.clicked.connect(self.unselect_all)

        self.select_all()
        self.choices = [self.model.item(i).text() for i in
                        range(self.model.rowCount())
                        if self.model.item(i).checkState()
                        == QtCore.Qt.Checked]
        self.exec_()

    def onAccepted(self):
        self.choices = [self.model.item(i).text() for i in
                        range(self.model.rowCount())
                        if self.model.item(i).checkState()
                        == QtCore.Qt.Checked]
        self.accept()

    def select_all(self):
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            item.setCheckState(QtCore.Qt.Checked)

    def unselect_all(self):
        for i in range(self.model.rowCount()):
            item = self.model.item(i)
            item.setCheckState(QtCore.Qt.Unchecked)


# Creates Spectral Analysis choice dialog --------------------------------------
Ui_SpectralChoice, _ = uic.loadUiType(os.path.join(path,"spectral_choice_gui.ui"))
class SpectralChoiceDialog(QtGui.QDialog, Ui_SpectralChoice):
    def __init__(self, nwb, fpath, fname):
        super().__init__()
        self.setupUi(self)
        self.nwb = nwb
        self.fpath = fpath
        self.fname = fname

        self.data_exists = False    #Indicates if data already exists or will be created
        self.decomp_type = None     #Indicates the chosen decomposition type
        self.custom_bands = None    #Values for custom filter bands (user input)
        self.value = -1             #Reference value for user pressed exit button

        self.radioButton_1.clicked.connect(self.choice_default)
        self.radioButton_2.clicked.connect(self.choice_highgamma)
        self.radioButton_3.clicked.connect(self.choice_custom)
        self.pushButton_1.clicked.connect(self.add_band)
        self.pushButton_2.clicked.connect(self.del_band)

        self.runButton.clicked.connect(self.run_decomposition)
        self.runButton.setEnabled(False)
        self.cancelButton.clicked.connect(self.out_cancel)
        self.setWindowTitle('Spectral decomposition')
        self.exec_()

    def choice_default(self):  # default chosen
        self.decomp_type = 'default'
        self.custom_bands = None
        self.pushButton_1.setEnabled(False)
        self.pushButton_2.setEnabled(False)
        self.tableWidget.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        try:    # if data already exists in file
            decomp = self.nwb.modules['ecephys'].data_interfaces['Bandpower_default']
            text = "'Default' frequency decomposition data already exists in current file.\n" \
                   "The bands are shown in the table."
            self.label_1.setText(text)
            self.runButton.setEnabled(False)
            self.data_exists = True
            # Populate table with values
            self.tableWidget.setHorizontalHeaderLabels(['center','sigma'])
            p0 = decomp.bands['filter_param_0']
            p1 = decomp.bands['filter_param_1']
            self.tableWidget.setRowCount(len(p0))
            for i in np.arange(len(p0)):
                self.tableWidget.setItem(i, 0, QTableWidgetItem(str(round(p0[i],1))))
                self.tableWidget.setItem(i, 1, QTableWidgetItem(str(round(p1[i],1))))
        except:   # if data does not exist in file
            text = "'Default' frequency decomposition data does not exist in current file.\n" \
                   "It can be created from the bands shown in the table. "\
                   "The results will be saved in the current NWB file.\nDo you want to create it?"
            self.label_1.setText(text)
            self.data_exists = False
            self.runButton.setEnabled(True)
            # Populate table with values
            self.tableWidget.setHorizontalHeaderLabels(['center [Hz]','sigma [Hz]'])
            p0 = default_bands.chang_lab['cfs']
            p1 = default_bands.chang_lab['sds']
            self.tableWidget.setRowCount(len(p0))
            for i in np.arange(len(p0)):
                self.tableWidget.setItem(i, 0, QTableWidgetItem(str(round(p0[i],1))))
                self.tableWidget.setItem(i, 1, QTableWidgetItem(str(round(p1[i],1))))

    def choice_highgamma(self):  # default chosen
        self.decomp_type = 'high_gamma'
        self.custom_bands = None
        self.pushButton_1.setEnabled(False)
        self.pushButton_2.setEnabled(False)
        self.tableWidget.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        try:    # if data already exists in file
            decomp = self.nwb.modules['ecephys'].data_interfaces['high_gamma']
            text = "'High gamma' frequency decomposition data already exists in current file.\n" \
                   "It corresponds to the averaged power of the bands shown in the table."
            self.label_1.setText(text)
            self.data_exists = True
            self.runButton.setEnabled(False)
            # Populate table with values
            self.tableWidget.setHorizontalHeaderLabels(['center [Hz]','sigma [Hz]'])
            p0 = default_bands.chang_lab['cfs'][29:37]
            p1 = default_bands.chang_lab['sds'][29:37]
            self.tableWidget.setRowCount(len(p0))
            for i in np.arange(len(p0)):
                self.tableWidget.setItem(i, 0, QTableWidgetItem(str(round(p0[i],1))))
                self.tableWidget.setItem(i, 1, QTableWidgetItem(str(round(p1[i],1))))
        except:   # if data does not exist in file
            text = "'High gamma' frequency decomposition data does not exist in current file.\n" \
                   "It can be created from the averaged power of the bands shown in the table. "\
                   "The results will be saved in the current NWB file.\nDo you want to create it?"
            self.label_1.setText(text)
            self.data_exists = False
            self.runButton.setEnabled(True)
            # Populate table with values
            self.tableWidget.setHorizontalHeaderLabels(['center [Hz]','sigma [Hz]'])
            p0 = default_bands.chang_lab['cfs'][29:37]
            p1 = default_bands.chang_lab['sds'][29:37]
            self.tableWidget.setRowCount(len(p0))
            for i in np.arange(len(p0)):
                self.tableWidget.setItem(i, 0, QTableWidgetItem(str(round(p0[i],1))))
                self.tableWidget.setItem(i, 1, QTableWidgetItem(str(round(p1[i],1))))


    def choice_custom(self):  # default chosen
        self.decomp_type = 'custom'
        self.custom_bands = None
        try:    # if data already exists in file
            decomp = self.nwb.modules['ecephys'].data_interfaces['Bandpower_custom']
            text = "'Custom' frequency decomposition data already exists in current file.\n" \
                   "The bands are shown in the table."
            self.label_1.setText(text)
            self.data_exists = True
            self.runButton.setEnabled(False)
            # Populate table with values
            self.tableWidget.setHorizontalHeaderLabels(['center [Hz]','sigma [Hz]'])
            p0 = decomp.bands['filter_param_0']
            p1 = decomp.bands['filter_param_1']
            self.tableWidget.setRowCount(len(p0))
            self.custom_bands = np.zeros((2,len(p0)))
            for i in np.arange(len(p0)):
                self.tableWidget.setItem(i, 0, QTableWidgetItem(str(round(p0[i],1))))
                self.tableWidget.setItem(i, 1, QTableWidgetItem(str(round(p1[i],1))))
                self.custom_bands[i,0] = round(p0[i],1)
                self.custom_bands[i,1] = round(p1[i],1)
        except:  # if data does not exist in file
            text = "'Custom' frequency decomposition data does not exist in current file.\n" \
                   "To create it, add the bands of interest to the table. "\
                   "The results will be saved in the current NWB file.\nDo you want to create it?"
            self.label_1.setText(text)
            self.data_exists = False
            self.runButton.setEnabled(True)
            # Allows user to populate table with values
            self.tableWidget.setRowCount(1)
            self.tableWidget.setHorizontalHeaderLabels(['center [Hz]','sigma [Hz]'])
            self.tableWidget.setItem(0, 0, QTableWidgetItem(str(0)))
            self.tableWidget.setItem(0, 1, QTableWidgetItem(str(0)))
            self.tableWidget.setEditTriggers(QtGui.QAbstractItemView.DoubleClicked)
            self.pushButton_1.setEnabled(True)
            self.pushButton_2.setEnabled(True)

    def add_band(self):
        nRows = self.tableWidget.rowCount()
        self.tableWidget.insertRow(nRows)
        self.tableWidget.setItem(nRows, 0, QTableWidgetItem(str(0)))
        self.tableWidget.setItem(nRows, 1, QTableWidgetItem(str(0)))

    def del_band(self):
        nRows = self.tableWidget.rowCount()
        self.tableWidget.removeRow(nRows-1)

    def run_decomposition(self):
        if self.decomp_type=='custom':
            nRows = self.tableWidget.rowCount()
            self.custom_bands = np.zeros((2,nRows))
            for i in np.arange(nRows):
                self.custom_bands[0,i] = float(self.tableWidget.item(i, 0).text())
                self.custom_bands[1,i] = float(self.tableWidget.item(i, 1).text())
        # If Decomposition data does not exist in NWB file and user decides to create it
        self.label_2.setText('Processing spectral decomposition. Please wait...')
        self.pushButton_1.setEnabled(False)
        self.pushButton_2.setEnabled(False)
        self.tableWidget.setEnabled(False)
        self.groupBox.setEnabled(False)
        self.runButton.setEnabled(False)
        self.cancelButton.setEnabled(False)
        if not self.data_exists:
            subj, aux = self.fname.split('_')
            block = [ aux.split('.')[0][1:] ]
            self.thread = ChildProgram(path=self.fpath, subject=subj,
                                       blocks=block, filter=self.decomp_type,
                                       bands_vals=self.custom_bands)
            self.thread.finished.connect(self.out_close)
            self.thread.start()

    def out_close(self):
        self.value = 1
        self.accept()

    def out_cancel(self):
        self.value = -1
        self.accept()


class ChildProgram(QtCore.QThread):
    def __init__(self, path, subject, blocks, filter, bands_vals):
        super().__init__()
        self.fpath = path
        self.subject = subject
        self.blocks = blocks
        self.filter = filter
        self.bands_vals = bands_vals

    def run(self):
        preprocess_data(path=self.fpath,
                        subject=self.subject,
                        blocks=self.blocks,
                        filter=self.filter,
                        bands_vals=self.bands_vals)



# Creates Periodogram dialog ---------------------------------------------------
class PeriodogramDialog(QtGui.QDialog):
    def __init__(self, model, x, y):
        super().__init__()

        self.model = model
        self.x = x
        self.y = y
        self.relative_index = np.argmin(np.abs(self.model.scaleVec-self.y))
        self.chosen_channel = model.selectedChannels[self.relative_index]
        self.BIs = model.IntRects2

        self.fig1 = pg.PlotWidget()               #uppper periodogram plot
        self.fig2 = pg.PlotWidget()               #lower voltage plot
        self.fig1.setBackground('w')
        self.fig2.setBackground('w')

        grid = QGridLayout() #QVBoxLayout()
        grid.setSpacing(0.0)
        grid.setRowStretch(0, 2)
        grid.setRowStretch(1, 1)
        grid.addWidget(self.fig1)
        grid.addWidget(self.fig2)

        self.setLayout(grid)
        self.setWindowTitle('Periodogram')

        # Draw plots -----------------------------------------------------------
        startSamp = self.model.intervalStartSamples
        endSamp = self.model.intervalEndSamples

        # Upper Panel: Periodogram plot ----------------------------------------
        trace = model.plotData[startSamp-1:endSamp, self.chosen_channel]
        fs = model.fs_signal
        dF = 0.1       #Frequency bin size
        nfft = fs/dF   #dF = fs/nfft
        fx, Py = signal.periodogram(trace, fs=fs, nfft=nfft)

        plt1 = self.fig1   # Lower voltage plot
        plt1.clear()       # Clear plot
        plt1.setLabel('bottom', 'Band center', units = 'Hz')
        plt1.setLabel('left', 'Average power', units = 'V**2/Hz')
        plt1.setTitle('Channel #'+str(self.chosen_channel+1))
        plt1.plot(fx, Py, pen='k', width=1)
        plt1.setXRange(0., 200.)

        # Lower Panel: Voltage time series plot --------------------------------
        try:
            plotVoltage = self.model.plotData[startSamp - 1 : endSamp, self.chosen_channel]
        except:  #if time segment shorter than window.
            plotVoltage = self.model.plotData[:, self.chosen_channel]

        timebaseGuiUnits = np.arange(startSamp - 1, endSamp) * (self.model.intervalStartGuiUnits/self.model.intervalStartSamples)
        plt2 = self.fig2   # Lower voltage plot
        plt2.clear()       # Clear plot
        plt2.setLabel('bottom', 'Time', units='sec')
        plt2.setLabel('left', 'Signal', units='Volts')
        plt2.plot(timebaseGuiUnits, np.zeros(len(timebaseGuiUnits)), pen='k', width=.8)
        if self.chosen_channel in self.model.badChannels:
            plt2.plot(timebaseGuiUnits, plotVoltage, pen='r', width=.8, alpha=.3)
        else:
            plt2.plot(timebaseGuiUnits, plotVoltage, pen='b', width=1)
        plt2.setXRange(timebaseGuiUnits[0], timebaseGuiUnits[-1], padding=0.003)
        yrange = 3*np.std(plotVoltage)
        plt2.setYRange(-yrange, yrange, padding = 0.06)

        # Make red box around bad time segments
        for i in model.IntRects2:
            x = i.rect().left()
            w = i.rect().width()
            c = pg.QtGui.QGraphicsRectItem(x, -1, w, 2)
            bc = [250, 0, 0, 100]
            c.setPen(pg.mkPen(color=QtGui.QColor(bc[0], bc[1], bc[2], 255)))
            c.setBrush(QtGui.QColor(bc[0], bc[1], bc[2], bc[3]))
            plt2.addItem(c)

        self.exec_()



# Creates Group Periodogram dialog ---------------------------------------------
class GroupPeriodogramDialog(QtGui.QDialog):
    def __init__(self, model, x, y):
        super().__init__()

        self.model = model
        self.x = x
        self.y = y
        self.relative_index = np.argmin(np.abs(self.model.scaleVec-self.y))
        self.chosen_channel = model.selectedChannels[self.relative_index]
        self.BIs = model.IntRects2

        self.fig1 = gl.GLViewWidget()               #uppper periodogram plot
        #self.fig1.setBackgroundColor('w')
        self.fig2 = pg.PlotWidget()               #lower voltage plot
        self.fig2.setBackground('w')

        self.fig1.opts['distance'] = 200
        # create the background grids
        gx = gl.GLGridItem()
        gx.rotate(90, 0, 1, 0)
        gx.translate(-10, 0, 0)
        self.fig1.addItem(gx)
        gy = gl.GLGridItem()
        gy.rotate(90, 1, 0, 0)
        gy.translate(0, -10, 0)
        self.fig1.addItem(gy)
        gz = gl.GLGridItem()
        gz.translate(0, 0, -10)
        self.fig1.addItem(gz)

        grid = QGridLayout() #QVBoxLayout()
        grid.setSpacing(0.0)
        grid.setRowStretch(0, 2)
        grid.setRowStretch(1, 1)
        grid.addWidget(self.fig1)
        grid.addWidget(self.fig2)

        self.setLayout(grid)
        self.setWindowTitle('Periodogram')

        # Upper Panel: Periodogram plot ----------------------------------------
        startSamp = self.model.intervalStartSamples
        endSamp = self.model.intervalEndSamples
        fs = model.fs_signal
        dF = 0.1       #Frequency bin size
        nfft = fs/dF   #dF = fs/nfft
        X = np.zeros((2000,3))
        for i in np.array([1,2,3]): #self.model.selectedChannels:
            trace = model.plotData[startSamp-1:endSamp, self.chosen_channel-1]
            fx, Py = signal.periodogram(trace, fs=fs, nfft=nfft)
            X[:,0] = i
            X[:,1] = fx[0:2000]
            X[:,2] = Py[0:2000]
            print(i)
            line = gl.GLLinePlotItem(pos=X, color=pg.glColor('w'))
            line.setLabel('bottom', 'Frequency', units = 'Hz')
            #line.setData()
            self.fig1.addItem(line)
        #self.fig1.show()

        #plt1.setLabel('left', 'Average power', units = 'V**2/Hz')
        #plt1.setTitle('Channel #'+str(self.chosen_channel+1))
        #plt1.plot(fx, Py, pen='k', width=1)
        self.fig1.setXRange(0., 200.)

        self.exec_()




# Creates Event-Related Potential dialog ---------------------------------------
class ERPDialog(QtGui.QDialog):
    def __init__(self, parent):
        super().__init__()
        # Enable antialiasing for prettier plots
        pg.setConfigOptions(antialias=True)

        self.parent = parent
        self.nCols = 16
        self.reference = 'start_time'
        self.Y_start_mean = {}
        self.Y_start_sem = {}
        self.Y_stop_mean = {}
        self.Y_stop_sem = {}
        self.X = []
        self.Yscale = {}

        #Left panel
        self.push0_0 = QPushButton('Calc ERP')
        self.push0_0.clicked.connect(self.draw_erp)
        label1 = QLabel('Reference:')
        self.push1_0 = QPushButton('Start')
        self.push1_0.setCheckable(True)
        self.push1_0.setChecked(True)
        self.push1_0.clicked.connect(self.set_start)
        self.push1_1 = QPushButton('Stop')
        self.push1_1.setCheckable(True)
        self.push1_1.setChecked(False)
        self.push1_1.clicked.connect(self.set_stop)
        label2 = QLabel('Width (sec):')
        self.qline2 = QLineEdit('2')
        self.qline2.returnPressed.connect(self.set_width)
        label3 = QLabel('Y scale:')
        self.combo1 = QComboBox()
        self.combo1.addItem('individual')
        self.combo1.addItem('global max')
        self.combo1.addItem('global std')
        self.combo1.activated.connect(self.scale_plots)
        self.push2_0 = QPushButton('Significant')
        self.push2_0.setCheckable(True)
        self.push2_0.setChecked(False)
        self.push3_0 = QPushButton('Channels')
        self.push3_0.clicked.connect(self.channel_select)

        self.push1_0.setEnabled(False)
        self.push1_1.setEnabled(False)
        self.qline2.setEnabled(False)
        self.combo1.setEnabled(False)
        self.push2_0.setEnabled(False)
        self.push3_0.setEnabled(False)

        grid0 = QGridLayout()
        grid0.addWidget(label1, 0, 0, 1, 2)
        grid0.addWidget(self.push1_0, 1, 0, 1, 1)
        grid0.addWidget(self.push1_1, 1, 1, 1, 1)
        grid0.addWidget(QHLine(), 2, 0, 1, 2)
        grid0.addWidget(label2, 3, 0, 1, 2)
        grid0.addWidget(self.qline2, 4, 0, 1, 2)
        grid0.addWidget(QHLine(), 5, 0, 1, 2)
        grid0.addWidget(label3, 6, 0, 1, 2)
        grid0.addWidget(self.combo1, 7, 0, 1, 2)
        grid0.addWidget(QHLine(), 8, 0, 1, 2)
        grid0.addWidget(self.push2_0, 9, 0, 1, 2)
        grid0.addWidget(self.push3_0, 10, 0, 1, 2)
        grid0.setAlignment(QtCore.Qt.AlignTop)

        panel0 = QGroupBox('Controls:')
        panel0.setFixedWidth(120)
        panel0.setLayout(grid0)

        self.leftbox = QVBoxLayout()
        self.leftbox.addWidget(self.push0_0)
        self.leftbox.addWidget(panel0)

        # Right panel
        self.win = pg.GraphicsLayoutWidget()
        self.win.resize(1020,1020)
        #self.win.setBackground('w')
        background_color = self.palette().color(QtGui.QPalette.Background)
        self.win.setBackground(background_color)
        for j in range(16):
            self.win.ci.layout.setRowFixedHeight(j, 60)
            self.win.ci.layout.setColumnFixedWidth(j, 60)
            self.win.ci.layout.setColumnSpacing(j, 3)
            self.win.ci.layout.setRowSpacing(j, 3)
        #Scroll Area Properties
        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setWidgetResizable(False)
        scroll.setWidget(self.win)

        self.hbox = QHBoxLayout()
        #self.hbox.addWidget(panel0)
        self.hbox.addLayout(self.leftbox)
        self.hbox.addWidget(scroll)
        self.setLayout(self.hbox)
        self.setWindowTitle('Event-Related Potentials')
        self.resize(1200,600)
        self.exec_()

    def set_start(self):
        self.reference = 'start_time'
        self.push1_1.setChecked(False)
        self.draw_erp()

    def set_stop(self):
        self.reference = 'stop_time'
        self.push1_0.setChecked(False)
        self.draw_erp()

    def set_width(self):
        self.Y_start_mean = {}
        self.Y_start_sem = {}
        self.Y_stop_mean = {}
        self.Y_stop_sem = {}
        self.X = []
        self.draw_erp()

    def scale_plots(self):
        for ch in np.arange(256):
            row = np.floor(ch/self.nCols)
            col = ch%self.nCols
            p = self.win.getItem(row=row, col=col)
            if p == None:
                return
            else:
                curr_txt = self.combo1.currentText()
                if curr_txt!='individual':
                    p.setYRange(self.Yscale[curr_txt][0], self.Yscale[curr_txt][1])
                else:
                    if self.reference == 'start_time':
                        yrng = max(abs(self.Y_start_mean[str(ch)]))
                    else:
                        yrng = max(abs(self.Y_stop_mean[str(ch)]))
                    p.setYRange(-yrng, yrng)

    def get_psth(self, ch):
        if self.reference == 'start_time':
            if str(ch) in self.Y_start_mean:   #If it was calculated already
                return self.Y_start_mean[str(ch)], self.Y_start_sem[str(ch)], self.X
            else:                              #If it isn't calculated yet
                Y_mean, Y_sem, X = self.calc_psth(ch=ch)
                self.Y_start_mean[str(ch)] = Y_mean
                self.Y_start_sem[str(ch)] = Y_sem
                self.X = X
                return self.Y_start_mean[str(ch)], self.Y_start_sem[str(ch)], self.X
        if self.reference == 'stop_time':
            if str(ch) in self.Y_stop_mean:
                return self.Y_stop_mean[str(ch)], self.Y_stop_sem[str(ch)], self.X
            else:
                Y_mean, Y_sem, X = self.calc_psth(ch=ch)
                self.Y_stop_mean[str(ch)] = Y_mean
                self.Y_stop_sem[str(ch)] = Y_sem
                self.X = X
                return self.Y_stop_mean[str(ch)], self.Y_stop_sem[str(ch)], self.X

    def calc_psth(self, ch):
        data = self.parent.model.nwb.modules['ecephys'].data_interfaces['high_gamma'].data
        fs = 400.#self.parent.model.fs_signal
        ref_times = self.parent.model.nwb.trials[self.reference][:]
        ref_bins = (ref_times*fs).astype('int')
        nBinsTr = int(float(self.qline2.text())*fs/2)
        start_bins = ref_bins - nBinsTr
        stop_bins = ref_bins + nBinsTr
        nTrials = len(ref_times)
        Y = np.zeros((nTrials,2*nBinsTr))+np.nan
        for tr in np.arange(nTrials):
            Y[tr,:] = data[start_bins[tr]:stop_bins[tr], ch]
        Y_mean = np.nanmean(Y, 0)
        Y_sem = np.nanstd(Y, 0)/np.sqrt(Y.shape[0])
        X = np.arange(0, 2*nBinsTr)/fs
        return Y_mean, Y_sem, X

    def draw_erp(self):
        self.push1_0.setEnabled(True)
        self.push1_1.setEnabled(True)
        self.qline2.setEnabled(True)
        self.combo1.setEnabled(True)
        self.push2_0.setEnabled(True)
        self.push3_0.setEnabled(True)
        self.combo1.setCurrentIndex(self.combo1.findText('individual'))
        cmap = get_lut()
        ymin, ymax = 0, 0
        ystd = 0
        for j in np.arange(256):
            Y_mean, Y_sem, X = self.get_psth(ch=j)
            dc = np.mean(Y_mean)
            Y_mean -= dc
            ymax = max(max(Y_mean), ymax)
            ymin = min(min(Y_mean), ymin)
            ystd = max(np.std(Y_mean), ystd)
            row = np.floor(j/self.nCols)
            col = j%self.nCols
            p = self.win.getItem(row=row, col=col)
            if p == None:
                vb = CustomViewBox(self, j)
                p = self.win.addPlot(row=row, col=col, viewBox = vb)
            p.clear()
            p.setMouseEnabled(x=False, y=False)
            p.setToolTip('Ch '+str(j+1)+'\n'+str(self.parent.model.nwb.electrodes['location'][j]))
            #Background
            loc = 'ctx-lh-'+self.parent.model.nwb.electrodes['location'][j]
            vb = p.getViewBox()
            color = tuple(cmap[loc])
            vb.setBackgroundColor((*color,70))  # append alpha to color tuple
            #vb.border = pg.mkPen(color = 'w')
            #Main plots
            mean = p.plot(x=X, y=Y_mean, pen=(60,60,60))
            semp = p.plot(x=X, y=Y_mean+Y_sem, pen=pg.mkPen((100,100,100,100), width=.1))
            semm = p.plot(x=X, y=Y_mean-Y_sem, pen=pg.mkPen((100,100,100,100), width=.1))
            fill = pg.FillBetweenItem(semm, semp, pg.mkBrush(100,100,100,100))
            p.addItem(fill)
            p.hideButtons()
            p.setXRange(X[0], X[-1])
            yrng = max(abs(Y_mean))
            p.setYRange(-yrng, yrng)
            xref = [X[int(len(X)/2)], X[int(len(X)/2)]]
            yref = [-1000, 1000]
            p.plot(x=xref, y=yref, pen=(0,0,0))    #reference mark
            p.plot(x=X, y=np.zeros(len(X)), pen=(0,0,0))  #Zero line
            #Axis control
            left = p.getAxis('left')
            left.setStyle(showValues=False)
            left.setTicks([])
            bottom = p.getAxis('bottom')
            bottom.setStyle(showValues=False)
            bottom.setTicks([])
            #txt = pg.TextItem(text="Ch #"+str(j), color='k')
            #txt = pg.TextItem(html='<div style="text-align: center"><span style="color: #FFF; font-size: 6pt;">Ch #</span></div>')
            #p.addItem(txt)
            #txt.setPos(0, max(Y_mean))
        #store scale limits
        self.Yscale['global max'] = [ymin, ymax]
        self.Yscale['global std'] = [-ystd, ystd]

    ## Channel functions -------------------------------------------------------
    def channel_select(self):
        # Dialog to choose channels from specific brain regions
        w = SelectChannelsDialog(self.parent.model.all_regions, self.parent.model.regions_mask)



class QHLine(QtGui.QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QtGui.QFrame.HLine)
        self.setFrameShadow(QtGui.QFrame.Sunken)

## Viewbox for ERP plots -------------------------------------------------------
class CustomViewBox(pg.ViewBox):
    def __init__(self, parent, ch):
        pg.ViewBox.__init__(self)
        self.parent = parent
        self.ch = ch

    def mouseDoubleClickEvent(self, ev):
        row = np.floor(self.ch/self.parent.nCols)
        col = self.ch%self.parent.nCols
        p = self.parent.win.getItem(row=row, col=col)
        #vb = p.getViewBox()
        #vb.border = pg.mkPen(color = 'k')
        IndividualERPDialog(self)

    #def hoverEvent(self, ev):
        #print('hover')
        #print(self.ch)

# Individual Event-Related Potential dialog ---------------------------------------
class IndividualERPDialog(QtGui.QDialog):
    def __init__(self, parent):
        super().__init__()
        # Enable antialiasing for prettier plots
        pg.setConfigOptions(antialias=True)

        self.parent = parent
        self.ch = parent.ch
        self.reference = 'start_time'
        self.Yscale = {}

        #Left panel
        label1 = QLabel('Reference:')
        self.push1_0 = QPushButton('Start')
        self.push1_0.setCheckable(True)
        self.push1_0.setChecked(True)
        #self.push1_0.clicked.connect(self.set_start)
        self.push1_1 = QPushButton('Stop')
        self.push1_1.setCheckable(True)
        self.push1_1.setChecked(False)
        #self.push1_1.clicked.connect(self.set_stop)
        label2 = QLabel('Width (sec):')
        self.qline2 = QLineEdit('2')
        #self.qline2.returnPressed.connect(self.set_width)
        label3 = QLabel('Y scale:')
        self.combo1 = QComboBox()
        self.combo1.addItem('individual')
        self.combo1.addItem('global max')
        self.combo1.addItem('global std')
        #self.combo1.activated.connect(self.scale_plots)

        grid0 = QGridLayout()
        grid0.addWidget(label1, 0, 0, 1, 2)
        grid0.addWidget(self.push1_0, 1, 0, 1, 1)
        grid0.addWidget(self.push1_1, 1, 1, 1, 1)
        grid0.addWidget(QHLine(), 2, 0, 1, 2)
        grid0.addWidget(label2, 3, 0, 1, 2)
        grid0.addWidget(self.qline2, 4, 0, 1, 2)
        grid0.addWidget(QHLine(), 5, 0, 1, 2)
        grid0.addWidget(label3, 6, 0, 1, 2)
        grid0.addWidget(self.combo1, 7, 0, 1, 2)
        grid0.setAlignment(QtCore.Qt.AlignTop)

        panel0 = QGroupBox('Controls:')
        panel0.setFixedWidth(120)
        panel0.setLayout(grid0)

        self.leftbox = QVBoxLayout()
        self.leftbox.addWidget(panel0)

        # Right panel
        self.win = pg.GraphicsLayoutWidget()
        self.win.resize(900,600)
        self.win.setBackground('w')

        self.hbox = QHBoxLayout()
        #self.hbox.addWidget(panel0)
        self.hbox.addLayout(self.leftbox)
        self.hbox.addWidget(self.win)
        self.setLayout(self.hbox)
        self.setWindowTitle('Individual Event-Related Potential - Ch '+str(self.ch+1))
        self.resize(900, 600)

        self.draw_erp()
        self.exec_()

    def calc_psth(self, ch):
        data = self.parent.parent.parent.model.nwb.modules['ecephys'].data_interfaces['high_gamma'].data
        fs = 400.#self.parent.model.fs_signal
        ref_times = self.parent.parent.parent.model.nwb.trials[self.reference][:]
        ref_bins = (ref_times*fs).astype('int')
        nBinsTr = int(float(self.qline2.text())*fs/2)
        start_bins = ref_bins - nBinsTr
        stop_bins = ref_bins + nBinsTr
        nTrials = len(ref_times)
        Y = np.zeros((nTrials,2*nBinsTr))+np.nan
        for tr in np.arange(nTrials):
            Y[tr,:] = data[start_bins[tr]:stop_bins[tr], ch]
        Y_mean = np.nanmean(Y, 0)
        Y_sem = np.nanstd(Y, 0)/np.sqrt(Y.shape[0])
        X = np.arange(0, 2*nBinsTr)/fs
        return Y_mean, Y_sem, X

    def draw_erp(self):
        cmap = get_lut()
        Y_mean, Y_sem, X = self.calc_psth(ch=self.ch)
        dc = np.mean(Y_mean)
        Y_mean -= dc
        p = self.win.getItem(row=0, col=0)
        if p == None:
            p = self.win.addPlot(row=0, col=0)
        p.clear()
        p.setMouseEnabled(x=False, y=True)
        #Background color
        loc = 'ctx-lh-'+self.parent.parent.parent.model.nwb.electrodes['location'][self.ch]
        vb = p.getViewBox()
        color = tuple(cmap[loc])
        vb.setBackgroundColor((*color,70))  # append alpha to color tuple
        vb.border = pg.mkPen(color = 'w')
        #Main plots
        mean = p.plot(x=X, y=Y_mean, pen=pg.mkPen((60,60,60), width=2.))
        semp = p.plot(x=X, y=Y_mean+Y_sem, pen=pg.mkPen((100,100,100,100), width=.1))
        semm = p.plot(x=X, y=Y_mean-Y_sem, pen=pg.mkPen((100,100,100,100), width=.1))
        fill = pg.FillBetweenItem(semm, semp, pg.mkBrush(100,100,100,100))
        p.addItem(fill)
        p.hideButtons()
        p.setXRange(X[0], X[-1])
        p.setYRange(min(Y_mean), max(Y_mean))
        xref = [X[int(len(X)/2)], X[int(len(X)/2)]]
        yref = [-1000, 1000]
        p.plot(x=xref, y=yref, pen=(0,0,0))    #reference mark
        p.plot(x=X, y=np.zeros(len(X)), pen=(0,0,0))  #Zero line
        #Axis control
        left = p.getAxis('left')
        left.setStyle(showValues=False)
        left.setTicks([])
        bottom = p.getAxis('bottom')
        bottom.setStyle(showValues=False)
        bottom.setTicks([])
