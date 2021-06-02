from types import SimpleNamespace
from PyQt5.QtCore import Qt
from PyQt5.QtMultimedia import QSound
import threading
import time
from dataclasses import dataclass
import pickle
import os
import sys

from .constants import DEBUG

# BUZZ_DELAY = 0 # ms

activation_time = 0


def rasync(f, *args, **kwargs):
    t = threading.Thread(target=f, args=args, kwargs=kwargs)
    t.start()


class QuestionTimer(object):
    def __init__(self, interval, f, *args, **kwargs):
        super().__init__()
        self.f = f
        self.args = args
        self.kwargs = kwargs
        self.interval = interval
        self.__thread = None
        self.__start_time = None
        self.__elapsed_time = 0

    def run(self, i):
        thread = self.__thread
        time.sleep(i)
        if thread == self.__thread:
            self.f(*self.args, **self.kwargs)

    def start(self):
        """wrapper for resume"""
        self.resume()

    def cancel(self):
        """wrapper for pause"""
        self.pause()

    def pause(self):
        self.__thread = None
        self.__elapsed_time += time.time() - self.__start_time

    def resume(self):
        self.__thread = threading.Thread(
            target=self.run, args=(self.interval - self.__elapsed_time,)
        )
        self.__thread.start()
        self.__start_time = time.time()


@dataclass
class KeystrokeEvent:
    key: int
    func: callable
    active: bool = False
    persistent: bool = True


class KeystrokeManager(object):
    def __init__(self):
        super().__init__()
        self.__events = {}

    def addEvent(self, ident, key, func, active=False, persistent=True):
        self.__events[ident] = KeystrokeEvent(key, func, active, persistent)

    def call(self, key):
        for ident, event in self.__events.items():
            if event.active and event.key == key:
                event.func()
                if not event.persistent:
                    self.deactivate(ident)

    def activate(self, ident):
        self.__events[ident].active = True

    def deactivate(self, ident):
        self.__events[ident].active = False


class CompoundObject(object):
    def __init__(self, *objs):
        self.__objs = list(objs)

    def __setattr__(self, name, value):
        if name[0] == "_":
            self.__dict__[name] = value
        else:
            for obj in self.__objs:
                setattr(obj, name, value)

    def __getattr__(self, name):
        ret = CompoundObject(*[getattr(obj, name) for obj in self.__objs])
        return ret

    def __iadd__(self, display):
        self.__objs.append(display)
        return self

    def __call__(self, *args, **kwargs):
        return CompoundObject(*[obj(*args, **kwargs) for obj in self.__objs])

    def __repr__(self):
        return "CompoundObject(" + ", ".join([repr(o) for o in self.__objs]) + ")"


class Question(object):
    def __init__(self, index, text, answer, value, dd=False):
        self.index = index
        self.text = text
        self.answer = answer
        self.value = value
        self.dd = dd


class Board(object):
    def __init__(self, categories, questions, final=False, dj=False):
        print(len(questions), "questions in round")
        self.complete = len(questions) == 30 if not final else len(questions) == 1
        if final:
            self.size = (1, 1)
        else:
            self.size = (6, 5)
        self.final = final
        self.categories = categories
        self.dj = dj
        if not questions is None:
            self.questions = questions
        else:
            self.questions = []

    def get_question(self, i, j):
        for q in self.questions:
            if q.index == (i, j):
                return q
        return None


def updateUI(f):
    def wrapper(self, *args):
        ret = f(self, *args)
        self.update()
        return ret
    return wrapper


