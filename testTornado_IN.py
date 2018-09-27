import signal
from tornado import web, gen
from tornado.options import options
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.iostream import StreamClosedError

import json

from simple_transformer_inference import *

from threading import Condition, Thread
import time

import numpy as np
import spacy
spacy_en = spacy.load('en')

#var source = new EventSource('http://ef9d4ce4.ngrok.io/events');
htmltest = """
<div id="nop">Bonjour :</div>
<div id="messages">gets :</div>
<script type="text/javascript">
    var source = new EventSource('/events');
    source.onmessage = function(message) {
        var div = document.getElementById("messages");
        div.innerHTML = div.innerHTML + "<br>" + message.data;
    };
    source.onerror  = function(err) {
        var div = document.getElementById("messages");
        div.innerHTML = div.innerHTML + "<br>" + "ERROR :";
        div.innerHTML = div.innerHTML + "<br>" + "type :" + err.type;
        div.innerHTML = div.innerHTML + "<br>" + "target  :" + err.target;
    };
    source.onopen  = function() {
        var div = document.getElementById("messages");
        div.innerHTML = div.innerHTML + "OPEN!!";
    };
</script>


<!-- 
    sourceEvents.addEventListener("change", function (event) { 
        div.innerHTML = div.innerHTML + "BUT WHY????";
    }, false);

 -->"""

htmltestv1 = """
<div id="nop">Bonjour :</div>
<div id="test">???? :</div>
<div id="messages">gets :</div>
<script type="text/javascript">
    document.getElementById("test").innerHTML = "YOLO";
    var source = new EventSource('/events');
    source.onmessage = function(message) {
        var div = document.getElementById("messages");
        div.innerHTML = message.data + "<br>" + div.innerHTML;
    };
</script>"""

html = """
<div>Main page (cookies set)</div>
"""

html2 = """
<div id="nop">Test page :</div>
<div id="messages">it's ok?</div>
"""

loop_sync = Condition()
send_sync = Condition()
sentences_to_send = []
list_mails = []

false_mail = {  'Sender': '"email.com" <name@email.com>', 
                'Subject': 'Lorem ipsum dolor sit ametLorem ipsum dolor sit amet', 
                   'Date': 'yyyy-mm-dd', 
           'Message_body': 'Would you please come to the meeting tomorrow?'}#dummy data


def print_dict(d):
    for k in d.keys():
        print(f"{k} : {d[k]}")

