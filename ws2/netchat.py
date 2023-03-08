import datetime
import socket
import logging
import enum
import json
import subprocess
import re
import concurrent.futures
import threading
import errno

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

IP_PATTERN = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

# TODO :Find a way of closing the self-listener thread. 

class MessageType(enum.Enum):
    hello = 1
    aleykumselam = 2
    message = 3


class Netchat:
    def __init__(self, name: str = None):
        logging.info("Finding out whoami.")
        self.terminate = False
        hostname: str = socket.gethostname()
        ipaddress: str = socket.gethostbyname_ex(hostname)[-1][-1]
        logging.info(f"Resolved whoami. IP:{ipaddress} \t Hostname:{hostname}")

        self.whoami: dict = dict()
        self.whoami["myname"] = name if name is not None else hostname
        self.whoami["ip"] = ipaddress

        self.peers: dict = {}
        self.listener_threads: dict = {}
        self.prune_list:list[str] = []
        possible_peers = self.discover_peers()

        for ip in possible_peers:
            self.listener_threads[ip] = threading.Thread(
                target=lambda: self.listen_peer(ip))
            logging.info(f"Starting the listener on {ip}")
            self.listener_threads[ip].start()

        self.join_network(possible_peers)

        self.user_input_thread = threading.Thread(target=self.listen_user)
        self.user_input_thread.start()
        self.user_input_thread.join()

    def show_peers(self):
        print("IP:\t\tName:")
        for peer in self.peers:
            print(f"{peer}\t{self.peers[peer]}")

    def get_ip_by_name(self, name: str):
        for peer in self.peers.keys():
            if self.peers[peer] == name:
                return peer
        return None

    def shutdown(self):
        logging.info("Terminating...")
        self.terminate = True
        print(self.listener_threads)
        for ip in self.listener_threads.keys():
            self.listener_threads[ip].join()
            logging.info(f"{ip} listener closed.")

        self.listener_threads[self.whoami["ip"]].join()

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

    def discover_peers(self, port: int = PORT) -> dict:
        # nmap this nmap that
        scanning_block = ".".join(self.whoami['ip'].split('.')[:-1]) + ".0/24"
        logging.info(
            f"Discovering peers using nmap, scanning block {scanning_block} on port {PORT}")
        syscall = f"nmap -p {port} " + \
            ".".join(self.whoami['ip'].split('.')[:-1]) + ".0/24"
        syscall = syscall.split(" ")
        process = subprocess.run(syscall, stdout=subprocess.PIPE)
        possible_peers = re.findall(IP_PATTERN, str(process.stdout))

        return [str(peer) for peer in possible_peers]

    def join_network(self, possible_peers: list[str]):
        if len(possible_peers) == 0:
            # TODO: add rescan
            logging.warn(
                "No peers on the network. Will rescan after 5 seconds.")
        else:
            logging.info(
                f"Sending 'hello' to {len(possible_peers)} possible peers")
            with concurrent.futures.ThreadPoolExecutor(len(possible_peers)) as executor_pool:
                for candidate in possible_peers:
                    if candidate != self.whoami["ip"]:
                        executor_pool.submit(
                            self.send_message, candidate, MessageType.hello)
                executor_pool.shutdown(wait=True)

    def send_message(self, ip: str, type: MessageType,
                     content: str = None, port: int = PORT):
        try:
            logging.info("Creating a socket")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                logging.info(f"Connecting to the {ip} on {port}")
                s.connect((ip, port))

                logging.info("Preparing the message.")
                if type == MessageType.hello:
                    message = HELLO_MESSAGE.copy()
                    message["myname"] = self.whoami["myname"]
                if type == MessageType.aleykumselam:
                    message = AS_MESSAGE.copy()
                    message["myname"] = self.whoami["myname"]
                if type == MessageType.message:
                    message = MESSAGE.copy()
                    message["content"] = content

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
            if data["type"] == HELLO_MESSAGE["type"]:
                logging.info(f"{ip} reached to say 'hello'")
                self.peers[ip] = data["myname"]
                logging.info(f"Sending 'aleykumselam' to {ip}")
                self.send_message(ip, MessageType.aleykumselam)
                self.listener_threads[ip] = threading.Thread(
                    target=lambda: self.listen_peer(ip))
                self.listener_threads[ip].start()

            if data["type"] == AS_MESSAGE["type"]:
                logging.info(f"{ip} said 'aleykumselam'")
                self.peers[ip] = data["myname"]

            if data["type"] == MESSAGE["type"]:
                logging.info(
                    f"Processing message from {self.peers[ip]}({ip})")
                _content = data['content']
                _from = 'UNKNOWN_HOST' if ip not in self.peers.keys(
                ) else self.peers[ip]
                print(
                    f"[{datetime.datetime.now()}] FROM: {_from}({ip}): {_content}")
        except KeyError as e:
            logging.error(
                f"Incoming message with unexpected structure. Message: {data}")
        except Exception as e:
            logging.error(f"Unexpected error. Check the exception: {e}")

    def listen_peer(self, ip: str, port: int = PORT):
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
                if e.errno == errno.ECONNREFUSED or 'Connection refused' in str(e):
                    logging.info(f"Host refused to connect")
                        # if addr in self.peers.keys():
                        #     self.peers.pop(addr)
                

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    netchat = Netchat()
