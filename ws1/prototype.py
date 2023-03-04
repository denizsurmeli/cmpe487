import subprocess
import json
import logging
import socket
import datetime
import threading


PORT = 12345

HELLO_MESSAGE = {
    "type":"hello",
    "ip":None,
    "name":None
}

ACK_MESSAGE = {
    "type": "aleykumselam",
    "ip":None,
    "name":None
}

MESSAGE = {
    "type": "message",
    "ip":None,
    "content":None
}

LEAVE_MESSAGE = {
    "type": "byebye",
    "ip":None,
    "name":None
}

class Peer:
    def __init__(self, ip: str, name: str):
        self.ip = ip
        self.name = name

class Netchat:
    def __init__(self, name: str):
        """
            Discovers peers and introduces itself to the network.
            Sets up the `peers` dictionary.
        """
        logging.info("Discovering peers...")
        hostname: str = socket.gethostname()
        ipaddress: str = socket.gethostbyname(hostname)
        logging.info(f"Hostname: {hostname} IP: {ipaddress}")

        self.whoami: Peer = Peer(ipaddress, name)
        self.peers: dict = {}

        self.dict_lock = threading.Lock()

        t1 = threading.Thread(target=self.listen_network)
        t2 = threading.Thread(target=self.discover_peers)
        t3 = threading.Thread(target=self.listen_user)

        t1.start()

        # first discover peers, then accept actions from the user
        t2.start()
        t2.join()
        t3.start()

        # these are practically alive until the program terminates
        t1.join()        
        t3.join()

    def listen_user(self):
        while True:
            line = input()
            if line == "exit":
                self.shutdown()
                break
            else:
                print("listen_user:", line)
                # self.send_message(line)
    
    def shutdown(self):
        byebye_message = LEAVE_MESSAGE.copy()
        byebye_message['ip'] = self.whoami.ip
        byebye_message['name'] = self.whoami.name

        for peer in self.peers:
            self.send_message(byebye_message, peer)
        logging.info("Left the network.")

    def discover_peers(self):
        """
            Sends a hello message to all the peers in the network.
        """
        hello_message = HELLO_MESSAGE.copy()
        hello_message['ip'] = self.whoami.ip    
        hello_message['name'] = self.whoami.name

        for i in range(1,256):
            # don't send to yourself
            if i == int(self.whoami.ip.split('.')[-1]):
                continue
            else:
                candidate: list[str] = self.whoami.ip.split('.')[:-1] + [str(i)]
                candidate: str = ".".join(candidate)
                # multithread here
                self.send_message(ip=candidate, message=hello_message)
        logging.info("Peers discovered.")

    def listen_network(self):
        process = subprocess.Popen([f'nc -lk {str(PORT)}'], shell=True, stdout=subprocess.PIPE)
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                self.process_message(output.strip())
    
    # def resolve_sender(self, ip:str) -> str:
    #     """
    #         Resolves the name of the sender.
    #     """

        
    def process_message(self, message: str):
        try:
            message: json = json.loads(message)
            if message['type'] == 'hello':
                logging.info(f"Peer reached, sending ACK. ip: {message['ip']} name: {message['name']}")

                ack = ACK_MESSAGE.copy()
                ack['ip'] = self.whoami.ip
                ack['name'] = self.whoami.name

                self.send_message(ack, name=message['name'], ip=message['ip'])
                self.add_peer(Peer(message['ip'], message['name']), self.dict_lock)
            
            if message['type'] == 'message':
                print(f"[{datetime.datetime.now()}] | FROM: ({message['ip']}): {message['content']}")

            if message['type'] == 'aleykumselam':
                logging.info(f"Peer found. ip: {message['ip']} name: {message['name']} ")
                self.add_peer(Peer(message['ip'], message['name']), self.dict_lock)
            
            # this is not in the spec but definetely needed
            if message['type'] == 'byebye':
                logging.info(f"Peer left. ip: {message['ip']} name: {message['name']}")
                self.peers.pop(message['ip']) 
            
        except Exception as e:
            print(e)
            logging.error("Error while processing the message.")


    def send_message(self, content:str, name:str):
        receiver_ip: str = self.peers[name]
        message = MESSAGE.copy()
        message['content'] = content
        message['ip'] = self.ip 
        self.send_message(message, receiver_ip)
    
    def send_message(self, message: dict[str], name:str, ip:str=None):
        if ip is None:
            ip = self.peers[name]
            self.send_message(message, ip)
        else:
            self.send_message(message, ip)
    
    def send_message(self, message: dict[str], ip:str, timeout:int= 1):
        try:
            logging.info(f"Sending \"{message['type']}\" message to {ip}")
            subprocess.check_output(['nc', ip, str(PORT)], input=bytes(json.dumps(message), 'utf-8'), timeout=0.02)
            logging.info(f"Message sent. ip: {ip}")
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            logging.error(f"Error while sending the message. ip: {ip}") 

    def add_peer(self, peer:Peer, lock:threading.Lock):
        if peer['ip'] not in self.peers:
            lock.acquire()
            self.peers[peer['ip']] = peer['name']
            lock.release()
            logging.info(f"Peer added. ip: {peer['ip']} name: {peer['name']}")
        




if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    Netchat('deniz')