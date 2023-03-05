import multiprocessing
import subprocess
import json
import logging
import socket
import datetime
import threading
import concurrent.futures

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


class Netchat:
    def __init__(self, name: str = None):
        print("Joining the network.\nDiscovering peers.")
        logging.info("Discovering peers...")
        hostname: str = socket.gethostname()
        ipaddress: str = socket.gethostbyname(hostname)
        logging.info(f"Hostname: {hostname} IP: {ipaddress}")

        self.whoami: dict = {}
        self.whoami['name'] = name if name is not None else hostname
        self.whoami['ip'] = ipaddress

        self.peers: dict = {}
        self.kill_all = False

        self.dict_lock = threading.Lock()

        self.t1 = threading.Thread(target=self.listen_network)
        self.t2 = threading.Thread(target=self.discover_peers)
        self.t3 = threading.Thread(target=self.listen_user)

        self.t1.start()

        # first discover peers, then accept actions from the user
        self.t2.start()
        self.t2.join()
        print("Possible peers discovered.")
        self.t3.start()

        # these are practically alive until the program terminates
        self.t3.join()
        self.t1.join()        
        

    def get_ip_by_name(self, name: str):
        for peer in self.peers:
            if self.peers[peer] == name:
                return peer
        return None
    
    def listen_user(self):
        while not self.kill_all:
            line = input()
            if line == ":whoami":
                print(f"IP:{self.whoami['ip']}\tName:{self.whoami['name']}")
            if line == ":quit":
                self.shutdown()
                self.kill_all = True
                break

            if line == ":peers":
                print("IP:\t\tName:")
                for peer in self.peers:
                    print(f"{peer}\t{self.peers[peer]}")
                
            if line.startswith(":hello"):
                try:
                    name = line.split()[1]
                    ip = name.strip()
                    hello_message = HELLO_MESSAGE.copy()
                    hello_message['ip'] = self.whoami['ip']
                    hello_message['name'] = self.whoami['name']
                    self.send_message(hello_message, ip)
                except:
                    print("Invalid command. Usage: :hello ip")

            
            if line.startswith(":send"):
                try:
                    name, content = line.split()[1:]
                    name = name.strip()
                    content = content.strip()
                    ip = self.get_ip_by_name(name)
                    message = MESSAGE.copy()
                    message['ip'] = self.whoami['ip']
                    message['content'] = content

                    if ip is None:
                        print(f"Peer with name \"{name}\" not found.")
                    else:
                        self.send_message(message, ip)
                except:
                    print("Invalid command. Usage: :send name message")
    
    def shutdown(self):
        byebye_message = LEAVE_MESSAGE.copy()
        byebye_message['ip'] = self.whoami['ip']
        byebye_message['name'] = self.whoami['name']

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            for peer in self.peers:
                executor.submit(self.send_message, byebye_message, peer)
        logging.info("Left the network.")

    def discover_peers(self):
        hello_message = HELLO_MESSAGE.copy()
        hello_message['ip'] = self.whoami['ip'] 
        hello_message['name'] = self.whoami['name']

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            for i in range(1,256):
                # don't send to yourself
                if i == int(self.whoami['ip'].split('.')[-1]):
                    continue
                else:
                    candidate: list[str] = self.whoami['ip'].split('.')[:-1] + [str(i)]
                    candidate: str = ".".join(candidate)
                    # multithread here
                    executor.submit(self.send_message, hello_message, candidate)
        logging.info("Peers discovered.")

    def listen_network(self):
        process = subprocess.Popen([f'nc -lk {str(PORT)}'], shell=True, stdout=subprocess.PIPE)
        while True and not self.kill_all:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                self.process_message(output.strip())
    
        
    def process_message(self, message: str):
        try:
            message: json = json.loads(message)
            if message['type'] == 'hello':
                logging.info(f"Peer reached, sending ACK. ip: {message['ip']} name: {message['name']}")

                ack = ACK_MESSAGE.copy()
                ack['ip'] = self.whoami['ip']
                ack['name'] = self.whoami['name']

                self.send_message(ack, ip=message['ip'])
                self.add_peer(message['ip'], message['name'], self.dict_lock)
            
            if message['type'] == 'message':
                _ip = message['ip']
                _content = message['content']
                _from = 'UNKNOWN_HOST' if message['ip'] not in self.peers.keys() else self.peers[message['ip']]

                print(f"[{datetime.datetime.now()}] | FROM: {_from}({_ip}): {_content}")

            if message['type'] == 'aleykumselam':
                logging.info(f"Peer found. ip: {message['ip']} name: {message['name']} ")
                self.add_peer(message['ip'], message['name'], self.dict_lock)
            
            # this is not in the spec but it's a nice touchup
            if message['type'] == 'byebye':
                logging.info(f"Peer left. ip: {message['ip']} name: {message['name']}")
                self.peers.pop(message['ip']) 
            
        except Exception as e:
            print(e)
            logging.error("Error while processing the message.")
    
    def send_message(self, message: dict[str], ip:str, timeout:int= 0.02):
        try:
            logging.info(f"Sending \"{message['type']}\" message to {ip}")
            subprocess.run([f'echo \'{json.dumps(message)}\' | nc {ip} {str(PORT)}'], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            logging.info(f"Message sent. ip: {ip}")
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            print(e)
            logging.error(f"Error while sending the message. ip: {ip}") 

    def add_peer(self, ip, name, lock:threading.Lock):
        if ip not in self.peers:
            lock.acquire()
            self.peers[ip] = name
            lock.release()
            logging.info(f"Peer added. ip:{ip} name: {name}")
        

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    Netchat('deniz')