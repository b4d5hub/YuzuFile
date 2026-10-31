"""Desktop activation uses a real local socket and never accesses Store."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import subprocess
import sys
import time

import pytest
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from PySide6.QtWidgets import QApplication
from yuzufile.desktop_instance import DesktopInstance


@pytest.fixture
def broker(tmp_path):
    app=QApplication.instance() or QApplication([])
    value=DesktopInstance(tmp_path/'library')
    yield value,app
    value.shutdown()
    app.processEvents()


def pump_until(app,predicate,timeout_ms=2000):
    loop=QEventLoop()
    check=QTimer()
    check.setInterval(5)
    check.timeout.connect(lambda:loop.quit() if predicate() else None)
    limit=QTimer()
    limit.setSingleShot(True)
    limit.timeout.connect(loop.quit)
    check.start();limit.start(timeout_ms)
    if not predicate():loop.exec()
    check.stop();limit.stop()
    app.processEvents()
    assert predicate(),'Local activation did not finish before timeout'


def request_from_second_process(value):
    env=dict(os.environ)
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    return subprocess.Popen([sys.executable,'-c',
        'import sys; from pathlib import Path; from PySide6.QtCore import QCoreApplication; '
        'from yuzufile.desktop_instance import DesktopInstance; app=QCoreApplication([]); '
        'sys.exit(0 if DesktopInstance(Path(sys.argv[1])).request_show(1000) else 1)',
        str(value.home)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def test_no_running_gui_returns_promptly_without_creating_library(broker):
    value,app=broker
    started=time.monotonic()
    assert not value.request_show(80)
    assert time.monotonic()-started<1
    assert not value.home.exists()


def test_startup_retry_waits_for_listener_created_by_other_process(broker,tmp_path):
    value,app=broker
    env=dict(os.environ)
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    # Real delayed listener in a separate process: the requester must keep
    # trying while the first GUI is constructing widgets, before it can listen.
    ready=tmp_path/'listening'
    script='''import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QTimer
from yuzufile.desktop_instance import DesktopInstance
app=QCoreApplication([])
instance=DesktopInstance(Path(sys.argv[1]))
def listen():
    assert instance.listen(lambda:QTimer.singleShot(20,app.quit))
    Path(sys.argv[2]).touch()
QTimer.singleShot(150,listen)
QTimer.singleShot(4000,app.quit)
app.exec()
instance.shutdown()
'''
    process=subprocess.Popen([sys.executable,'-c',script,str(value.home),str(ready)],env=env,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        assert value.request_show(2500,retry=True)
        stdout,stderr=process.communicate(timeout=3)
        assert process.returncode==0,(stdout,stderr)
        assert ready.exists() and not value.home.exists()
    finally:
        if process.poll() is None:process.kill();process.wait()


def test_real_activation_restores_existing_gui_and_receives_ack(broker):
    value,app=broker
    restored=[]
    assert value.listen(lambda:restored.append('shown'))
    assert value.server.socketOptions() & QLocalServer.SocketOption.UserAccessOption
    process=request_from_second_process(value)
    try:
        pump_until(app,lambda:process.poll() is not None)
        stdout,stderr=process.communicate(timeout=1)
        assert process.returncode==0,(stdout,stderr)
        assert restored==['shown']
    finally:
        if process.poll() is None:process.kill();process.wait()
    assert not value.home.exists()


def test_competing_listener_cannot_replace_live_server(broker):
    value,app=broker
    restored=[]
    assert value.listen(lambda:restored.append(True))
    other=DesktopInstance(value.home)
    try:
        assert other.name==value.name
        assert not other.listen(lambda:restored.append(False))
        other.shutdown()
        process=request_from_second_process(value)
        try:
            pump_until(app,lambda:process.poll() is not None)
            stdout,stderr=process.communicate(timeout=1)
            assert process.returncode==0,(stdout,stderr)
            assert restored==[True]
        finally:
            if process.poll() is None:process.kill();process.wait()
    finally:other.shutdown()


def test_library_identity_and_shutdown_are_independent(broker,tmp_path):
    value,app=broker
    other=DesktopInstance(tmp_path/'another library')
    try:
        assert value.name!=other.name
        assert value.listen(lambda:None) and other.listen(lambda:None)
        value.shutdown();value.shutdown()
        assert not value.server.isListening() and other.server.isListening()
        assert not value.request_show(80)
        assert not value.listen(lambda:None)
    finally:other.shutdown()


@pytest.mark.parametrize('payload',[b'unknown\n',b'show\nextra',b'show\x00'])
def test_invalid_or_oversized_requests_never_restore_gui(broker,payload):
    value,app=broker
    restored=[]
    assert value.listen(lambda:restored.append(True))
    socket=QLocalSocket()
    try:
        socket.connectToServer(value.name)
        assert socket.waitForConnected(500)
        socket.write(payload);socket.flush()
        pump_until(app,lambda:socket.state()==QLocalSocket.LocalSocketState.UnconnectedState)
        assert not restored and not socket.bytesAvailable()
    finally:socket.abort()


def test_partial_request_is_bounded_and_shutdown_closes_client(broker):
    value,app=broker
    restored=[]
    assert value.listen(lambda:restored.append(True))
    socket=QLocalSocket()
    try:
        socket.connectToServer(value.name)
        assert socket.waitForConnected(500)
        socket.write(b'sh');socket.flush()
        pump_until(app,lambda:bool(value._clients))
        assert not restored
        value.shutdown()
        pump_until(app,lambda:socket.state()==QLocalSocket.LocalSocketState.UnconnectedState)
        assert not value._clients and not restored
    finally:socket.abort()
