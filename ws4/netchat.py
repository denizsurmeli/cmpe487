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
import traceback
import base64

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

FILE_MESSAGE = {
    "type": '4',
    "name": None,
    "seq": None,
    "body":None
}

ACK_MESSAGE = {
    "type": '5',
    "name": None,
    "seq": None,
    "rwnd":None
}


IP_PATTERN = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
BROADCAST_PERIOD = 60
PRUNING_PERIOD = 120
BATCH_SIZE = 1500 # bytes
RWND = 10
PACKET_TIMEOUT = 1
# TODO :Find a way of closing the self-listener thread.


class MessageType(enum.Enum):
    hello = 1
    aleykumselam = 2
    message = 3
    file = 4
    ack = 5




class SendCtx: 
    """
        Context manager for sending a file over UDP.
    """
    def __init__(self, filepath, ip, batch_size = BATCH_SIZE, rwnd = 1):
        self.filepath = filepath
        self.ip = ip
        self.filesize = os.stat(filepath).st_size
        self.batch_size = batch_size

        self.packet_count = self.filesize // self.batch_size if self.filesize % self.batch_size == 0 else self.filesize // self.batch_size + 1
        self.seq = 0
        self.rwnd = rwnd
        self.packets = []
        self.acked = []
        self.on_fly = []
        self.sent = []

        with open(self.filepath, "rb") as file:
            # divide into batch size packets and store in self.packets
            while (batch := file.read(self.batch_size)):
                self.packets.append(base64.b64encode(batch))

    def build_message(self, seq):
        message = FILE_MESSAGE.copy()
        message["name"] = self.filepath
        message["seq"] = seq
        message["body"] = self.packets[seq - 1].decode("utf-8") if seq != 0 else self.packet_count
    
        return message
    
    def get_next_message(self):
        if self.seq >= self.packet_count or len(self.on_fly) > self.rwnd:
            return None

        self.seq += 1
        self.on_fly.append((time.time(), self.seq))
        return self.build_message(self.seq - 1)

    def is_complete(self):
        return len(self.on_fly) == 0 and len(self.acked) == self.packet_count
    
    def ack(self, seq):

        if seq not in self.acked:
            self.acked.append(seq)
        self.on_fly = [x for x in self.on_fly if x[1] != seq]
    
    def is_open_to_send(self):
        return len(self.on_fly) < self.rwnd + 1 and not self.is_complete()
    

    def handle_on_fly(self, executor):
        sent = []
        for packet in self.on_fly:
            if time.time() - packet[0] > PACKET_TIMEOUT:
                sent.append(packet[1])
                logging.info(f"[SendCtxExecutor] Resending packet {packet[1]}")
                executor.send_message(self.ip, MessageType.file, content=self.build_message(packet[1]), override=True, protocol=socket.SOCK_DGRAM)
        self.on_fly = [x for x in self.on_fly if x[1] not in sent] + [(time.time(), x) for x in sent]
    
    def execute(self, seq, rwnd, executor):
        # ack the seq
        logging.info(f"[SendCtxExecutor] ACK: {seq}, RWND: {rwnd} TARGET: {self.packet_count} REMAINING: {self.packet_count - len(self.acked)}")
        self.rwnd = rwnd
        if seq != 0:
            self.ack(seq)
            logging.info(f"[SendCtxExecutor] ACKED: {self.acked} ON_FLY: {self.on_fly} RWND: {self.rwnd}")
        while self.is_open_to_send():
            message = self.get_next_message()
            if message and message["seq"] not in self.sent:
                executor.send_message(self.ip, MessageType.file, content=message, override=True, protocol=socket.SOCK_DGRAM)
                self.sent.append(message["seq"])
            elif message and  message["seq"] in self.sent and message["seq"] not in self.on_fly:
                executor.send_message(self.ip, MessageType.file, content=message, override=True, protocol=socket.SOCK_DGRAM)
                self.on_fly.append((time.time(), message["seq"]))
            else:
                break
        # resend timed out packets
        self.handle_on_fly(executor)
        # check if all packets are acked
        return len(self.acked) == self.packet_count
    
