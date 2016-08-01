#!/usr/bin/env python

import os
from slackclient import SlackClient
import time
import logging
import requests

VERSION = 'v1.1'
KEY='AAAAB3NzaC'

SLACKBOT_API_TOKEN = os.environ.get('SLACKBOT_API_TOKEN')
SLACKTEST_TOKEN = os.environ.get('SLACKTEST_TOKEN')

logger = logging.getLogger('hr.chatbot.slackclient')

class HRSlackBot(SlackClient):

    def __init__(self, host, port):
        self.sc = SlackClient(SLACKBOT_API_TOKEN)
        self.sc.rtm_connect()
        self.botname = 'sophia'
        self.chatbot_ip = host
        self.chatbot_port = str(port)
        self.chatbot_url = 'http://{}:{}/{}'.format(
            self.chatbot_ip, self.chatbot_port, VERSION)
        self.lang = 'en'
        self.session = None
        self.icon_url='https://avatars.slack-edge.com/2016-05-30/46725216032_4983112db797f420c0b5_48.jpg'

    def set_sid(self, user):
        params = {
            "Auth": KEY,
            "botname": self.botname,
            "user": user
        }
        r = None
        retry = 3
        while r is None and retry > 0:
            try:
                r = requests.get('{}/start_session'.format(self.chatbot_url), params=params)
            except Exception:
                retry -= 1
                time.sleep(1)
        if r is None:
            logger.error("Can't get session\n")
            return
        ret = r.json().get('ret')
        if r.status_code != 200:
            logger.error("Request error: {}\n".format(r.status_code))
        self.session = r.json().get('sid')
        logger.info("Get session {}\n".format(self.session))

    def ask(self, question):
        params = {
            "question": "{}".format(question),
            "session": self.session,
            "lang": self.lang,
            "Auth": KEY
        }
        r = requests.get('{}/chat'.format(self.chatbot_url), params=params)
        ret = r.json().get('ret')
        if r.status_code != 200:
            logger.error("Request error: {}\n".format(r.status_code))

        if ret != 0:
            logger.error("QA error: error code {}, botname {}, question {}, lang {}\n".format(
                ret, self.botname, question, self.lang))

        response = {'text': '', 'emotion': '', 'botid': '', 'botname': ''}
        response.update(r.json().get('response'))

        return ret, response

    def _rate(self, rate):
        params = {
            "session": self.session,
            "rate": rate,
            "index": -1,
            "Auth": KEY
        }
        r = requests.get('{}/rate'.format(self.chatbot_url), params=params)
        ret = r.json().get('ret')
        response = r.json().get('response')
        return ret, response

    def send_message(self, channel, attachments):
        self.sc.api_call(
            "chat.postMessage", channel=channel,
            attachments=attachments, username=self.botname.title(),
            icon_url=self.icon_url)

    def run(self):
        while True:
            messages = self.sc.rtm_read()
            if not messages:
                continue
            for message in messages:
                if message['type']!=u'message':
                    continue
                if message.get('subtype')==u'bot_message':
                    continue
                usr_obj = self.sc.api_call(
                    'users.info', token=SLACKTEST_TOKEN, user=message['user'])
                if not usr_obj['ok']:
                    continue
                name = usr_obj['user']['profile']['first_name']
                question = message.get('text')
                channel = message.get('channel')

                logger.info("Question {}".format(question))
                if question in [':+1:', ':slightly_smiling_face:']:
                    ret, _ = self._rate('good')
                    if ret:
                        logger.info("Rate good")
                        answer = 'Thanks for rating'
                    else:
                        logger.info("Rate failed")
                        answer = 'Rating failed'
                    attachments = [{
                        'title': answer,
                        'color': 'good',
                        'fallback': answer
                    }]
                    self.send_message(channel, attachments)
                    continue
                if question in [':-1:', ':disappointed:']:
                    ret, _ = self._rate('bad')
                    if ret:
                        logger.info("Rate bad")
                        answer = 'Thanks for rating'
                    else:
                        logger.info("Rate failed")
                        answer = 'Rating failed'
                    attachments = [{
                        'title': answer,
                        'color': 'danger',
                        'fallback': answer
                    }]
                    self.send_message(channel, attachments)
                    continue

                ret, response = self.ask(question)
                if ret == 3:
                    self.set_sid(name)
                    ret, response = self.ask(question)
                answer = response.get('text')
                trace = response.get('trace', '')
                botid = response.get('botid', '')
                if ret != 0:
                    answer = u"Sorry, I can't answer it right now"
                    title = ''
                else:
                    title = 'answered by {}\ntrace:\n{}'.format(botid, str(trace))
                attachments = [{
                    'pretext': answer,
                    'title': title,
                    'color': '#3AA3E3',
                    'fallback': answer,
                }]
                self.send_message(channel, attachments)

if __name__ == '__main__':
    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)
    host = 'localhost'
    port = 8001
    while True:
        try:
            HRSlackBot(host, port).run()
        except Exception:
            pass
