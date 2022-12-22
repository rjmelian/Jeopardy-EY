from PyQt6.QtGui import (
    QPainter,
    QPen,
    QBrush,
    QImage,
    QColor,
    QFont,
    QPalette,
    QPixmap,
    QTextDocument,
    QTextOption,
    QGuiApplication,
    QFontMetrics,
    QTransform
)
from PyQt6.QtWidgets import *  # QWidget, QApplication, QDesktopWidget, QPushButton
from PyQt6.QtCore import (
    Qt,
    QRectF,
    QRect,
    QPoint,
    QPointF,
    QTimer,
    QRect,
    QSize,
    QSizeF,
    QMargins,
)
from PyQt6.sip import delete
from .version import version
import qrcode


import os
import sys
from .retrieve import get_game, get_game_sum, get_random_game
from .game import game_params as gp
from .utils import resource_path, SongPlayer, add_shadow, DynamicLabel, DynamicButton
from .constants import DEBUG
from .helpmsg import helpmsg
import time
from threading import Thread, active_count
import re
import logging
from base64 import urlsafe_b64decode


WINDOWPAL= QPalette()
WINDOWPAL.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
WINDOWPAL.setColor(QPalette.ColorRole.WindowText, QColor("black"))
WINDOWPAL.setColor(QPalette.ColorRole.Text, QColor("black"))
WINDOWPAL.setColor(QPalette.ColorRole.Window, QColor("#fefefe"))
WINDOWPAL.setColor(QPalette.ColorRole.ButtonText, QColor("black"))

class Image(qrcode.image.base.BaseImage):
    def __init__(self, border, width, box_size):
        self.border = border
        self.width = width
        self.box_size = box_size
        size = (width + border * 2) * box_size
        self._image = QImage(
            size, size, QImage.Format.Format_RGB16)
        self._image.fill(WINDOWPAL.color(QPalette.ColorRole.Window))

    def pixmap(self):
        return QPixmap.fromImage(self._image)

    def drawrect(self, row, col):
        painter = QPainter(self._image)
        painter.fillRect(
            (col + self.border) * self.box_size,
            (row + self.border) * self.box_size,
            self.box_size, self.box_size,
            Qt.GlobalColor.black)

    def save(self, stream, kind=None):
        pass

class StartWidget(QWidget):
    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.setBrush(QBrush(WINDOWPAL.color(QPalette.ColorRole.Window)))
        # qp.drawPixmap(self.rect(), self.background_img)
        qp.drawRect(self.rect())


