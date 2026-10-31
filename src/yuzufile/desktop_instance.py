"""Wake an existing desktop instance without opening or recovering its library."""
from __future__ import annotations

import hashlib
import math
import os
import time
from pathlib import Path

from PySide6.QtCore import QObject,QTimer
from PySide6.QtNetwork import QLocalServer,QLocalSocket


_SHOW=b'show\n'
_ACK=b'ok\n'


class DesktopInstance(QObject):
    """Small, user-local activation channel; Store remains the instance lock.

    Call request_show before acquiring Store. Only the process holding Store's
    lock should call listen. A failed connection never removes another server.
    """

    def __init__(self,home:Path,parent:QObject|None=None):
        super().__init__(parent)
        self.home=Path(home).resolve()
        identity=os.path.normcase(str(self.home)).encode('utf-8')
        self.name='yuzufile-desktop-'+hashlib.sha256(identity).hexdigest()[:32]
        self.server=QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept_connections)
        self._callback=None
        self._clients={}
        self._closed=False

    def request_show(self,timeout_ms:int=600,retry:bool=False)->bool:
        """Ask the owner to restore itself; optionally cover its startup race."""
        if self._closed or timeout_ms<=0:return False
        deadline=time.monotonic()+timeout_ms/1000
        while True:
            remaining=max(0,math.ceil((deadline-time.monotonic())*1000))
            if not remaining:return False
            if self._request_once(remaining):return True
            if not retry:return False
            remaining=deadline-time.monotonic()
            if remaining<=0:return False
            # Used only before opening this launch's GUI; the existing GUI has
            # its own process/event loop and can finish constructing/listening.
            time.sleep(min(.05,remaining))

    def _request_once(self,timeout_ms:int)->bool:
        if timeout_ms<=0:return False
        deadline=time.monotonic()+timeout_ms/1000
        def remaining():return max(0,math.ceil((deadline-time.monotonic())*1000))
        socket=QLocalSocket()
        try:
            socket.connectToServer(self.name)
            if not socket.waitForConnected(remaining()):return False
            if socket.write(_SHOW)!=len(_SHOW):return False
            if socket.bytesToWrite() and not socket.waitForBytesWritten(remaining()):return False
            reply=b''
            while len(reply)<len(_ACK):
                if socket.bytesAvailable():
                    reply+=bytes(socket.read(len(_ACK)-len(reply)))
                    continue
                wait=remaining()
                if not wait:break
                if not socket.waitForReadyRead(wait) and not socket.bytesAvailable():break
            return reply==_ACK
        finally:
            socket.abort()

    def listen(self,callback)->bool:
        """Listen only after Store was acquired, without replacing a live pipe."""
        if self._closed:return False
        if self.server.isListening():return True
        # Windows permits multiple listeners with the same named-pipe name.
        # Refuse an existing endpoint rather than sharing its incoming clients.
        probe=QLocalSocket()
        try:
            probe.connectToServer(self.name)
            if probe.waitForConnected(50):return False
        finally:probe.abort()
        self._callback=callback
        return self.server.listen(self.name)

    def _accept_connections(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection()
            if socket is None:continue
            socket.setReadBufferSize(len(_SHOW)+1)
            timer=QTimer(socket)
            timer.setSingleShot(True)
            timer.setInterval(1000)
            self._clients[socket]={'buffer':b'','timer':timer,'handled':False}
            socket.readyRead.connect(lambda socket=socket:self._read_request(socket))
            socket.disconnected.connect(lambda socket=socket:self._forget(socket))
            timer.timeout.connect(lambda socket=socket:self._reject(socket))
            timer.start()
            self._read_request(socket)

    def _read_request(self,socket):
        client=self._clients.get(socket)
        if client is None or client['handled']:return
        client['buffer']+=bytes(socket.read(len(_SHOW)+1))
        request=client['buffer']
        if len(request)>len(_SHOW) or not _SHOW.startswith(request):
            self._reject(socket)
        elif request==_SHOW:
            client['handled']=True
            client['timer'].stop()
            socket.write(_ACK)
            socket.disconnectFromServer()
            # Restore in the GUI loop after this socket callback has returned.
            QTimer.singleShot(0,self,self._deliver_show)

    def _deliver_show(self):
        if not self._closed and self._callback is not None:self._callback()

    def _reject(self,socket):
        if socket not in self._clients:return
        socket.abort()
        self._forget(socket)

    def _forget(self,socket):
        client=self._clients.pop(socket,None)
        if client is not None:
            client['timer'].stop()
            socket.deleteLater()

    def shutdown(self):
        if self._closed:return
        self._closed=True
        self._callback=None
        self.server.close()
        for socket in list(self._clients):self._reject(socket)