class RecvCtx:
    """
        Context manager for receiving a file over UDP.
        This context has no on-fly packets, since ACKs are sent via TCP.
    """
    def __init__(self, filepath, ip, packet_count):
        self.filepath = filepath
        self.ip = ip

        self.packet_count = packet_count
        self.seq = 1

        self.packets = []
        self.acked = []

    def build_message(self, seq):
        message = ACK_MESSAGE.copy()
        message["name"] = self.filepath
        message["seq"] = seq
        message["rwnd"] = RWND if self.packet_count - seq > RWND else self.packet_count - seq

        return message

    def add_packet(self, packet):
        is_duplicate = False
        for p in self.packets:
            if p["seq"] == packet["seq"]:
                is_duplicate = True
                break
        if not is_duplicate:
            self.packets.append(packet)
        

    def is_complete(self):
        return len(self.acked) == self.packet_count

    def build_file(self):
        self.packets.sort(key=lambda x: x["seq"])
        self.write_to_file()
        return self.filepath
    
    def write_to_file(self):
        with open(self.filepath, "wb") as file:
            for packet in self.packets:
                file.write(packet["body"])

    def save(self):
        self.build_file()
        self.write_to_file()

    def write_to_file(self):
        with open(self.filepath, "wb") as file:
            for packet in self.packets:
                data = base64.b64decode(packet["body"])
                file.write(data)
    
    def ack(self, seq):
        if seq not in self.acked:
            self.acked.append(seq)
        

    def execute(self,  data, executor):
        if data["seq"] == 0:
            logging.info("[RecvCtxExecutor] File size is received.")
            message = self.build_message(data["seq"])
            executor.send_message(self.ip, MessageType.ack, content=message, override=True, protocol=socket.SOCK_STREAM)
            return False
        else:
            logging.info(f"[RecvCtxExecutor] ACK: {data['seq']}")
            self.add_packet(data)
            self.ack(data["seq"])
            logging.info(f"[RecvCtxExecutor] ACKED: {self.acked} rate: {len(self.acked) / self.packet_count}")
            message = self.build_message(data["seq"])
            executor.send_message(self.ip, MessageType.ack, content=message, override=True, protocol=socket.SOCK_STREAM)

            if self.is_complete():
                logging.info(f"[RecvCtxExecutor] File {self.filepath} is complete.")
                self.save()
                return True
            return False