class Game(object):
    def __init__(self, rounds, date, comments):
        self.new_game(rounds, date, comments)

    def new_game(self, rounds, date, comments):
        self.date = date
        self.comments = comments
        self.rounds = rounds
        self.players = []
        self.dc = CompoundObject()
        self.paused = False
        self.active_question = None
        self.accepting_responses = False
        self.answering_player = None
        self.completed_questions = []
        self.previous_answerer = None
        self.timer = None
        if DEBUG:
            self.__current_round = 1
        else:
            self.__current_round = 0

        self.song = QSound(':data/song.wav')
        self.__judgement_round = -1
        self.__judgement_subround = 2
        self.__sorted_players = None

        self.buzzer_controller = None

        self.keystroke_manager = KeystrokeManager()
        self.keystroke_manager.addEvent(
            "CORRECT_RESPONSE", Qt.Key_Left, self.correct_answer
        )
        self.keystroke_manager.addEvent(
            "INCORRECT_RESPONSE", Qt.Key_Right, self.incorrect_answer
        )
        self.keystroke_manager.addEvent(
            "BACK_TO_BOARD", Qt.Key_Space, self.back_to_board, persistent=False
        )
        self.keystroke_manager.addEvent(
            "OPEN_RESPONSES", Qt.Key_Space, self.open_responses, persistent=False
        )
        self.keystroke_manager.addEvent(
            "NEXT_ROUND", Qt.Key_Space, self.next_round, persistent=False
        )
        self.keystroke_manager.addEvent(
            "NEXT_SLIDE", Qt.Key_Space, self.final_next_slide, persistent=True
        )

        # if DEBUG:
            # self.completed_questions = self.rounds[1].questions[:-1]

    def update(self):
        self.dc.update()

    def complete(self):
        return all(b.complete for b in self.rounds)

    @property
    def current_round(self):
        return self.rounds[self.__current_round]

    def __accept_responses(self):
        print("accepting responses")
        self.accepting_responses = True
        global activation_time
        activation_time = time.time()


    @updateUI
    def open_responses(self):
        print("open responses")
        self.dc.borderwidget.spacehints = False
        self.dc.borderwidget.lit = True
        if self.current_round.final:
            self.buzzer_controller.prompt_answers()
            self.song.play()
            self.timer = QuestionTimer(31, self.stumped)
        else:
            # accept_timer = threading.Timer(BUZZ_DELAY/1000, self.__accept_responses)
            # accept_timer.start()
            self.__accept_responses()

            if not self.timer:
                self.timer = QuestionTimer(4, self.stumped)
        self.timer.start()

    @updateUI
    def close_responses(self):
        print("close responses")
        self.timer.pause()
        self.accepting_responses = False
        self.dc.borderwidget.lit = True

    # Don't update UI every buzz
    def buzz(self, player):
        if self.accepting_responses and player is not self.previous_answerer:
            print(f"✅ {player.name}: buzz ({time.time() - activation_time:.6f} s)")
            self.accepting_responses = False
            self.timer.pause()
            self.previous_answerer = player
            self.dc.scoreboard.run_lights()

            self.answering_player = player
            self.keystroke_manager.activate("CORRECT_RESPONSE")
            self.keystroke_manager.activate("INCORRECT_RESPONSE")
            self.dc.borderwidget.arrowhints = True
            self.dc.borderwidget.lit = False
            self.update()
        else:
            print(f"❌ {player.name}: buzz")

    def answer_given(self):
        print("answer given")
        if not self.current_round.final:
            self.dc.scoreboard.stop_lights()
            self.deactivate_responses()
            self.answering_player = None
        else:
            self.final_next_slide()
            self.keystroke_manager.activate("NEXT_SLIDE")
            self.dc.borderwidget.spacehints = True


        self.dc.borderwidget.arrowhints = False


    def deactivate_responses(self):
        print("deactivate responses")
        self.keystroke_manager.deactivate("CORRECT_RESPONSE")
        self.keystroke_manager.deactivate("INCORRECT_RESPONSE")
        # else:
            # self.buzzer_controller.toolate()

    @updateUI
    def back_to_board(self):
        print("back_to_board")
        self.dc.borderwidget.spacehints = False
        self.timer = None
        self.completed_questions.append(self.active_question)
        self.active_question = None
        self.previous_answerer = None
        rasync(self.save)
        if len(self.completed_questions) == len(self.current_round.questions):
            self.keystroke_manager.activate("NEXT_ROUND")
            self.dc.borderwidget.spacehints = True

    @updateUI
    def next_round(self):
        print("next round")
        self.dc.borderwidget.spacehints = False
        self.completed_questions = []
        self.__current_round += 1
        # self.completed_questions = self.rounds[self.__current_round].questions[:-1]  # EDIT
        if self.__current_round == 2:
            self.start_final()

    def start_final(self):
        self.buzzer_controller.open_wagers()

    def wager(self,player,amount):
        player.wager = amount
        print(f"{player.name} wagered {amount}")

    def answer(self,player,guess):
        player.finalanswer = guess
        print(f"{player.name} guessed {guess}")


    @updateUI
    def final_next_slide(self):
        print("NEXT SLIDE")
        if self.__judgement_round == -1:
            self.dc.finalanswerwindow.setVisible(True)
            self.__sorted_players = sorted(self.players, key = lambda x : x.score)

        if self.__judgement_subround == 2:
            if self.__judgement_round == len(self.players)-1:
                self.end_game()
            else:
                self.__judgement_subround = 0
                self.__judgement_round += 1
                self.answering_player = self.__sorted_players[self.__judgement_round]
        else:
            self.__judgement_subround += 1


        self.dc.finalanswerwindow.info_level = self.__judgement_subround

        if self.__judgement_subround == 1:
            self.keystroke_manager.deactivate("NEXT_SLIDE")
            self.keystroke_manager.activate("CORRECT_RESPONSE")
            self.keystroke_manager.activate("INCORRECT_RESPONSE")
            self.dc.borderwidget.arrowhints = True
            self.dc.borderwidget.spacehints = False

    @updateUI
    def end_game(self):
        self.dc.finalanswerwindow.setVisible(False)
        self.answering_player = max(self.players, key = lambda x:x.score)


    @updateUI
    def open_final(self):
        self.dc.borderwidget.spacehints = True
        self.active_question = self.current_round.questions[0]
        self.keystroke_manager.activate("OPEN_RESPONSES")

    def save(self):
        # pickle.dump(self, open(".bkup",'wb'))
        pass

    @updateUI
    def correct_answer(self):
        print("correct")
        if not self.current_round.final:
            self.timer.cancel()
            self.answering_player.score += self.active_question.value
            self.back_to_board()
            self.dc.borderwidget.lit = False
        else:
            self.answering_player.score += self.answering_player.wager
        self.answer_given()

    @updateUI
    def incorrect_answer(self):
        print("incorrect")
        if not self.current_round.final:
            self.answering_player.score -= self.active_question.value
            self.open_responses()
            self.timer.resume()
        else:
            self.answering_player.score -= self.answering_player.wager
        self.answer_given()

    @updateUI
    def stumped(self):
        print("stumped")
        self.deactivate_responses()
        self.accepting_responses = False

        #flash
        self.dc.borderwidget.lit = False
        time.sleep(0.2)
        self.dc.borderwidget.lit = True
        time.sleep(0.2)
        self.dc.borderwidget.lit = False
        self.dc.borderwidget.spacehints = True
        if self.current_round.final:
            self.keystroke_manager.activate("NEXT_SLIDE")
        else:
            self.keystroke_manager.activate("BACK_TO_BOARD")

    def __getstate__(self):
        return (
            (self.rounds, self.date, self.comments),
            self.players,
            self.completed_questions,
        )

    def __setstate__(self, state):
        self.new_game(*state[0])
        self.players = state[1]
        print(1, state[1])
        # self.completed_questions = state[2]

    ### Final Jeopardy ###


class Player(object):
    def __init__(self, name, waiter):
        self.name = name
        self.token = os.urandom(15)
        self.score = 0
        self.waiter = waiter
        self.wager = None
        self.finalanswer = ""

    def __hash__(self):
        return int.from_bytes(self.token, sys.byteorder)


game_params = SimpleNamespace()
game_params.money1 = [200, 400, 600, 800, 1000]
game_params.money2 = [400, 800, 1200, 1600, 2000]
