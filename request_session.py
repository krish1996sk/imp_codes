import socket
import json
import threading
import time
import select
import sys
import signal
import os
import argparse

s = None
t1 = None

def prGreen(skk): print("\033[92m {}\033[00m".format(skk))

def receive_data():
    global s
    global session_type

    while True:              # checking wheather first message is received
        ready = select.select([s], [], [], 5)
        if ready[0]:
            data_r= s.recv(1024)
            if data_r.decode().strip() == "":
                return
            prGreen(data_r.decode())
            if data_r.decode().startswith('Client is stopping,'):
                return
            break
        # else:
        #     print("No response, maybe client is disconnected, please close this session if client is not running")


    while True:
        data_r = s.recv(1024)
        if data_r.decode().strip() == "":
            return
        prGreen(data_r.decode())
        if data_r.decode().startswith('Client is stopping,'):
            return



def send_data():
    global t1
    while (t1.isAlive()):
        i, o, e = select.select( [sys.stdin], [], [], 1 )
        if i:
            str_in = sys.stdin.readline().strip()
            s.send(str_in.encode())
        else:
            pass

def signal_handler(sig, frame):
    print("Force exit")
    pid = os.getpid()
    os.kill(pid, signal.SIGKILL)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGQUIT, signal_handler)
    # signal.signal(signal.SIGKILL, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--device', help='device name',
                        required=True)
    parser.add_argument('-sk', '--secret_key', help='secret key',
                        required=True)
    parser.add_argument('-s', '--session', help='session type')
    args = parser.parse_args()
    device = args.device
    secret_key = args.secret_key
    session_type = args.session or 'csh'
    device = device.strip()


    s = socket.socket()
    while 1:
        try:
            with open('server_data.json', 'r') as f1:
                server_data = json.load(f1)

            port = server_data[device]
            s.connect(('localhost', int(port)))
            # print("connected")
            s.send((session_type + ":" + secret_key).encode())
            # print("first message is sent")
            break

        except:
            # print("client is not connected or server is not running, retrying after 2s")
            time.sleep(2)
    ready = select.select([s], [], [], 5)
    if ready[0]:
        data_rec = s.recv(1024)
        if data_rec.decode().strip() == "wrong secret key":
            print("incorrect secret")
            sys.exit(0)
        else:
            # print("Secret matched, client is authenticated")
            pass
    else:
        # print("No response, maybe server is not running")
        sys.exit(0)

    t1 = threading.Thread(target=receive_data)
    t1.start()

    t2 = threading.Thread(target=send_data)
    t2.start()
    if session_type == "csh":
        print("$ "),
