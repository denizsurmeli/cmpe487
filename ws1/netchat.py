import threading
import subprocess

def listen_network():
    process = subprocess.Popen([f'nc -lk 12345'], shell=True, stdout=subprocess.PIPE)
    while True:
        line = process.stdout.readline()
        print(line)
        if process.poll() is not None:
            break

def listen_user():
    while True:
        line = input()

if __name__ == "__main__":
    t1 = threading.Thread(target=listen_network)
    t2 = threading.Thread(target=listen_user)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()


