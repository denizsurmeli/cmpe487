import datetime
import select
import socket
import logging
import enum
import json
import re
import threading
import errno
import time
import os 
import math

PORT = 12345

HELLO_MESSAGE = {
    "type": "hello",
    "myname": None
}

AS_MESSAGE = {
    "type": "aleykumselam",
    "myname": None
}

MESSAGE = {
    "type": "message",
    "content": None
}

SYN_MESSAGE = {
    "type": "syn",
    "name": None,
    "size": None
}

ACK_MESSAGE = {
    "type": "5",
    "seq": None,
    "rwnd": None,
}

IP_PATTERN = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
BROADCAST_PERIOD = 60
PRUNING_PERIOD = 120
BATCH_SIZE = 1500 # bytes
RWND = 10

# TODO :Find a way of closing the self-listener thread.


class MessageType(enum.Enum):
    hello = 1
    aleykumselam = 2
    message = 3
    file = 4
    ack = 5
    syn = 6



class Netchat:
    def __init__(self, name: str = None):
        logging.info("Finding out whoami.")
        self.terminate = False
        hostname: str = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(hostname)[-1]
        if len(ip_addresses) > 1:
            # TODO: search/ask about this issue 
            ipaddress: str = socket.gethostbyname_ex(hostname)[-1][1]
        else:
            ipaddress: str = socket.gethostbyname_ex(hostname)[-1][0]
        logging.info(f"Resolved whoami. IP:{ipaddress} \t Hostname:{hostname}")
        self.whoami: dict = dict()
        self.whoami["myname"] = name if name is not None else hostname
        self.whoami["ip"] = ipaddress

        self.peers: dict = {}
        self.listener_threads: dict = {}
        self.prune_list: list[str] = []
        self.messages: dict = {}

        self.listener_threads["BROADCAST"] = threading.Thread(
            target=self.listen_broadcast, daemon=True).start()
        self.listener_threads[self.whoami["ip"]] = threading.Thread(
            target=lambda: self.listen_peer(self.whoami["ip"]), daemon=True
        ).start()
        self.last_timestamp = time.time() - BROADCAST_PERIOD
        self.broadcast_thread = threading.Thread(
            target=self.broadcast, daemon=True).start()

        print(f"Discovery completed, ready to chat.")
        self.user_input_thread = threading.Thread(target=self.listen_user)
        self.user_input_thread.start()
        self.user_input_thread.join()

    def show_peers(self):
        print("IP:\t\tName:")
        for peer in self.peers:
            print(f"{peer}\t{self.peers[peer][1]}")

    def get_ip_by_name(self, name: str):
        for peer in self.peers.keys():
            if self.peers[peer][1] == name:
                return peer
        return None

    def shutdown(self):
        logging.info("Terminating...")
        self.terminate = True
        for ip in self.listener_threads.keys():
            if ip not in [self.whoami["ip"], "BROADCAST"]:
                self.listener_threads[ip].join()
                logging.info(f"{ip} listener closed.")

    def listen_user(self):
        while True and not self.terminate:
            line = input()
            if line == ":whoami":
                print(f'IP:{self.whoami["ip"]}\tName:{self.whoami["myname"]}')

            if line == ":quit":
                self.shutdown()

            if line == ":peers":
                self.show_peers()

            if line.startswith(":hello"):
                try:
                    name = line.split()[1]
                    ip = name.strip()
                    match = re.match(IP_PATTERN, ip)
                    if match and self.whoami["ip"] != ip:
                        hello_message = HELLO_MESSAGE.copy()
                        hello_message["myname"] = self.whoami["myname"]
                        self.send_message(ip, MessageType.hello)
                    else:
                        logging.warn("Incorrect IP string.")
                except BaseException:
                    print("Invalid command. Usage: :hello ip")

            if line.startswith(":send_file"):
                try:
                    name, filepath = line.split(
                        " ", 2)[1], line.split(
                        " ", 2)[2]
                    name = name.strip()

                    logging.info(f"Collecting metadata and sending SYN to {ip}")
                    filepath = filepath.strip()
                    with open(filepath, "rb") as f:
                        size = os.stat(filepath).st_size
                    content = f"{filepath},{size}"
                    ip = self.get_ip_by_name(name)

                    self.send_message(ip, MessageType.syn, content=content)

                    self.send_file(ip, filepath, MessageType.file)
                except BaseException as e:
                    logging.error(e)

            if line.startswith(":send"):
                try:
                    # strip command from the second empty spaace and keep the
                    # rest as content
                    name, content = line.split(
                        " ", 2)[1], line.split(
                        " ", 2)[2]
                    name = name.strip()
                    content = content.strip()
                    ip = self.get_ip_by_name(name)
                    if ip is None:
                        print(f"Peer with name \"{name}\" not found.")
                    else:
                        self.send_message(
                            ip, MessageType.message, content=content)
                except BaseException as e:
                    print("Invalid command. Usage: :send name message")
            

    def broadcast(self, port: int = PORT) -> dict:
        # nmap this nmap that
        # broadcast_address = ".".join(self.whoami['ip'].split('.')[:-1]) + ".255"
        while True:
            if time.time() - self.last_timestamp > BROADCAST_PERIOD:
                logging.info("Broadcasting...")
                self.last_timestamp = time.time()
                hello_message = HELLO_MESSAGE.copy()
                hello_message['myname'] = self.whoami["myname"]
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.bind(('', 0))
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    s.sendto(json.dumps(hello_message).encode(
                        'utf-8'), ('<broadcast>', port))
                logging.info("Done.")
    
    def send_file(self, ip: str, filepath: str, type: MessageType, port:int = PORT, batch_size: int = BATCH_SIZE):
        try:
            logging.info(f"Sending a file to {ip} on {port}")
            with open(filepath, "rb") as f:
                length:int = os.stat(filepath).st_size
                batch_count:int  = math.ceil(length / batch_size) + 1
                logging.info(f"to_be_sent: {batch_count}, batch_size:{batch_size} ")
                counter: int = 1
                while (batch := f.read(batch_size)):
                    logging.info(f"[FILE] packet_number: {counter} packet_size: {len(batch)} to_be_sent: {batch_count - counter - 1} on_flight : {0}")

                    counter += 1
        except BaseException as e:
            print(e)

    def send_message(self, ip: str, type: MessageType,
                     content: str = None, 
                     port: int = PORT, 
                     protocol = socket.SOCK_STREAM):
        try:
            logging.info("Creating a socket")
            with socket.socket(socket.AF_INET, protocol) as s:
                logging.info(f"Connecting to the {ip} on {port} using {protocol}")
                s.connect((ip, port))
                logging.info("Preparing the message.")
                if type == MessageType.hello:
                    logging.info(f"Sending [hello] message to {ip}")
                    message = HELLO_MESSAGE.copy()
                    message["myname"] = self.whoami["myname"]
                if type == MessageType.aleykumselam:
                    logging.info(f"Sending [aleykumselam] message to {ip}")
                    message = AS_MESSAGE.copy()
                    message["myname"] = self.whoami["myname"]
                if type == MessageType.message:
                    logging.info(f"Sending [message] message to {ip}")
                    message = MESSAGE.copy()
                    message["content"] = content
                if type == MessageType.syn:
                    logging.info(f"Sending [syn] message to {ip}")
                    parameters = content.split(",")
                    message = SYN_MESSAGE.copy()
                    message["name"] = parameters[0]
                    message["size"] = int(parameters[1])
                if type == MessageType.ack:
                    logging.info(f"Sending [ack] message to {ip}")
                    message = ACK_MESSAGE.copy()
                    parameters = content.split(",")
                    message["seq"] = int(parameters[0])
                    message["rwnd"] = int(parameters[1])


                encode = json.dumps(message).encode('utf-8')
                s.sendall(encode)
                logging.info("Sent the message")
                s.close()
                logging.info(f"Closed the connection on {ip}")

        except Exception as e:
            logging.error(f"Error while sending the message. Reason: {e}")

    def process_message(self, data: str, ip: str):
        data = json.loads(data)
        try:
            if data["type"] == HELLO_MESSAGE["type"] and ip != self.whoami["ip"]:
                logging.info(f"{ip} reached to say 'hello'")
                self.peers[ip] = (time.time(), data["myname"])

                # TODO: refactor this mess 
                self.listener_threads[ip] = [threading.Thread(
                    target=lambda: self.listen_peer(ip))]
                self.listener_threads[ip].start()
                self.listener_threads[ip].append(threading.Thread(
                    target=lambda: self.listen_peer(ip, protocol=socket.SOCK_DGRAM)
                ))
                self.listener_threads[ip][1].start()

                logging.info(f"Sending 'aleykumselam' to {ip}")
                self.send_message(ip, MessageType.aleykumselam)

            if data["type"] == AS_MESSAGE["type"]:
                logging.info(f"{ip} said 'aleykumselam'")
                self.peers[ip] = (time.time(), data["myname"])

            if data["type"] == MESSAGE["type"]:
                logging.info(
                    f"Processing message from {self.peers[ip]}({ip})")
                _content = data['content']
                _from = 'UNKNOWN_HOST' if ip not in self.peers.keys(
                ) else self.peers[ip][1]
                print(
                    f"[{datetime.datetime.now()}] FROM: {_from}({ip}): {_content}")
            # if data["type"] == SYN["type"]:

            # if data["type"] == ACK["type"]:

        except KeyError as e:
            logging.error(
                f"Incoming message with unexpected structure. Message: {data}")
        except Exception as e:
            logging.error(f"Unexpected error. Check the exception: {e}")

    def listen_peer(self, ip: str, port: int = PORT, protocol = socket.SOCK_STREAM):
        ### TODO: REFACTOR THIS
        if protocol == socket.SOCK_STREAM:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((ip, port))
                    s.listen()
                    while True and not self.terminate:
                        conn, addr = s.accept()
                        addr = addr[0]
                        with conn:
                            while True:
                                data = conn.recv(1024)
                                if not data:
                                    break
                                data = data.decode('utf-8')
                                self.process_message(data, addr)
                    if self.terminate:
                        logging.info(f"Closed the connection on {ip}")
                        s.close()
                except socket.error as e:
                    if e.errno == errno.EADDRNOTAVAIL:
                        logging.info(f"Host not available")
                    if e.errno == errno.ECONNREFUSED or 'Connection refused' in str(
                            e):
                        logging.info(f"Host refused to connect")
        if protocol == socket.SOCK_DGRAM:
            buffer_size = 1024
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.bind((ip, port))
                s.setblocking(0)
                while True and not self.terminate:
                    result = select.select([s], [], [])
                    msg, sender = result[0][0].recvfrom(buffer_size)
                    sender = sender[0]
                    self.process_message(msg, sender)
                if self.terminate:
                    logging.info(f"Closed the connection on {ip}")
                    s.close()

    def listen_broadcast(self, port=PORT):
        while True and not self.terminate:
            buffer_size = 1024
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.bind(('', port))
                s.setblocking(0)
                result = select.select([s], [], [])
                msg, sender = result[0][0].recvfrom(buffer_size)
                sender = sender[0]
                self.process_message(msg, sender)

                for peer in list(self.peers.keys()):
                    if time.time() - self.peers[peer][0] > PRUNING_PERIOD:
                        logging.info(
                            f"Pruning peer due to inactivity: {self.peers[peer][1]}({peer})")
                        self.peers.pop(peer)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    netchat = Netchat("Deniz")
