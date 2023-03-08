import datetime
import socket
import logging
import enum
import json
import subprocess
import re
import concurrent.futures
import threading

PORT = 12345

HELLO_MESSAGE = {
    "type":"hello",
    "myname":None
}

AS_MESSAGE = {
    "type": "aleykumselam",
    "myname":None
}

MESSAGE = {
    "type": "message",
    "content":None
}

IP_PATTERN = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'

class MessageType(enum.Enum):
    hello = 1
    aleykumselam = 2
    message = 3

class Netchat:
    def __init__(self, name: str = None):
        logging.info("Finding out whoami.")
        hostname: str = socket.gethostname()
        ipaddress: str = socket.gethostbyname_ex(hostname)[-1][-1] 
        logging.info(f"Resolved whoami. IP:{ipaddress} \t Hostname:{hostname}")

        self.whoami:dict = dict()
        self.whoami["myname"] = name if name is not None else hostname
        self.whoami["ip"] = ipaddress

        self.peers: dict = {}
        self.listener_threads: dict = {}

        self.discover_peers()
        for ip, _ in self.peers:
            self.listener_threads[ip] = threading.Thread(target=self.listen_peer, args=(ip))
        
        self.user_input_thread = threading.Thread(target=self.listen_user)
    
        self.user_input_thread.join()
        for ip, thread in self.listener_threads:
            thread.join()
        




    def get_ip_by_name(self, name: str):
        for peer in self.peers:
            if self.peers[peer] == name:
                return peer
        return None
    
    def shutdown(self):
        return None 
    
    def listen_user(self):
            while True:
                line = input()
                if line == ":whoami":
                    print(f'IP:{self.whoami["ip"]}\tName:{self.whoami["myname"]}')

                if line == ":quit":
                    self.shutdown()
                    break

                if line == ":peers":
                    print("IP:\t\tName:")
                    for peer in self.peers:
                        print(f"{peer}\t{self.peers[peer]}")
                    
                if line.startswith(":hello"):
                    try:
                        name = line.split()[1]
                        ip = name.strip()
                        match = re.match(IP_PATTERN, ip)
                        if match:
                            hello_message = HELLO_MESSAGE.copy()
                            hello_message["myname"] = self.whoami["myname"]
                            self.send_message(ip)
                        else:
                            logging.warn("Incorrect IP string.")
                    except:
                        print("Invalid command. Usage: :hello ip")

                
                if line.startswith(":send"):
                    try:
                        # strip command from the second empty spaace and keep the rest as content
                        name, content = line.split(" ", 2)[1], line.split(" ", 2)[2]
                        name, content = name.strip(), content.strip()
                        ip = self.get_ip_by_name(name)
                        if ip is None:
                            print(f"Peer with name \"{name}\" not found.")
                        else:
                            self.send_message(ip, MessageType.message, content=content)
                    except:
                        print("Invalid command. Usage: :send name message")

    def discover_peers(self, port:int = PORT) -> dict:
        # nmap this nmap that
        scanning_block = ".".join(self.whoami['ip'].split('.')[:-1]) + ".0/24"
        logging.info(f"Discovering peers using nmap, scanning block {scanning_block} on port {PORT}")
        syscall = f"nmap -p {port} "+ ".".join(self.whoami['ip'].split('.')[:-1]) + ".0/24"
        print(syscall)
        syscall = syscall.split(" ")
        process = subprocess.run(syscall, stdout=subprocess.PIPE)
        possible_peers = re.findall(IP_PATTERN, str(process.stdout))
        if len(possible_peers) == 0:
            # TODO: add rescan
            logging.warn("No peers on the network. Will rescan after 5 seconds.")
        else:
            logging.info(f"Sending 'hello' to {len(possible_peers)} possible peers")
            with concurrent.futures.ThreadPoolExecutor(len(possible_peers)) as executor_pool:
                for candidate in possible_peers:
                    executor_pool.submit(self.send_message, candidate, MessageType.hello)
                executor_pool.shutdown(wait=True)


    def send_message(self, ip:str, type:MessageType, content: str = None, port: int = PORT):
        try:
            logging.info("Creating a socket")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                logging.info(f"Connecting to the {ip} on {port}")
                s.connect((ip, port))

                logging.info("Preparing the message.")
                if type == MessageType.hello or type == MessageType.aleykumselam:
                    message = HELLO_MESSAGE.copy()
                    message["myname"] = self.whoami["myname"]

                if type == MessageType.message:
                    message = MESSAGE.copy()
                    message["content"] = content
                
                encode = json.dumps(message).encode('ascii')
                s.sendall(encode)
                logging.info("Sent the message.")
        except Exception as e:
            logging.error(f"Error while sending the message. Reason: {e}")

    def process_message(self, data: str, ip: str):
        data = json.loads(data)
        try:
            if data["type"] ==  HELLO_MESSAGE["type"]:
                logging.info(f"{ip} reached to say 'hello'")
                self.peers[ip] = data["myname"]
                logging.info(f"Sending 'aleykumselam' to {ip}")
                self.send_message(ip, MessageType.aleykumselam)

            if data["type"] == AS_MESSAGE["type"]:
                logging.info(f"{ip} said 'aleykumselam'")
                self.peers[ip] = data["myname"]

            if data["type"] == MESSAGE["type"]:
                logging.info(f"Processing message from {self.whoami[ip]}({ip})")
                _content = data['content']
                _from = 'UNKNOWN_HOST' if ip not in self.peers.keys() else self.peers[ip]
                print(f"[{datetime.datetime.now()}] | FROM: {_from}({ip}): {_content}")
        except KeyError as e:
            logging.error(f"Incoming message with unexpected structure. Message: {data}")
        except Exception as e:
            logging.error(f"Unexpected error. Check the exception: {e}")
                


    
    def listen_peer(self, ip: str, port: int = PORT):
        # TODO: add error handling here, definetly it will break
        # TODO: add some checks whether the host still has port, or even host is alive
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((ip, port))
                s.listen()
                while True:
                    conn, addr = s.accept()
                    with conn:
                        while True:
                            data = conn.recv(1024) # TODO: draining here, find a way of better communication
                            if not data:
                                break
                            data = str(data) # deserialize here
                            self.process_message(data, addr)
            except OSError as os_error:
                if os_error.errno == 61:
                    logging.error("The port is closed on the peer. Dropping the peer from book")
                    self.peers.pop(addr)



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # chat = Netchat('deniz')
    # chat.discover_peers()
    # chat.send_message(chat.whoami['ip'], MessageType.hello)


        