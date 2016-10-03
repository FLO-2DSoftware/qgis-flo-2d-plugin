# fix issue with loading of PyQT libraries before QGIS PyQT libraries
# /usr/lib/python2.7/dist-packages/qgis/PyQt/QtCore.py
import sip
for api in ["QDate", "QDateTime", "QString", "QTextStream", "QTime", "QUrl", "QVariant"]:
    sip.setapi(api, 2)
