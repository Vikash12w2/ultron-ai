import os
import sys

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
INSTANCE_NAME = "ULTRON-single-instance"


def main() -> int:
    try:
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("ULTRON needs its packages. In this folder run:  pip install -r requirements.txt")
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName("ULTRON")
    app.setQuitOnLastWindowClosed(False)


    probe = QLocalSocket()
    probe.connectToServer(INSTANCE_NAME)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(INSTANCE_NAME)
    server = QLocalServer()
    server.listen(INSTANCE_NAME)

    try:
        from gui.main_window import MainWindow
    except ModuleNotFoundError as exc:
        print(f"ULTRON is missing the package '{exc.name}'. In this folder run:\n"
              "    python -m pip install -r requirements.txt")
        return 2
    window = MainWindow()

    def on_connection():
        conn = server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(window.show_window)
    server.newConnection.connect(on_connection)

    if "--background" in sys.argv and window.tray:
        window.tray.showMessage("ULTRON", "Running in the background. Ctrl+Alt+Space for voice mode.")
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())