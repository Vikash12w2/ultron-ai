import json
from pathlib import Path
from PySide6.QtCore import Qt, QThreadPool, QTimer, QEvent
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (QMainWindow,QWidget,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,QListWidget,QListWidgetItem,QTextBrowser,QTextEdit,QLineEdit,QFrame,QProgressBar,QDialog,QDialogButtonBox,QFormLayout,QComboBox,QCheckBox,QMessageBox,QTableWidget,QTableWidgetItem,QHeaderView,QFileDialog)
from config import APP_NAME,MODEL,OLLAMA_HOST,DATA_DIR,DATABASE,ALLOWED_ROOTS
from memory.database import Database
from core.agent import Agent
from gui.workers import ChatWorker

ROOT=Path(__file__).resolve().parent.parent
COLORS={"bg":"#0B0E13","panel":"#11151C","line":"#232A35","text":"#E8EAEE","muted":"#A3ACBA","accent":"#E5484D","blue":"#5AA9FF","gold":"#F2C14E"}

def icon(name,color="#E8EAEE"):
    path=ROOT/"ultron-icons"/"ultron-icons"/"ui"/(name+".svg")
    if not path.exists():return QIcon()
    from PySide6.QtGui import QPixmap
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    data=path.read_text(encoding="utf-8").replace("currentColor",color).encode()
    pix=QPixmap(24,24);pix.fill(Qt.GlobalColor.transparent);renderer=QSvgRenderer(QByteArray(data));from PySide6.QtGui import QPainter
    painter=QPainter(pix);renderer.render(painter);painter.end();return QIcon(pix)

