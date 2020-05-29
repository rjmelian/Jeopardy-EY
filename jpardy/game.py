from types import SimpleNamespace
from PyQt5.QtCore import Qt
import threading
import time
from dataclasses import dataclass
import pickle

def rasync(f,*args,**kwargs):
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
        '''wrapper for resume'''
        self.resume()

    def cancel(self):
        '''wrapper for pause'''
        self.pause()

    def pause(self):
        self.__thread = None
        self.__elapsed_time += (time.time() - self.__start_time)

    def resume(self):
        self.__thread = threading.Thread(target=self.run, args=(self.interval - self.__elapsed_time,))
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
    def addEvent(self,ident,key,func,active=False, persistent=True):
        self.__events[ident] = KeystrokeEvent(key, func, active, persistent)

    def call(self, key):
        for ident, event in self.__events.items():
            if event.active and event.key==key:
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
        if name[0] == '_':
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
        return "CompoundObject("+", ".join([ repr(o) for o in self.__objs])+")"


class Question(object):
    def __init__(self,index,text,answer,value):
        self.index = index
        self.text = text
        self.answer = answer
        self.value = value

class Board(object):
    def __init__(self,categories, questions, final=False, dj=False):
        if final:
            self.size = (1,1)
        else:
            self.size = (6,5)
        self.final = final
        self.categories = categories
        self.dj = dj
        if not questions is None:
            self.questions = questions
        else:
            self.questions = []
    def get_question(self,i,j):
        for q in self.questions:
            if q.index == (i,j):
                return q
        return None
def updateUI(f):
    def wrapper(self, *args):
        ret = f(self, *args)
        self.update()
        return ret
    return wrapper

class Game(object):
    def __init__(self,rounds):
        self.new_game(rounds)

    def new_game(self, rounds):
        self.rounds = rounds
        self.scores = {}
        self.dc = CompoundObject()
        self.paused = False
        self.active_question = None
        self.accepting_responses = False
        self.answering_player = None
        self.completed_questions = []
        self.previous_answerer = None
        self.timer = None

        self.buzzer_controller = None

        self.keystroke_manager = KeystrokeManager()
        self.keystroke_manager.addEvent('CORRECT_RESPONSE', Qt.Key_Left, self.correct_answer)
        self.keystroke_manager.addEvent('INCORRECT_RESPONSE', Qt.Key_Right, self.incorrect_answer)
        self.keystroke_manager.addEvent('BACK_TO_BOARD', Qt.Key_Space, self.back_to_board, persistent=False)
        self.keystroke_manager.addEvent('OPEN_RESPONSES', Qt.Key_Space, self.open_responses, persistent=False)

    def update(self):
        self.dc.update()

    @updateUI
    def open_responses(self):
        print("open responses")
        self.accepting_responses = True
        self.dc.borderwidget.lit = True
        if not self.timer:
            self.timer = QuestionTimer(4, self.stumped)
        self.timer.start()

    @updateUI
    def close_responses(self):
        print("close responses")
        self.timer.pause()
        self.accepting_responses = False
        self.dc.borderwidget.lit = True



    @updateUI
    def buzz(self, player):
        print("buzz")
        if self.accepting_responses and player is not self.previous_answerer:
            print("buzz accepted")
            self.timer.pause()
            self.previous_answerer = player
            self.dc.scoreboard.run_lights()

            self.answering_player = player
            self.buzzer_controller.activate_buzzer(player)
            self.keystroke_manager.activate('CORRECT_RESPONSE')
            self.keystroke_manager.activate('INCORRECT_RESPONSE')

    def answer_given(self):
        print("answer given")
        self.dc.scoreboard.stop_lights()
        self.deactivate_responses()
        self.answering_player = None

    def deactivate_responses(self):
        print("deactivate responses")
        self.keystroke_manager.deactivate('CORRECT_RESPONSE')
        self.keystroke_manager.deactivate('INCORRECT_RESPONSE')

    @updateUI
    def back_to_board(self):
        print("back_to_board")
        self.timer = None
        self.completed_questions.append(self.active_question)
        self.active_question = None
        self.previous_answerer = None
        rasync(self.save)

    def save(self):
        pickle.dump(self, open(".bkup",'wb'))

    @updateUI
    def correct_answer(self):
        print("correct")
        self.timer.cancel()
        self.scores[self.answering_player] += self.active_question.value
        self.answer_given()
        self.back_to_board()
        self.dc.borderwidget.lit = False

    @updateUI
    def incorrect_answer(self):
        print("incorrect")
        self.scores[self.answering_player] -= self.active_question.value
        self.answer_given()
        self.open_responses()
        self.timer.resume()

    @updateUI
    def stumped(self):
        print("stumped")
        self.deactivate_responses()
        self.accepting_responses = False
        self.flash()

    def flash(self):
        self.dc.borderwidget.lit = False
        time.sleep(0.2)
        self.dc.borderwidget.lit = True
        time.sleep(0.2)
        self.dc.borderwidget.lit = False
        self.keystroke_manager.activate('BACK_TO_BOARD')

    def __getstate__(self):
        return (self.rounds, self.scores, self.completed_questions)

    def __setstate__(self, state):

        self.new_game(state[0])
        self.scores = state[1]
        print(1,state[1])
        self.completed_questions = state[2]


game_params = SimpleNamespace()
game_params.money1 = [200,400,600,800,1000]
game_params.money2 = [400,800,1200,1600,2000]