class Netchat:
    def __init__(self, name: str = None):
        logging.info("Finding out whoami.")
        self.terminate = False
        hostname: str = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(hostname)[-1]
        if len(ip_addresses) > 1:
            # TODO: lookup why this happens ?
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

        self.send_ctxs : dict = {}
        self.recv_ctxs : dict  = {}

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

        self.send_ctx_manager_thread = threading.Thread(target=lambda : self.send_ctx_manager(self))
        self.send_ctx_manager_thread.start()

        self.user_input_thread.start()
        self.user_input_thread.join()
        self.send_ctx_manager_thread.join()

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
                for t in self.listener_threads[ip]:
                    t.join()
                logging.info(f"{ip} listener(s) closed.")

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
                    # strip command from the second empty spaace and keep the
                    # rest as content
                    name, filename = line.split(
                        " ", 2)[1], line.split(
                        " ", 2)[2]
                    name = name.strip()
                    filename = filename.strip()
                    ip = self.get_ip_by_name(name)
                    if ip is None:
                        print(f"Peer with name \"{name}\" not found.")
                    else:
                        logging.info(f"Sending file {filename} to {name}.")
                        if ip not in self.send_ctxs:
                            logging.info(f"Creating new send context for {ip}.")
                            self.send_ctxs[ip] = {}
                        self.send_ctxs[ip][filename] = SendCtx(filename, ip)
                        message = self.send_ctxs[ip][filename].build_message(0)
                        logging.info(f"Sending first packet of {filename}. Message: {message}")
                        self.send_message(
                            ip, 
                            MessageType.file, 
                            content=message, 
                            override=True,
                            protocol=socket.SOCK_DGRAM
                            )
                except BaseException as e:
                    # TODO: Add handling
                    print(e)

            elif line.startswith(":send"):
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
                
    # def file_transfer_daemon(self):
    #     while True and not self.terminate:
    #         for ip in self.send_ctxs:
    #             for filename in self.send_ctxs[ip]:
    #                 ctx = self.send_ctxs[ip][filename]
    #                 state = ctx.execute(executor=self)
    #                 if state == True:
    #                     del self.send_ctxs[ip][filename]
    #                     print(f"File {filename} sent to {ip}.")

    def send_message(self, 
                     ip: str, 
                     type: MessageType,
                     content = None, 
                     override: bool = False,
                     port: int = PORT,
                    protocol = socket.SOCK_STREAM) -> None:
        # TODO: Refactor this function
        if protocol == socket.SOCK_STREAM:
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
                    if type == MessageType.ack:
                        message = content # it's overriden we know

                    encode = json.dumps(message).encode('utf-8')
                    s.sendall(encode)
                    logging.info("Sent the message")
                    s.close()
                    logging.info(f"Closed the connection on {ip}")
            except Exception as e:
                logging.error(f"Error while sending the message. Reason: {type, content, e}")
        elif protocol == socket.SOCK_DGRAM:
            try:
                logging.info("Creating a socket")
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    logging.info(f"Connecting to the {ip} on {port}")
                    logging.info("Preparing the message.")
                    # the only message is file, so no need to check the type
                    encode = json.dumps(content).encode('utf-8')
                    s.sendto(encode, (ip, port))
                    logging.info("Sent the message")
                    s.close()
                    logging.info(f"Closed the connection on {ip}")
            except Exception as e:
                logging.error(f"Error while sending the file. Reason: {type, content, e}")
    
    def send_ctx_manager(self,executor):
        while True and not self.terminate:
            time.sleep(0.5) # 1 sec timeout, poll every 0.5
            try:
                for ip in self.send_ctxs:
                    for filename in self.send_ctxs[ip]:
                        ctx = self.send_ctxs[ip][filename]
                        if ctx != None and ctx.is_complete():
                            logging.info(f"[send_ctx_manager]: {ip} {filename} is complete")
                            del self.send_ctxs[ip][filename]
                        elif ctx != None:
                            logging.info(f"[send_ctx_manager]: {ip} {filename} is not complete.Resending...")
                            ctx.handle_on_fly(executor)
            except IndexError:
                # concurrency issue, should have implemented locks
                pass
            except Exception as e:
                print(e)
    
    def process_message(self, data: str, ip: str):
        try:
            data = json.loads(data)
        except Exception as e:
            print(f"Error while parsing the message. Reason: {data, traceback.format_exc()}")
        try:
            # logging.info(f"Processing the message from {ip, data}")
            if data["type"] == HELLO_MESSAGE["type"] and ip != self.whoami["ip"]:
                logging.info(f"{ip} reached to say 'hello'")
                self.peers[ip] = (time.time(), data["myname"])
                self.listener_threads[ip] = [
                    threading.Thread(target=lambda: self.listen_peer(ip)),
                    threading.Thread(target=lambda: self.listen_peer(ip, protocol=socket.SOCK_DGRAM))
                ]
                self.listener_threads[ip][0].start()
                self.listener_threads[ip][1].start()
                logging.info(f"Sending 'aleykumselam' to {ip}")
                self.send_message(ip, MessageType.aleykumselam)

            if data["type"] == AS_MESSAGE["type"]:
                logging.info(f"{ip} said 'aleykumselam'")
                self.peers[ip] = (time.time(), data["myname"])

            if data["type"] == MESSAGE["type"]:
                logging.info(
                    f"Processing message from {self.peers[ip][1]}({ip})")
                _content = data['content']
                _from = 'UNKNOWN_HOST' if ip not in self.peers.keys(
                ) else self.peers[ip][1]
                print(
                    f"[{datetime.datetime.now()}] FROM: {_from}({ip}): {_content}")
                
            if data["type"] == ACK_MESSAGE["type"]:
                logging.info(
                    f"Processing ACK from {self.peers[ip][1]}({ip}) for {data['name']}")
                _sender = 'UNKNOWN_HOST' if ip not in self.peers.keys(
                ) else self.peers[ip][1]
                ## DAEMON WILL HANDLE THIS
                send_ctx = self.send_ctxs[ip][data["name"]]
                state = send_ctx.execute(seq=data["seq"], rwnd = int(data["rwnd"]), executor=self)
                if state == True:
                    logging.info(f"{data['name']} sent to {ip}")
                    self.send_ctxs[ip][data["name"]] = None
                    

            if data["type"] == FILE_MESSAGE["type"]:
                logging.info(
                    f"Processing {data['name']} from {self.peers[ip][1]}({ip})")
                _sender = 'UNKNOWN_HOST' if ip not in self.peers.keys(
                ) else self.peers[ip][1]
                # lazy init
                if ip not in self.recv_ctxs.keys():
                    self.recv_ctxs[ip] = {}
                if data["seq"] == 0:
                    packet_count = int(data["body"])
                if data["name"] not in self.recv_ctxs[ip].keys():
                    self.recv_ctxs[ip][data["name"]] = RecvCtx(data["name"], ip, packet_count)
                recv_ctx = self.recv_ctxs[ip][data["name"]]
                state = recv_ctx.execute(data=data, executor=self)
                if state:
                    logging.info(f"{data['name']} received from {ip}")
                    print(f"FROM:{_sender}(file): <{data['name']} received.>")
                    recv_ctx.save()
                    del self.recv_ctxs[ip][data["name"]]

        except KeyError as e:
            logging.error(
                f"Incoming message with unexpected structure. Message: {e, data, traceback.format_exc()}")
        except Exception as e:
            logging.error(f"Unexpected error. Check the exception: {traceback.format_exc()}")

    def listen_peer(self, ip: str, protocol = socket.SOCK_STREAM, port: int = PORT):
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
                                data = conn.recv(16384)
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

    def listen_broadcast(self, port=PORT):
        while True and not self.terminate:
            buffer_size = 16384 # lmao this took 4 hours to figure out
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.bind(('', port))
                s.setblocking(0)
                result = select.select([s], [], [])
                msg, sender = result[0][0].recvfrom(buffer_size)
                sender = sender[0]
                msg = msg.decode('utf-8')
                threading.Thread(target=lambda :self.process_message(msg, sender)).start()

                for peer in list(self.peers.keys()):
                    if time.time() - self.peers[peer][0] > PRUNING_PERIOD:
                        logging.info(
                            f"Pruning peer due to inactivity: {self.peers[peer][1]}({peer})")
                        self.peers.pop(peer)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    netchat = Netchat("Deniz")
