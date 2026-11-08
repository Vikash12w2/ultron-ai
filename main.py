import sys

def main():
    try:
        from PySide6.QtWidgets import QApplication,QMessageBox
    except ImportError:
        print("ULTRON needs PySide6. From this project folder, install the packages listed in requirements.txt, then run: python main.py")
        return 2
    from gui.main_window import MainWindow
    app=QApplication(sys.argv);app.setApplicationName("ULTRON")
    window=MainWindow();window.show()
    return app.exec()

if __name__=="__main__":raise SystemExit(main())