class BaseHandler(web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie("user")
           
class EventSource(BaseHandler):
    """Basic handler for server-sent events."""
    def initialize(self, source):
        """The ``source`` parameter is a string that is updated with
        new data. The :class:`EventSouce` instance will continuously
        check if it is updated and publish to clients when it is.
        """
        self.to_send_list = source
        self.set_header('content-type', 'text/event-stream')
        self.set_header('cache-control', 'no-cache')

    @gen.coroutine
    def publish(self, data):
        """Pushes data to a listener."""
        try:
            self.write('data: {}\n\n'.format(data))
            yield self.flush()
        except StreamClosedError:
            pass

    @gen.coroutine
    def get(self):
        print("yay GET EVENT!!!")
        while True:
            print(f"actu = {len(self.to_send_list)}")
            if not len(self.to_send_list) == 0: #check before lock is uncertain but can help don't use the lock
                send_sync.acquire()
                to_send = None
                if not len(self.to_send_list) == 0:
                    to_send = self.to_send_list.pop(0)
                send_sync.release()
                if not to_send is None:
                    to_send = list(to_send)
                    print("SEND:")
                    print(to_send)
                    print(to_send[0])
                    print_dict(to_send[1])
                    print(to_send[2])
                    print(to_send[3])
                    yield self.publish(json.dumps(to_send))
                else:
                    print(f"wait weird")
                    yield gen.sleep(1.005)
            else:
                print(f"wait qq")
                yield gen.sleep(1.005)
            print(f"end")

class MainHandler(BaseHandler):
    def get(self):
        print("get main")
        self.set_secure_cookie("test", "test?")
        self.set_secure_cookie("user", "cookie get user!")
        self.write(html)
        
    def post(self):
        name = self.get_argument("name")
        key = self.get_argument("password")  #??
        mail = self.get_argument("mail")     #??
        
        print(f"name = {name} / key = {key} / mail = {mail}")
        #if (it's ok) :
        self.set_secure_cookie("test", "{name} {key} {mail}")
        self.set_secure_cookie("user", "STRING that is ok")
        self.redirect("/test")
        #else:
        #self.redirect("/") #not ok page? flash? http response??
        
        
class HtmlTestHandler(BaseHandler):
    def get(self):
        print("get html")
        self.write(htmltest)

class CookieTestHandler(BaseHandler):
    def get(self):
        d1 = self.get_secure_cookie("user")
        d2 = self.get_secure_cookie("test")
        print(f"cookie 1 : {d1}")
        print(f"cookie 2 : {d2}")
        self.write(html2)
        list_mails.append(false_mail.copy())
        print("add false mail")


#####

def handle_mails(mails):
    infer_sents = []
    
    for i in range(len(mails)):
        body = mails[i]["Message_body"].replace('\r\n', '  ').replace('\n', ' ')
        infer_sents.extend([(str(s),mails[i],s.start_char,s.end_char) for s in spacy_en(body).sents])
        
    return infer_sents # make infer_sents global or???

def get_strongs(model, infer_sents):
    array_sents = np.array(infer_sents)
    preds = model_multi_inferences(sentences = array_sents[:,0], **model)
    
    return [array_sents[i] for i in range(len(preds)) if preds[i] == 2]

class MailLoopThread(Thread):

    def __init__(self, mail_list, batch_size):
        Thread.__init__(self)
        self.mail_list = mail_list
        self.batch_size = batch_size
        self.setDaemon(True)

    def run(self):
        model = load_model()
        sents = []
        print("mail loop started")
        while True:
            loop_sync.acquire()
            mails = self.mail_list.copy()
            self.mail_list.clear()
            loop_sync.release()
            if len(mails) == 0:
                time.sleep(1) # or wait + notif
                continue
            sents = handle_mails(mails)
            if len(sents) < self.batch_size:
                time.sleep(0.5)
                loop_sync.acquire()
                mails2 = self.mail_list.copy()
                self.mail_list.clear()
                loop_sync.release()
                if len(mails2):
                    sents.extend(handle_mails(mails2))
                    
            while len(sents) > 0:
                sents_batch_size = sents[:self.batch_size]
                sents = sents[self.batch_size:]
                strongs_sents = get_strongs(model, sents_batch_size)
                
                send_sync.acquire()
                sentences_to_send.extend(strongs_sents)
                send_sync.release()
        print("mail loop ended")
        

def add_false_mail(mail_list):
    while True:
        mail_list.append(false_mail)
        time.sleep(10)


if __name__ == "__main__":
    options.parse_command_line()
    
    list_mails = [false_mail.copy() for i in range(15)]
    
    th = MailLoopThread(list_mails,10)
    
    # th2 = Thread(target=add_false_mail, args=[list_mails])
    # th2.setDaemon(True)
    # th2.start()
    
    routes = [
            (r'/', MainHandler),
            (r'/ct', CookieTestHandler),
            (r'/html', HtmlTestHandler),
            (r'/events', EventSource, dict(source=sentences_to_send)) #args=[list_mails,1]
        ]  
    app = web.Application(routes, cookie_secret="2dcc68f313e6df64cd1360e879a14f94c2c6b88d12d6596", debug=True) 
    ####!!!! generate better random_value ??
    
    server = HTTPServer(app)
    server.listen(8080)
    th.start()
    signal.signal(signal.SIGINT, lambda x, y: IOLoop.instance().stop())
    
print("serv start")
IOLoop.instance().start()
print("serv end")