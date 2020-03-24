import pytest
import os
from .app import app, SignalApplication, SignalMessage
from flask import json


class Bunch(dict):
    __getattr__, __setattr__ = dict.get, dict.__setitem__


class MyExecutor:
    def __init__(self):
        self.commands = []
        self.PIPE = ''
        self.mocked_responses = []

    def returns(self, returns):
        self.mocked_responses = returns

    def Popen(self, command, shell=True, stdout='plop'):
        self.commands.append(command)

        def wait():
            pass

        def readlines():
            response = self.mocked_responses.pop(0)
            return iter(response)

        def readline():
            response = self.mocked_responses.pop(0)
            return response[0]

        return Bunch({'pid': 2, 'wait': wait, 'stdout': Bunch({'readlines': readlines, 'readline': readline})})


@pytest.fixture
def executor():
    return MyExecutor()


@pytest.fixture
def client(executor):
    os.environ["SIGNAL_CONFIG_PATH"] = 'path_to_signal'
    os.environ["PHONE_NUMBER"] = '+0102030405'
    application = app(injected_signal=SignalApplication(executor=executor))
    application.config['TESTING'] = True

    with application.test_client() as client:
        yield client


def test_retrieve_groups(client, executor):
    mocked_answers = [[b'010203040506\n'], [b'MyGroup\n']]
    executor.returns(mocked_answers)
    response = client.get('/group')
    data = json.loads(response.data)
    print(data)
    assert {'MyGroup': '010203040506'} == data
    assert executor.commands == [
        ['//signal-cli/bin/signal-cli', '--config', 'path_to_signal', '-u', '+0102030405', 'daemon', '--system'],
        'dbus-send --system --type=method_call --print-reply --dest="org.asamk.Signal" /org/asamk/Signal org.asamk.Signal.getGroupIds',
        'dbus-send --system --type=method_call --print-reply=literal --dest="org.asamk.Signal" /org/asamk/Signal org.asamk.Signal.getGroupName array:byte:0x010203040506']


def test_signal_message_empty():
    tested = SignalMessage()
    assert [] == tested.get_messages()
    tested.new_line_received('')
    assert [] == tested.get_messages()


def test_signal_message_simple_message():
    tested = SignalMessage()
    tested.new_line_received('Envelope from:  (device: 0)')
    tested.new_line_received('Timestamp: 1585036027540 (2020-03-24T07:47:07.540Z)')
    tested.new_line_received('Sent by unidentified/sealed sender')
    tested.new_line_received('Sender: +330102030405 (device: 2)')
    tested.new_line_received('Message timestamp: 1585036027540 (2020-03-24T07:47:07.540Z)')
    tested.new_line_received('Body: Plop')
    tested.new_line_received('Profile key update, key length:32')

    assert [{'sender': '+330102030405', 'message': 'Plop'}] == tested.get_messages()


def test_signal_message_discard_receipt():
    tested = SignalMessage()
    tested.new_line_received('Envelope from: +330102030405 (device: 2)')
    tested.new_line_received('Timestamp: 1585029602621 (2020-03-24T06:00:02.621Z)')
    tested.new_line_received('Got receipt.')

    assert [] == tested.get_messages()

    tested.new_line_received('Envelope from:  (device: 0)')
    tested.new_line_received('Timestamp: 1585035919367 (2020-03-24T07:45:19.367Z)')
    tested.new_line_received('Sent by unidentified/sealed sender')
    tested.new_line_received('Sender: +330102030405 (device: 2)')
    tested.new_line_received('Received a receipt message')
    tested.new_line_received('- When: 1585035919367 (2020-03-24T07:45:19.367Z)')
    tested.new_line_received('- Is read receipt')
    tested.new_line_received('- Timestamps:')
    tested.new_line_received('1585029602621 (2020-03-24T06:00:02.621Z)')

    assert [] == tested.get_messages()


def test_signal_message_utf8():
    tested = SignalMessage()

    assert [] == tested.get_messages()

    tested.new_line_received('Envelope from:  (device: 0)')
    tested.new_line_received('Timestamp: 1585035968139 (2020-03-24T07:46:08.139Z)')
    tested.new_line_received('Sent by unidentified/sealed sender')
    tested.new_line_received('Sender: +330102030405 (device: 2)')
    tested.new_line_received('Message timestamp: 1585035968139 (2020-03-24T07:46:08.139Z)')
    tested.new_line_received('Body: Comment ça va ?')
    tested.new_line_received('Group info:')
    tested.new_line_received('Id: base64Id==')
    tested.new_line_received('Name: Maison')
    tested.new_line_received('Type: DELIVER')

    assert [{'message': 'Comment ça va ?', 'sender': '+330102030405'}] == tested.get_messages()


def test_signal_message_multiline():
    tested = SignalMessage()

    assert [] == tested.get_messages()


    tested.new_line_received('Envelope from:  (device: 0)')
    tested.new_line_received('Timestamp: 1585035982672 (2020-03-24T07:46:22.672Z)')
    tested.new_line_received('Sent by unidentified/sealed sender')
    tested.new_line_received('Sender: +330102030405 (device: 2)')
    tested.new_line_received('Message timestamp: 1585035982672 (2020-03-24T07:46:22.672Z)')
    tested.new_line_received('Body: T\'es sûr que ça va bien ?')
    tested.new_line_received('Sur plusieurs lignes ça va aussi ?')
    tested.new_line_received('')
    tested.new_line_received('Vraiment ?')
    tested.new_line_received('Group info:')
    tested.new_line_received('Id: base64Id==')
    tested.new_line_received('Name: Maison')
    tested.new_line_received('Type: DELIVER')

    assert [{'message': 'T\'es sûr que ça va bien ?\nSur plusieurs lignes ça va aussi ?\n\nVraiment ?', 'sender': '+330102030405'}] == tested.get_messages()


# TODO 2020-03-24: If a message ends with nothing, how can we detect the end of body vs the end of the envelope message?