class ApprovalDialog(QDialog):
    def __init__(self,description,parent=None):
        super().__init__(parent);self.setWindowTitle("ULTRON · Permission request");self.setMinimumWidth(470)
        lay=QVBoxLayout(self);title=QLabel("This action needs your approval");title.setStyleSheet("font-size:19px;font-weight:650")
        text=QLabel(description);text.setWordWrap(True);text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(title);lay.addWidget(QLabel("Review the exact action and resolved arguments."));lay.addWidget(text)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel);self.approve=buttons.addButton("Approve",QDialogButtonBox.ButtonRole.AcceptRole);self.approve.setObjectName("primary")
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);lay.addWidget(buttons)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle(APP_NAME);self.resize(1440,900);self.setMinimumSize(1000,650)
        appicon=ROOT/"ultron-icons"/"ultron-icons"/"app"/"ultron.ico"
        if appicon.exists():self.setWindowIcon(QIcon(str(appicon)))
        self.db=Database(DATABASE);self.pool=QThreadPool.globalInstance();self.agent=Agent(self.db,model=self.db.get_setting("model",MODEL),host=self.db.get_setting("ollama_host",OLLAMA_HOST))
        conversations=self.db.conversations();self.conversation_id=conversations[0]["id"] if conversations else self.db.new_conversation()
        self.low_memory=self.db.get_setting("low_memory","false")=="true";self.build();self.load_history();self.refresh_conversations();self.timer=QTimer(self);self.timer.timeout.connect(self.refresh_status);self.timer.start(5000);self.refresh_status()
    def build(self):
        self.setStyleSheet(f"""
        QMainWindow,QWidget{{background:{COLORS['bg']};color:{COLORS['text']};font-family:'Segoe UI';font-size:14px}}
        QFrame#top,QFrame#sidebar,QFrame#right{{background:{COLORS['panel']}}} QFrame#top{{border-bottom:1px solid {COLORS['line']}}}
        QFrame#sidebar{{border-right:1px solid {COLORS['line']}}} QFrame#right{{border-left:1px solid {COLORS['line']}}}
        QPushButton{{background:#191f29;border:1px solid {COLORS['line']};border-radius:10px;padding:10px 14px}} QPushButton:hover{{background:#222a36}}
        QPushButton#primary{{background:#C62F33;border:0;font-weight:600}} QPushButton#primary:hover{{background:{COLORS['accent']}}}
        QPushButton#new{{background:#201719;border:1px solid #3a2529;color:#ffdfe0;font-size:15px;font-weight:600}}
        QLineEdit,QTextEdit,QComboBox{{background:#11151c;border:1px solid {COLORS['line']};border-radius:10px;padding:10px;color:{COLORS['text']}}}
        QListWidget{{background:transparent;border:0;outline:0}} QListWidget::item{{padding:12px;border-radius:8px}} QListWidget::item:selected{{background:#1b222d}}
        QTextBrowser{{background:transparent;border:0;padding:8px}} QProgressBar{{background:#202630;border:0;border-radius:4px;height:8px;text-align:center}} QProgressBar::chunk{{background:#5AA9FF;border-radius:4px}}
        QHeaderView::section,QTableWidget{{background:{COLORS['panel']};border:1px solid {COLORS['line']};padding:7px}} QTableWidget{{gridline-color:{COLORS['line']}}}
        """)
        root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        top=QFrame(objectName="top");top.setFixedHeight(66);tl=QHBoxLayout(top);tl.setContentsMargins(22,8,22,8)
        brand=QLabel("◉  ULTRON");brand.setStyleSheet("font-size:21px;font-weight:750;letter-spacing:2px");tl.addWidget(brand)
        self.online=QLabel("●  Checking local AI…");self.online.setStyleSheet("color:#8ebfff;background:#172231;border:1px solid #283d56;border-radius:16px;padding:8px 12px");tl.addWidget(self.online);tl.addStretch()
        hist=QPushButton("History");hist.setIcon(icon("history"));hist.clicked.connect(self.show_history);tl.addWidget(hist)
        settings=QPushButton("Settings");settings.setIcon(icon("settings"));settings.clicked.connect(self.show_settings);tl.addWidget(settings);outer.addWidget(top)
        body=QHBoxLayout();body.setSpacing(0);outer.addLayout(body,1)
        side=QFrame(objectName="sidebar");side.setFixedWidth(290);sl=QVBoxLayout(side);sl.setContentsMargins(14,18,14,14)
        new=QPushButton("＋   New chat",objectName="new");new.clicked.connect(self.new_chat);sl.addWidget(new);self.search_chats=QLineEdit();self.search_chats.setPlaceholderText("⌕   Search chats");self.search_chats.textChanged.connect(self.filter_chats);sl.addWidget(self.search_chats)
        lbl=QLabel("YOUR CHATS");lbl.setStyleSheet("color:#7e899b;font-weight:bold;letter-spacing:1px;margin-top:15px");sl.addWidget(lbl)
        self.chat_list=QListWidget();self.chat_list.itemClicked.connect(self.select_chat);sl.addWidget(self.chat_list,1)
        body.addWidget(side)
        center=QWidget();cl=QVBoxLayout(center);cl.setContentsMargins(30,20,30,16)
        self.chat=QTextBrowser();self.chat.setOpenExternalLinks(True);cl.addWidget(self.chat,1)
        compose=QHBoxLayout();self.input=QTextEdit();self.input.setPlaceholderText("Type a message…   ·   Enter to send");self.input.setFixedHeight(76);self.input.installEventFilter(self);compose.addWidget(self.input,1)
        mic=QPushButton();mic.setIcon(icon("mic"));mic.setToolTip("Voice input requires optional voice dependencies");mic.clicked.connect(self.voice_unavailable);compose.addWidget(mic)
        send=QPushButton("Send ➤",objectName="primary");send.clicked.connect(self.send_message);compose.addWidget(send);cl.addLayout(compose)
        self.task=QLabel("Ready · Enter to send");self.task.setStyleSheet("color:#8792a4;padding:4px");cl.addWidget(self.task);body.addWidget(center,1)
        right=QFrame(objectName="right");right.setFixedWidth(300);rl=QVBoxLayout(right);rl.setContentsMargins(18,20,18,18)
        hdr=QLabel("SYSTEM");hdr.setStyleSheet("color:#7e899b;font-weight:bold;letter-spacing:1px");rl.addWidget(hdr)
        self.cpu_card,self.cpu_bar=self.metric_card("CPU");rl.addWidget(self.cpu_card)
        self.ram_card,self.ram_bar=self.metric_card("RAM");rl.addWidget(self.ram_card)
        self.model_card=QLabel(f"Model\n{MODEL}\n\nVoice  Off");self.model_card.setWordWrap(True);self.model_card.setStyleSheet("background:#141922;border:1px solid #252d39;border-radius:12px;padding:14px;line-height:1.5");rl.addWidget(self.model_card)
        taskhdr=QLabel("TASK");taskhdr.setStyleSheet("color:#7e899b;font-weight:bold;letter-spacing:1px;margin-top:12px");rl.addWidget(taskhdr)
        self.task_card=QLabel("Idle\nWaiting for your next command");self.task_card.setWordWrap(True);self.task_card.setStyleSheet("background:#141922;border:1px solid #252d39;border-radius:12px;padding:14px;color:#b8c0cc");rl.addWidget(self.task_card);rl.addStretch()
        log=QPushButton("☷  View action log");log.setStyleSheet("color:#72b6ff;text-decoration:underline;background:transparent;border:0;text-align:left");log.clicked.connect(self.show_logs);rl.addWidget(log);body.addWidget(right)
    def metric_card(self,title):
        card=QFrame();v=QVBoxLayout(card);v.setContentsMargins(12,10,12,12);line=QHBoxLayout();line.addWidget(QLabel(title));val=QLabel("—");val.setObjectName("value");line.addStretch();line.addWidget(val);v.addLayout(line);bar=QProgressBar();bar.setTextVisible(False);v.addWidget(bar);card.value_label=val;return card,bar
    def load_history(self):
        self.chat.clear()
        for m in self.db.messages(self.conversation_id):self.append_message(m["role"],m["content"])
    def append_message(self,role,text):
        who="You" if role=="user" else "ULTRON"; color="#9ca9bb" if role=="user" else "#E8EAEE"
        safe=(text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br>"))
        self.chat.append(f'<p style="margin:12px 0 4px;color:#8f9caf;font-size:12px;font-weight:bold">{who}</p><div style="color:{color};line-height:1.55;margin-bottom:20px">{safe}</div>')
    def refresh_conversations(self):
        self.chat_list.clear()
        for c in self.db.conversations():
            item=QListWidgetItem(c["title"]);item.setData(Qt.ItemDataRole.UserRole,c["id"]);self.chat_list.addItem(item)
            if c["id"]==self.conversation_id:self.chat_list.setCurrentItem(item)
    def filter_chats(self,text):
        for i in range(self.chat_list.count()):self.chat_list.item(i).setHidden(text.casefold() not in self.chat_list.item(i).text().casefold())
    def select_chat(self,item):self.conversation_id=item.data(Qt.ItemDataRole.UserRole);self.load_history()
    def new_chat(self):self.conversation_id=self.db.new_conversation();self.chat.clear();self.refresh_conversations();self.input.setFocus()
    def eventFilter(self,obj,event):
        if obj is self.input and event.type()==QEvent.Type.KeyPress and event.key()==Qt.Key.Key_Return and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send_message();return True
        return super().eventFilter(obj,event)
    def send_message(self):
        text=self.input.toPlainText().strip()
        if not text or self.pool.activeThreadCount():return
        self.input.clear();self.append_message("user",text);self.refresh_conversations();self.task.setText("ULTRON is thinking…");self.task_card.setText("Processing your request…")
        worker=ChatWorker(self.agent,self.conversation_id,text);worker.signals.result.connect(self.receive_answer);worker.signals.error.connect(self.receive_error);worker.signals.finished.connect(self.finished);worker.signals.status.connect(self.update_status);worker.signals.approval_requested.connect(self.request_approval);self.pool.start(worker)
    def request_approval(self,name,description,handshake):
        event,state=handshake;dialog=ApprovalDialog(description,self);state["approved"]=dialog.exec()==QDialog.DialogCode.Accepted;event.set()
    def receive_answer(self,text):self.append_message("assistant",text);self.task_card.setText("Done\nWaiting for your next command")
    def receive_error(self,text):self.append_message("assistant",f"I couldn't complete that: {text}");self.task_card.setText("Failed\nSee the error above")
    def finished(self):self.task.setText("Ready · Enter to send");self.refresh_conversations()
    def update_status(self,text):self.task.setText(text);self.task_card.setText(text)
    def voice_unavailable(self):QMessageBox.information(self,"Voice input","Voice is optional and isn't set up yet. Text chat works without it.")
    def refresh_status(self):
        try:
            import psutil
            cpu=psutil.cpu_percent(interval=None);mem=psutil.virtual_memory();self.cpu_card.value_label.setText(f"{cpu:.0f}%");self.cpu_bar.setValue(int(cpu));self.ram_card.value_label.setText(f"{mem.used/1024**3:.1f} / {mem.total/1024**3:.1f} GB");self.ram_bar.setValue(int(mem.percent))
            self.ram_bar.setStyleSheet("QProgressBar::chunk{background:#F2C14E}" if mem.percent>=80 else "")
        except ImportError:self.cpu_card.value_label.setText("psutil missing");self.ram_card.value_label.setText("psutil missing")
        try:
            import ollama
            data=ollama.Client(host=self.db.get_setting("ollama_host",OLLAMA_HOST)).list();models=getattr(data,"models",None)
            if models is None:models=data.get("models",[])
            tags=[getattr(m,"model",None) or getattr(m,"name",None) or (m.get("name",m.get("model","")) if isinstance(m,dict) else "") for m in models]
            self.online.setText("●  Local AI online" if tags else "●  Ollama online · no models")
            selected=self.db.get_setting("model",MODEL);found=next((t for t in tags if t==selected or t.split(":")[0]==selected.split(":")[0]),None)
            self.model_card.setText(f"Model\n{selected}\n\nState  {'Available' if found else 'Not downloaded'}\nVoice  {'Off · low-memory mode' if self.low_memory else 'Not configured'}")
        except Exception:self.online.setText("●  Local AI unavailable");self.online.setStyleSheet("color:#ff9a83;background:#241916;border:1px solid #50342d;border-radius:16px;padding:8px 12px")
    def show_history(self):
        dlg=QDialog(self);dlg.setWindowTitle("Conversation history");dlg.resize(520,460);lay=QVBoxLayout(dlg);lst=QListWidget()
        for c in self.db.conversations():it=QListWidgetItem(c["title"]);it.setData(Qt.ItemDataRole.UserRole,c["id"]);lst.addItem(it)
        lay.addWidget(lst);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dlg.reject);lay.addWidget(buttons)
        def choose(item):self.conversation_id=item.data(Qt.ItemDataRole.UserRole);self.load_history();self.refresh_conversations();dlg.accept()
        lst.itemDoubleClicked.connect(choose);dlg.exec()
    def show_logs(self):
        dlg=QDialog(self);dlg.setWindowTitle("Action log");dlg.resize(900,520);lay=QVBoxLayout(dlg);table=QTableWidget(0,5);table.setHorizontalHeaderLabels(["Time","Tool","Approval","Status","Result"]);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row in self.db.action_logs():
            i=table.rowCount();table.insertRow(i)
            for col,key in enumerate(("created_at","tool","approval","status","result")):table.setItem(i,col,QTableWidgetItem(str(row[key])))
        lay.addWidget(table);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dlg.reject);lay.addWidget(buttons);dlg.exec()
    def show_settings(self):
        dlg=QDialog(self);dlg.setWindowTitle("ULTRON settings");dlg.resize(600,500);layout=QVBoxLayout(dlg);form=QFormLayout();layout.addLayout(form)
        model=QComboBox();model.setEditable(True);model.addItems([MODEL,"llama3.2:latest"]);model.setCurrentText(self.db.get_setting("model",MODEL));host=QLineEdit(self.db.get_setting("ollama_host",OLLAMA_HOST));low=QCheckBox("Low-memory mode (voice disabled)");low.setChecked(self.low_memory)
        form.addRow("Ollama model",model);form.addRow("Ollama address",host);form.addRow("Memory",low);form.addRow("Data stored locally",QLabel(str(DATABASE)))
        roots=QListWidget()
        for r in ALLOWED_ROOTS:roots.addItem(str(r))
        layout.addWidget(QLabel("Allowed folders · file tools cannot access other locations"));layout.addWidget(roots)
        add=QPushButton("Add allowed folder…");layout.addWidget(add)
        def add_root():
            path=QFileDialog.getExistingDirectory(dlg,"Choose an allowed folder",str(Path.home()))
            if path and not any(Path(path).resolve()==Path(roots.item(i).text()).resolve() for i in range(roots.count())):roots.addItem(path)
        add.clicked.connect(add_root);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);layout.addWidget(buttons)
        if dlg.exec()==QDialog.DialogCode.Accepted:
            self.db.set_setting("model",model.currentText().strip());self.db.set_setting("ollama_host",host.text().strip());self.db.set_setting("low_memory",str(low.isChecked()).lower());self.low_memory=low.isChecked()
            from security.path_security import PathSecurity
            try:
                allowed=[roots.item(i).text() for i in range(roots.count())]
                PathSecurity(allowed);self.db.set_setting("allowed_roots",json.dumps(allowed))
                self.agent.registry.fs.security=PathSecurity(allowed)
            except Exception as exc:QMessageBox.warning(self,"Invalid folder",str(exc))
            self.agent.provider.model=self.db.get_setting("model",MODEL);self.agent.provider.host=self.db.get_setting("ollama_host",OLLAMA_HOST);self.refresh_status()
