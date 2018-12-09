import selectors2 as selectors
import socket
import time
import logging
import os
import sys
import struct
import threading
import hyperion.lib.util.config as config
import hyperion.lib.util.actionSerializer as actionSerializer
import hyperion.lib.util.exception as exceptions
from hyperion.manager import AbstractController
from hyperion.lib.util.events import ServerDisconnectEvent, DisconnectEvent, ReconnectEvent
from signal import *
from subprocess import Popen, PIPE

is_py2 = sys.version[0] == '2'
if is_py2:
    import Queue as queue
else:
    import queue as queue


def recvall(connection, n):
    """Helper function to recv n bytes or return None if EOF is hit
    
    To read a message with an expected size and combine it to one object, even if it was split into more than one 
    packets.
    
    :param connection: Connection to a socket
    :param n: Size of the message to read in bytes
    :type n: int
    :return: Expected message combined into one string
    """

    data = b''
    while len(data) < n:
        packet = connection.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data


class RemoteControllerInterface(AbstractController):
    def __init__(self, host, port):
        super(RemoteControllerInterface, self).__init__(None)
        self.host_list = None
        self.config = None
        self.host = host
        self.port = port
        self.logger = logging.getLogger(__name__)
        self.receive_queue = queue.Queue()
        self.send_queue = queue.Queue()
        self.mysel = selectors.DefaultSelector()
        self.keep_running = True
        self.ui_event_queue = None
        self.mounted_hosts = []

        signal(SIGINT, self._handle_sigint)

        self.function_mapping = {
            'get_conf_response': self._set_config,
            'get_host_list_response': self._set_host_list,
            'queue_event': self._forward_event
        }

        server_address = (host, port)
        self.logger.debug('connecting to {} port {}'.format(*server_address))
        self.sock = sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(server_address)
        except socket.error:
            self.logger.critical("Master session does not seem to be running. Quitting remote client")
            self.cleanup()
            sys.exit(1)
        sock.setblocking(False)

        # Set up the selector to watch for when the socket is ready
        # to send data as well as when there is data to read.
        self.mysel.register(
            sock,
            selectors.EVENT_READ | selectors.EVENT_WRITE,
        )

        self.thread = threading.Thread(target=self.loop)
        self.thread.start()

        self.request_config()
        while not self.config or not self.host_list:
            self.logger.debug("Waiting for config")
            time.sleep(0.5)

        for host in self.host_list:
            if not self.is_localhost(host):
                self._mount_host(host)

    def request_config(self):
        action = 'get_conf'
        payload = []
        message = actionSerializer.serialize_request(action, payload)
        self.send_queue.put(message)

        action = 'get_host_list'
        message = actionSerializer.serialize_request(action, payload)
        self.send_queue.put(message)

    def cleanup(self, full=False, exit_code=0):
        if full:
            action = 'quit'
            message = actionSerializer.serialize_request(action, [full])
            self.logger.debug("Sending quit to server")
        else:
            action = 'unsubscribe'
            message = actionSerializer.serialize_request(action, [])
            self.logger.debug("Sending unsubscribe to server")
        self.send_queue.put(message)

        for host in self.mounted_hosts:
            self.logger.debug("Unmounting host %s" % host)
            self._unmount_host(host)

        self.keep_running = False

    def get_component_by_id(self, comp_id):
        for group in self.config['groups']:
            for comp in group['components']:
                if comp['id'] == comp_id:
                    self.logger.debug("Component '%s' found" % comp_id)
                    return comp
        raise exceptions.ComponentNotFoundException(comp_id)

    def kill_session_by_name(self, session_name):
        self.logger.debug("Serializing kill session by name")
        action = 'kill_session'
        payload = [session_name]

        message = actionSerializer.serialize_request(action, payload)
        self.send_queue.put(message)

    def start_all(self):
        action = 'start_all'
        message = actionSerializer.serialize_request(action, [])
        self.send_queue.put(message)

    def start_component(self, comp):
        self.logger.debug("Serializing component start")
        action = 'start'
        payload = [comp['id']]

        message = actionSerializer.serialize_request(action, payload)
        self.send_queue.put(message)

    def stop_all(self):
        action = 'stop_all'
        message = actionSerializer.serialize_request(action, [])
        self.send_queue.put(message)

    def stop_component(self, comp):
        self.logger.debug("Serializing component stop")
        action = 'stop'
        payload = [comp['id']]

        message = actionSerializer.serialize_request(action, payload)
        self.send_queue.put(message)

    def check_component(self, comp):
        self.logger.debug("Serializing component check")
        action = 'check'
        payload = [comp['id']]

        message = actionSerializer.serialize_request(action, payload)
        self.send_queue.put(message)

    def _interpret_message(self, action, args):
        func = self.function_mapping.get(action)
        func(*args)

    def _set_config(self, config):
        self.config = config
        self.logger.debug("Got config from server")

    def _set_host_list(self, host_list):
        self.host_list = host_list
        self.logger.debug("Updated host list")

    def _forward_event(self, event):
        if self.ui_event_queue:
            self.ui_event_queue.put(event)

        # Special events handling
        if isinstance(event, DisconnectEvent):
            self.host_list[event.host_name] = None
            self._unmount_host(event.host_name)
        elif isinstance(event, ReconnectEvent):
            self.host_list[event.host_name] = True
            self._mount_host(event.host_name)

    def loop(self):
        # Keep alive until shutdown is requested and no messages are left to send
        while self.keep_running or not self.send_queue.empty():
            for key, mask in self.mysel.select(timeout=1):
                connection = key.fileobj

                if mask & selectors.EVENT_READ:
                    self.logger.debug("Got read event")
                    raw_msglen = connection.recv(4)
                    if raw_msglen:
                        # A readable client socket has data
                        msglen = struct.unpack('>I', raw_msglen)[0]
                        data = recvall(connection, msglen)
                        self.logger.debug("Received message")
                        action, args = actionSerializer.deserialize(data)
                        self._interpret_message(action, args)

                    # Interpret empty result as closed connection
                    else:
                        self.keep_running = False
                        # Reset queue for shutdown condition
                        self.send_queue = queue.Queue()
                        self.logger.critical("Connection to server was lost!")
                        self.ui_event_queue.put(ServerDisconnectEvent())

                if mask & selectors.EVENT_WRITE:
                    if not self.send_queue.empty():  # Server is ready to read, check if we have messages to send
                        self.logger.debug("Sending next message in queue to Server")
                        next_msg = self.send_queue.get()
                        self.sock.sendall(next_msg)

    def add_subscriber(self, subscriber_queue):
        """Set reference to ui event queue.

        :param subscriber_queue: Event queue of the used ui
        :type subscriber_queue: queue.Queue
        :return: None
        """
        self.ui_event_queue = subscriber_queue

    ###################
    # Host related
    ###################
    def _mount_host(self, hostname):
        """Mount remote host log directory via sshfs.

        :param hostname: Remote host name
        :type hostname: str
        :return: None
        """
        directory = "%s/%s" % (config.TMP_LOG_PATH, hostname)
        # First unmount to prevent unknown permissions issue on disconnected mountpoint
        self._unmount_host(hostname)

        if not self.host_list[hostname]:
            self.logger.error("'%s' seems not to be connected. Aborting mount! Logs will not be available" % hostname)
            return
        try:
            os.makedirs(directory)
        except OSError as err:
            if err.errno == 17:
                # Dir already exists
                pass
            else:
                self.logger.error("Error while trying to create directory '%s'" % directory)

        cmd = 'sshfs %s:%s %s -F %s' % (hostname,
                                        config.TMP_LOG_PATH,
                                        directory,
                                        config.SSH_CONFIG_PATH
                                        )
        self.logger.debug("running command: %s" % cmd)
        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)

        while p.poll() is None:
            time.sleep(.5)

        if p.returncode == 0:
            self.logger.debug("Successfully mounted remote '%s' with sshfs" % hostname)
            self.mounted_hosts.append(hostname)
        else:
            self.logger.error("Could not mount remote '%s' with sshfs - logs will not be accessible!" % hostname)
            self.logger.debug("sshfs exited with error: %s (code: %s)" % (p.stderr.readlines(), p.returncode))

        self.logger.debug("mounted hosts: %s" % self.mounted_hosts)

    def _unmount_host(self, hostname):
        """Unmount fuse mounted remote log directory.

        :param hostname: Remote host name.
        :type hostname: str
        :return: None
        """
        directory = "%s/%s" % (config.TMP_LOG_PATH, hostname)

        cmd = 'fusermount -u %s' % directory
        self.logger.debug("running command: %s" % cmd)
        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)

        if hostname in self.mounted_hosts:
            self.mounted_hosts.remove(hostname)

        while p.poll() is None:
            time.sleep(.5)

        self.logger.debug("mounted hosts: %s" % self.mounted_hosts)

    def reconnect_with_host(self, hostname):
        action = 'reconnect_with_host'
        payload = [hostname]

        message = actionSerializer.serialize_request(action, payload)
        self.send_queue.put(message)

    def is_localhost(self, hostname):
        """Check if 'hostname' resolves to localhost.

        :param hostname: Name of host to check
        :type hostname: str
        :return: Whether 'host' resolves to localhost or not
        :rtype: bool
        """

        if hostname == 'localhost':
            hostname = self.host

        try:
            hn_out = socket.gethostbyname('%s' % hostname)
            if hn_out == '127.0.0.1' or hn_out == '127.0.1.1' or hn_out == '::1':
                self.logger.debug("Host '%s' is localhost" % hostname)
                return True
            else:
                self.logger.debug("Host '%s' is not localhost" % hostname)
                return False
        except socket.gaierror:
            raise exceptions.HostUnknownException("Host '%s' is unknown! Update your /etc/hosts file!" % hostname)

    def run_on_localhost(self, comp):
        """Check if component 'comp' is run on localhost or not.

        :param comp: Component to check
        :type comp: dict
        :return: Whether component is run on localhost or not
        :rtype: bool
        """
        try:
            return self.is_localhost(comp['host'])
        except exceptions.HostUnknownException as ex:
            raise ex

    def _handle_sigint(self, signum, frame):
        self.cleanup(False)
