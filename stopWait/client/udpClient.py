import argparse
from enum import Enum
from os.path import isfile
from socket import socket, AF_INET, SOCK_DGRAM
from struct import pack, unpack
from sys import argv, exit

parser = argparse.ArgumentParser(description="Retrieve the file and store it on the local machine")
parser.add_argument('filename', help='name of the file to be retrieved')
parser.add_argument('--server', required=False, default='localhost:50001', help='server address from which, the file will be retrieved')
parser.add_argument('--timeout', required=False, default=2, help='number of seconds before re-sending a request to the server')
parser.add_argument('--maxtries', required=False, default=5, help='number of tries of re-sending a request to the server before giving up')

args = parser.parse_args(['C:\Users\jesus\source\repos\s19-nets\udp-file-transfer-team-10\stopWait\client\message'])
print(args)

# Parse the server address
addr_list = str(args.server).split(':')
if len(addr_list) != 2 or len(addr_list[0]) == 0 or len(addr_list[1]) == 0:
    print('Error: enter a valid server address i.e., IP:port')
    exit(1)

try:
    f = open(str(args.filename), 'w')
except FileNotFoundError:
    print('Error: specified file was not found')
    exit(1)

class State(Enum):
    READY = 0
    WAITING = 1 
    EXITING = 2

class MsgType(Enum):
    DATA = 0
    REQUEST = 1
    ACK = 2
    ERROR = 3   

client_socket = socket(AF_INET, SOCK_DGRAM)
fname = args.filename
last_ack_block = 0
max_tries = args.maxtries
server_addr = (addr_list[0], addr_list[1])
state = State.READY
timeout = args.timeout
tries = 0

def encode_msg(is_last_block, msgtype, ack_block, payload):
    is_last_block_id = 0x10 if is_last_block else 0
    metadata = is_last_block_id + msgtype_id
    
    struct_fmt = "{}s".format(len(payload))
    payload = payload.encode()
    
    msg = pack('B', metadata)
    msg += pack('I', ack_block)
    msg += pack(struct_fmt, payload)

    return msg

def decode_msg(msg):
    metadata = unpack('B', msg[:1])[0]
    ack_block = unpack('I', msg[1:5])[0]
    payload = msg[5:].decode()

    msgtype_mask = 0x0F
    lastblock_mask = 0x10

    is_last_block = metadata & lastblock_mask == 1
    msgtype = metadata & msgtype_mask

    return is_last_block, msgtype, ack_block, payload

def get(sock=None, retry=True):
    global f, fname, state, last_ack_block, server_addr 

    client_msgtype = MsgType.REQUEST if state == State.READY else MsgType.ACK
    stop_writing = False
         
    if retry == True:
        msg = encode_msg(True, client_msgtype, last_ack_block, fname)
        client_socket.sendto(msg, server_addr)
    else:
        msg, server_addr = sock.recvfrom(100)
        is_last_block, msgtype, ack_block, payload = decode_msg(msg)

        if msgtype == MsgType.DATA:
            if ack_block == last_ack_block + 1:
                f.write(payload)
                last_ack_block += 1
                state = State.WAITING
                stop_writing = is_last_block
                
            msg = encode_msg(True, MsgType.ACK, last_ack_block, fname)
            client_socket.sendto(msg, server_addr)  
        elif msgtype == MsgType.ERROR:
            print(payload)
            exit(1)

    return stop_writing

# map socket to function to call when socket is....
read_sockfunc = {}      # ready for reading
write_sockfunc = {}     # ready for writing
error_sockfunc = {}     # broken

read_sockfunc[client_socket] = get

# Send first request before sleeping for 'timeout' seconds
get()
tries += 1

while 1:
    read_rdyset, write_rdyset, err_rdyset = select(list(read_sockfunc.keys()),
                                                   list(write_sockfunc.keys()), 
                                                   list(error_sockfunc.keys()),
                                                   timeout)
    if not read_rdyset and not write_rdyset and not err_rdyset:
        print("retry")
        keep_trying = True
        if tries == MAX_TRIES: 
            print("Error: maximum number of tries was reached, would you like to keep trying? [t | f]")
            keep_trying = input('prompt') != "t"
        elif keep_trying: 
            tries += 1
            get()
    else:
        print("a msg was received")
        tries = 0
        for sock in read_rdyset:
            stop_program = read_sockfunc[sock](None, request, False)
            if stop_program:
                f.close()   # when last block is received, the program terminates
                return