class Welcome(StartWidget):
    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game


        self.setPalette(WINDOWPAL)

        add_shadow(self, radius=0.2)

        self.background_img = QPixmap( resource_path("welcome_background.png") )

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.icon = QPixmap(resource_path("icon.png"))
        self.icon_label = DynamicLabel("", 0, self)

        icon_layout = QHBoxLayout()
        icon_layout.addStretch()
        icon_layout.addWidget(self.icon_label)
        icon_layout.addStretch()



        self.title_font = QFont()
        self.title_font.setBold(True)

        self.title_label = DynamicLabel("JParty!", lambda : self.height() * 0.1, self)
        self.title_label.setFont(self.title_font)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.version_label = DynamicLabel(f"version {version}", lambda : self.height() * 0.03)
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setStyleSheet("QLabel { color : grey}")

        select_layout = QHBoxLayout()

        template_url = "https://docs.google.com/spreadsheets/d/1_vBBsWn-EVc7npamLnOKHs34Mc2iAmd9hOGSzxHQX0Y/edit#gid=0"
        gameid_text = f"Game ID (from J-Archive URL)<br>or <a href=\"{template_url}\">GSheet ID for custom game</a>"
        self.gameid_label = DynamicLabel(gameid_text, lambda : self.height() * 0.1, self)
        self.gameid_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.gameid_label.setOpenExternalLinks(True)
        # self.gameid_label.setStyleSheet("background-color: red")

        self.textbox = QLineEdit(self)
        self.textbox.textChanged.connect(self.show_summary)
        f = self.textbox.font()
        self.textbox.setFont(f)

        button_layout = QVBoxLayout()
        self.start_button = DynamicButton("Start!", self)
        self.start_button.clicked.connect(self.game.start_game)
        self.start_button.setEnabled(False)

        self.rand_button = DynamicButton("Random", self)
        self.rand_button.clicked.connect(self.random)

        button_layout.addWidget(self.start_button,10)
        button_layout.addStretch(1)
        button_layout.addWidget(self.rand_button,10)

        select_layout.addStretch(5)
        select_layout.addWidget(self.gameid_label, 40)
        select_layout.addStretch(2)
        select_layout.addWidget(self.textbox, 40)
        select_layout.addLayout(button_layout, 20)
        select_layout.addStretch(5)


        self.summary_label = DynamicLabel("", lambda : self.height() * 0.04, self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        # self.summary_label.setStyleSheet("background-color: blue;")

        self.quit_button = DynamicButton("Quit", self)
        self.quit_button.clicked.connect(self.game.close)

        self.help_button = DynamicButton("Show help", self)
        self.help_button.clicked.connect(self.show_help)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch(5)
        footer_layout.addWidget(self.quit_button, 3)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.help_button, 3)
        footer_layout.addStretch(5)

        main_layout.addStretch(3)
        main_layout.addLayout(icon_layout, 6)
        main_layout.addWidget(self.title_label, 3)
        main_layout.addWidget(self.version_label, 1)
        main_layout.addStretch(1)
        main_layout.addLayout(select_layout, 5)
        main_layout.addStretch(1)
        main_layout.addWidget(self.summary_label, 5)
        main_layout.addLayout(footer_layout,3)
        main_layout.addStretch(3)

        self.setLayout(main_layout)

        if DEBUG:
            self.textbox.setText(str(2534))  # EDIT

        self.show()


    def show_help(self):
        logging.info("Showing help")
        msgbox = QMessageBox(
            QMessageBox.Icon.NoIcon,
            "JParty Help",
            helpmsg,
            QMessageBox.StandardButton.Ok,
            self
        )
        msgbox.exec()


    def resizeEvent(self, event):
        icon_size = self.icon_label.height()
        self.icon_label.setPixmap(
            self.icon.scaled(
                icon_size,
                icon_size,
                transformMode=Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.icon_label.setMaximumWidth(icon_size)

        textbox_height = self.gameid_label.height() * 0.8
        self.textbox.setMinimumSize(QSize(0, textbox_height))
        f = self.textbox.font()
        f.setPixelSize(textbox_height * 0.9)  # sets the size to 27
        self.textbox.setFont(f)

        # qp.setBrush(FILLBRUSH)
        # qp.drawRect(QRect(0,0,200,200))

    # def show_overlay(self):
    #     if not DEBUG:
    #         self.host_overlay = HostOverlay(
    #         self.windowHandle().setScreen(QApplication.instance().screens()[1])
    #         self.host_overlay.showNormal()


    def __random(self):
        complete = False
        while not complete:
            game_id = get_random_game()
            logging.info(f"GAMEID {game_id}")
            self.game.data = get_game(game_id)
            complete = self.game.valid_game()
            time.sleep(0.25)

        self.textbox.setText(str(game_id))
        self.textbox.show()

    def random(self, checked):
        self.summary_label.setText("Loading...")
        t = Thread(target=self.__random)
        t.start()

    def __show_summary(self):
        game_id = self.textbox.text()
        try:
            self.game.data = get_game(game_id)
            if self.game.valid_game():
                gamedata = self.game.data
                self.summary_label.setText(gamedata.date + "\n" + gamedata.comments)
            else:
                self.summary_label.setText("Game has blank questions")

        except Exception as e:
            self.summary_label.setText("Cannot get game")
            raise e

        self.check_start()

    def show_summary(self, text=None):
        self.summary_label.setText("Loading...")
        t = Thread(target=self.__show_summary)
        t.start()

        self.check_start()

    def check_start(self):
        if self.game.startable():
            self.start_button.setEnabled(True)
        else:
            self.start_button.setEnabled(False)

    def restart(self):
        self.show_summary(self)





class QRWidget(StartWidget):
    def __init__(self, host, parent=None):
        super().__init__(parent)

        self.setPalette(WINDOWPAL)

        self.font = QFont()
        self.font.setPointSize(30)

        add_shadow(self, radius=0.2)

        main_layout = QVBoxLayout()

        self.background_img = QPixmap( resource_path("welcome_background.png") )

        self.hint_label = DynamicLabel("Scan for Buzzer:", self.start_fontsize, self)
        self.hint_label.setFont(self.font)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.qrlabel = QLabel(self)
        self.qrlabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.url = "http://" + host
        self.url_label = DynamicLabel(self.url, self.start_fontsize, self)
        self.url_label.setFont(self.font)
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addStretch(1)
        main_layout.addWidget(self.hint_label, 2)
        main_layout.addWidget(self.qrlabel, 9)
        main_layout.addWidget(self.url_label, 2)
        main_layout.addStretch(1)

        self.setLayout(main_layout)

        self.show()

    def start_fontsize(self):
        return 0.1 * self.width()

    def resizeEvent(self, event):
        self.qrlabel.setPixmap(
            qrcode.make(self.url,
                        image_factory=Image,
                        box_size=max(self.height() / 40, 1)).pixmap())

    def restart(self):
        pass
